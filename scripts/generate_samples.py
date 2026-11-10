"""
Generate the InvoiceIQ test-invoice set.

    python scripts/generate_samples.py

Each spec deliberately varies what real vendors vary: layout, field labels
("Invoice No" / "Bill No" / "Tax Invoice No"), GST registration labels,
number formats (1,20,000.00 / 120,000.00 / Rs. 54,000.00/-), units
(Nos / EA / Pcs / Rolls / Ream), table style (ruled / unruled), tax
presentation (IGST vs CGST + SGST), and medium (digital PDF / scanned PDF / photo).

All values agree with data/*.csv unless a spec says otherwise.

File names and labels are deliberately neutral: they say who sent the invoice
and what kind of document it is, never what InvoiceIQ should decide. The
"expect" and "about" fields are for tests and demo preparation only.
"""
from __future__ import annotations

import io
import random
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

OUT = ROOT / "sample_documents"
BUYER = {"name": "Northwind Components Pvt Ltd",
         "address": ["Plot 14, Phase II, IDA Patancheru", "Sangareddy, Telangana 502319"],
         "gstin": "36AAACN5678K1ZZ"}


# --------------------------------------------------------------------------- number formats
def indian(v: Decimal) -> str:
    integer, frac = f"{money(v):.2f}".split(".")
    if len(integer) > 3:
        head, tail, parts = integer[:-3], integer[-3:], []
        while len(head) > 2:
            parts.insert(0, head[-2:]); head = head[:-2]
        if head:
            parts.insert(0, head)
        integer = ",".join(parts + [tail])
    return f"{integer}.{frac}"


FORMATS = {
    "indian": indian,
    "western": lambda v: f"{money(v):,.2f}",
    "inr_western": lambda v: f"INR {money(v):,.2f}",
    "rs_indian": lambda v: f"Rs. {indian(v)}",
    "rs_slash": lambda v: f"Rs. {indian(v)}/-",
}

