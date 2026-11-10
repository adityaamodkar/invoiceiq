"""
Duplicate detection against previously processed invoices.

EXACT duplicate (BLOCKED):
  * the identical file (SHA-256) was processed before, or
  * same vendor + same normalized invoice number + same total
POSSIBLE duplicate (NEEDS REVIEW):
  * same vendor + same invoice number but a different amount (revised invoice?)
  * same vendor + same total within N days but a different invoice number

Prior records are passed in, so the logic is testable without a database.
Only current, completed runs count; a re-run after review excludes its own lineage.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from config import settings
from services.models import CheckResult, InvoiceDraft, Outcome, Severity
from services.normalizers import format_inr, from_paise, normalize_invoice_number, to_paise


def _ref(r: dict) -> str:
    return f"{r.get('invoice_number') or '(no number)'} from {r.get('file_name')} (run {r['run_id']}, {r.get('decision')})"


def check(draft: InvoiceDraft, vendor_id: str | None, sha256: str,
          by_sha: list[dict], by_number: list[dict], by_vendor: list[dict]) -> tuple[list[CheckResult], dict]:
    total_paise = to_paise(draft.get("total_amount"))
    inv_date: date | None = draft.get("invoice_date")
    evidence = {"fingerprint": sha256[:16], "invoice_number_normalized":
                normalize_invoice_number(draft.get("invoice_number")) or None,
                "compared_against": len(by_vendor)}

    if by_sha:
        r = by_sha[0]
        return [CheckResult(
            "duplicate", "Duplicate", Outcome.FAIL, Severity.CRITICAL,
            f"Exact duplicate: this identical file was already processed as {_ref(r)}.",
            expected="New document", actual=f"Same file fingerprint as run {r['run_id']}",
            field="invoice_number",
            recommended_action="Do not process. Refer to the original run; no second approval is created.")], \
            {**evidence, "match_type": "exact_file", "original_run": r["run_id"]}

    same_amount = [r for r in by_number if r.get("total_paise") == total_paise]
    if same_amount:
        r = same_amount[0]
        return [CheckResult(
            "duplicate", "Duplicate", Outcome.FAIL, Severity.CRITICAL,
            f"Exact duplicate: vendor already billed invoice {r['invoice_number']} for "
            f"{format_inr(from_paise(r['total_paise']))}, processed as {_ref(r)}.",
            expected="Unique invoice number per vendor", actual=draft.get("invoice_number"),
            field="invoice_number",
            recommended_action="Do not process. Inform the vendor the invoice was already received.")], \
            {**evidence, "match_type": "exact_number_amount", "original_run": r["run_id"]}

    results: list[CheckResult] = []
    if by_number:
        r = by_number[0]
        results.append(CheckResult(
            "duplicate", "Duplicate", Outcome.WARN, Severity.WARNING,
            f"Possible duplicate: invoice number {r['invoice_number']} was already processed for this vendor "
            f"with a different total ({format_inr(from_paise(r['total_paise']))} vs "
            f"{format_inr(draft.get('total_amount'))}).",
            expected=format_inr(from_paise(r["total_paise"])), actual=format_inr(draft.get("total_amount")),
            field="invoice_number",
            recommended_action="Check whether this is a revised invoice replacing the earlier one."))
        evidence.update(match_type="possible_same_number", original_run=r["run_id"])
    else:
        near = []
        for r in by_vendor:
            if total_paise is None or r.get("total_paise") != total_paise:
                continue
            if inv_date and r.get("invoice_date"):
                gap = abs((inv_date - date.fromisoformat(r["invoice_date"])).days)
                if gap > settings.POSSIBLE_DUPLICATE_WINDOW_DAYS:
                    continue
            near.append(r)
        if near:
            r = near[0]
            results.append(CheckResult(
                "duplicate", "Duplicate", Outcome.WARN, Severity.WARNING,
                f"Possible duplicate: same vendor and same total {format_inr(draft.get('total_amount'))} as "
                f"{_ref(r)}, within {settings.POSSIBLE_DUPLICATE_WINDOW_DAYS} days, but a different invoice number.",
                expected="Distinct invoice", actual=draft.get("invoice_number"), field="invoice_number",
                recommended_action="Compare both invoices; vendors sometimes re-issue with a new number."))
            evidence.update(match_type="possible_same_amount", original_run=r["run_id"])

    if not results:
        results.append(CheckResult(
            "duplicate", "Duplicate", Outcome.PASS, Severity.INFO,
            f"No duplicate found: checked file fingerprint, invoice number and amount against "
            f"{len(by_vendor)} previously processed invoice(s) from this vendor.",
            field="invoice_number"))
        evidence["match_type"] = "none"
    return results, evidence
