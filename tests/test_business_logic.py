"""Core business rules, tested without the UI and (mostly) without a database."""
import copy
from datetime import date
from decimal import Decimal as D

import pytest

from services import decision_engine, duplicate_detector, financial_validator, po_matcher, vendor_matcher
from services.document_processor import extract_text, validate_document
from services.invoice_extractor import extract_invoice
from services.models import (
    CheckResult, DecisionStatus, ExtractedField, Outcome, POLine, PurchaseOrder, Severity, Vendor,
)


def V(vid="V001", name="Dell Technologies India Pvt Ltd", gstin="29AABCD1234E1Z4", status="Active",
      aliases=("Dell India",)):
    return Vendor(vid, name, name, list(aliases), gstin, status, "INR", "", gstin[:2] if gstin else "", "Net 30")


def PO(po_number="PO-2026-0001", vendor_id="V001", status="Open", baseline="0", tol="1.0"):
    lines = [POLine(po_number, 1, "DL-LAT5450-I7", "Dell Latitude 5450 Laptop (i7/16GB/512GB)", "Nos",
                    D("10"), D("82500.00"), D("825000.00"), D("18")),
             POLine(po_number, 2, "DL-WD22TB4", "Dell WD22TB4 Thunderbolt Dock", "Nos",
                    D("10"), D("12000.00"), D("120000.00"), D("18"))]
    return PurchaseOrder(po_number, vendor_id, "2026-10-01", "INR", D("945000.00"), D("170100.00"),
                         D("1115100.00"), D(baseline), status, D(tol), lines)


@pytest.fixture(scope="module")
def base_draft(sample_bytes):
    info = validate_document("inv.pdf", sample_bytes)
    return extract_invoice(extract_text(info, sample_bytes))[0]


@pytest.fixture()
def draft(base_draft):
    return copy.deepcopy(base_draft)


def _set(d, name, value):
    d.header[name] = ExtractedField(value, str(value), D("0.98"), 1, "test")


def keys(results, outcome):
    return {r.check_key for r in results if r.outcome == outcome}


# ---------------------------------------------------------------- vendor
def test_vendor_verified_by_gstin_and_name(draft):
    v, res, _ = vendor_matcher.verify_vendor(draft, [V(), V("V002", "HP India Sales Pvt Ltd", "29AAACH4321M1ZI")])
    assert v.vendor_id == "V001" and all(r.outcome == Outcome.PASS for r in res)


def test_vendor_alias_is_accepted(draft):
    _set(draft, "vendor_name", "Dell India")
    v, res, _ = vendor_matcher.verify_vendor(draft, [V()])
    assert v.vendor_id == "V001" and "alias" in res[1].message


def test_inactive_vendor_is_critical(draft):
    _, res, _ = vendor_matcher.verify_vendor(draft, [V(status="Inactive")])
    assert any(r.check_key == "vendor_status" and r.severity == Severity.CRITICAL for r in res)


def test_unknown_vendor_is_critical(draft):
    _set(draft, "vendor_name", "Zenith Traders")
    _set(draft, "vendor_gstin", "27AAFFA9876Q1ZG")
    v, res, _ = vendor_matcher.verify_vendor(draft, [V()])
    assert v is None and any(r.severity == Severity.CRITICAL for r in res)


def test_gstin_of_one_vendor_with_name_of_another_is_critical(draft):
    _set(draft, "vendor_gstin", "29AAACH4321M1ZI")   # HP's GSTIN, Dell's name
    _, res, _ = vendor_matcher.verify_vendor(draft, [V(), V("V002", "HP India Sales Pvt Ltd", "29AAACH4321M1ZI")])
    ident = next(r for r in res if r.check_key == "vendor_identity")
    assert ident.severity == Severity.CRITICAL


def test_similar_name_is_only_a_suggestion(draft):
    _set(draft, "vendor_name", "Dell Technology India Pvt Ltd")
    draft.header["vendor_gstin"] = ExtractedField()
    v, res, _ = vendor_matcher.verify_vendor(draft, [V()])
    assert v is None and res[0].outcome == Outcome.WARN


# ---------------------------------------------------------------- PO
def test_explicit_po_matched_and_lines_match(draft):
    m, res = po_matcher.identify_po(draft, V(), [PO()])
    res += po_matcher.match_lines(draft, m, {})
    assert m.po.po_number == "PO-2026-0001" and m.line_matches == {1: 1, 2: 2}
    assert all(r.outcome == Outcome.PASS for r in res)


def test_po_of_other_vendor_is_critical(draft):
    _, res = po_matcher.identify_po(draft, V(), [PO(vendor_id="V002")])
    assert "po_vendor" in keys(res, Outcome.FAIL)


def test_closed_po_is_critical(draft):
    _, res = po_matcher.identify_po(draft, V(), [PO(status="Closed")])
    assert "po_status" in keys(res, Outcome.FAIL)


def test_missing_po_with_several_candidates_is_ambiguous_not_guessed(draft):
    draft.header["po_number"] = ExtractedField()
    m, res = po_matcher.identify_po(draft, V(), [PO(), PO("PO-2026-0009")])
    assert m.po is None and m.method == "ambiguous" and res[0].outcome == Outcome.WARN


