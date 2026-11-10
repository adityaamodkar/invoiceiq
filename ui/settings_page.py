"""Settings: the matching rules in force, extraction setup, company profile and demo data."""
from __future__ import annotations

import streamlit as st

from config import settings
from config.settings import LLMConfig
from database import db
from services import ocr_service
from ui.components import card, header, html


def render() -> None:
    header("Settings")
    if msg := st.session_state.pop("settings_msg", None):
        st.toast(msg)
    t = settings.TOLERANCE
    a, b = st.container(key="stack_settings").columns(2, gap="medium")
    with a, card("rules"):
        html("<h3>Matching rules</h3><table class='tbl nwcols'><thead><tr><th>Check</th><th>Pass</th><th>Needs review</th>"
             "<th>Blocked</th></tr></thead><tbody>"
             f"<tr><td>Invoiced value vs PO value (before tax)</td><td>≤ {t.amount_pass_pct}%*</td>"
             f"<td>≤ {t.amount_review_upper_pct}%</td><td>&gt; {t.amount_review_upper_pct}%</td></tr>"
             f"<tr><td>Unit price vs PO price</td><td>Exact</td><td>≤ {t.unit_price_review_upper_pct}% over</td>"
             f"<td>&gt; {t.unit_price_review_upper_pct}% over</td></tr>"
             f"<tr><td>Quantity vs quantity left on PO</td><td>Within</td><td>≤ {t.amount_review_upper_pct}% over</td>"
             f"<td>&gt; {t.amount_review_upper_pct}% over</td></tr>"
             f"<tr><td>Arithmetic and tax</td><td>Within ₹{t.arithmetic_rounding_abs}</td><td>Otherwise</td><td></td></tr>"
             f"<tr><td>Field confidence</td><td>≥ {settings.MIN_FIELD_CONFIDENCE}</td><td>Below</td><td></td></tr>"
             "</tbody></table>")
        st.caption("*A purchase order can set its own pass tolerance. Billing below the PO always passes.")
        html("<h3 class='grp'>Duplicate detection</h3><table class='tbl nwcols'><tbody>"
             "<tr><td>Same file, or same vendor + invoice number + total</td><td>Blocked</td></tr>"
             "<tr><td>Same vendor + invoice number, different total</td><td>Needs review</td></tr>"
             f"<tr><td>Same vendor + total within {settings.POSSIBLE_DUPLICATE_WINDOW_DAYS} days, different number</td>"
             "<td>Needs review</td></tr></tbody></table>")
    with b:
        with card("extraction"):
            llm = LLMConfig()
            html("<h3>Extraction</h3><table class='tbl'><tbody>"
                 "<tr><td>Digital PDFs</td><td>Text layer (pdfplumber)</td></tr>"
                 f"<tr><td>Scans and photos</td><td>{'Tesseract OCR' if ocr_service.is_available() else 'Unavailable: Tesseract not installed'}</td></tr>"
                 "<tr><td>Field extraction</td><td>Rule-based</td></tr>"
                 f"<tr><td>LLM extraction</td><td>{'Configured' if llm.is_configured else 'Not configured'}</td></tr>"
                 "<tr><td>Uploaded files</td><td>Not stored; kept in memory for the session only</td></tr>"
                 "</tbody></table>")
        with card("company"):
            html("<h3>Company</h3><table class='tbl'><tbody>"
                 f"<tr><td>Legal name</td><td>{settings.BUYER.legal_name}</td></tr>"
                 f"<tr><td>GSTIN</td><td>{settings.BUYER.gstin}</td></tr>"
                 f"<tr><td>Address</td><td>{settings.BUYER.address}</td></tr></tbody></table>")
        with card("demo"):
            html("<h3>Demo data</h3>")
            st.caption("Clears all invoices and reloads vendors and purchase orders from data/*.csv.")
            sure = st.checkbox("Delete all invoice records", key="reset_sure")
            if st.button("Reset demo data", key="danger_reset", disabled=not sure):
                db.reset_demo_data()
                for k in ("doc", "done", "batch_ids", "docs", "inbox_view", "reset_sure"):  # untick the confirmation
                    st.session_state.pop(k, None)
                st.session_state["settings_msg"] = "Demo data reset."
                st.rerun()  # so the sidebar count, drawn before this point, is refreshed too
