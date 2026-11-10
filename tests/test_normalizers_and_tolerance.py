from decimal import Decimal as D
from datetime import date

from services import tolerance
from services.models import Outcome, Severity
from services.normalizers import (
    format_inr, gstin_checksum, normalize_invoice_number, normalize_name, parse_amount,
    parse_date, validate_gstin,
)


def test_parse_amount_indian_and_western_grouping():
    assert parse_amount("₹ 9,45,000.00") == D("945000.00")
    assert parse_amount("Rs. 1,170.50") == D("1170.50")
    assert parse_amount("945,000.00") == D("945000.00")
    assert parse_amount("(1,000.00)") == D("-1000.00")
    assert parse_amount("N/A") is None and parse_amount("") is None


def test_decimal_has_no_float_drift():
    assert parse_amount("0.10") + parse_amount("0.20") == D("0.30")


def test_format_inr():
    assert format_inr(D("1115100")) == "₹11,15,100.00"
    assert format_inr(D("999")) == "₹999.00"


def test_dates_are_day_first():
    assert parse_date("14-Oct-2026") == date(2026, 10, 14)
    assert parse_date("03/04/2026") == date(2026, 4, 3)
    assert parse_date("not a date") is None


def test_invoice_number_normalization():
    assert normalize_invoice_number("DELL/INV/2026/00418") == normalize_invoice_number("dell-inv-2026-418")
    assert normalize_invoice_number("INV-0418") != normalize_invoice_number("INV-0419")


def test_name_normalization_strips_legal_suffix():
    assert normalize_name("Dell Technologies India Pvt Ltd") == normalize_name("Dell Technologies India Private Limited")


def test_gstin_checksum():
    assert validate_gstin("29AABCD1234E1Z4")[0]
    assert not validate_gstin("29AABCD1234E1Z5")[0]          # wrong check digit
    assert not validate_gstin("29AABCD1234E1X4")[0]          # malformed
    assert gstin_checksum("36AAACN5678K1Z") == "Z"


def test_tolerance_bands_follow_agreed_policy():
    ref, p, r = D("500000"), D("1"), D("10")
    assert tolerance.evaluate(D("502000"), ref, p, r).outcome == Outcome.PASS     # 0.4% (brief example)
    assert tolerance.evaluate(D("505000"), ref, p, r).outcome == Outcome.PASS     # exactly 1%
    b = tolerance.evaluate(D("505100"), ref, p, r)                                # 1.02%
    assert (b.outcome, b.severity) == (Outcome.WARN, Severity.WARNING)
    assert tolerance.evaluate(D("550000"), ref, p, r).outcome == Outcome.WARN     # exactly 10%
    assert tolerance.evaluate(D("550100"), ref, p, r).outcome == Outcome.FAIL     # > 10%
    assert tolerance.evaluate(D("400000"), ref, p, r).outcome == Outcome.PASS     # under-billing
    assert tolerance.evaluate(D("1"), D("0"), p, r).outcome == Outcome.FAIL       # nothing left
