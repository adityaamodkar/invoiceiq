"""
InvoiceIQ entrypoint.

    streamlit run app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from database import repository as repo  # noqa: E402
from database.db import init_db  # noqa: E402
from ui import home, inbox, invoice, pos, settings_page, upload, vendors  # noqa: E402
from ui.theme import apply_theme  # noqa: E402

st.set_page_config(page_title="InvoiceIQ", page_icon=str(ROOT / "assets" / "icon.svg"), layout="wide",
                   initial_sidebar_state="expanded")


@st.cache_resource
def _bootstrap() -> bool:
    init_db()  # creates tables, applies migrations, seeds procurement data if empty
    return True


_bootstrap()
if "dark_mode" not in st.session_state:  # remembered across reloads and restarts
    st.session_state["dark_mode"] = repo.get_pref("dark_mode") == "1"
apply_theme()
st.logo(str(ROOT / "assets" / ("logo_dark.svg" if st.session_state["dark_mode"] else "logo.svg")), size="large")


def _save_theme() -> None:
    repo.set_pref("dark_mode", "1" if st.session_state["dark_mode"] else "0")


pages = {
    "home": st.Page(home.render, title="Home", url_path="home", default=True),
    "invoices": st.Page(inbox.render, title="Invoices", url_path="invoices"),
    "upload": st.Page(upload.render, title="Upload", url_path="upload"),
    "invoice": st.Page(invoice.render, title="Invoice", url_path="invoice"),
    "vendors": st.Page(vendors.render, title="Vendors", url_path="vendors"),
    "pos": st.Page(pos.render, title="Purchase orders", url_path="purchase-orders"),
    "settings": st.Page(settings_page.render, title="Settings", url_path="settings"),
}
st.session_state["pages"] = pages
nav = st.navigation(list(pages.values()), position="hidden")

# Remember the last screen that was not the invoice detail, so its Back button returns to where the user came from.
current = next((k for k, p in pages.items() if p is nav or p.title == nav.title), "home")
if current != "invoice":
    st.session_state["came_from"] = current

with st.sidebar:
    rows = inbox.load_rows()
    to_action = sum(r["status"] in ("NEEDS_REVIEW", "READY") for r in rows)
    if st.button("Upload invoice", type="primary", width="stretch", icon=":material/add:", key="nav_upload"):
        st.switch_page(pages["upload"])
    with st.container(key="nav_home"):
        st.page_link(pages["home"], label="Home", icon=":material/home:")
    with st.container(key="nav_invoices"):
        st.page_link(pages["invoices"], label="Invoices", icon=":material/receipt_long:")
    st.markdown("<div class='side-group'>Records</div>", unsafe_allow_html=True)
    st.page_link(pages["vendors"], label="Vendors", icon=":material/storefront:")
    st.page_link(pages["pos"], label="Purchase orders", icon=":material/inventory_2:")
    st.markdown("<div class='side-group'>Admin</div>", unsafe_allow_html=True)
    st.page_link(pages["settings"], label="Settings", icon=":material/settings:")
    st.markdown(f"<div class='entity'><div class='cap'>Company</div><b>{settings.BUYER.legal_name}</b>"
                f"<span>GSTIN {settings.BUYER.gstin}</span></div>", unsafe_allow_html=True)
    st.toggle("Dark mode", key="dark_mode", on_change=_save_theme)
    if to_action:  # count badge on the Invoices link: invoices waiting for a person
        st.markdown(f"<style>[class*='st-key-nav_invoices'] a::after {{ content:'{to_action}'; margin-left:auto; "
                    "font-size:.75rem; font-weight:700; padding:.05rem .5rem; border-radius:999px; "
                    "background:var(--review-bg); color:var(--review); }}</style>", unsafe_allow_html=True)

nav.run()
