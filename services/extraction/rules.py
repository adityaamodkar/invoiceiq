"""
Rule-based (deterministic) invoice extraction.

Vendors describe the same thing in different words and formats. This module
handles that variation with explicit, testable rules:

  * Labels: every field has a synonym list, searched in priority order
    ("Invoice No" / "Bill No" / "Tax Invoice No" / "Document No" ...).
    A value must also match the field's type (identifier, date, amount).
  * Amounts: 1,20,000.00 / 120,000.00 / INR 120,000 / Rs. 1,20,000.00/- / ₹1,20,000.
  * Dates: 14-Oct-2026, 14/10/2026, 14.10.2026, 2026-10-14, Oct 14, 2026 (day first).
  * Quantities and units: "1,200", "1,200 Pcs", Nos / EA / Pcs / Rolls / Ream / Box ...
  * GSTINs are found by their pattern (and checksum), whatever the label:
    "GSTIN", "GSTIN No.", "GST Regn. No.", "GSTIN/UIN", "Registration No." ...
  * Tax lines: "IGST @ 18%", "IGST (18%)", "Add: CGST @ 9%", "SGST 9%".
  * Line items: ruled tables (header row mapped by synonyms), else text rows.

Confidence is a stated heuristic, not a probability:
  label-anchored value .................................. 0.98
  table row ............................................. 0.97
  text row whose qty x rate = amount (self-consistent) .. 0.95, otherwise 0.75
    (OCR: a self-consistent row uses its second-weakest number, because one misread
     value alone cannot keep qty x rate = amount true)
  vendor name from page position ........................ 0.85
For OCR text, each value's confidence is multiplied by Tesseract's own
confidence for the words that make up that value (measured, not assumed).
"""
from __future__ import annotations

import re
from decimal import Decimal

from config import settings
from services.extraction.base import ExtractionProvider
from services.models import DocumentText, ExtractedField, ExtractedLineItem, InvoiceDraft
from services.normalizers import (
    money, normalize_gstin, normalize_text, parse_amount, parse_date, parse_percent, parse_quantity,
    validate_gstin,
)

CONF_LABEL = Decimal("0.98")
CONF_TABLE = Decimal("0.97")
CONF_ROW_CONSISTENT = Decimal("0.95")
CONF_ROW_INCONSISTENT = Decimal("0.75")
CONF_POSITION = Decimal("0.85")
CONF_INFERRED = Decimal("0.90")

# --- value patterns ----------------------------------------------------------
ID_PAT = r"([A-Za-z0-9][A-Za-z0-9/\-_.]*\d[A-Za-z0-9/\-_.]*)"
DATE_PAT = (r"(\d{1,2}[-/. ][A-Za-z]{3,9}[-/. ,]+\d{4}|[A-Za-z]{3,9} \d{1,2},? \d{4}"
            r"|\d{4}-\d{2}-\d{2}|\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4})")
CUR = r"(?:INR|Rs\.?|₹)"
NUM = r"(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d{1,2})?"
AMT_PAT = rf"({CUR}?\s*\(?{NUM}\)?(?:\s*/-)?)"

