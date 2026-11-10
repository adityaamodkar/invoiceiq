"""
PO identification and line-item matching.

Pure functions: callers pass in the vendor's POs (with balances already
computed from processing history) so this logic is testable without a database.

Rules:
  * Explicit PO number on the invoice is used first.
  * Without one, open POs of the same vendor are candidates. A single candidate
    is PROPOSED (needs review); several are reported as ambiguous. The system
    never silently picks a PO.
  * Line items match on item code, then exact normalized description.
    Similar descriptions are surfaced as "possible match" and never assumed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from difflib import SequenceMatcher

from config import settings
from services import tolerance
from services.models import (
    CheckResult, ExtractedLineItem, InvoiceDraft, Outcome, POLine, PurchaseOrder, Severity, Vendor,
)
from services.normalizers import format_inr, normalize_text

INVOICEABLE_STATUSES = {"open", "partially invoiced"}
POSSIBLE_MATCH_THRESHOLD = 0.60


@dataclass
class POMatch:
    po: PurchaseOrder | None
    method: str                         # explicit / inferred / none
    line_matches: dict[int, int | None] = field(default_factory=dict)  # invoice line -> PO line
    evidence: dict = field(default_factory=dict)


def _norm_po(s: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def identify_po(draft: InvoiceDraft, vendor: Vendor | None,
                all_pos: list[PurchaseOrder]) -> tuple[POMatch, list[CheckResult]]:
    results: list[CheckResult] = []
    ref = draft.get("po_number")

    if ref:
        po = next((p for p in all_pos if _norm_po(p.po_number) == _norm_po(ref)), None)
        if not po:
            results.append(CheckResult(
                "po_exists", "Purchase order", Outcome.WARN, Severity.WARNING,
                f"PO '{ref}' referenced on the invoice was not found in the procurement system.",
                actual=ref, field="po_number",
                recommended_action="Confirm the PO number with the requester or vendor."))
            return POMatch(None, "explicit"), results
        results.append(CheckResult(
            "po_exists", "Purchase order", Outcome.PASS, Severity.INFO,
            f"PO {po.po_number} referenced on the invoice exists.",
            expected=po.po_number, actual=ref, field="po_number"))
        return POMatch(po, "explicit"), results + _po_eligibility(po, vendor, draft)

    # No PO number on the invoice: look for candidates, but never auto-select
    candidates = [p for p in all_pos if vendor and p.vendor_id == vendor.vendor_id
                  and p.po_status.lower() in INVOICEABLE_STATUSES and p.remaining_balance > 0]
    if len(candidates) == 1:
        po = candidates[0]
        results.append(CheckResult(
            "po_exists", "Purchase order", Outcome.WARN, Severity.WARNING,
            f"No PO number on the invoice. One open PO for this vendor could apply: {po.po_number} "
            f"(remaining {format_inr(po.remaining_balance)}).",
            expected=po.po_number, actual="(not on invoice)", field="po_number",
            recommended_action=f"Confirm the invoice belongs to {po.po_number}."))
        return POMatch(po, "inferred"), results + _po_eligibility(po, vendor, draft)
    if len(candidates) > 1:
        results.append(CheckResult(
            "po_exists", "Purchase order", Outcome.WARN, Severity.WARNING,
            "No PO number on the invoice and several open POs could apply: "
            + ", ".join(f"{p.po_number} ({format_inr(p.remaining_balance)} left)" for p in candidates) + ".",
            actual="(not on invoice)", field="po_number",
            recommended_action="Select the correct PO; the system will not choose between them."))
        return POMatch(None, "ambiguous", evidence={"candidates": [p.po_number for p in candidates]}), results
    results.append(CheckResult(
        "po_exists", "Purchase order", Outcome.WARN, Severity.WARNING,
        "No PO number on the invoice and no open PO was found for this vendor.",
        actual="(not on invoice)", field="po_number",
        recommended_action="Ask the requester for the PO, or confirm whether this is a non-PO invoice."))
    return POMatch(None, "none"), results


def _po_eligibility(po: PurchaseOrder, vendor: Vendor | None, draft: InvoiceDraft) -> list[CheckResult]:
    out: list[CheckResult] = []
    if vendor:
        same = po.vendor_id == vendor.vendor_id
        out.append(CheckResult(
            "po_vendor", "Purchase order", Outcome.PASS if same else Outcome.FAIL,
            Severity.INFO if same else Severity.CRITICAL,
            f"PO {po.po_number} belongs to vendor {po.vendor_id}"
            + (", the same vendor as the invoice." if same else f", not to invoice vendor {vendor.vendor_id}."),
            expected=vendor.vendor_id, actual=po.vendor_id, field="po_number",
            recommended_action=None if same else "Do not process against this PO. Confirm the correct PO."))
    eligible = po.po_status.lower() in INVOICEABLE_STATUSES
    out.append(CheckResult(
        "po_status", "Purchase order", Outcome.PASS if eligible else Outcome.FAIL,
        Severity.INFO if eligible else Severity.CRITICAL,
        f"PO {po.po_number} status is {po.po_status}" + ("." if eligible else "; it cannot accept invoices."),
        expected="Open / Partially Invoiced", actual=po.po_status, field="po_number",
        recommended_action=None if eligible else "Ask procurement whether the PO should be reopened or amended."))
    cur = draft.get("currency")
    if cur is None:
        out.append(CheckResult(
            "po_currency", "Purchase order", Outcome.WARN, Severity.WARNING,
            f"Invoice does not state a currency; PO is in {po.currency}.",
            expected=po.currency, actual="(not stated)", field="currency",
            recommended_action="Confirm the invoice currency."))
    else:
        same = cur == po.currency
        out.append(CheckResult(
            "po_currency", "Purchase order", Outcome.PASS if same else Outcome.FAIL,
            Severity.INFO if same else Severity.CRITICAL,
            f"Invoice currency {cur} " + ("matches" if same else "does not match") + f" PO currency {po.currency}.",
            expected=po.currency, actual=cur, field="currency",
            recommended_action=None if same else "Request an invoice in the PO currency."))
    return out


# ---------------------------------------------------------------------------
# Line items
# ---------------------------------------------------------------------------
def _match_line(li: ExtractedLineItem, po_lines: list[POLine]) -> tuple[POLine | None, str, float]:
    if li.item_code:
        hit = next((p for p in po_lines if p.item_code and p.item_code.upper() == li.item_code.upper()), None)
        if hit:
            return hit, "item code", 1.0
    d = normalize_text(li.description)
    if d:
        hit = next((p for p in po_lines if normalize_text(p.item_description) == d), None)
        if hit:
            return hit, "description", 1.0
        best = max(po_lines, key=lambda p: SequenceMatcher(None, d, normalize_text(p.item_description)).ratio(),
                   default=None)
        if best:
            score = SequenceMatcher(None, d, normalize_text(best.item_description)).ratio()
            if score >= POSSIBLE_MATCH_THRESHOLD:
                return best, "possible", score
    return None, "none", 0.0


def match_lines(draft: InvoiceDraft, match: POMatch,
                invoiced_qty: dict[int, Decimal]) -> list[CheckResult]:
    po = match.po
    if not po or not draft.line_items:
        return []
    pol = settings.TOLERANCE
    out: list[CheckResult] = []
    for li in draft.line_items:
        label = f"Line {li.line_no} ({li.item_code or li.description or 'item'})"
        hit, how, score = _match_line(li, po.lines)
        if hit is None:
            match.line_matches[li.line_no] = None
            out.append(CheckResult(
                f"line{li.line_no}_match", "Line items", Outcome.WARN, Severity.WARNING,
                f"{label} does not correspond to any line on PO {po.po_number}.",
                actual=li.description, field=f"line_{li.line_no}",
                recommended_action="Confirm whether this item was ordered; it may need a PO amendment."))
            continue
        if how == "possible":
            match.line_matches[li.line_no] = None
            out.append(CheckResult(
                f"line{li.line_no}_match", "Line items", Outcome.WARN, Severity.WARNING,
                f"{label} looks similar to PO line {hit.line_no} '{hit.item_description}' "
                f"({score:.0%} similar) but is not an exact match.",
                expected=hit.item_description, actual=li.description, field=f"line_{li.line_no}",
                recommended_action="Confirm the item is the one ordered on the PO."))
            continue

        match.line_matches[li.line_no] = hit.line_no
        out.append(CheckResult(
            f"line{li.line_no}_match", "Line items", Outcome.PASS, Severity.INFO,
            f"{label} matched PO line {hit.line_no} by {how}.",
            expected=f"{hit.item_code} {hit.item_description}", actual=f"{li.item_code or ''} {li.description}",
            field=f"line_{li.line_no}"))

        # Quantity vs remaining quantity on the PO line
        already = invoiced_qty.get(hit.line_no, Decimal("0"))
        remaining = hit.quantity_ordered - already
        if li.quantity is not None:
            b = tolerance.evaluate(li.quantity, remaining, Decimal("0"), pol.amount_review_upper_pct)
            msg = (f"{label} quantity {li.quantity} vs {remaining} remaining on PO line "
                   f"(ordered {hit.quantity_ordered}, previously invoiced {already}): {b.band_label}.")
            out.append(CheckResult(
                f"line{li.line_no}_qty", "Line items", b.outcome, b.severity, msg,
                expected=str(remaining), actual=str(li.quantity), field=f"line_{li.line_no}",
                recommended_action=None if b.outcome == Outcome.PASS else
                "Check the goods receipt: the invoice bills more units than remain on the PO."))

        # Unit price vs PO price
        if li.unit_price is not None:
            b = tolerance.evaluate(li.unit_price, hit.unit_price, pol.unit_price_pass_pct,
                                   pol.unit_price_review_upper_pct)
            pct = f" ({b.variance_pct}%)" if b.variance_pct else ""
            out.append(CheckResult(
                f"line{li.line_no}_price", "Line items", b.outcome, b.severity,
                f"{label} unit price {format_inr(li.unit_price)} vs PO {format_inr(hit.unit_price)}"
                f"{pct}: {b.band_label}.",
                expected=format_inr(hit.unit_price), actual=format_inr(li.unit_price),
                field=f"line_{li.line_no}",
                recommended_action=None if b.outcome == Outcome.PASS else
                "Ask the vendor to justify the price difference or issue a corrected invoice."))
    return out
