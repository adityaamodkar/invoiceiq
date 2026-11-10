from datetime import date
from decimal import Decimal as D

import pytest

from services.document_processor import DocumentError, extract_text, validate_document
from services.extraction.rules import RuleBasedProvider
from services.invoice_extractor import check_extraction, extract_invoice
from services.models import Outcome


def _draft(sample_bytes):
    info = validate_document("inv.pdf", sample_bytes)
    doc = extract_text(info, sample_bytes)
    return doc, extract_invoice(doc)[0]


def test_digital_pdf_is_read_without_ocr(sample_bytes):
    doc, _ = _draft(sample_bytes)
    assert doc.method == "digital_text" and doc.char_count > 500


def test_header_fields_extracted_exactly(sample_bytes):
    _, d = _draft(sample_bytes)
    assert d.get("vendor_name") == "Dell Technologies India Pvt Ltd"
    assert d.get("vendor_gstin") == "29AABCD1234E1Z4"
    assert d.get("buyer_gstin") == "36AAACN5678K1ZZ"
    assert d.get("invoice_number") == "DELL/INV/2026/00418"
    assert d.get("invoice_date") == date(2026, 10, 14)
    assert d.get("due_date") == date(2026, 11, 13)
    assert d.get("po_number") == "PO-2026-0001"
    assert d.get("currency") == "INR"
    assert d.get("subtotal") == D("945000.00")
    assert d.get("tax_amount") == D("170100.00")
    assert d.get("total_amount") == D("1115100.00")
    assert d.get("discount") is None            # absent, not invented
    assert d.header["invoice_number"].source_page == 1
    assert d.header["invoice_number"].raw == "DELL/INV/2026/00418"


def test_line_items_extracted(sample_bytes):
    _, d = _draft(sample_bytes)
    assert [(l.item_code, l.quantity, l.unit_price, l.amount) for l in d.line_items] == [
        ("DL-LAT5450-I7", D("10"), D("82500.00"), D("825000.00")),
        ("DL-WD22TB4", D("10"), D("12000.00"), D("120000.00")),
    ]


def test_text_fallback_when_no_table(sample_bytes):
    doc, _ = _draft(sample_bytes)
    doc.tables = []
    d = RuleBasedProvider().extract(doc)
    assert len(d.line_items) == 2 and d.line_items[0].amount == D("825000.00")
    assert d.line_items[0].confidence < D("0.97")    # fallback is less confident


def test_extraction_checks_pass_on_happy_path(sample_bytes):
    _, d = _draft(sample_bytes)
    assert all(c.outcome == Outcome.PASS for c in check_extraction(d))


@pytest.mark.parametrize("name,data,fragment", [
    ("a.docx", b"PK..", "not supported"),
    ("a.pdf", b"", "empty"),
    ("a.pdf", b"hello world", "not a valid PDF"),
    ("a.pdf", b"%PDF-1.4 garbage", "damaged"),
    ("a.png", b"\x89PNG broken", "could not be opened"),
])
def test_bad_documents_are_rejected_with_clear_messages(name, data, fragment):
    with pytest.raises(DocumentError, match=fragment):
        validate_document(name, data)


def test_photocopy_cleanup_straightens_and_whitens():
    """Preprocessing must undo skew and grey paper well enough for OCR."""
    import numpy as np
    from PIL import Image, ImageDraw

    from services.ocr_service import _deskew, prepare
    img = Image.new("L", (1200, 900), 200)
    d = ImageDraw.Draw(img)
    for y in range(100, 800, 60):
        d.rectangle([100, y, 1100, y + 14], fill=60)
    skewed = img.rotate(2.0, fillcolor=200)
    _, angle = _deskew(skewed)
    assert abs(angle + 2.0) <= 0.5
    out = np.asarray(prepare(skewed))
    assert np.median(out) > 230          # grey paper becomes white