# --- label synonyms (priority order: most specific first) ---------------------
LABELS: dict[str, tuple[list[str], str]] = {
    "invoice_number": (["Tax Invoice No", "Tax Invoice Number", "Invoice Number", "Invoice No",
                        "Invoice #", "Inv. No", "Inv No", "Bill Number", "Bill No", "Document No",
                        "Invoice Ref"], ID_PAT),
    "invoice_date": (["Invoice Date", "Date of Invoice", "Invoice Dt", "Inv. Date", "Inv Date",
                      "Bill Date", "Document Date", "Dated", "Date"], DATE_PAT),
    "due_date": (["Payment Due Date", "Due Date", "Payment Due", "Due On"], DATE_PAT),
    "po_number": (["Purchase Order Number", "Purchase Order No", "Buyer's Order No", "Buyer's Order Number",
                   "Customer PO No", "Your Order No", "PO Reference", "PO Number", "PO No", "P.O. No",
                   "PO Ref", "Order Reference", "Order Ref", "Purchase Order"], ID_PAT),
    "subtotal": (["Total Taxable Value", "Taxable Value", "Taxable Amount", "Assessable Value",
                  "Sub Total", "Sub-Total", "Subtotal", "Amount Before Tax", "Total Before Tax",
                  "Basic Amount"], AMT_PAT),
    "discount": (["Less: Discount", "Trade Discount", "Discount"], AMT_PAT),
    "other_charges": (["Freight Charges", "Freight", "Shipping Charges", "Shipping", "Delivery Charges",
                       "Packing Charges", "Packing & Forwarding"], AMT_PAT),
    "total_amount": (["Grand Total", "Total Invoice Value", "Invoice Total", "Invoice Value",
                      "Total Amount Payable", "Net Amount Payable", "Amount Payable", "Total Amount",
                      "Net Payable", "Total Payable", "Amount Due", "Balance Due"], AMT_PAT),
}
# Bare "Date" must not pick up "Due Date", "PO Date", "Order Date" ...
_DATE_GUARD = "".join(f"(?<!{w} )" for w in ("Due", "PO", "Order", "Delivery", "Dispatch", "Challan", "Bill", "Invoice"))

TAX_LINE_RE = re.compile(
    r"\b(IGST|CGST|SGST|UTGST|GST|VAT)\b\s*(?:@|at)?\s*\(?\s*(\d+(?:\.\d+)?)\s*%\s*\)?[^\d\n]*?"
    + rf"({CUR}?\s*{NUM}(?:\s*/-)?)\s*$",
    re.IGNORECASE,
)
GSTIN_RE = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b")
TOTAL_TAX_RE = re.compile(rf"\bTotal\s+(?:Tax|GST)(?:\s+Amount)?\b[^\d\n]*?({CUR}?\s*{NUM})", re.I)

# --- line-item table header synonyms (after normalization) --------------------
COLUMN_SYNONYMS = {
    "item_code": ["item code", "code", "sku", "part no", "part number", "product code", "article no"],
    "description": ["description", "item description", "description of goods", "particulars", "item",
                    "product", "service", "goods", "item name"],
    "hsn": ["hsn", "hsn sac", "sac", "hsn code"],
    "quantity": ["qty", "quantity", "units", "no of units"],
    "uom": ["uom", "unit", "per", "unit of measure"],
    "unit_price": ["unit price", "rate", "price", "unit rate", "rate per unit", "unit cost"],
    "amount": ["amount", "line total", "total", "value", "taxable value", "net amount"],
    "tax_rate": ["tax", "gst", "gst rate", "tax rate"],
}
_HEADER_NOISE = re.compile(r"\((?:inr|rs\.?|₹)\)|\b(?:inr|rs)\b\.?|₹|\bin\b", re.I)

_ROW_CUR = r"(?:(?:Rs\.?|INR|₹)\s*)?"
TEXT_ROW_RE = re.compile(
    r"^(?:\d{1,3}[.)]?\s+)?(?:(?P<code>[A-Z0-9]+(?:-[A-Z0-9]+)+)\s+)?(?P<desc>.+?)\s+"
    r"(?:(?P<hsn>\d{4,8})\s+)?(?P<qty>\d{1,3}(?:,\d{2,3})+|\d+(?:\.\d+)?)\s+"
    r"(?:(?P<uom>[A-Za-z]{2,6})\.?\s+)?"
    rf"{_ROW_CUR}(?P<rate>[\d,]+\.\d{{2}})\s+{_ROW_CUR}(?P<amt>[\d,]+\.\d{{2}})(?:\s*/-)?$"
)
_TITLE_WORDS = re.compile(r"(?i)\b(tax\s+invoice|invoice|original\s+for\s+recipient|duplicate|bill\s+of\s+supply)\b")


