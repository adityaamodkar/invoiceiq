"""
Repository layer: the only place (besides db.py) that contains SQL.
Services and UI call these functions and receive domain objects or dicts.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from config import settings
from database.db import connect
from services.models import (
    CheckResult, Decision, InvoiceDraft, POLine, PurchaseOrder, Vendor, to_jsonable,
)
from services.normalizers import from_paise, normalize_invoice_number, to_paise


# An invoice draws down its PO when the checks cleared it and nobody rejected it,
# or when a person approved it after review.
CONSUMES = ("((r.decision='READY_FOR_APPROVAL' AND COALESCE(r.approval_status,'')<>'REJECTED')"
            " OR r.approval_status='APPROVED')")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Master data
# ---------------------------------------------------------------------------
def _row_to_vendor(r) -> Vendor:
    return Vendor(
        vendor_id=r["vendor_id"], legal_vendor_name=r["legal_vendor_name"],
        display_name=r["display_name"] or r["legal_vendor_name"],
        aliases=[a.strip() for a in (r["aliases"] or "").split("|") if a.strip()],
        gstin=r["gstin"], status=r["status"], currency=r["currency"],
        address=r["address"], state_code=r["state_code"], payment_terms=r["payment_terms"],
    )


def list_vendors() -> list[Vendor]:
    with connect() as c:
        return [_row_to_vendor(r) for r in c.execute("SELECT * FROM vendors ORDER BY vendor_id")]


def get_vendor(vendor_id: str) -> Vendor | None:
    with connect() as c:
        r = c.execute("SELECT * FROM vendors WHERE vendor_id=?", (vendor_id,)).fetchone()
        return _row_to_vendor(r) if r else None


def _invoiced_in_system(c, po_number: str, exclude_run_ids: Iterable[str]) -> Decimal:
    excl = list(exclude_run_ids)
    sql = (
        "SELECT COALESCE(SUM(i.subtotal_paise),0) FROM invoices i "
        "JOIN processing_runs r ON r.run_id=i.run_id "
        f"WHERE i.po_number=? AND r.is_current=1 AND {CONSUMES}"
    )
    params: list[Any] = [po_number]
    if excl:
        sql += f" AND r.run_id NOT IN ({','.join('?' * len(excl))})"
        params += excl
    return from_paise(c.execute(sql, params).fetchone()[0]) or Decimal("0")


def _row_to_po(c, r, exclude_run_ids: Iterable[str] = ()) -> PurchaseOrder:
    lines = [
        POLine(
            po_number=l["po_number"], line_no=l["line_no"], item_code=l["item_code"],
            item_description=l["item_description"], uom=l["uom"],
            quantity_ordered=Decimal(l["quantity_ordered"]),
            unit_price=from_paise(l["unit_price_paise"]),
            line_total=from_paise(l["line_total_paise"]),
            tax_rate=Decimal(l["tax_rate"] or "0"),
        )
        for l in c.execute(
            "SELECT * FROM po_line_items WHERE po_number=? ORDER BY line_no", (r["po_number"],)
        )
    ]
    return PurchaseOrder(
        po_number=r["po_number"], vendor_id=r["vendor_id"], po_date=r["po_date"],
        currency=r["currency"], subtotal=from_paise(r["subtotal_paise"]),
        tax_amount=from_paise(r["tax_paise"]), total_po_amount=from_paise(r["total_paise"]),
        baseline_invoiced=from_paise(r["baseline_invoiced_paise"]),
        po_status=r["po_status"], tolerance_pct=Decimal(r["tolerance_pct"]), lines=lines,
        invoiced_in_system=_invoiced_in_system(c, r["po_number"], exclude_run_ids),
    )


def get_purchase_order(po_number: str, exclude_run_ids: Iterable[str] = ()) -> PurchaseOrder | None:
    with connect() as c:
        r = c.execute("SELECT * FROM purchase_orders WHERE po_number=?", (po_number,)).fetchone()
        return _row_to_po(c, r, exclude_run_ids) if r else None


def list_purchase_orders(vendor_id: str | None = None,
                         exclude_run_ids: Iterable[str] = ()) -> list[PurchaseOrder]:
    with connect() as c:
        if vendor_id:
            rows = c.execute("SELECT * FROM purchase_orders WHERE vendor_id=? ORDER BY po_number",
                             (vendor_id,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM purchase_orders ORDER BY po_number").fetchall()
        return [_row_to_po(c, r, exclude_run_ids) for r in rows]


# ---------------------------------------------------------------------------
# Processing runs and audit trail
# ---------------------------------------------------------------------------
def create_run(run_id: str, file_name: str, file_type: str, size: int, sha256: str,
               uploaded_at: str, parent_run_id: str | None = None) -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO processing_runs (run_id,parent_run_id,is_current,file_name,file_type,"
            "file_size_bytes,file_sha256,uploaded_at,started_at,run_status) "
            "VALUES (?,?,1,?,?,?,?,?,?, 'RUNNING')",
            (run_id, parent_run_id, file_name, file_type, size, sha256, uploaded_at, now_iso()),
        )
        if parent_run_id:  # the new run supersedes its parent
            c.execute("UPDATE processing_runs SET is_current=0 WHERE run_id=?", (parent_run_id,))


def add_stage_event(run_id: str, seq: int, stage_key: str, stage_name: str, status: str,
                    message: str, output: Any, duration_ms: int | None) -> None:
    with connect() as c:
        c.execute(
            "INSERT OR REPLACE INTO stage_events VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, seq, stage_key, stage_name, status, message,
             json.dumps(to_jsonable(output)) if output is not None else None,
             duration_ms, now_iso()),
        )


def save_invoice(run_id: str, draft: InvoiceDraft, vendor_id: str | None,
                 po_number: str | None, line_matches: dict[int, int | None]) -> None:
    g = draft.get
    raw = {k: {"raw": f.raw, "confidence": f.confidence, "page": f.source_page, "method": f.method,
               "bbox": f.bbox, "warning": f.warning}
           for k, f in draft.header.items()}
    raw["_lines"] = [{"line_no": li.line_no, "page": li.source_page, "bbox": li.bbox,
                      "confidence": li.confidence} for li in draft.line_items]
    raw["_page_count"] = None
    normalized = {k: f.value for k, f in draft.header.items()}
    with connect() as c:
        c.execute(
            "INSERT OR REPLACE INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, vendor_id, g("vendor_name"), g("vendor_gstin"), g("invoice_number"),
             normalize_invoice_number(g("invoice_number")) or None,
             g("invoice_date").isoformat() if g("invoice_date") else None,
             po_number or g("po_number"), g("currency"),
             to_paise(g("subtotal")), to_paise(g("tax_amount")), to_paise(g("total_amount")),
             json.dumps(to_jsonable(raw)), json.dumps(to_jsonable(normalized))),
        )
        c.execute("DELETE FROM invoice_line_items WHERE run_id=?", (run_id,))
        for li in draft.line_items:
            c.execute(
                "INSERT INTO invoice_line_items VALUES (?,?,?,?,?,?,?,?,?)",
                (run_id, li.line_no, li.description, li.item_code,
                 str(li.quantity) if li.quantity is not None else None, li.uom,
                 to_paise(li.unit_price), to_paise(li.amount), line_matches.get(li.line_no)),
            )


def save_results(run_id: str, results: list[CheckResult]) -> None:
    with connect() as c:
        c.execute("DELETE FROM validation_results WHERE run_id=?", (run_id,))
        for i, r in enumerate(results):
            c.execute(
                "INSERT INTO validation_results VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, i, r.check_key, r.category, r.outcome.value, r.severity.value,
                 r.message, r.expected, r.actual, r.field, r.recommended_action),
            )


def save_exceptions(run_id: str, results: list[CheckResult]) -> None:
    with connect() as c:
        for r in results:
            if r.severity.value == "INFO":
                continue
            c.execute(
                "INSERT INTO exceptions (run_id,category,severity,summary,suggested_action,"
                "status,created_at) VALUES (?,?,?,?,?, 'OPEN', ?)",
                (run_id, r.category, r.severity.value, r.message, r.recommended_action, now_iso()),
            )


def complete_run(run_id: str, decision: Decision, extraction_method: str) -> None:
    with connect() as c:
        c.execute(
            "UPDATE processing_runs SET run_status='COMPLETED', finished_at=?, decision=?,"
            " decision_reason=?, next_action=?, extraction_method=? WHERE run_id=?",
            (now_iso(), decision.status.value, decision.reason, decision.next_action,
             extraction_method, run_id),
        )


def fail_run(run_id: str, stage: str, reason: str) -> None:
    with connect() as c:
        c.execute(
            "UPDATE processing_runs SET run_status='FAILED', finished_at=?, failure_stage=?,"
            " failure_reason=? WHERE run_id=?",
            (now_iso(), stage, reason, run_id),
        )
        c.execute(
            "INSERT INTO exceptions (run_id,category,severity,summary,suggested_action,status,created_at)"
            " VALUES (?, 'Document', 'CRITICAL', ?, ?, 'OPEN', ?)",
            (run_id, f"Could not be processed at '{stage}': {reason}",
             "Request a readable copy of the invoice from the vendor and upload it again.", now_iso()),
        )


# ---------------------------------------------------------------------------
# Duplicate lookups (only current, completed runs count as "previously processed")
# ---------------------------------------------------------------------------
_PRIOR = (
    "SELECT r.run_id, r.file_name, r.decision, r.finished_at, i.invoice_number, i.invoice_date,"
    " i.total_paise, i.vendor_id FROM processing_runs r JOIN invoices i ON i.run_id=r.run_id"
    " WHERE r.is_current=1 AND r.run_status='COMPLETED'"
)


def _exclude(sql: str, params: list, excl: list[str]) -> tuple[str, list]:
    if excl:
        sql += f" AND r.run_id NOT IN ({','.join('?' * len(excl))})"
        params += excl
    return sql, params


def find_prior_by_sha(sha256: str, exclude: list[str]) -> list[dict]:
    sql, params = _exclude(_PRIOR + " AND r.file_sha256=?", [sha256], exclude)
    with connect() as c:
        return [dict(r) for r in c.execute(sql, params)]


def find_prior_by_vendor_number(vendor_id: str, number_norm: str, exclude: list[str]) -> list[dict]:
    sql, params = _exclude(_PRIOR + " AND i.vendor_id=? AND i.invoice_number_norm=?",
                           [vendor_id, number_norm], exclude)
    with connect() as c:
        return [dict(r) for r in c.execute(sql, params)]


def find_prior_by_vendor(vendor_id: str, exclude: list[str]) -> list[dict]:
    sql, params = _exclude(_PRIOR + " AND i.vendor_id=?", [vendor_id], exclude)
    with connect() as c:
        return [dict(r) for r in c.execute(sql, params)]


def lineage(run_id: str | None) -> list[str]:
    """All ancestors of a run (used to exclude itself from duplicate checks)."""
    ids: list[str] = []
    with connect() as c:
        while run_id:
            ids.append(run_id)
            r = c.execute("SELECT parent_run_id FROM processing_runs WHERE run_id=?",
                          (run_id,)).fetchone()
            run_id = r["parent_run_id"] if r else None
    return ids


# ---------------------------------------------------------------------------
# Read models for the UI
# ---------------------------------------------------------------------------
_RUN_LIST = (
    "SELECT r.*, i.vendor_id, i.vendor_name, i.invoice_number, i.invoice_date, i.po_number,"
    " i.total_paise, i.subtotal_paise, json_extract(i.normalized_json, '$.due_date') AS printed_due"
    " FROM processing_runs r LEFT JOIN invoices i"
    " ON i.run_id=r.run_id"
)


def list_runs(current_only: bool = False) -> list[dict]:
    sql = _RUN_LIST + (" WHERE r.is_current=1" if current_only else "") + " ORDER BY r.started_at DESC"
    with connect() as c:
        return [dict(r) for r in c.execute(sql)]


def get_run(run_id: str) -> dict | None:
    with connect() as c:
        r = c.execute(_RUN_LIST + " WHERE r.run_id=?", (run_id,)).fetchone()
        if not r:
            return None
        out = dict(r)
        inv = c.execute("SELECT * FROM invoices WHERE run_id=?", (run_id,)).fetchone()
        out["invoice"] = dict(inv) if inv else None
        out["line_items"] = [dict(x) for x in c.execute(
            "SELECT * FROM invoice_line_items WHERE run_id=? ORDER BY line_no", (run_id,))]
        out["stages"] = [dict(x) for x in c.execute(
            "SELECT * FROM stage_events WHERE run_id=? ORDER BY seq", (run_id,))]
        out["results"] = [dict(x) for x in c.execute(
            "SELECT * FROM validation_results WHERE run_id=? ORDER BY seq", (run_id,))]
        out["exceptions"] = [dict(x) for x in c.execute(
            "SELECT * FROM exceptions WHERE run_id=? ORDER BY exception_id", (run_id,))]
        out["reviews"] = [dict(x) for x in c.execute(
            "SELECT * FROM review_actions WHERE run_id=? OR new_run_id=? ORDER BY action_id",
            (run_id, run_id))]
        return out


def list_open_exceptions() -> list[dict]:
    sql = (
        "SELECT e.*, r.decision, r.uploaded_at, r.file_name, i.invoice_number, i.vendor_name,"
        " i.total_paise FROM exceptions e JOIN processing_runs r ON r.run_id=e.run_id"
        " LEFT JOIN invoices i ON i.run_id=e.run_id"
        " WHERE r.is_current=1 AND e.status='OPEN' ORDER BY"
        " CASE e.severity WHEN 'CRITICAL' THEN 0 WHEN 'WARNING' THEN 1 ELSE 2 END, e.created_at DESC"
    )
    with connect() as c:
        return [dict(r) for r in c.execute(sql)]


def invoiced_qty_by_po_line(po_number: str, exclude_run_ids: Iterable[str] = ()) -> dict[int, Decimal]:
    """Quantity already invoiced per PO line by balance-consuming invoices."""
    excl = list(exclude_run_ids)
    sql = (
        "SELECT li.matched_po_line, li.quantity FROM invoice_line_items li"
        " JOIN invoices i ON i.run_id=li.run_id JOIN processing_runs r ON r.run_id=li.run_id"
        f" WHERE i.po_number=? AND r.is_current=1 AND {CONSUMES}"
        " AND li.matched_po_line IS NOT NULL"
    )
    params: list[Any] = [po_number]
    if excl:
        sql += f" AND r.run_id NOT IN ({','.join('?' * len(excl))})"
        params += excl
    out: dict[int, Decimal] = {}
    with connect() as c:
        for row in c.execute(sql, params):
            out[row[0]] = out.get(row[0], Decimal("0")) + Decimal(row[1] or "0")
    return out


def exact_duplicate_run_ids() -> set[str]:
    """Runs blocked as exact duplicates: excluded from value totals to avoid double counting."""
    with connect() as c:
        return {r[0] for r in c.execute(
            "SELECT run_id FROM validation_results WHERE check_key='duplicate' AND outcome='FAIL'")}


def processing_ms_by_run() -> dict[str, int]:
    """Measured processing time per run (sum of stage durations)."""
    with connect() as c:
        return {r[0]: r[1] or 0 for r in c.execute(
            "SELECT run_id, SUM(duration_ms) FROM stage_events GROUP BY run_id")}


def delete_runs(run_ids: list[str]) -> int:
    """Delete runs and everything recorded for them, in one transaction.

    PO balances are computed from history, so deleting a run that was Ready for
    approval returns its amount to the PO. (A production AP system would archive
    rather than delete; this exists to manage demo and test data.)
    """
    if not run_ids:
        return 0
    marks = ",".join("?" * len(run_ids))
    with connect() as c:
        for table in ("review_actions", "exceptions", "validation_results", "stage_events",
                      "invoice_line_items", "invoices"):
            c.execute(f"DELETE FROM {table} WHERE run_id IN ({marks})", run_ids)
        c.execute(f"UPDATE processing_runs SET parent_run_id=NULL WHERE parent_run_id IN ({marks})", run_ids)
        return c.execute(f"DELETE FROM processing_runs WHERE run_id IN ({marks})", run_ids).rowcount


# ---------------------------------------------------------------------------
# Human workflow: approve, reject, notes (every action is logged in review_actions)
# ---------------------------------------------------------------------------
def set_approval(run_id: str, status: str, note: str | None, user: str = "AP user") -> None:
    assert status in ("APPROVED", "REJECTED")
    with connect() as c:
        c.execute("UPDATE processing_runs SET approval_status=?, approval_note=?, approval_at=? WHERE run_id=?",
                  (status, note, now_iso(), run_id))
        c.execute("UPDATE exceptions SET status='RESOLVED' WHERE run_id=? AND status='OPEN'", (run_id,))
        c.execute("INSERT INTO review_actions (run_id, action, reason, reviewer, created_at) VALUES (?,?,?,?,?)",
                  (run_id, "APPROVE" if status == "APPROVED" else "REJECT", note, user, now_iso()))


def add_note(run_id: str, text: str, user: str = "AP user") -> None:
    with connect() as c:
        c.execute("INSERT INTO review_actions (run_id, action, reason, reviewer, created_at) VALUES (?,?,?,?,?)",
                  (run_id, "NOTE", text, user, now_iso()))


def flags_by_run() -> dict[str, list[tuple[str, str]]]:
    """Non-passing check keys per run, for the flag chips in lists."""
    out: dict[str, list[tuple[str, str]]] = {}
    with connect() as c:
        for r in c.execute("SELECT run_id, check_key, outcome FROM validation_results WHERE outcome<>'PASS' ORDER BY seq"):
            out.setdefault(r[0], []).append((r[1], r[2]))
    return out


def get_pref(key: str, default: str | None = None) -> str | None:
    with connect() as c:
        r = c.execute("SELECT value FROM app_prefs WHERE key=?", (key,)).fetchone()
        return r[0] if r else default


def set_pref(key: str, value: str) -> None:
    with connect() as c:
        c.execute("INSERT INTO app_prefs (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, value))
