"""Machine-readable PDF extraction with pdfplumber."""
from __future__ import annotations

import io

import pdfplumber

from services.errors import DocumentError
from services.models import DocumentText


def page_count(data: bytes) -> int:
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            n = len(pdf.pages)
    except Exception as exc:  # noqa: BLE001  (pdfminer raises many types)
        msg = str(exc).lower()
        if "password" in msg or "encrypt" in msg:
            raise DocumentError("The PDF is password-protected. Ask the vendor for an unlocked copy.") from exc
        raise DocumentError("The PDF is damaged or not a readable PDF file.") from exc
    if n == 0:
        raise DocumentError("The PDF has no pages.")
    return n


def extract(data: bytes) -> DocumentText:
    pages: list[str] = []
    words: list[list[dict]] = []
    tables: list[list[list[list[str | None]]]] = []
    sizes: list[tuple[float, float]] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
            sizes.append((float(page.width), float(page.height)))
            words.append([
                {"text": w["text"], "x0": w["x0"], "x1": w["x1"], "top": w["top"], "bottom": w["bottom"]}
                for w in page.extract_words()
            ])
            tables.append(page.extract_tables() or [])
    doc = DocumentText(
        pages=pages, words=words, method="digital_text", page_count=len(pages),
        char_count=sum(len(p.strip()) for p in pages), tables=tables, page_sizes=sizes,
    )
    return doc