def _label_regex(label: str, value_pat: str) -> re.Pattern:
    lab = re.escape(label).replace(r"\ ", r"\s*").replace("'", r"\s*['’‘`]?\s*")
    guard = _DATE_GUARD if label == "Date" else ""
    return re.compile(
        rf"{guard}(?<![A-Za-z]){lab}\.?(?![A-Za-z])\s*(?:\((?:INR|Rs\.?|₹)\))?\s*[:#\-]?\s*{value_pat}",
        re.IGNORECASE)


_COMPILED = {k: [(lab, _label_regex(lab, pat)) for lab in labs] for k, (labs, pat) in LABELS.items()}


class RuleBasedProvider(ExtractionProvider):
    name = "rules"

    def is_available(self) -> tuple[bool, str]:
        return True, "Rule-based extraction (no external service)"

    # ------------------------------------------------------------------
    def extract(self, doc: DocumentText) -> InvoiceDraft:
        self.doc = doc
        self.is_ocr = doc.method.startswith("ocr")
        self.method = "ocr+rules" if self.is_ocr else "text+rules"
        draft = InvoiceDraft(extraction_method=doc.method, provider=self.name)

        for name, patterns in _COMPILED.items():
            draft.header[name] = self._find_labeled(name, patterns)
        self._extract_parties(draft)
        self._extract_tax(draft)
        self._extract_currency(draft)
        draft.line_items = self._lines_from_tables() or self._lines_from_text()

        if not draft.line_items:
            draft.warnings.append("No line items could be identified on the invoice.")
        if self.is_ocr and doc.ocr_confidence is not None:
            draft.warnings.append(f"Text was read by OCR (mean word confidence {doc.ocr_confidence:.0%}).")
        return draft

    # ------------------------------------------------------------------ confidence
    def _measured(self, page_no: int | None, raw: str | None) -> Decimal:
        """OCR: Tesseract's lowest word confidence among the words forming this value."""
        if not self.is_ocr or not raw:
            return Decimal("1")
        words = self.doc.words[(page_no or 1) - 1] if self.doc.words else []
        confs = []
        for tok in (t.strip(".,:;()") for t in raw.split()):
            if not tok:
                continue
            hit = (next((w for w in words if w["text"].strip(".,:;()") == tok), None)
                   or next((w for w in words if tok in w["text"]), None))
            if hit is not None and hit.get("conf") is not None:
                confs.append(Decimal(str(hit["conf"])) / 100)
        if confs:
            return min(confs)
        return self.doc.ocr_confidence or Decimal("0.80")

    def _field(self, value, raw, base: Decimal, page: int | None, how: str, warning=None) -> ExtractedField:
        conf = (base * self._measured(page, raw)).quantize(Decimal("0.001"))
        return ExtractedField(value, raw, conf, page, f"{self.method}:{how}", warning, self._locate(page, raw))

    # ------------------------------------------------------------------ position on the page
    def _box(self, page_no: int, words: list[dict]):
        if not words or not self.doc.page_sizes:
            return None
        w, h = self.doc.page_sizes[page_no - 1]
        pad_x, pad_y = w * 0.004, h * 0.002
        return (round(max(0, min(x["x0"] for x in words) - pad_x) / w, 4),
                round(max(0, min(x["top"] for x in words) - pad_y) / h, 4),
                round(min(w, max(x["x1"] for x in words) + pad_x) / w, 4),
                round(min(h, max(x.get("bottom", x["top"] + 10) for x in words) + pad_y) / h, 4))

    def _locate(self, page_no: int | None, raw: str | None):
        """Where a value sits on the page, so reviewers can see it highlighted (None if not found)."""
        if not page_no or not raw or not self.doc.words or page_no > len(self.doc.words):
            return None
        words = self.doc.words[page_no - 1]
        tol = self._line_tol(page_no)
        tokens = [t for t in raw.split() if t.strip(".,:;()")]
        if not tokens:
            return None
        clean = lambda t: t.strip(".,:;()|")  # noqa: E731
        partial = None
        for i, w in enumerate(words):
            if clean(w["text"]) != clean(tokens[0]):
                continue
            found, j = [w], i + 1
            for tok in tokens[1:]:
                while j < len(words) and abs(words[j]["top"] - w["top"]) < tol and clean(words[j]["text"]) != clean(tok):
                    j += 1
                if j < len(words) and abs(words[j]["top"] - w["top"]) < tol:
                    found.append(words[j]); j += 1
            if len(found) == len(tokens):
                return self._box(page_no, found)
            if partial is None and len(tokens) > 2 and len(found) * 2 >= len(tokens):
                partial = found
        if partial:
            return self._box(page_no, partial)
        # fall back to the most distinctive token (the one with the most digits)
        anchor = max(tokens, key=lambda t: (sum(ch.isdigit() for ch in t), len(t)))
        hit = next((w for w in words if clean(w["text"]) == clean(anchor)), None)
        return self._box(page_no, [hit]) if hit else None

    def _row_box(self, page_no: int, amount_raw: str | None):
        """Box around the whole table row that contains this line amount."""
        if not amount_raw or not self.doc.words:
            return None
        words = self.doc.words[page_no - 1]
        hit = next((w for w in words if w["text"].strip("|") == amount_raw.strip()), None)
        if not hit:
            return None
        tol = self._line_tol(page_no)
        return self._box(page_no, [w for w in words if abs(w["top"] - hit["top"]) < tol])

    def _line_tol(self, page_no: int) -> float:
        """Words within ~0.45% of the page height of each other are on the same line."""
        return self.doc.page_sizes[page_no - 1][1] * 0.0045 if self.doc.page_sizes else 4

    # ------------------------------------------------------------------ header fields
    def _find_labeled(self, name, patterns) -> ExtractedField:
        for label, rx in patterns:  # label priority first, then position on the page
            for page_no, text in enumerate(self.doc.pages, start=1):
                for line in text.splitlines():
                    m = rx.search(line)
                    if not m:
                        continue
                    raw = m.group(1).strip()
                    value = self._parse(name, raw)
                    if value is None:
                        continue
                    return self._field(value, raw, CONF_LABEL, page_no, f"label '{label}'")
        return ExtractedField(warning="Not found on the document")

    @staticmethod
    def _parse(name: str, raw: str):
        if name in ("invoice_date", "due_date"):
            return parse_date(raw)
        if name in ("subtotal", "discount", "other_charges", "total_amount"):
            return parse_amount(raw)
        return raw.rstrip(".")

    # ------------------------------------------------------------------ parties
    def _extract_parties(self, draft: InvoiceDraft) -> None:
        """Vendor GSTIN = the GSTIN on the page that is not the buyer's own, whatever its label."""
        doc = self.doc
        gstins: list[tuple[str, int]] = []
        for page_no, page in enumerate(doc.pages, start=1):
            for g in GSTIN_RE.findall(page.upper()):
                if g not in [x[0] for x in gstins]:
                    gstins.append((g, page_no))
        buyer = [g for g in gstins if g[0] == settings.BUYER.gstin]
        others = [g for g in gstins if g[0] != settings.BUYER.gstin]
        draft.header["buyer_gstin"] = (self._field(buyer[0][0], buyer[0][0], CONF_LABEL, buyer[0][1], "gstin")
                                       if buyer else ExtractedField(warning="Buyer GSTIN not found"))
        if len(others) == 1:
            g, pg = others[0]
            ok, _ = validate_gstin(normalize_gstin(g))
            draft.header["vendor_gstin"] = self._field(
                g, g, CONF_LABEL, pg, "gstin", None if ok else "GSTIN fails format/checksum validation")
        elif len(others) > 1:
            draft.header["vendor_gstin"] = ExtractedField(
                warning=f"Multiple non-buyer GSTINs found: {', '.join(o[0] for o in others)}")
            draft.warnings.append("More than one possible vendor GSTIN on the document.")
        else:
            draft.header["vendor_gstin"] = ExtractedField(warning="Vendor GSTIN not found")

        # Vendor name: explicit label first, then the first meaningful line of page 1
        text = "\n".join(doc.pages)
        name_field = ExtractedField(warning="Vendor name not found")
        m = re.search(r"(?im)^\s*(?:Vendor|Supplier|Seller|Sold\s+By|From)\s*[:\-]\s*(.+)$", text)
        if m:
            raw = m.group(1).strip()
            name_field = self._field(raw, raw, CONF_LABEL, 1, "label")
        else:
            for line in [l.strip() for l in doc.pages[0].splitlines() if l.strip()][:4]:
                cleaned = _TITLE_WORDS.sub("", line).strip(" -|:,;.")
                if cleaned and not re.search(r"\d{4,}|GSTIN|@", cleaned, re.I):
                    name_field = self._field(cleaned, cleaned, CONF_POSITION, 1, "top-of-page")
                    break
        draft.header["vendor_name"] = name_field

        addr = ExtractedField(warning="Vendor address not found")
        if name_field.present:
            lines = [l.strip() for l in doc.pages[0].splitlines() if l.strip()]
            try:
                start = next(i for i, l in enumerate(lines) if name_field.raw and name_field.raw in l)
                end = next(i for i, l in enumerate(lines) if i > start and GSTIN_RE.search(l.upper()))
                block = [l for l in lines[start + 1:end] if l]
                if 0 < len(block) <= 4:
                    addr = self._field(", ".join(block), "\n".join(block), Decimal("0.80"), 1, "block")
            except StopIteration:
                pass
        draft.header["vendor_address"] = addr

    # ------------------------------------------------------------------ tax / currency
    def _extract_tax(self, draft: InvoiceDraft) -> None:
        for page_no, page in enumerate(self.doc.pages, start=1):
            for line in page.splitlines():
                m = TAX_LINE_RE.search(line.strip())
                if m and (amount := parse_amount(m.group(3))) is not None:
                    draft.tax_lines.append({"type": m.group(1).upper(), "rate": Decimal(m.group(2)),
                                            "amount": amount, "page": page_no, "raw": m.group(3)})
        if draft.tax_lines:
            total = sum((t["amount"] for t in draft.tax_lines), Decimal("0"))
            raw = "; ".join(f"{t['type']} @{t['rate']}% = {t['amount']}" for t in draft.tax_lines)
            conf = min(CONF_LABEL * self._measured(t["page"], t["raw"]) for t in draft.tax_lines)
            boxes = [b for t in draft.tax_lines if (b := self._locate(t["page"], t["raw"]))]
            bbox = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes),
                    max(b[3] for b in boxes)) if boxes else None
            draft.header["tax_amount"] = ExtractedField(total, raw, conf.quantize(Decimal("0.001")),
                                                        draft.tax_lines[0]["page"], f"{self.method}:tax-lines",
                                                        None, bbox)
            return
        m = TOTAL_TAX_RE.search("\n".join(self.doc.pages))
        if m and parse_amount(m.group(1)) is not None:
            draft.header["tax_amount"] = self._field(parse_amount(m.group(1)), m.group(1), CONF_LABEL, 1, "label")
        else:
            draft.header["tax_amount"] = ExtractedField(warning="Tax amount not found")

    def _extract_currency(self, draft: InvoiceDraft) -> None:
        text = "\n".join(self.doc.pages)
        found = []
        if re.search(r"\bINR\b|₹|\bRs\.?\s*\d|\(Rs\.?\)|\bRupees\b", text, re.I):
            found.append("INR")
        if re.search(r"\bUSD\b|US\$|\$\s*\d", text):
            found.append("USD")
        if len(found) == 1:
            draft.header["currency"] = ExtractedField(found[0], found[0], CONF_LABEL, 1,
                                                      f"{self.method}:currency-marker")
        elif len(found) > 1:
            draft.header["currency"] = ExtractedField(warning="Multiple currencies mentioned")
        elif draft.header["vendor_gstin"].present and draft.header["buyer_gstin"].present:
            # A tax invoice between two GST-registered Indian parties is denominated in INR.
            draft.header["currency"] = ExtractedField(
                "INR", "(not printed)", CONF_INFERRED, None, f"{self.method}:inferred from GST registrations",
                "Currency not printed; inferred as INR because both parties are GST-registered in India")
        else:
            draft.header["currency"] = ExtractedField(warning="Currency not stated on invoice")

    # ------------------------------------------------------------------ line items
    @staticmethod
    def _norm_header(cell: str | None) -> str:
        return normalize_text(_HEADER_NOISE.sub(" ", cell or ""))

    def _map_header(self, row: list[str | None]) -> dict[str, int]:
        mapping: dict[str, int] = {}
        for idx, cell in enumerate(row):
            # Headers are often wrapped mid-word ("Quanti\nty", "UO\nM"): try both readings.
            readings = {self._norm_header(cell), self._norm_header((cell or "").replace("\n", ""))}
            for key, syns in COLUMN_SYNONYMS.items():
                if key not in mapping and readings & set(syns):
                    mapping[key] = idx
                    break
        return mapping

    def _lines_from_tables(self) -> list[ExtractedLineItem]:
        out: list[ExtractedLineItem] = []
        for page_no, tables in enumerate(self.doc.tables, start=1):
            for table in tables:
                if not table:
                    continue
                cols = self._map_header(table[0])
                if not {"quantity", "amount", "description"} <= cols.keys():
                    continue
                for row in table[1:]:
                    def get(k, row=row):
                        return row[cols[k]] if k in cols and cols[k] < len(row) else None
                    qty, amt = parse_quantity(get("quantity")), parse_amount(get("amount"))
                    if qty is None or amt is None:
                        continue
                    uom = (get("uom") or "").strip() or None
                    if uom is None and get("quantity"):  # "1,200 Pcs" in one cell
                        m = re.search(r"[A-Za-z]+", get("quantity"))
                        uom = m.group(0) if m else None
                    out.append(ExtractedLineItem(
                        line_no=len(out) + 1, description=" ".join((get("description") or "").split()) or None,
                        item_code=(get("item_code") or "").strip() or None, quantity=qty, uom=uom,
                        unit_price=parse_amount(get("unit_price")), amount=amt,
                        tax_rate=parse_percent(get("tax_rate")) if get("tax_rate") else None,
                        raw=" | ".join(c or "" for c in row), confidence=CONF_TABLE, source_page=page_no,
                        bbox=self._row_box(page_no, get("amount"))))
        return out

    def _lines_from_text(self) -> list[ExtractedLineItem]:
        out: list[ExtractedLineItem] = []
        for page_no, page in enumerate(self.doc.pages, start=1):
            for line in page.splitlines():
                line = re.sub(r"\s*[|¦]\s*", " ", line).strip()  # OCR'd table borders
                line = re.sub(r"^[^\w(]+", "", line).strip()         # specks read as leading punctuation
                line = re.sub(r"[_~`]+", " ", line).strip()             # scan noise; invoices don't use these
                if re.match(r"(?i)^(sub\s*-?\s*total|grand|total|add|less|igst|cgst|sgst|gst|taxable|net)\b", line):
                    continue
                m = TEXT_ROW_RE.match(line)
                if not m:
                    continue
                qty = parse_quantity(m.group("qty"))
                rate, amt = parse_amount(m.group("rate")), parse_amount(m.group("amt"))
                consistent = None not in (qty, rate, amt) and abs(money(qty * rate) - amt) <= Decimal("1")
                base = CONF_ROW_CONSISTENT if consistent else CONF_ROW_INCONSISTENT
                confs = sorted(self._measured(page_no, m.group(g)) for g in ("qty", "rate", "amt"))
                # In a self-consistent row a single misread value would break qty x rate = amount,
                # so the row is as reliable as its two best-read numbers. Otherwise use the weakest.
                measured = confs[1] if consistent else confs[0]
                out.append(ExtractedLineItem(
                    line_no=len(out) + 1, description=m.group("desc").strip(), item_code=m.group("code"),
                    quantity=qty, uom=m.group("uom"), unit_price=rate, amount=amt, raw=line,
                    confidence=(base * measured).quantize(Decimal("0.001")), source_page=page_no,
                    bbox=self._row_box(page_no, m.group("amt"))))
        return out
