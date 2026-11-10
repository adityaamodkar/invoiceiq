"""Register: every processing run. Select runs to delete them; open any run in full."""
from __future__ import annotations

import streamlit as st

from database import repository as repo
from ui.components import sheet, STATUS_LABELS, empty_state, inr_paise, mark, page_header, run_status_key, when_short
from ui.register import cell, register

FILTERS = ["All", "Ready for approval", "Needs review", "Blocked", "Could not be read"]


def render() -> None:
    page_header("Register", "Every invoice InvoiceIQ has processed, newest first. Open a run to see exactly "
                            "what was read, what it was checked against, and why it was decided.")
    if msg := st.session_state.pop("register_msg", None):
        st.success(msg)
    runs = repo.list_runs()
    if not runs:
        empty_state("Nothing in the register yet", "Processed invoices are recorded here with their full audit trail.")
        return

    f = st.segmented_control("Show", FILTERS, default="All", label_visibility="collapsed", key="reg_filter")
    rows = []
    for r in runs:
        status = run_status_key(r)
        if f not in (None, "All") and STATUS_LABELS[status] != f:
            continue
        rows.append({"run_id": r["run_id"],
                     "inv": cell(r["invoice_number"] or "Number not read", r["file_name"]),
                     "ven": cell(r["vendor_name"] or "Vendor not read", r["po_number"] or None),
                     "amt": inr_paise(r["total_paise"]), "out": mark(status),
                     "when": when_short(r["started_at"])})
    if not rows:
        st.caption("No runs match this filter.")
        return

    st.caption(f"{len(rows)} run(s). Tick runs to delete them.")
    with sheet("register_list"):
        selected = register(rows, [("Invoice", 2.2, "inv"), ("Vendor and PO", 2.4, "ven"), ("Amount>", 1.3, "amt"),
                                   ("Outcome", 1.6, "out"), ("Processed", 1.3, "when")],
                            key="reg", selectable=True)
    if selected:
        _delete_bar(selected)


def _delete_bar(selected: list[str]) -> None:
    with sheet("history_1"):
        st.markdown(f"**{len(selected)} run(s) selected.** Deleting removes each run and its audit trail. "
                    "If a deleted run was ready for approval, its amount goes back to the purchase order balance.")
        c1, c2, _ = st.columns([1.2, 1, 3])
        sure = c1.checkbox("Yes, delete them", key="reg_confirm")
        if c2.button("Delete selected", type="primary", disabled=not sure, width="stretch", key="reg_delete"):
            n = repo.delete_runs(selected)
            for k in [k for k in st.session_state if str(k).startswith("reg_sel_") or k == "reg_confirm"]:
                del st.session_state[k]
            if st.session_state.get("last_run_id") in selected:
                st.session_state.pop("last_run_id", None)
            st.session_state["register_msg"] = f"Deleted {n} run(s)."
            st.rerun()
