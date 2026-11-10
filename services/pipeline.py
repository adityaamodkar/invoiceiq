"""
Pipeline orchestrator.

Runs the ten stages in order and reports each transition (RUNNING -> COMPLETED
or FAILED) through a callback the moment it happens. The UI renders those
events live, and every event is also written to stage_events for the audit
trail. Durations are measured execution time only.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from database import repository as repo
from services import (
    decision_engine, document_processor, duplicate_detector, financial_validator,
    invoice_extractor, po_matcher, vendor_matcher,
)
from services.errors import DocumentError
from services.models import (
    DECISION_LABELS, CheckResult, Decision, DocumentText, InvoiceDraft, PurchaseOrder, Vendor,
)
from services.normalizers import format_inr, normalize_invoice_number

STAGES: list[tuple[str, str]] = [
    ("received", "Invoice received"),
    ("validation", "Document validation"),
    ("text", "PDF / image text extraction"),
    ("fields", "Structured field extraction"),
    ("vendor", "Vendor verification"),
    ("po", "PO identification and matching"),
    ("financial", "Financial validation"),
    ("duplicate", "Duplicate detection"),
    ("decision", "Decision generation"),
    ("audit", "Audit record creation"),
]


@dataclass
class StageEvent:
    seq: int
    key: str
    name: str
    status: str                 # PENDING / RUNNING / COMPLETED / FAILED / SKIPPED
    message: str = ""
    output: Any = None
    duration_ms: int | None = None


@dataclass
class PipelineResult:
    run_id: str
    run_status: str = "RUNNING"
    decision: Decision | None = None
    draft: InvoiceDraft | None = None
    doc: DocumentText | None = None
    vendor: Vendor | None = None
    po: PurchaseOrder | None = None
    results: list[CheckResult] = field(default_factory=list)
    events: list[StageEvent] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    provider_notes: list[str] = field(default_factory=list)
    failure: str | None = None


Callback = Callable[[StageEvent], None]


class _StageFailed(Exception):
    pass


def run_pipeline(file_name: str, data: bytes, on_event: Callback | None = None,
                 pace_seconds: float = 0.0, parent_run_id: str | None = None,
                 uploaded_at: str | None = None) -> PipelineResult:
    """Process one document end to end. Never raises for document problems."""
    run_id = uuid.uuid4().hex[:10]
    res = PipelineResult(run_id=run_id)
    emit = on_event or (lambda e: None)
    exclude = repo.lineage(parent_run_id) if parent_run_id else []
    sha = hashlib.sha256(data).hexdigest()
    ext = Path(file_name).suffix.lower()

    for i, (k, n) in enumerate(STAGES):
        ev = StageEvent(i, k, n, "PENDING")
        res.events.append(ev)
        emit(ev)

    def stage(i: int, fn: Callable[[], tuple[str, Any]]) -> None:
        ev = res.events[i]
        ev.status, ev.message = "RUNNING", "Running…"
        emit(ev)
        if i > 0:  # stage 0 creates the run record
            repo.add_stage_event(run_id, i, ev.key, ev.name, "RUNNING", ev.message, None, None)
        t0 = time.perf_counter()
        try:
            msg, out = fn()
        except Exception as exc:  # noqa: BLE001
            ev.duration_ms = int((time.perf_counter() - t0) * 1000)
            ev.status = "FAILED"
            ev.message = str(exc) if isinstance(exc, DocumentError) else \
                f"Unexpected error: {exc.__class__.__name__}: {exc}"
            emit(ev)
            if i > 0:
                repo.add_stage_event(run_id, i, ev.key, ev.name, ev.status, ev.message, None,
                                     ev.duration_ms)
            raise _StageFailed(ev.message) from exc
        ev.duration_ms = int((time.perf_counter() - t0) * 1000)
        ev.status, ev.message, ev.output = "COMPLETED", msg, out
        emit(ev)
        repo.add_stage_event(run_id, i, ev.key, ev.name, ev.status, msg, out, ev.duration_ms)
        if pace_seconds:
            time.sleep(pace_seconds)  # presentation pacing; not included in durations

    ctx: dict[str, Any] = {}

    # --- stage functions ------------------------------------------------
    def s_received():
        repo.create_run(run_id, file_name, ext.lstrip(".").upper() or "UNKNOWN", len(data), sha,
                        uploaded_at or repo.now_iso(), parent_run_id)
        return (f"Received {file_name} ({len(data) / 1024:.1f} KB).",
                {"run_id": run_id, "file_name": file_name, "size_bytes": len(data), "sha256": sha})

    def s_validation():
        info = document_processor.validate_document(file_name, data)
        ctx["info"] = info
        return (f"Valid {info.file_type}, {info.page_count} page(s).",
                {"file_type": info.file_type, "pages": info.page_count})

    def s_text():
        doc = document_processor.extract_text(ctx["info"], data)
        res.doc = doc
        label = {"digital_text": "machine-readable text (no OCR needed)",
                 "ocr_pdf": "OCR of scanned PDF pages", "ocr_image": "OCR of image"}[doc.method]
        return (f"Read {doc.char_count} characters from {doc.page_count} page(s) using {label}.",
                {"method": doc.method, "characters": doc.char_count,
                 "tables_found": sum(len(t) for t in doc.tables),
                 "ocr_confidence": doc.ocr_confidence})

    def s_fields():
        draft, notes = invoice_extractor.extract_invoice(res.doc)
        res.draft, res.provider_notes = draft, notes
        checks = invoice_extractor.check_extraction(draft)
        res.results += checks
        found = sum(1 for f in draft.header.values() if f.present)
        how = ("read by OCR" if res.doc.method.startswith("ocr") else "from the document text")
        return (f"Extracted {found} invoice fields and {len(draft.line_items)} line item(s) {how}.",
                {"provider": draft.provider, "provider_notes": notes,
                 "invoice_number": draft.get("invoice_number"), "po_number": draft.get("po_number"),
                 "total": draft.get("total_amount"), "missing": draft.missing_fields,
                 "checks": [c.outcome.value for c in checks]})

    def s_vendor():
        vendor, checks, ev = vendor_matcher.verify_vendor(res.draft, repo.list_vendors())
        res.vendor, res.evidence["vendor"] = vendor, ev
        res.results += checks
        ident = next(c for c in checks if c.check_key == "vendor_identity")
        status = next((c for c in checks if c.check_key == "vendor_status"), None)
        msg = ident.message + (f" {status.message}" if status else "")
        return msg, ev

    def s_po():
        all_pos = repo.list_purchase_orders(exclude_run_ids=exclude)
        match, checks = po_matcher.identify_po(res.draft, res.vendor, all_pos)
        if match.po:
            qty = repo.invoiced_qty_by_po_line(match.po.po_number, exclude)
            checks += po_matcher.match_lines(res.draft, match, qty)
        res.po, ctx["match"] = match.po, match
        res.results += checks
        res.evidence["po"] = {"method": match.method, "po_number": match.po.po_number if match.po else None,
                              "line_matches": match.line_matches, **match.evidence}
        if match.po:
            matched = sum(1 for v in match.line_matches.values() if v)
            msg = (f"Matched to {match.po.po_number} ({match.method}); {matched} of "
                   f"{len(res.draft.line_items)} line(s) matched. Remaining PO balance "
                   f"{format_inr(match.po.remaining_balance)}.")
        else:
            msg = checks[0].message
        return msg, res.evidence["po"]

    def s_financial():
        checks, ev = financial_validator.validate(res.draft, res.po)
        res.results += checks
        res.evidence["financial"] = ev
        bad = [c for c in checks if c.outcome.value != "PASS"]
        msg = f"{len(checks)} financial checks run; " + (
            f"{len(bad)} need attention." if bad else "all passed.")
        return msg, ev

    def s_duplicate():
        vid = res.vendor.vendor_id if res.vendor else None
        num = normalize_invoice_number(res.draft.get("invoice_number"))
        by_sha = repo.find_prior_by_sha(sha, exclude + [run_id])
        by_num = repo.find_prior_by_vendor_number(vid, num, exclude + [run_id]) if vid and num else []
        by_vendor = repo.find_prior_by_vendor(vid, exclude + [run_id]) if vid else []
        checks, ev = duplicate_detector.check(res.draft, vid, sha, by_sha, by_num, by_vendor)
        res.results += checks
        res.evidence["duplicate"] = ev
        return checks[0].message, ev

    def s_decision():
        res.decision = decision_engine.decide(res.results)
        label = DECISION_LABELS[res.decision.status.value]
        return (f"{label}. {res.decision.reason}",
                {"status": res.decision.status.value, **res.decision.summary_counts})

    def s_audit():
        repo.save_invoice(run_id, res.draft, res.vendor.vendor_id if res.vendor else None,
                          res.po.po_number if res.po else None, ctx["match"].line_matches)
        repo.save_results(run_id, res.results)
        repo.save_exceptions(run_id, res.results)
        repo.complete_run(run_id, res.decision, res.draft.extraction_method)
        return (f"Saved run {run_id}: extracted data, {len(res.results)} check results and the decision.",
                {"run_id": run_id, "results_saved": len(res.results)})

    fns = [s_received, s_validation, s_text, s_fields, s_vendor, s_po, s_financial,
           s_duplicate, s_decision, s_audit]
    try:
        for i, fn in enumerate(fns):
            stage(i, fn)
        res.run_status = "COMPLETED"
    except _StageFailed as exc:
        res.run_status, res.failure = "FAILED", str(exc)
        failed = next(e for e in res.events if e.status == "FAILED")
        for e in res.events[failed.seq + 1:]:
            e.status, e.message = "SKIPPED", "Not run because an earlier stage failed."
            emit(e)
            if failed.seq > 0:
                repo.add_stage_event(run_id, e.seq, e.key, e.name, e.status, e.message, None, None)
        if failed.seq > 0:  # run record exists
            repo.fail_run(run_id, failed.name, res.failure)
    return res
