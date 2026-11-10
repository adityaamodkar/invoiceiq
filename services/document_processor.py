"""
Document validation and text-extraction routing.

Decides between three paths:
  * digital PDF  -> pdfplumber text and tables
  * scanned PDF  -> render pages, then OCR
  * image upload -> OCR directly
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from config import settings
from services import ocr_service, pdf_extractor
from services.errors import DocumentError
from services.models import DocumentText

__all__ = ["DocumentError", "DocumentInfo", "validate_document", "extract_text"]


@dataclass
class DocumentInfo:
    file_name: str
    extension: str
    file_type: str          # "PDF" / "PNG image" / "JPEG image"
    size_bytes: int
    sha256: str
    page_count: int
    kind: str               # pdf / image


_MAGIC = {
    ".pdf": (b"%PDF",),
    ".png": (b"\x89PNG",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}


def validate_document(file_name: str, data: bytes) -> DocumentInfo:
    ext = Path(file_name).suffix.lower()
    if ext not in settings.SUPPORTED_EXTENSIONS:
        raise DocumentError(
            f"'{ext or 'no extension'}' files are not supported. Upload a PDF, PNG, JPG or JPEG.")
    if not data:
        raise DocumentError("The file is empty.")
    size_mb = len(data) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_MB:
        raise DocumentError(f"The file is {size_mb:.1f} MB; the limit is {settings.MAX_UPLOAD_MB} MB.")
    if not data.startswith(_MAGIC[ext]):
        raise DocumentError(
            f"The file is named {ext} but its contents are not a valid {ext[1:].upper()} file.")

    sha = hashlib.sha256(data).hexdigest()
    if ext == ".pdf":
        pages = pdf_extractor.page_count(data)  # raises DocumentError on corrupt/encrypted PDFs
        return DocumentInfo(file_name, ext, "PDF", len(data), sha, pages, "pdf")

    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            im.verify()
    except Exception as exc:  # noqa: BLE001
        raise DocumentError(f"The image could not be opened ({exc.__class__.__name__}).") from exc
    label = "PNG image" if ext == ".png" else "JPEG image"
    return DocumentInfo(file_name, ext, label, len(data), sha, 1, "image")


def extract_text(info: DocumentInfo, data: bytes) -> DocumentText:
    """Pick the extraction path. Raises DocumentError if no usable text is found."""
    if info.kind == "pdf":
        doc = pdf_extractor.extract(data)
        if doc.char_count >= settings.MIN_TEXT_CHARS_PER_PAGE * doc.page_count:
            return doc
        # Too little machine-readable text: treat as a scanned PDF
        if not ocr_service.is_available():
            raise DocumentError(
                "This PDF appears to be scanned (no machine-readable text) and OCR is not "
                "available on this machine. Install Tesseract to process scanned invoices.")
        return ocr_service.ocr_pdf(data)

    if not ocr_service.is_available():
        raise DocumentError("Image uploads need OCR, but Tesseract is not installed on this machine.")
    return ocr_service.ocr_image(data)
