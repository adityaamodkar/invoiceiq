"""Purchase orders with live balances."""
from __future__ import annotations

from html import escape

import streamlit as st

from database import repository as repo
from services.normalizers import format_inr
from ui.components import card, day, empty, header, html


def render() -> None:
    header("Purchase orders")
    vendors = {v.vendor_id: v.legal_vendor_name for v in repo.list_vendors()}
    pos = repo.list_purchase_orders()
    status = st.segmented_control("Status", ["All", "Open", "Fully invoiced", "Closed"], default="All",
                                  label_visibility="collapsed")
    body = ""
    for p in pos:
        fully = p.remaining_balance <= 0 and p.po_status.lower() != "closed"
        if status == "Fully invoiced" and not fully:
            continue
        if status == "Open" and (fully or p.po_status.lower() == "closed"):
            continue
        if status == "Closed" and p.po_status.lower() != "closed":
            continue
        before = float(p.baseline_invoiced / p.subtotal) if p.subtotal else 0
        here = float(p.invoiced_in_system / p.subtotal) if p.subtotal else 0
        used = before + here
        lines = "".join(f"<tr><td class='sub'>{l.line_no}</td><td class='sub'>{escape(l.item_description)}</td>"
                        f"<td class='r sub'>{l.quantity_ordered} {escape(l.uom)}</td><td class='r sub'>{format_inr(l.unit_price)}</td>"
                        f"<td class='r sub'>{format_inr(l.line_total)}</td></tr>" for l in p.lines)
        remaining = (f"<td class='r' style='color:var(--blocked);font-weight:600'>{format_inr(-p.remaining_balance)} over</td>"
                     if p.remaining_balance < 0 else f"<td class='r'>{format_inr(p.remaining_balance)}</td>")
        shown_status = ("Fully invoiced" if p.remaining_balance <= 0 and p.po_status.lower() != "closed"
                        else p.po_status)
        status_cls = shown_status.split()[0]
        body += (f"<tr><td class='nw'><details><summary><b>{escape(p.po_number)}</b></summary>"
                 f"<table class='tbl' style='margin:.4rem 0 .2rem'>{lines}</table></details></td>"
                 f"<td class='main'>{escape(vendors.get(p.vendor_id, p.vendor_id))}</td><td class='nw'>{day(p.po_date)}</td>"
                 f"<td><span class='badge b-{escape(status_cls)}'>{escape(shown_status)}</span></td>"
                 f"<td class='r'>{format_inr(p.subtotal)}</td>"
                 f"<td class='r'>{format_inr(p.baseline_invoiced) if p.baseline_invoiced else '—'}</td>"
                 f"<td class='r'>{format_inr(p.invoiced_in_system) if p.invoiced_in_system else '—'}</td>"
                 f"<td style='width:11%'><div class='bar'><span class='before' style='width:{min(before, 1)*100:.1f}%'></span>"
                 f"<span style='width:{max(0, min(here, 1 - before))*100:.1f}%'></span></div>"
                 f"<div class='sub'>{used:.0%} used</div></td>{remaining}</tr>")
    if not body:
        empty("No purchase orders here", "No purchase order has this status.")
        return
    with card("pos"):
        html("<table class='tbl'><thead><tr><th>PO</th><th>Vendor</th><th>Date</th><th>Status</th>"
             "<th class='r'>Value<div class='sub'>before tax</div></th><th class='r'>Invoiced<div class='sub'>before InvoiceIQ</div></th>"
             "<th class='r'>Invoiced<div class='sub'>in InvoiceIQ</div></th>"
             f"<th>Used</th><th class='r'>Remaining</th></tr></thead><tbody>{body}</tbody></table>"
             "<div class='key'><span><i style='background:var(--bar-before)'></i>Invoiced before InvoiceIQ (opening balance)</span>"
             "<span><i style='background:var(--bar)'></i>Invoiced in InvoiceIQ (cleared or approved)</span></div>")
    st.caption("All amounts are before tax: GST on an invoice is checked separately and does not use up the PO. "
               "Click a PO number to see its lines.")