# --------------------------------------------------------------------------- specs
SPECS: list[dict] = [
    {   # 1. The original happy path: clean digital PDF, ruled table, IGST
        "file": "dell_inv_00418.pdf", "label": "Dell Technologies, invoice 00418", "medium": "Digital PDF", "expect": "READY_FOR_APPROVAL",
        "about": "Digital PDF, ruled table, item codes, IGST (inter-state).",
        "font": "Helvetica", "brand": "#0A5A9C", "title_first": False,
        "vendor": {"name": "Dell Technologies India Pvt Ltd",
                   "address": ["Divyasree Greens, Challaghatta", "Bengaluru, Karnataka 560071"],
                   "gstin": "29AABCD1234E1Z4", "gstin_label": "GSTIN"},
        "meta": [("Invoice No.", "DELL/INV/2026/00418"), ("Invoice Date", "14-Oct-2026"),
                 ("Due Date", "13-Nov-2026"), ("PO Reference", "PO-2026-0001"),
                 ("Place of Supply", "Telangana (36)")],
        "columns": [("#", "sn"), ("Item Code", "code"), ("Description", "desc"), ("HSN", "hsn"),
                    ("Qty", "qty"), ("UOM", "uom"), ("Unit Price", "rate"), ("Amount (INR)", "amount")],
        "lines": [("DL-LAT5450-I7", "Dell Latitude 5450 Laptop (i7/16GB/512GB)", "84713010", 10, "Nos", "82500.00"),
                  ("DL-WD22TB4", "Dell WD22TB4 Thunderbolt Dock", "84733099", 10, "Nos", "12000.00")],
        "tax": [("IGST @ {r}%", "18")], "table": "grid", "fmt_table": "indian", "fmt_totals": "indian",
        "subtotal_label": "Sub Total", "total_label": "Grand Total (INR)", "render": "pdf",
    },
    {   # 2. Corporate layout: title first, western digit grouping, "EA", different labels
        "file": "hp_inv_77031.pdf", "label": "HP India Sales, invoice 77031", "medium": "Digital PDF", "expect": "READY_FOR_APPROVAL",
        "about": "Title above vendor name; 'Invoice Number' / 'Date' / 'Purchase Order No.'; "
                 "western grouping with INR prefix; unit 'EA'.",
        "font": "Times-Roman", "brand": "#0096D6", "title_first": True,
        "vendor": {"name": "HP India Sales Pvt Ltd",
                   "address": ["24 Salarpuria Arena, Hosur Road", "Bengaluru, Karnataka 560030"],
                   "gstin": "29AAACH4321M1ZI", "gstin_label": "GSTIN No."},
        "meta": [("Invoice Number", "HPI-KA-2026-77031"), ("Date", "16/10/2026"),
                 ("Purchase Order No.", "PO-2026-0002"), ("Payment Terms", "Net 45")],
        "columns": [("S.No", "sn"), ("Part Number", "code"), ("Item Description", "desc"),
                    ("Quantity", "qty"), ("Unit", "uom"), ("Unit Rate (INR)", "rate"),
                    ("Taxable Value (INR)", "amount")],
        "lines": [("HP-ELB840-G11", "HP EliteBook 840 G11 Laptop", "", 5, "EA", "100000.00")],
        "tax": [("IGST (18%)", "18")], "table": "grid", "fmt_table": "western", "fmt_totals": "inr_western",
        "subtotal_label": "Total Taxable Value", "total_label": "Total Invoice Value", "render": "pdf",
    },
    {   # 3. Local trader: unruled table, no item codes, Rs./- amounts, CGST + SGST
        "file": "deccan_bill_1187.pdf", "label": "Deccan Packaging, bill 1187", "medium": "Digital PDF", "expect": "READY_FOR_APPROVAL",
        "about": "Unruled columns; 'Bill No.' / 'Bill Date' / 'Your Order No.' / 'GST Regn. No.'; "
                 "no item codes (matched by description); 'Rs. ... /-' amounts; quantities like 1,200 Pcs; "
                 "CGST + SGST (intra-state).",
        "font": "Courier", "brand": "#5B3A1A", "title_first": False,
        "vendor": {"name": "Deccan Packaging Solutions",
                   "address": ["Plot 7, IDA Bollaram", "Sangareddy, Telangana 502325"],
                   "gstin": "36AAJFD4321P1Z6", "gstin_label": "GST Regn. No."},
        "meta": [("Bill No.", "DPS/1187/26-27"), ("Bill Date", "18.10.2026"), ("Your Order No.", "PO-2026-0007")],
        "columns": [("Sl", "sn"), ("Particulars", "desc"), ("HSN", "hsn"), ("Qty", "qty"),
                    ("Unit", "uom"), ("Rate", "rate"), ("Amount", "amount")],
        "lines": [("", "Corrugated Box 5-Ply 18x12x10 in", "48191010", 1200, "Pcs", "45.00"),
                  ("", "BOPP Packing Tape 48mm x 65m", "39191000", 150, "Rolls", "120.00")],
        "tax": [("Add: CGST @ {r}%", "9"), ("Add: SGST @ {r}%", "9")], "table": "plain",
        "fmt_table": "indian", "fmt_totals": "rs_slash",
        "subtotal_label": "Taxable Amount", "total_label": "Net Amount Payable", "render": "pdf",
    },
    {   # 4. Scanned PDF: image only, needs OCR; a partial delivery against the PO
        "file": "sigma_inv_0932_scan.pdf", "label": "Sigma Office Solutions, invoice 0932", "medium": "Scanned PDF", "expect": "READY_FOR_APPROVAL",
        "about": "Scanned (image-only) PDF read by OCR; 'Tax Invoice No' / 'Invoice Dt' / "
                 "\"Buyer's Order No.\"; partial invoice: 120 of 200 reams, so PO balance remains.",
        "font": "Helvetica", "brand": "#2E2E2E", "title_first": False,
        "vendor": {"name": "Sigma Office Solutions Pvt Ltd",
                   "address": ["88 Residency Road", "Bengaluru, Karnataka 560025"],
                   "gstin": "29AAFCS2468L1ZS", "gstin_label": "GSTIN/UIN"},
        "meta": [("Tax Invoice No", "SOS-2026-0932"), ("Invoice Dt", "20-Oct-2026"),
                 ("Buyer's Order No.", "PO-2026-0005")],
        "columns": [("No", "sn"), ("Item Code", "code"), ("Description of Goods", "desc"), ("HSN", "hsn"),
                    ("Qty", "qty"), ("Per", "uom"), ("Rate", "rate"), ("Amount", "amount")],
        "lines": [("SG-A4-75", "A4 Copier Paper 75 GSM (Ream)", "48025690", 120, "Ream", "260.00"),
                  ("SG-TONER-12A", "Laser Toner Cartridge 12A Compatible", "84439959", 10, "Nos", "1000.00")],
        "tax": [("IGST @ {r}%", "18")], "table": "grid", "fmt_table": "indian", "fmt_totals": "indian",
        "subtotal_label": "Assessable Value", "total_label": "Amount Payable", "render": "scan_pdf",
    },
    {   # 5. Price increase: 4% over PO price and 2% over PO value -> review band
        "file": "hp_inv_77104.pdf", "label": "HP India Sales, invoice 77104", "medium": "Digital PDF", "expect": "NEEDS_REVIEW",
        "about": "Unit price ₹15,600 vs PO ₹15,000 (+4%); cumulative value 2% over PO. "
                 "Inside the 10% review band, so a person decides.",
        "font": "Times-Roman", "brand": "#0096D6", "title_first": True,
        "vendor": {"name": "HP India Sales Pvt Ltd",
                   "address": ["24 Salarpuria Arena, Hosur Road", "Bengaluru, Karnataka 560030"],
                   "gstin": "29AAACH4321M1ZI", "gstin_label": "GSTIN No."},
        "meta": [("Invoice Number", "HPI-KA-2026-77104"), ("Date", "22/10/2026"),
                 ("Purchase Order No.", "PO-2026-0003"), ("Payment Terms", "Net 45")],
        "columns": [("S.No", "sn"), ("Part Number", "code"), ("Item Description", "desc"),
                    ("Quantity", "qty"), ("Unit", "uom"), ("Unit Rate (INR)", "rate"),
                    ("Taxable Value (INR)", "amount")],
        "lines": [("HP-M27F", "HP M27f 27-inch FHD Monitor", "", 8, "EA", "15600.00")],
        "tax": [("IGST (18%)", "18")], "table": "grid", "fmt_table": "western", "fmt_totals": "inr_western",
        "subtotal_label": "Total Taxable Value", "total_label": "Total Invoice Value", "render": "pdf",
    },
    {   # 6. Inactive vendor, photographed invoice -> blocked
        "file": "abc_inv_0571_photo.jpg", "label": "ABC Industrial Supplies, invoice 0571", "medium": "Phone photo (JPG)", "expect": "BLOCKED",
        "about": "Phone photo (JPG) of an invoice from ABC Industrial Supplies, whose vendor record is "
                 "Inactive. Everything else matches PO-2026-0004.",
        "font": "Helvetica", "brand": "#8A1C1C", "title_first": False,
        "vendor": {"name": "ABC Industrial Supplies",
                   "address": ["Plot 22, MIDC Bhosari", "Pune, Maharashtra 411026"],
                   "gstin": "27AAFFA9876Q1ZG", "gstin_label": "GSTIN"},
        "meta": [("Invoice No.", "ABC/26/0571"), ("Invoice Date", "21-Oct-2026"), ("PO No.", "PO-2026-0004")],
        "columns": [("#", "sn"), ("Item Code", "code"), ("Description", "desc"), ("Qty", "qty"),
                    ("UOM", "uom"), ("Rate", "rate"), ("Amount", "amount")],
        "lines": [("ABC-SG-500", "Industrial Safety Gloves (Box of 50)", "", 300, "Box", "600.00")],
        "tax": [("IGST @ {r}%", "18")], "table": "grid", "fmt_table": "indian", "fmt_totals": "indian",
        "subtotal_label": "Sub Total", "total_label": "Total Amount", "render": "jpg",
    },
    # ---------------------------------------------------------------- extended set (07-14)
    {  # 7. Split invoicing, part 1 of a 30-unit PO
        "file": "hp_inv_77188.pdf", "label": "HP India Sales, invoice 77188", "medium": "Digital PDF",
        "expect": "READY_FOR_APPROVAL",
        "about": "First delivery against PO-2026-0008: 18 of 30 monitors. PO keeps 12 units / Rs 1,50,000.",
        "vendor": {"name": "HP India Sales Pvt Ltd",
                   "address": ["24 Salarpuria Arena, Hosur Road", "Bengaluru, Karnataka 560030"],
                   "gstin": "29AAACH4321M1ZI", "gstin_label": "GSTIN No."},
        "columns": [("S.No", "sn"), ("Part Number", "code"), ("Item Description", "desc"),
                    ("Quantity", "qty"), ("Unit", "uom"), ("Unit Rate (INR)", "rate"),
                    ("Taxable Value (INR)", "amount")],
        "tax": [("IGST (18%)", "18")], "table": "grid", "fmt_table": "western", "fmt_totals": "inr_western",
        "subtotal_label": "Total Taxable Value", "total_label": "Total Invoice Value",
        "font": "Times-Roman", "brand": "#0096D6", "title_first": True,
        "meta": [("Invoice Number", "HPI-KA-2026-77188"), ("Date", "24/10/2026"),
                 ("Purchase Order No.", "PO-2026-0008"), ("Payment Terms", "Net 45")],
        "lines": [("HP-P24G5", "HP P24 G5 24-inch FHD Monitor", "", 18, "EA", "12500.00")],
        "render": "pdf",
    },
    {  # 8. Split invoicing, part 2: completes the PO
        "file": "hp_inv_77245.pdf", "label": "HP India Sales, invoice 77245", "medium": "Digital PDF",
        "expect": "READY_FOR_APPROVAL",
        "about": "Second delivery against PO-2026-0008: the remaining 12 monitors. Run after 77188; the PO is then fully used.",
        "vendor": {"name": "HP India Sales Pvt Ltd",
                   "address": ["24 Salarpuria Arena, Hosur Road", "Bengaluru, Karnataka 560030"],
                   "gstin": "29AAACH4321M1ZI", "gstin_label": "GSTIN No."},
        "columns": [("S.No", "sn"), ("Part Number", "code"), ("Item Description", "desc"),
                    ("Quantity", "qty"), ("Unit", "uom"), ("Unit Rate (INR)", "rate"),
                    ("Taxable Value (INR)", "amount")],
        "tax": [("IGST (18%)", "18")], "table": "grid", "fmt_table": "western", "fmt_totals": "inr_western",
        "subtotal_label": "Total Taxable Value", "total_label": "Total Invoice Value",
        "font": "Times-Roman", "brand": "#0096D6", "title_first": True,
        "meta": [("Invoice Number", "HPI-KA-2026-77245"), ("Date", "29/10/2026"),
                 ("Purchase Order No.", "PO-2026-0008"), ("Payment Terms", "Net 45")],
        "lines": [("HP-P24G5", "HP P24 G5 24-inch FHD Monitor", "", 12, "EA", "12500.00")],
        "render": "pdf",
    },
    {  # 9. Split invoicing, part 3: bills beyond the PO
        "file": "hp_inv_77302.pdf", "label": "HP India Sales, invoice 77302", "medium": "Digital PDF",
        "expect": "BLOCKED",
        "about": "Third invoice against PO-2026-0008 for 4 more monitors after all 30 were billed (77188 + 77245): "
                 "nothing is left on the PO.",
        "vendor": {"name": "HP India Sales Pvt Ltd",
                   "address": ["24 Salarpuria Arena, Hosur Road", "Bengaluru, Karnataka 560030"],
                   "gstin": "29AAACH4321M1ZI", "gstin_label": "GSTIN No."},
        "columns": [("S.No", "sn"), ("Part Number", "code"), ("Item Description", "desc"),
                    ("Quantity", "qty"), ("Unit", "uom"), ("Unit Rate (INR)", "rate"),
                    ("Taxable Value (INR)", "amount")],
        "tax": [("IGST (18%)", "18")], "table": "grid", "fmt_table": "western", "fmt_totals": "inr_western",
        "subtotal_label": "Total Taxable Value", "total_label": "Total Invoice Value",
        "font": "Times-Roman", "brand": "#0096D6", "title_first": True,
        "meta": [("Invoice Number", "HPI-KA-2026-77302"), ("Date", "02/11/2026"),
                 ("Purchase Order No.", "PO-2026-0008"), ("Payment Terms", "Net 45")],
        "lines": [("HP-P24G5", "HP P24 G5 24-inch FHD Monitor", "", 4, "EA", "12500.00")],
        "render": "pdf",
    },
    {  # 10. The Dell invoice again, re-sent by the vendor as a photocopy
        "file": "dell_inv_00418_resent_photocopy.pdf", "label": "Dell Technologies, invoice 00418 (re-sent)",
        "medium": "Photocopy, scanned", "expect": "BLOCKED",
        "about": "The vendor re-sent invoice 00418 as a scanned photocopy: a different file, so only the invoice "
                 "number and amount reveal the duplicate. Run after dell_inv_00418.pdf.",
        "font": "Helvetica", "brand": "#0A5A9C", "title_first": False,
        "vendor": {"name": "Dell Technologies India Pvt Ltd",
                   "address": ["Divyasree Greens, Challaghatta", "Bengaluru, Karnataka 560071"],
                   "gstin": "29AABCD1234E1Z4", "gstin_label": "GSTIN"},
        "meta": [("Invoice No.", "DELL/INV/2026/00418"), ("Invoice Date", "14-Oct-2026"),
                 ("Due Date", "13-Nov-2026"), ("PO Reference", "PO-2026-0001"),
                 ("Place of Supply", "Telangana (36)")],
        "columns": [("#", "sn"), ("Item Code", "code"), ("Description", "desc"), ("HSN", "hsn"),
                    ("Qty", "qty"), ("UOM", "uom"), ("Unit Price", "rate"), ("Amount (INR)", "amount")],
        "lines": [("DL-LAT5450-I7", "Dell Latitude 5450 Laptop (i7/16GB/512GB)", "84713010", 10, "Nos", "82500.00"),
                  ("DL-WD22TB4", "Dell WD22TB4 Thunderbolt Dock", "84733099", 10, "Nos", "12000.00")],
        "tax": [("IGST @ {r}%", "18")], "table": "grid", "fmt_table": "indian", "fmt_totals": "indian",
        "subtotal_label": "Sub Total", "total_label": "Grand Total (INR)", "render": "photocopy",
    },
    {  # 11. Photocopy that should still clear: second delivery for PO-2026-0005
        "file": "sigma_inv_0987_photocopy.pdf", "label": "Sigma Office Solutions, invoice 0987",
        "medium": "Photocopy, scanned", "expect": "READY_FOR_APPROVAL",
        "about": "Grey, skewed photocopy with toner specks and a copier-lid shadow. Bills the remaining 80 reams of "
                 "PO-2026-0005 (after sigma_inv_0932_scan.pdf), which completes the PO.",
        "font": "Helvetica", "brand": "#2E2E2E", "title_first": False,
        "vendor": {"name": "Sigma Office Solutions Pvt Ltd", "address": ["88 Residency Road", "Bengaluru, Karnataka 560025"],
                   "gstin": "29AAFCS2468L1ZS", "gstin_label": "GSTIN/UIN"},
        "meta": [("Tax Invoice No", "SOS-2026-0987"), ("Invoice Dt", "28-Oct-2026"), ("Buyer's Order No.", "PO-2026-0005")],
        "columns": [("No", "sn"), ("Item Code", "code"), ("Description of Goods", "desc"), ("HSN", "hsn"),
                    ("Qty", "qty"), ("Per", "uom"), ("Rate", "rate"), ("Amount", "amount")],
        "lines": [("SG-A4-75", "A4 Copier Paper 75 GSM (Ream)", "48025690", 80, "Ream", "260.00")],
        "tax": [("IGST @ {r}%", "18")], "table": "grid", "fmt_table": "indian", "fmt_totals": "indian",
        "subtotal_label": "Assessable Value", "total_label": "Amount Payable", "render": "photocopy",
    },
    {  # 12. No PO reference on the bill
        "file": "deccan_bill_1203.pdf", "label": "Deccan Packaging, bill 1203", "medium": "Digital PDF",
        "expect": "NEEDS_REVIEW",
        "about": "The bill quotes no PO number. InvoiceIQ proposes the vendor's open PO but will not pick it on its own.",
        "vendor": {"name": "Deccan Packaging Solutions",
                   "address": ["Plot 7, IDA Bollaram", "Sangareddy, Telangana 502325"],
                   "gstin": "36AAJFD4321P1Z6", "gstin_label": "GST Regn. No."},
        "columns": [("Sl", "sn"), ("Particulars", "desc"), ("HSN", "hsn"), ("Qty", "qty"),
                    ("Unit", "uom"), ("Rate", "rate"), ("Amount", "amount")],
        "tax": [("Add: CGST @ {r}%", "9"), ("Add: SGST @ {r}%", "9")], "table": "plain",
        "fmt_table": "indian", "fmt_totals": "rs_slash",
        "subtotal_label": "Taxable Amount", "total_label": "Net Amount Payable",
        "font": "Courier", "brand": "#5B3A1A", "title_first": False,
        "meta": [("Bill No.", "DPS/1203/26-27"), ("Bill Date", "27.10.2026")],
        "lines": [("", "Stretch Film Roll 23 mic 500 mm", "39201012", 120, "Rolls", "380.00")],
        "render": "pdf",
    },
    {  # 13. Vendor not in the vendor master
        "file": "orbit_inv_2231.pdf", "label": "Orbit Electricals, invoice 2231", "medium": "Digital PDF",
        "expect": "BLOCKED",
        "about": "A valid-looking GST invoice from a vendor that has never been onboarded. Unapproved vendors can't be paid.",
        "font": "Helvetica", "brand": "#7A3E9D", "title_first": False,
        "vendor": {"name": "Orbit Electricals", "address": ["14 SP Road", "Bengaluru, Karnataka 560002"],
                   "gstin": "29AAGFO7788K1ZA", "gstin_label": "GSTIN"},
        "meta": [("Invoice No.", "OE/2231"), ("Invoice Date", "30-Oct-2026"), ("PO Reference", "PO-2026-0001")],
        "columns": [("#", "sn"), ("Description", "desc"), ("Qty", "qty"), ("UOM", "uom"), ("Rate", "rate"),
                    ("Amount", "amount")],
        "lines": [("", "UPS 1 kVA Line Interactive", "", 6, "Nos", "7800.00")],
        "tax": [("IGST @ {r}%", "18")], "table": "grid", "fmt_table": "indian", "fmt_totals": "indian",
        "subtotal_label": "Sub Total", "total_label": "Total Amount", "render": "pdf",
    },
    {  # 14. Faded, low-contrast photocopy: read, but not trusted without a look
        "file": "deccan_bill_1219_faded_copy.jpg", "label": "Deccan Packaging, bill 1219", "medium": "Faded photocopy (JPG)",
        "expect": "NEEDS_REVIEW",
        "about": "A badly faded second-generation photocopy. The values can be read, but with low confidence, so a "
                 "person confirms them against the paper before approval.",
        "vendor": {"name": "Deccan Packaging Solutions",
                   "address": ["Plot 7, IDA Bollaram", "Sangareddy, Telangana 502325"],
                   "gstin": "36AAJFD4321P1Z6", "gstin_label": "GST Regn. No."},
        "columns": [("Sl", "sn"), ("Particulars", "desc"), ("HSN", "hsn"), ("Qty", "qty"),
                    ("Unit", "uom"), ("Rate", "rate"), ("Amount", "amount")],
        "tax": [("Add: CGST @ {r}%", "9"), ("Add: SGST @ {r}%", "9")], "table": "plain",
        "fmt_table": "indian", "fmt_totals": "rs_slash",
        "subtotal_label": "Taxable Amount", "total_label": "Net Amount Payable",
        "font": "Courier", "brand": "#5B3A1A", "title_first": False,
        "meta": [("Bill No.", "DPS/1219/26-27"), ("Bill Date", "31.10.2026"), ("Your Order No.", "PO-2026-0009")],
        "lines": [("", "Stretch Film Roll 23 mic 500 mm", "39201012", 60, "Rolls", "380.00")],
        "render": "faded",
    },
]


