"""
Financial validation.

Comparison methodology (shown to the user):
  * PO amounts are pre-tax. The invoice's pre-tax value (subtotal) is compared
    against the PO; tax is validated separately against the GST rate.
  * PO tolerance is measured on the ORIGINAL PO value:
        cumulative pre-tax invoiced (previous + this invoice) vs PO subtotal
        Variance % = (cumulative - PO subtotal) / PO subtotal x 100
    This supports split invoicing: the first invoice of a split PO and the last
    one are judged against the same reference.
  * All arithmetic uses Decimal with a Rs 1 rounding allowance.
"""
from __future__ import annotations

from decimal import Decimal

from config import settings
from services import tolerance
from services.models import CheckResult, InvoiceDraft, Outcome, PurchaseOrder, Severity
from services.normalizers import format_inr, money

ZERO = Decimal("0")


def _close(a: Decimal, b: Decimal, allowance: Decimal) -> bool:
    return abs(money(a) - money(b)) <= allowance


def validate(draft: InvoiceDraft, po: PurchaseOrder | None) -> tuple[list[CheckResult], dict]:
    pol = settings.TOLERANCE
    out: list[CheckResult] = []
    g = draft.get
    subtotal, tax, total = g("subtotal"), g("tax_amount"), g("total_amount")
    discount, charges = g("discount") or ZERO, g("other_charges") or ZERO
    evidence: dict = {}

    # 1. Line arithmetic: qty x unit price = line amount
    bad = []
    for li in draft.line_items:
        if None in (li.quantity, li.unit_price, li.amount):
            continue
        calc = money(li.quantity * li.unit_price)
        if not _close(calc, li.amount, pol.arithmetic_rounding_abs):
            bad.append(f"line {li.line_no}: {li.quantity} x {format_inr(li.unit_price)} = "
                       f"{format_inr(calc)}, invoice shows {format_inr(li.amount)}")
    if draft.line_items:
        out.append(CheckResult(
            "line_arithmetic", "Financial", Outcome.WARN if bad else Outcome.PASS,
            Severity.WARNING if bad else Severity.INFO,
            ("Line arithmetic errors: " + "; ".join(bad) + ".") if bad else
            f"Quantity x unit price equals the line amount on all {len(draft.line_items)} lines.",
            field="line_items",
            recommended_action="Ask the vendor for a corrected invoice." if bad else None))

    # 2. Sum of lines = subtotal
    if draft.line_items and subtotal is not None:
        lines_sum = sum((li.amount for li in draft.line_items if li.amount is not None), ZERO)
        ok = _close(lines_sum, subtotal, pol.arithmetic_rounding_abs) or (
            discount and _close(lines_sum - discount, subtotal, pol.arithmetic_rounding_abs))
        out.append(CheckResult(
            "subtotal_arithmetic", "Financial", Outcome.PASS if ok else Outcome.WARN,
            Severity.INFO if ok else Severity.WARNING,
            f"Sum of line items {format_inr(lines_sum)} "
            + ("agrees with" if ok else "does not agree with") + f" the subtotal {format_inr(subtotal)}.",
            expected=format_inr(lines_sum), actual=format_inr(subtotal), field="subtotal",
            recommended_action=None if ok else "Check for missing or bundled line items."))

    # 3. Tax = subtotal x rate, and GST type matches the supply
    if draft.tax_lines and subtotal is not None:
        taxable = subtotal - discount + charges
        problems = []
        for t in draft.tax_lines:
            calc = money(taxable * t["rate"] / 100)
            if not _close(calc, t["amount"], pol.tax_rounding_abs):
                problems.append(f"{t['type']} @{t['rate']}% on {format_inr(taxable)} should be "
                                f"{format_inr(calc)}, invoice shows {format_inr(t['amount'])}")
        out.append(CheckResult(
            "tax_calculation", "Financial", Outcome.WARN if problems else Outcome.PASS,
            Severity.WARNING if problems else Severity.INFO,
            ("Tax calculation differs: " + "; ".join(problems) + ".") if problems else
            "Tax amount agrees with the stated rate: " + "; ".join(
                f"{t['type']} @{t['rate']}% = {format_inr(t['amount'])}" for t in draft.tax_lines) + ".",
            field="tax_amount",
            recommended_action="Ask the vendor to correct the tax computation." if problems else None))

        vendor_state = (draft.get("vendor_gstin") or "")[:2]
        types = {t["type"] for t in draft.tax_lines}
        if vendor_state:
            inter = vendor_state != settings.BUYER.state_code
            ok = (types == {"IGST"}) if inter else (types == {"CGST", "SGST"} or types == {"CGST", "UTGST"})
            expected = "IGST (inter-state supply)" if inter else "CGST + SGST (intra-state supply)"
            out.append(CheckResult(
                "tax_type", "Financial", Outcome.PASS if ok else Outcome.WARN,
                Severity.INFO if ok else Severity.WARNING,
                f"Vendor state {vendor_state}, buyer state {settings.BUYER.state_code}: expected {expected}; "
                f"invoice charges {' + '.join(sorted(types))}.",
                expected=expected, actual=" + ".join(sorted(types)), field="tax_amount",
                recommended_action=None if ok else "Wrong GST type cannot be claimed as input credit; "
                                                   "request a corrected invoice."))
        if po and po.lines:
            po_rates = {l.tax_rate for l in po.lines}
            inv_rate = sum((t["rate"] for t in draft.tax_lines), ZERO)
            ok = po_rates == {inv_rate}
            out.append(CheckResult(
                "tax_rate_vs_po", "Financial", Outcome.PASS if ok else Outcome.WARN,
                Severity.INFO if ok else Severity.WARNING,
                f"Invoice GST rate {inv_rate}% " + ("matches" if ok else "differs from")
                + f" the PO rate {', '.join(f'{r}%' for r in sorted(po_rates))}.",
                expected=", ".join(f"{r}%" for r in sorted(po_rates)), actual=f"{inv_rate}%",
                field="tax_amount",
                recommended_action=None if ok else "Confirm the applicable GST rate with tax/procurement."))
    elif subtotal is not None and tax is None:
        out.append(CheckResult(
            "tax_calculation", "Financial", Outcome.WARN, Severity.WARNING,
            "Tax could not be identified on the invoice, so it was not validated.",
            field="tax_amount", recommended_action="Confirm the tax treatment on the original document."))

    # 4. Total = subtotal - discount + charges + tax
    if None not in (subtotal, tax, total):
        calc = subtotal - discount + charges + tax
        ok = _close(calc, total, pol.arithmetic_rounding_abs)
        out.append(CheckResult(
            "total_arithmetic", "Financial", Outcome.PASS if ok else Outcome.WARN,
            Severity.INFO if ok else Severity.WARNING,
            f"Subtotal {format_inr(subtotal)}"
            + (f" - discount {format_inr(discount)}" if discount else "")
            + (f" + charges {format_inr(charges)}" if charges else "")
            + f" + tax {format_inr(tax)} = {format_inr(calc)}; invoice total is {format_inr(total)}.",
            expected=format_inr(calc), actual=format_inr(total), field="total_amount",
            recommended_action=None if ok else "The stated total does not add up; request a corrected invoice."))

    if charges and po:
        out.append(CheckResult(
            "charges_on_po", "Financial", Outcome.WARN, Severity.WARNING,
            f"Invoice includes other charges of {format_inr(charges)} (e.g. freight) that are not on PO {po.po_number}.",
            expected=format_inr(ZERO), actual=format_inr(charges), field="other_charges",
            recommended_action="Confirm whether these charges were agreed."))

    # 5. PO balance and tolerance (pre-tax vs pre-tax)
    if po and subtotal is not None:
        invoice_value = subtotal - discount
        cumulative = po.amount_already_invoiced + invoice_value
        pass_pct = po.tolerance_pct if po.tolerance_pct is not None else pol.amount_pass_pct
        b = tolerance.evaluate(cumulative, po.subtotal, pass_pct, pol.amount_review_upper_pct)
        evidence.update({
            "po_subtotal": po.subtotal, "previously_invoiced": po.amount_already_invoiced,
            "this_invoice_pre_tax": invoice_value, "cumulative_after_invoice": cumulative,
            "remaining_before": po.remaining_balance, "remaining_after": po.subtotal - cumulative,
            "variance_amount": max(b.difference, ZERO), "variance_pct": b.variance_pct,
            "tolerance_pass_pct": pass_pct, "review_upper_pct": pol.amount_review_upper_pct,
        })
        if b.difference <= 0:
            msg = (f"Pre-tax invoice value {format_inr(invoice_value)} fits within the PO's remaining balance "
                   f"{format_inr(po.remaining_balance)} (PO {format_inr(po.subtotal)}, previously invoiced "
                   f"{format_inr(po.amount_already_invoiced)}).")
        else:
            msg = (f"Cumulative invoiced {format_inr(cumulative)} exceeds PO value {format_inr(po.subtotal)} by "
                   f"{format_inr(b.difference)} ({b.variance_pct}%): {b.band_label}.")
        out.append(CheckResult(
            "po_balance", "Financial", b.outcome, b.severity, msg,
            expected=f"<= {format_inr(po.subtotal)} (+{pass_pct}% tolerance)",
            actual=format_inr(cumulative), field="subtotal",
            recommended_action=None if b.outcome == Outcome.PASS else (
                "Hold for buyer approval of the overrun or a PO amendment." if b.outcome == Outcome.WARN
                else "Do not process. The invoice exceeds the PO beyond the review band; "
                     "a PO amendment is required.")))
    return out, evidence
