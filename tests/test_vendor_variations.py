"""Vendors say the same thing differently. Each variation the extractor supports is pinned here."""
from datetime import date
from decimal import Decimal as D

import pytest

from config import settings
from database import repository as repo
from scripts.generate_samples import SPECS
from services import ocr_service
from services.extraction.rules import RuleBasedProvider
from services.models import DocumentText
from services.normalizers import parse_amount, parse_date, parse_quantity
from services.pipeline import run_pipeline


def extract_text(text: str, method="digital_text"):
    doc = DocumentText(pages=[text], words=[[]], method=method, page_count=1, char_count=len(text))
    return RuleBasedProvider().extract(doc)


@pytest.mark.parametrize("raw,expected", [
    ("1,20,000.00", "120000.00"), ("120,000.00", "120000.00"), ("INR 120,000.00", "120000.00"),
    ("Rs. 1,20,000.00/-", "120000.00"), ("₹1,20,000", "120000"), ("Rs.54,000/-", "54000"),
])
def test_amount_formats(raw, expected):
    assert parse_amount(raw) == D(expected)


@pytest.mark.parametrize("raw", ["14-Oct-2026", "14/10/2026", "14.10.2026", "2026-10-14", "Oct 14, 2026", "14 October 2026"])
def test_date_formats(raw):
    assert parse_date(raw) == date(2026, 10, 14)


@pytest.mark.parametrize("raw,expected", [("1,200", "1200"), ("1,200 Pcs", "1200"), ("10 Nos", "10"), ("2.5", "2.5")])
def test_quantity_formats(raw, expected):
    assert parse_quantity(raw) == D(expected)


@pytest.mark.parametrize("label", ["Invoice No.", "Invoice Number", "Bill No.", "Tax Invoice No", "Inv. No.", "Document No"])
def test_invoice_number_labels(label):
    assert extract_text(f"{label}: ABC/26/0571").get("invoice_number") == "ABC/26/0571"


@pytest.mark.parametrize("label", ["PO Reference", "PO No.", "Purchase Order No.", "Your Order No.",
                                   "Buyer's Order No.", "Buyer 's Order No.", "Buyer’s Order No."])
def test_po_labels_including_ocr_apostrophes(label):
    assert extract_text(f"{label}: PO-2026-0005").get("po_number") == "PO-2026-0005"


def test_bare_date_label_ignores_due_and_po_dates():
    d = extract_text("PO Date: 01/10/2026\nDue Date: 15/11/2026\nDate: 16/10/2026")
    assert d.get("invoice_date") == date(2026, 10, 16) and d.get("due_date") == date(2026, 11, 15)


@pytest.mark.parametrize("label", ["GSTIN", "GSTIN No.", "GST Regn. No.", "GSTIN/UIN", "Registration No.", "Tax ID"])
def test_gstin_found_whatever_the_label(label):
    d = extract_text(f"Acme Traders\n{label}: 29AABCD1234E1Z4\nBill To\nGSTIN: {settings.BUYER.gstin}")
    assert d.get("vendor_gstin") == "29AABCD1234E1Z4" and d.get("buyer_gstin") == settings.BUYER.gstin


@pytest.mark.parametrize("line,typ,rate,amt", [
    ("IGST @ 18% 1,70,100.00", "IGST", "18", "170100.00"), ("IGST (18%) INR 90,000.00", "IGST", "18", "90000.00"),
    ("Add: CGST @ 9% Rs. 6,480.00/-", "CGST", "9", "6480.00"), ("SGST 9% 6,480.00", "SGST", "9", "6480.00"),
])
def test_tax_line_formats(line, typ, rate, amt):
    t = extract_text(line).tax_lines[0]
    assert (t["type"], t["rate"], t["amount"]) == (typ, D(rate), D(amt))


