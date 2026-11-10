"""
Access to original documents for viewing.

Uploaded files are never written to disk: they are kept in this browser session's
memory only, so the reviewer can see the page while working on it. Test invoices can
always be shown because they ship with the app. Anything else shows a notice instead.
"""
from __future__ import annotations

import base64
import hashlib
import io

import streamlit as st

from config import settings


def remember(sha: str, data: bytes) -> None:
    st.session_state.setdefault("docs", {})[sha] = data


@st.cache_data(show_spinner=False)
def _sample_index() -> dict[str, str]:
    out = {}
    for p in settings.SAMPLE_DIR.glob("*"):
        if p.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg"):
            out[hashlib.sha256(p.read_bytes()).hexdigest()] = str(p)
    return out


def get(sha: str | None) -> bytes | None:
    if not sha:
        return None
    if data := st.session_state.get("docs", {}).get(sha):
        return data
    if path := _sample_index().get(sha):
        with open(path, "rb") as fh:
            return fh.read()
    return None


@st.cache_data(show_spinner=False, max_entries=32)
def page_image_b64(sha: str, data: bytes, page: int = 1) -> tuple[str, int]:
    """(base64 JPEG of the page, page count)."""
    from PIL import Image

    if data[:4] == b"%PDF":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        img = pdf[min(page, len(pdf)) - 1].render(scale=1.6).to_pil()
        count = len(pdf)
    else:
        img, count = Image.open(io.BytesIO(data)), 1
        img.thumbnail((1400, 1800))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=86)
    return base64.b64encode(buf.getvalue()).decode(), count