def test_unit_price_bands(draft):
    draft.line_items[0].unit_price = D("86625.00")          # +5%
    m, _ = po_matcher.identify_po(draft, V(), [PO()])
    assert "line1_price" in keys(po_matcher.match_lines(draft, m, {}), Outcome.WARN)
    draft.line_items[0].unit_price = D("94875.00")          # +15%
    assert "line1_price" in keys(po_matcher.match_lines(draft, m, {}), Outcome.FAIL)


def test_similar_description_without_code_is_not_auto_matched(draft):
    draft.line_items[1].item_code = None
    draft.line_items[1].description = "Dell WD22 Dock Thunderbolt"
    m, _ = po_matcher.identify_po(draft, V(), [PO()])
    res = po_matcher.match_lines(draft, m, {})
    assert m.line_matches[2] is None and "line2_match" in keys(res, Outcome.WARN)


# ---------------------------------------------------------------- financial
def test_financials_pass_on_happy_path(draft):
    res, ev = financial_validator.validate(draft, PO())
    assert all(r.outcome == Outcome.PASS for r in res)
    assert ev["remaining_after"] == D("0.00")


def test_pre_tax_value_is_compared_with_po_not_tax_inclusive_total(draft):
    res, ev = financial_validator.validate(draft, PO())
    assert ev["this_invoice_pre_tax"] == D("945000.00")     # not 11,15,100


def test_po_balance_uses_cumulative_invoicing(draft):
    res, ev = financial_validator.validate(draft, PO(baseline="500000"))  # 5L already invoiced
    bal = next(r for r in res if r.check_key == "po_balance")
    assert bal.outcome == Outcome.FAIL and ev["variance_pct"] == D("52.91")


def test_po_tolerance_band_within_one_percent(draft):
    _set(draft, "subtotal", D("950000.00"))                 # +0.53% over PO
    res, _ = financial_validator.validate(draft, PO())
    assert next(r for r in res if r.check_key == "po_balance").outcome == Outcome.PASS


def test_total_arithmetic_mismatch_is_flagged(draft):
    _set(draft, "total_amount", D("1115900.00"))
    res, _ = financial_validator.validate(draft, PO())
    assert "total_arithmetic" in keys(res, Outcome.WARN)


def test_wrong_gst_type_is_flagged(draft):
    draft.tax_lines = [{"type": "CGST", "rate": D("9"), "amount": D("85050.00"), "page": 1},
                       {"type": "SGST", "rate": D("9"), "amount": D("85050.00"), "page": 1}]
    res, _ = financial_validator.validate(draft, PO())
    assert "tax_type" in keys(res, Outcome.WARN)            # Karnataka -> Telangana must be IGST


# ---------------------------------------------------------------- duplicates
PRIOR = {"run_id": "r1", "file_name": "x.pdf", "decision": "READY_FOR_APPROVAL",
         "invoice_number": "DELL/INV/2026/00418", "invoice_date": "2026-10-14",
         "total_paise": 111510000, "vendor_id": "V001"}


def test_no_duplicate(draft):
    res, _ = duplicate_detector.check(draft, "V001", "abc", [], [], [])
    assert res[0].outcome == Outcome.PASS


def test_same_file_is_exact_duplicate(draft):
    res, ev = duplicate_detector.check(draft, "V001", "abc", [PRIOR], [], [PRIOR])
    assert res[0].severity == Severity.CRITICAL and ev["match_type"] == "exact_file"


def test_same_number_and_amount_is_exact_duplicate(draft):
    res, ev = duplicate_detector.check(draft, "V001", "new", [], [PRIOR], [PRIOR])
    assert res[0].severity == Severity.CRITICAL and ev["match_type"] == "exact_number_amount"


def test_same_number_different_amount_is_possible_duplicate(draft):
    other = {**PRIOR, "total_paise": 100000000}
    res, _ = duplicate_detector.check(draft, "V001", "new", [], [other], [other])
    assert res[0].severity == Severity.WARNING


def test_same_amount_different_number_is_possible_duplicate(draft):
    other = {**PRIOR, "invoice_number": "DELL/INV/2026/00419"}
    res, _ = duplicate_detector.check(draft, "V001", "new", [], [], [other])
    assert res[0].severity == Severity.WARNING


# ---------------------------------------------------------------- decision
def _r(sev, cat="Financial"):
    out = {Severity.INFO: Outcome.PASS, Severity.WARNING: Outcome.WARN, Severity.CRITICAL: Outcome.FAIL}[sev]
    return CheckResult("k", cat, out, sev, f"{sev.value} msg", recommended_action="act")


def test_decision_mapping():
    assert decision_engine.decide([_r(Severity.INFO)]).status == DecisionStatus.READY_FOR_APPROVAL
    assert decision_engine.decide([_r(Severity.INFO), _r(Severity.WARNING)]).status == DecisionStatus.NEEDS_REVIEW
    assert decision_engine.decide([_r(Severity.WARNING), _r(Severity.CRITICAL)]).status == DecisionStatus.BLOCKED


def test_decision_leads_with_root_cause_and_never_pays():
    d = decision_engine.decide([_r(Severity.CRITICAL, "Financial"), _r(Severity.CRITICAL, "Duplicate")])
    assert d.reason.startswith("CRITICAL msg") and "1 further issue" in d.reason and "No payment has been initiated" in d.next_action
