"""
OCR for scanned PDFs and images (Tesseract via pytesseract).

Tesseract is a system binary. Locally: brew/apt/Windows installer.
On Streamlit Community Cloud it is installed from packages.txt.
If it is missing, is_available() returns False and the UI says so.
"""
from __future__ import annotations

import io
from decimal import Decimal
from functools import lru_cache

from services.models import DocumentText

OCR_DPI = 300


def _configure() -> None:
    """Allow an explicit Tesseract path (common on Windows, where it is often not on PATH)."""
    import os

    import pytesseract

    cmd = os.getenv("INVOICEIQ_TESSERACT_CMD")
    if not cmd and os.name == "nt":
        default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        cmd = default if os.path.exists(default) else None
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


@lru_cache(maxsize=1)
def is_available() -> bool:
    try:
        import pytesseract

        _configure()
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Image clean-up for scans and photocopies
# ---------------------------------------------------------------------------
def _trim_dark_edges(img):
    """Cut copier-lid shadows and scanner borders: edge columns/rows much darker than the page."""
    import numpy as np

    a = np.asarray(img, dtype=np.float32)
    page = float(np.median(a))
    cols, rows = a.mean(axis=0), a.mean(axis=1)
    limit = page * 0.8
    left = next((i for i, v in enumerate(cols) if v > limit), 0)
    right = len(cols) - next((i for i, v in enumerate(cols[::-1]) if v > limit), 0)
    top = next((i for i, v in enumerate(rows) if v > limit), 0)
    bottom = len(rows) - next((i for i, v in enumerate(rows[::-1]) if v > limit), 0)
    if right - left < img.width * 0.6 or bottom - top < img.height * 0.6:
        return img
    return img.crop((left, top, right, bottom))


def _deskew(img):
    """Straighten text lines: the rotation that makes the row-darkness profile sharpest."""
    import numpy as np
    from PIL import Image

    small = img.copy()
    small.thumbnail((900, 900))
    ink = (np.asarray(small) < 140).astype(np.uint8) * 255
    probe = Image.fromarray(ink)
    best, best_score = 0.0, -1.0
    for angle in [x / 4 for x in range(-16, 17)]:          # -4 to +4 degrees in 0.25 steps
        rows = np.asarray(probe.rotate(angle, resample=Image.NEAREST, fillcolor=0)).sum(axis=1).astype(np.float64)
        score = float(np.square(np.diff(rows)).sum())
        if score > best_score:
            best, best_score = angle, score
    if abs(best) < 0.25:
        return img, 0.0
    return img.rotate(best, resample=Image.BICUBIC, expand=False, fillcolor=255), best


def prepare(image):
    """Grayscale, trim dark edges, stretch contrast, straighten, remove specks."""
    from PIL import ImageFilter, ImageOps

    gray = image.convert("L")
    gray = _trim_dark_edges(gray)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray, _ = _deskew(gray)
    return gray.filter(ImageFilter.MedianFilter(3))


def _binarize(gray):
    """Otsu threshold: high-contrast black-and-white variant for faint or grey copies."""
    import numpy as np
    from PIL import Image

    a = np.asarray(gray)
    hist = np.bincount(a.ravel(), minlength=256).astype(np.float64)
    total, sum_all = a.size, float(np.dot(np.arange(256), hist))
    w_b = sum_b = 0.0
    best_t, best_var = 128, -1.0
    for t in range(256):
        w_b += hist[t]
        if w_b == 0 or w_b == total:
            continue
        sum_b += t * hist[t]
        m_b, m_f = sum_b / w_b, (sum_all - sum_b) / (total - w_b)
        var = w_b * (total - w_b) * (m_b - m_f) ** 2
        if var > best_var:
            best_t, best_var = t, var
    return Image.fromarray(((a > best_t) * 255).astype("uint8"))


def _ocr_best(image):
    """OCR the cleaned image; for weak reads also try a black-and-white version and keep the better."""
    prepared = prepare(image)
    first = _ocr_pil(prepared)
    if first[2] is not None and first[2] >= Decimal("0.88"):
        return first
    second = _ocr_pil(_binarize(prepared))
    return second if (second[2] or 0) > (first[2] or 0) else first


def _ocr_pil(image) -> tuple[str, list[dict], Decimal | None]:
    import pytesseract

    gray = image.convert("L")
    text = pytesseract.image_to_string(gray, config="--psm 4")
    data = pytesseract.image_to_data(gray, config="--psm 4", output_type=pytesseract.Output.DICT)
    words, confs = [], []
    for i, w in enumerate(data["text"]):
        if w.strip():
            c = float(data["conf"][i])
            words.append({"text": w, "x0": data["left"][i], "x1": data["left"][i] + data["width"][i],
                          "top": data["top"][i], "bottom": data["top"][i] + data["height"][i],
                          "conf": c if c >= 0 else None})
            if c >= 0:
                confs.append(c)
    mean = Decimal(str(round(sum(confs) / len(confs) / 100, 3))) if confs else None
    return text, words, mean, gray.size


def _combine(results: list[tuple], method: str) -> DocumentText:
    confs = [r[2] for r in results if r[2] is not None]
    pages = [r[0] for r in results]
    return DocumentText(
        pages=pages, words=[r[1] for r in results], method=method, page_count=len(pages),
        char_count=sum(len(p.strip()) for p in pages),
        ocr_confidence=(sum(confs) / len(confs)).quantize(Decimal("0.001")) if confs else None,
        page_sizes=[(float(r[3][0]), float(r[3][1])) for r in results],
    )


def ocr_pdf(data: bytes) -> DocumentText:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    results = [_ocr_best(page.render(scale=OCR_DPI / 72).to_pil()) for page in pdf]
    return _combine(results, "ocr_pdf")


def ocr_image(data: bytes) -> DocumentText:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as im:
        im.load()
        return _combine([_ocr_best(im)], "ocr_image")
