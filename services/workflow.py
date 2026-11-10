"""
The invoice lifecycle as an AP user sees it, and the rules for human actions.

System decision + human action -> status shown in the inbox:
    READY_FOR_APPROVAL, pending   -> Ready to approve
    NEEDS_REVIEW,       pending   -> Needs review
    BLOCKED,            pending   -> Blocked
    FAILED (unreadable)           -> Unreadable
    approved by a person          -> Approved      (approval, not payment: InvoiceIQ never pays)
    rejected by a person          -> Rejected
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

STATUS_ORDER = ["NEEDS_REVIEW", "READY", "BLOCKED", "UNREADABLE", "APPROVED", "REJECTED"]
STATUS_LABEL = {"NEEDS_REVIEW": "Needs review", "READY": "Ready to approve", "BLOCKED": "Blocked",
                "UNREADABLE": "Unreadable", "APPROVED": "Approved", "REJECTED": "Rejected"}


def status_of(run: dict) -> str:
    if run.get("approval_status") == "APPROVED":
        return "APPROVED"
    if run.get("approval_status") == "REJECTED":
        return "REJECTED"
    if run.get("run_status") == "FAILED":
        return "UNREADABLE"
    return {"READY_FOR_APPROVAL": "READY", "NEEDS_REVIEW": "NEEDS_REVIEW", "BLOCKED": "BLOCKED"}.get(
        run.get("decision") or "", "UNREADABLE")


def can_approve(run: dict) -> tuple[bool, str]:
    s = status_of(run)
    if s == "READY":
        return True, ""
    if s == "NEEDS_REVIEW":
        return True, "A reason is required to approve an invoice that needs review."
    if s == "BLOCKED":
        return False, "Blocked invoices can't be approved. Resolve the cause and process the invoice again."
    if s == "UNREADABLE":
        return False, "The document could not be read."
    return False, f"Already {STATUS_LABEL[s].lower()}."


def can_reject(run: dict) -> bool:
    return status_of(run) not in ("APPROVED", "REJECTED")


def note_required_to_approve(run: dict) -> bool:
    return status_of(run) == "NEEDS_REVIEW"


# ---------------------------------------------------------------- due dates
@dataclass
class Due:
    date: date | None
    source: str          # "invoice" (printed) / "terms" (invoice date + payment terms) / ""

    def label(self, today: date) -> str:
        if not self.date:
            return "—"
        days = (self.date - today).days
        if days < 0:
            return f"Overdue {-days}d"
        if days == 0:
            return "Due today"
        if days <= 14:
            return f"Due in {days}d"
        return self.date.strftime("%d %b")


def due_of(invoice_date: str | None, printed_due: str | None, payment_terms: str | None) -> Due:
    if printed_due:
        return Due(date.fromisoformat(printed_due), "invoice")
    if invoice_date and payment_terms and (m := re.search(r"(\d+)", payment_terms)):
        return Due(date.fromisoformat(invoice_date) + timedelta(days=int(m.group(1))), "terms")
    return Due(None, "")


# ---------------------------------------------------------------- flags
FLAG_LABEL = [  # (check key prefix/regex, short label) as reviewers name these problems
    (r"^duplicate$", "Duplicate"), (r"^vendor_status$", "Inactive vendor"),
    (r"^vendor_identity$", "Vendor mismatch"), (r"^vendor_gstin_format$", "GSTIN invalid"),
    (r"^vendor_name_confidence$", "Vendor unclear"), (r"^po_exists$", "PO not matched"),
    (r"^po_vendor$", "PO of other vendor"), (r"^po_status$", "PO closed"), (r"^po_currency$", "Currency"),
    (r"^line\d+_price$", "Price variance"), (r"^line\d+_qty$", "Quantity over PO"),
    (r"^line\d+_match$", "Item not on PO"), (r"^po_balance$", "Over PO value"),
    (r"^required_fields$", "Missing fields"), (r"^extraction_confidence$", "Low confidence"),
    (r"^line_items_present$", "No line items"), (r"^(tax_calculation|tax_type|tax_rate_vs_po)$", "Tax mismatch"),
    (r"^(line_arithmetic|subtotal_arithmetic|total_arithmetic)$", "Totals don't add up"),
    (r"^charges_on_po$", "Extra charges"),
]


def flags(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """[(check_key, outcome)] -> unique [(label, 'FAIL'|'WARN')], blocking first."""
    seen: dict[str, str] = {}
    rank: dict[str, int] = {}
    for key, outcome in items:
        idx, label = next(((i, lbl) for i, (rx, lbl) in enumerate(FLAG_LABEL) if re.match(rx, key)), (99, key))
        if key == "vendor_identity":
            label = "Vendor not approved" if outcome == "FAIL" else "Vendor unclear"
        rank[label] = idx
        if seen.get(label) != "FAIL":
            seen[label] = outcome
    # root causes first (e.g. Duplicate before the PO overrun it causes), then blocking before review
    return sorted(seen.items(), key=lambda kv: (rank[kv[0]] > 1, kv[1] != "FAIL", rank[kv[0]]))
