"""
Generate synthetic vendor invoice PDFs from a spec.

Usage:
    python scripts/generate_sample_invoice.py

The happy-path spec below is deliberately consistent with data/*.csv:
vendor V001 (Dell), PO-2026-0001, 10 laptops + 10 docks, IGST 18%.
Edge-case specs will be added later by copying and modifying this one.
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.normalizers import money  # noqa: E402

HAPPY_PATH = {
    "file_name": "dell_invoice_00418.pdf",
    "vendor": {
        "name": "Dell Technologies India Pvt Ltd",
        "address": ["Divyasree Greens, Challaghatta", "Bengaluru, Karnataka 560071"],
        "gstin": "29AABCD1234E1Z4",
    },
    "buyer": {
        "name": "Northwind Components Pvt Ltd",
        "address": ["Plot 14, Phase II, IDA Patancheru", "Sangareddy, Telangana 502319"],
        "gstin": "36AAACN5678K1ZZ",
    },
    "invoice_number": "DELL/INV/2026/00418",
    "invoice_date": "14-Oct-2026",
    "due_date": "13-Nov-2026",
    "po_number": "PO-2026-0001",
    "place_of_supply": "Telangana (36)",
    "lines": [
        {"code": "DL-LAT5450-I7", "desc": "Dell Latitude 5450 Laptop (i7/16GB/512GB)",
         "hsn": "84713010", "qty": 10, "uom": "Nos", "rate": "82500.00"},
        {"code": "DL-WD22TB4", "desc": "Dell WD22TB4 Thunderbolt Dock",
         "hsn": "84733099", "qty": 10, "uom": "Nos", "rate": "12000.00"},
    ],
    "tax": {"type": "IGST", "rate": "18"},
}

INK = colors.HexColor("#1B2733")
MUTED = colors.HexColor("#5B6B79")
RULE = colors.HexColor("#C9D3DB")
BRAND = colors.HexColor("#0A5A9C")


def fmt(v: Decimal) -> str:
    """Indian grouping without currency symbol (Helvetica has no ₹ glyph)."""
    integer, frac = f"{money(v):.2f}".split(".")
    if len(integer) > 3:
        head, tail = integer[:-3], integer[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        integer = ",".join(parts + [tail])
    return f"{integer}.{frac}"


def build_invoice(spec: dict, out_path: Path) -> dict:
    s_norm = ParagraphStyle("n", fontName="Helvetica", fontSize=9, leading=12, textColor=INK)
    s_small = ParagraphStyle("s", parent=s_norm, fontSize=8, leading=10, textColor=MUTED)
    s_vendor = ParagraphStyle("v", parent=s_norm, fontName="Helvetica-Bold", fontSize=14,
                              leading=17, textColor=BRAND)
    s_title = ParagraphStyle("t", parent=s_norm, fontName="Helvetica-Bold", fontSize=16,
                             leading=20, alignment=2)

    v, b = spec["vendor"], spec["buyer"]
    story = []

    head = Table(
        [[
            [Paragraph(v["name"], s_vendor)]
            + [Paragraph(line, s_small) for line in v["address"]]
            + [Paragraph(f"GSTIN: {v['gstin']}", s_small)],
            [Paragraph("TAX INVOICE", s_title)],
        ]],
        colWidths=[110 * mm, 70 * mm],
    )
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [head, Spacer(1, 6 * mm)]

    meta_rows = [
        ["Invoice No.:", spec["invoice_number"]],
        ["Invoice Date:", spec["invoice_date"]],
        ["Due Date:", spec.get("due_date") or ""],
        ["PO Reference:", spec.get("po_number") or ""],
        ["Place of Supply:", spec.get("place_of_supply") or ""],
    ]
    meta_rows = [r for r in meta_rows if r[1]]
    bill_to = (
        [Paragraph("<b>Bill To</b>", s_norm), Paragraph(b["name"], s_norm)]
        + [Paragraph(line, s_small) for line in b["address"]]
        + [Paragraph(f"GSTIN: {b['gstin']}", s_small)]
    )
    meta = Table(meta_rows, colWidths=[28 * mm, 52 * mm])
    meta.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9), ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    block = Table([[bill_to, meta]], colWidths=[100 * mm, 80 * mm])
    block.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [block, Spacer(1, 6 * mm)]

    rows = [["#", "Item Code", "Description", "HSN", "Qty", "UOM", "Unit Price", "Amount (INR)"]]
    subtotal = Decimal("0")
    for i, ln in enumerate(spec["lines"], start=1):
        amt = money(Decimal(ln["rate"]) * Decimal(ln["qty"]))
        subtotal += amt
        rows.append([str(i), ln["code"], ln["desc"], ln["hsn"], str(ln["qty"]), ln["uom"],
                     fmt(Decimal(ln["rate"])), fmt(amt)])
    items = Table(rows, colWidths=[7 * mm, 27 * mm, 62 * mm, 17 * mm, 10 * mm, 11 * mm,
                                   22 * mm, 24 * mm], repeatRows=1)
    items.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2F5")),
        ("GRID", (0, 0), (-1, -1), 0.5, RULE),
        ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story += [items, Spacer(1, 4 * mm)]

    tax_rate = Decimal(spec["tax"]["rate"])
    tax = money(subtotal * tax_rate / 100)
    total = subtotal + tax
    totals = Table(
        [["Sub Total", fmt(subtotal)],
         [f"{spec['tax']['type']} @ {spec['tax']['rate']}%", fmt(tax)],
         ["Grand Total (INR)", fmt(total)]],
        colWidths=[45 * mm, 30 * mm], hAlign="RIGHT",
    )
    totals.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, INK), ("TEXTCOLOR", (0, 0), (-1, -1), INK),
    ]))
    story += [totals, Spacer(1, 8 * mm)]
    story += [
        Paragraph("Payment terms: Net 30 days from invoice date.", s_small),
        Paragraph("This is a synthetic invoice generated for the InvoiceIQ prototype. "
                  "It does not represent a real transaction.", s_small),
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(out_path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                      topMargin=15 * mm, bottomMargin=15 * mm,
                      title=f"Invoice {spec['invoice_number']}",
                      author=v["name"]).build(story)
    return {"subtotal": subtotal, "tax": tax, "total": total}


if __name__ == "__main__":
    out = ROOT / "sample_documents" / HAPPY_PATH["file_name"]
    t = build_invoice(HAPPY_PATH, out)
    print(f"Wrote {out.relative_to(ROOT)}  subtotal={t['subtotal']} tax={t['tax']} total={t['total']}")