# --------------------------------------------------------------------------- builder
def _fonts(base: str) -> tuple[str, str]:
    return base, {"Helvetica": "Helvetica-Bold", "Times-Roman": "Times-Bold", "Courier": "Courier-Bold"}[base]


def build_pdf(spec: dict) -> tuple[bytes, dict]:
    reg, bold = _fonts(spec["font"])
    ink, muted, rule = colors.HexColor("#1B2733"), colors.HexColor("#4A5865"), colors.HexColor("#B9C4CC")
    brand = colors.HexColor(spec["brand"])
    s_n = ParagraphStyle("n", fontName=reg, fontSize=9, leading=12, textColor=ink)
    s_s = ParagraphStyle("s", parent=s_n, fontSize=8.5, leading=11, textColor=muted)
    s_v = ParagraphStyle("v", parent=s_n, fontName=bold, fontSize=14, leading=18, textColor=brand)
    s_t = ParagraphStyle("t", parent=s_n, fontName=bold, fontSize=15, leading=19)
    v = spec["vendor"]
    story = []

    vendor_block = ([Paragraph(v["name"], s_v)] + [Paragraph(a, s_s) for a in v["address"]]
                    + [Paragraph(f"{v['gstin_label']}: {v['gstin']}", s_s)])
    if spec["title_first"]:
        story += [Paragraph("TAX INVOICE", ParagraphStyle("tc", parent=s_t, alignment=1)), Spacer(1, 5 * mm)]
        story += vendor_block
    else:
        head = Table([[vendor_block, [Paragraph("TAX INVOICE", ParagraphStyle("tr", parent=s_t, alignment=2))]]],
                     colWidths=[115 * mm, 65 * mm])
        head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(head)
    story.append(Spacer(1, 6 * mm))

    bill_to = ([Paragraph("<b>Bill To</b>", s_n), Paragraph(BUYER["name"], s_n)]
               + [Paragraph(a, s_s) for a in BUYER["address"]] + [Paragraph(f"GSTIN: {BUYER['gstin']}", s_s)])
    meta = Table([[f"{k}:", val] for k, val in spec["meta"]], colWidths=[34 * mm, 48 * mm])
    meta.setStyle(TableStyle([("FONTNAME", (0, 0), (0, -1), bold), ("FONTNAME", (1, 0), (1, -1), reg),
                              ("FONTSIZE", (0, 0), (-1, -1), 9), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
                              ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
    block = Table([[bill_to, meta]], colWidths=[98 * mm, 82 * mm])
    block.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [block, Spacer(1, 6 * mm)]

    ft, ftot = FORMATS[spec["fmt_table"]], FORMATS[spec["fmt_totals"]]
    s_h = ParagraphStyle("h", fontName=bold, fontSize=8.5, leading=10, textColor=ink)
    s_hr = ParagraphStyle("hr", parent=s_h, alignment=2)
    rows = [[Paragraph(h, s_hr if k in ("qty", "rate", "amount") else s_h) for h, k in spec["columns"]]]
    subtotal = Decimal("0")
    for i, (code, desc, hsn, qty, uom, rate) in enumerate(spec["lines"], start=1):
        amt = money(Decimal(rate) * qty)
        subtotal += amt
        cell = {"sn": str(i), "code": code, "desc": desc, "hsn": hsn, "qty": f"{qty:,}", "uom": uom,
                "rate": ft(Decimal(rate)), "amount": ft(amt)}
        rows.append([cell[k] for _, k in spec["columns"]])
    widths = {"sn": 11, "code": 26, "desc": 62, "hsn": 16, "qty": 18, "uom": 12, "rate": 21, "amount": 25}
    total_w = sum(widths[k] for _, k in spec["columns"])
    col_w = [widths[k] * 180 / total_w * mm for _, k in spec["columns"]]
    items = Table(rows, colWidths=col_w, repeatRows=1)
    num_cols = [i for i, (_, k) in enumerate(spec["columns"]) if k in ("qty", "rate", "amount")]
    style = [("FONTNAME", (0, 0), (-1, 0), bold), ("FONTNAME", (0, 1), (-1, -1), reg),
             ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("TEXTCOLOR", (0, 0), (-1, -1), ink),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    style += [("ALIGN", (c, 0), (c, -1), "RIGHT") for c in num_cols]
    if spec["table"] == "grid":
        style += [("GRID", (0, 0), (-1, -1), 0.5, rule), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2F5"))]
    else:
        style += [("LINEBELOW", (0, 0), (-1, 0), 0.8, ink)]
    items.setStyle(TableStyle(style))
    story += [items, Spacer(1, 4 * mm)]

    tax_rows, tax_total = [], Decimal("0")
    for label, rate in spec["tax"]:
        t = money(subtotal * Decimal(rate) / 100)
        tax_total += t
        tax_rows.append([label.format(r=rate), ftot(t)])
    total = subtotal + tax_total
    totals = Table([[spec["subtotal_label"], ftot(subtotal)], *tax_rows, [spec["total_label"], ftot(total)]],
                   colWidths=[52 * mm, 40 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), reg), ("FONTSIZE", (0, 0), (-1, -1), 9),
                                ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("FONTNAME", (0, -1), (-1, -1), bold),
                                ("LINEABOVE", (0, -1), (-1, -1), 0.8, ink), ("TEXTCOLOR", (0, 0), (-1, -1), ink)]))
    story += [totals, Spacer(1, 10 * mm),
              Paragraph("Synthetic invoice generated for the InvoiceIQ prototype. Not a real transaction.", s_s)]

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm,
                      bottomMargin=15 * mm, title=spec["file"]).build(story)
    return buf.getvalue(), {"subtotal": subtotal, "tax": tax_total, "total": total}


def _as_scan(pdf_bytes: bytes, dpi: int, angle: float, seed: int, blur: float):
    """Rasterize like a scanner/phone: grayscale, slight skew, light noise."""
    import pypdfium2 as pdfium
    from PIL import Image, ImageFilter

    img = pdfium.PdfDocument(pdf_bytes)[0].render(scale=dpi / 72).to_pil().convert("L")
    img = img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=255)
    rnd = random.Random(seed)
    px = img.load()
    w, h = img.size
    for _ in range(w * h // 400):  # sparse speckle
        x, y = rnd.randrange(w), rnd.randrange(h)
        px[x, y] = max(0, px[x, y] - rnd.randrange(40, 110))
    return img.filter(ImageFilter.GaussianBlur(blur))


def _photocopy(pdf_bytes: bytes, seed: int, faded: bool = False):
    """Simulate an office photocopy that was then scanned: grey paper, lifted blacks, toner specks,
    a copier-lid shadow down one edge, skew and softness. 'faded' is a worn second-generation copy."""
    import pypdfium2 as pdfium
    from PIL import Image, ImageDraw, ImageFilter

    dpi = 170 if faded else 220
    img = pdfium.PdfDocument(pdf_bytes)[0].render(scale=dpi / 72).to_pil().convert("L")
    lo, hi = (115, 232) if faded else (35, 238)            # black lifted, white greyed
    img = img.point(lambda v: int(lo + (hi - lo) * v / 255))
    rnd = random.Random(seed)
    w, h = img.size
    px = img.load()
    for _ in range(w * h // (90 if faded else 160)):        # toner specks
        x, y = rnd.randrange(w), rnd.randrange(h)
        px[x, y] = max(0, px[x, y] - rnd.randrange(50, 140))
    draw = ImageDraw.Draw(img)
    band = int(w * 0.035)                                   # copier-lid shadow on the left edge
    for i in range(band):
        shade = int(90 + 120 * i / band)
        draw.line([(i, 0), (i, h)], fill=shade)
    img = img.rotate(-2.0 if faded else 1.3, resample=Image.BICUBIC, expand=False, fillcolor=hi)
    return img.filter(ImageFilter.GaussianBlur(0.75 if faded else 0.5))


def write(spec: dict) -> dict:
    pdf_bytes, totals = build_pdf(spec)
    out = OUT / spec["file"]
    if spec["render"] == "pdf":
        out.write_bytes(pdf_bytes)
    elif spec["render"] == "scan_pdf":
        _as_scan(pdf_bytes, 300, 0.4, 4, 0.25).save(out, "PDF", resolution=300)
    elif spec["render"] == "photocopy":
        _photocopy(pdf_bytes, len(spec["file"])).save(out, "PDF", resolution=220)
    elif spec["render"] == "faded":
        _photocopy(pdf_bytes, len(spec["file"]), faded=True).convert("RGB").save(out, "JPEG", quality=70)
    elif spec["render"] == "jpg":
        img = _as_scan(pdf_bytes, 260, -0.6, 6, 0.35)
        img.convert("RGB").save(out, "JPEG", quality=82)
    return totals


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for old in [*OUT.glob("*.pdf"), *OUT.glob("*.jpg"), *OUT.glob("*.png")]:
        old.unlink()
    for spec in SPECS:
        t = write(spec)
        print(f"{spec['file']:40} expect {spec['expect']:19} subtotal {t['subtotal']:>10} total {t['total']:>10}")