def test_subtotal_never_confused_with_net_payable():
    d = extract_text("Taxable Amount Rs. 72,000.00/-\nNet Amount Payable Rs. 84,960.00/-")
    assert d.get("subtotal") == D("72000.00") and d.get("total_amount") == D("84960.00")


def test_title_line_is_not_taken_as_vendor_name():
    assert extract_text("TAX INVOICE\nHP India Sales Pvt Ltd\nGSTIN No.: 29AAACH4321M1ZI").get("vendor_name") == \
        "HP India Sales Pvt Ltd"


def test_wrapped_table_headers_are_understood():
    cols = RuleBasedProvider()._map_header(["S.\nNo", "Quanti\nty", "UO\nM", "Unit Rate\n(INR)", "Particulars", "Amount (Rs.)"])
    assert {"quantity", "uom", "unit_price", "description", "amount"} <= cols.keys()


def test_unruled_text_rows_with_grouped_quantities():
    d = extract_text("1 Corrugated Box 5-Ply 18x12x10 in 48191010 1,200 Pcs 45.00 54,000.00")
    li = d.line_items[0]
    assert (li.description, li.quantity, li.uom, li.amount) == ("Corrugated Box 5-Ply 18x12x10 in", D("1200"), "Pcs", D("54000.00"))


def test_currency_inferred_only_from_two_gst_registrations():
    with_gst = extract_text(f"Acme\nGSTIN: 29AABCD1234E1Z4\nGSTIN: {settings.BUYER.gstin}\nTotal Amount 100.00")
    assert with_gst.get("currency") == "INR" and with_gst.header["currency"].warning
    assert extract_text("Acme\nTotal Amount 100.00").get("currency") is None


# ------------------------------------------------------------------ the shipped test set
def test_sample_set_in_order_produces_expected_decisions(fresh_db):
    """The set is a sequence: re-sent duplicates and later deliveries depend on what came before."""
    got = {}
    for spec in SPECS:
        if spec["render"] != "pdf" and not ocr_service.is_available():
            continue
        r = run_pipeline(spec["file"], (settings.SAMPLE_DIR / spec["file"]).read_bytes())
        got[spec["file"]] = r.decision.status.value
    expected = {s["file"]: s["expect"] for s in SPECS if s["file"] in got}
    assert got == expected


def test_partial_invoice_leaves_po_balance(fresh_db):
    if not ocr_service.is_available():
        pytest.skip("Tesseract not installed")
    run_pipeline("s.pdf", (settings.SAMPLE_DIR / "sigma_inv_0932_scan.pdf").read_bytes())
    po = repo.get_purchase_order("PO-2026-0005")
    assert po.remaining_balance == D("20800.00")      # 62,000 - 41,200


def test_split_invoicing_draws_down_one_po_until_exhausted(fresh_db):
    for f in ("hp_inv_77188.pdf", "hp_inv_77245.pdf"):
        assert run_pipeline(f, (settings.SAMPLE_DIR / f).read_bytes()).decision.status.value == "READY_FOR_APPROVAL"
    assert repo.get_purchase_order("PO-2026-0008").remaining_balance == 0
    third = run_pipeline("x.pdf", (settings.SAMPLE_DIR / "hp_inv_77302.pdf").read_bytes())
    assert third.decision.status.value == "BLOCKED"
    assert any(c.check_key == "line1_qty" and c.outcome.value == "FAIL" for c in third.results)


def test_resent_photocopy_is_caught_by_number_not_file(fresh_db):
    if not ocr_service.is_available():
        pytest.skip("Tesseract not installed")
    run_pipeline("a.pdf", (settings.SAMPLE_DIR / "dell_inv_00418.pdf").read_bytes())
    r = run_pipeline("b.pdf", (settings.SAMPLE_DIR / "dell_inv_00418_resent_photocopy.pdf").read_bytes())
    dup = next(c for c in r.results if c.check_key == "duplicate")
    assert dup.outcome.value == "FAIL" and "Exact duplicate" in dup.message and "identical file" not in dup.message
