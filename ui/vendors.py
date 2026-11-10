"""Vendors: the approved vendor master with activity."""
from __future__ import annotations

from html import escape

import streamlit as st

from database import repository as repo
from ui.components import card, empty, header, html, inr
from ui.inbox import load_rows


def render() -> None:
    header("Vendors")
    rows = load_rows()
    dupes = repo.exact_duplicate_run_ids()
    pos = repo.list_purchase_orders()
    q = st.text_input("Search", placeholder="Search vendor or GSTIN", label_visibility="collapsed")
    body = ""
    for v in repo.list_vendors():
        if q and q.lower() not in f"{v.legal_vendor_name} {v.gstin} {' '.join(v.aliases)}".lower():
            continue
        mine = [r for r in rows if r["vendor_id"] == v.vendor_id and r["status"] != "REJECTED" and r["run_id"] not in dupes]
        open_pos = sum(1 for p in pos if p.vendor_id == v.vendor_id and p.po_status.lower() != "closed")
        body += (f"<tr><td class='main'><b>{escape(v.legal_vendor_name)}</b><div class='sub'>{escape(v.vendor_id)}"
                 f"{'  ·  ' + escape(', '.join(v.aliases[:2])) if v.aliases else ''}</div></td>"
                 f"<td><span class='badge b-{escape(v.status)}'>{escape(v.status)}</span></td><td class='num'>{escape(v.gstin or '—')}</td>"
                 f"<td class='nw'>{escape(v.payment_terms)}</td><td class='r'>{open_pos}</td><td class='r'>{len(mine)}</td>"
                 f"<td class='r'>{inr(sum(r['total_paise'] or 0 for r in mine))}</td></tr>")
    if not body:
        empty("No vendors found", "No vendor matches this search.")
        return
    with card("vendors"):
        html("<table class='tbl'><thead><tr><th>Vendor</th><th>Status</th><th>GSTIN</th><th>Terms</th>"
             "<th class='r'>Open POs</th><th class='r'>Invoices</th><th class='r'>Billed</th></tr></thead>"
             f"<tbody>{body}</tbody></table>")
    st.caption("Invoices from inactive or unlisted vendors are blocked. Vendor records are loaded from data/vendors.csv.")
