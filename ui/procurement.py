"""Procurement data: the vendor master and purchase orders the checks run against."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from database import db
from database import repository as repo
from services.normalizers import format_inr
from ui.components import page_header


def render() -> None:
    page_header("Procurement data",
                "The approved vendors and purchase orders that every invoice is verified against. "
                "Balances include invoices approved in InvoiceIQ.")
    tab_v, tab_p, tab_admin = st.tabs(["Vendors", "Purchase orders", "Demo data"])
    with tab_v:
        st.dataframe(pd.DataFrame([{
            "Vendor ID": v.vendor_id, "Legal name": v.legal_vendor_name, "Aliases": ", ".join(v.aliases),
            "GSTIN": v.gstin, "Status": v.status, "Currency": v.currency, "Terms": v.payment_terms,
            "Address": v.address} for v in repo.list_vendors()]), hide_index=True, width="stretch")
    with tab_p:
        pos = repo.list_purchase_orders()
        st.dataframe(pd.DataFrame([{
            "PO": p.po_number, "Vendor": p.vendor_id, "Date": p.po_date, "Status": p.po_status,
            "Value (pre-tax)": format_inr(p.subtotal), "Tax": format_inr(p.tax_amount),
            "Value (incl. tax)": format_inr(p.total_po_amount),
            "Invoiced before InvoiceIQ": format_inr(p.baseline_invoiced),
            "Invoiced in InvoiceIQ": format_inr(p.invoiced_in_system),
            "Remaining (pre-tax)": format_inr(p.remaining_balance),
            "Tolerance": f"{p.tolerance_pct}%"} for p in pos]), hide_index=True, width="stretch")
        st.markdown("**PO lines**")
        st.dataframe(pd.DataFrame([{
            "PO": l.po_number, "Line": l.line_no, "Item code": l.item_code, "Description": l.item_description,
            "UOM": l.uom, "Qty ordered": str(l.quantity_ordered), "Unit price": format_inr(l.unit_price),
            "Line total": format_inr(l.line_total), "GST": f"{l.tax_rate}%"} for p in pos for l in p.lines]),
            hide_index=True, width="stretch")
    with tab_admin:
        st.markdown("To remove individual runs, tick them in the **Register** and delete them there. "
                    "To start over completely, reset: this clears all processing history and reloads the vendor "
                    "and purchase order records from `data/*.csv`.")
        sure = st.checkbox("I understand this deletes all processing history")
        if st.button("Reset demo data", disabled=not sure):
            db.reset_demo_data()
            for k in ("doc", "last_run_id", "processed_key", "batch_runs"):
                st.session_state.pop(k, None)
            st.success("Processing history cleared and procurement data reloaded.")
