"""Invoices inbox: status tabs, search, due dates, flags, bulk actions."""
from __future__ import annotations

from html import escape

import streamlit as st

from database import repository as repo
from services import workflow as wf
from ui.components import badge, card, day, empty, flag_chips, header, html, inr, today

TABS = [("NEEDS_REVIEW", "Needs review"), ("READY", "Ready to approve"), ("BLOCKED", "Blocked"),
        ("APPROVED", "Approved"), ("REJECTED", "Rejected"), ("ALL", "All")]
COLS = [0.3, 2.5, 1.3, 1.1, 1.5, 1.35, 1.4, 2.0]
SORTS = ["Newest first", "Due date", "Amount"]


def load_rows() -> list[dict]:
    vendors = {v.vendor_id: v for v in repo.list_vendors()}
    flags = repo.flags_by_run()
    out = []
    for r in repo.list_runs(current_only=True):
        if r["run_status"] == "RUNNING":
            continue
        v = vendors.get(r["vendor_id"])
        due = wf.due_of(r["invoice_date"], r.get("printed_due"), v.payment_terms if v else None)
        out.append({**r, "status": wf.status_of(r), "due": due, "flags": flags.get(r["run_id"], [])})
    return out


@st.dialog("Reject invoices")
def _bulk_reject(ids: list[str]) -> None:
    reason = st.text_area("Reason", height=90)
    c1, c2 = st.columns(2)
    if c1.button("Cancel", key="cancel_bulk_reject", width="stretch"):
        st.rerun()
    if c2.button(f"Reject {len(ids)}", type="primary", disabled=not reason.strip(), key="confirm_reject_bulk", width="stretch"):
        for i in ids:
            repo.set_approval(i, "REJECTED", reason.strip())
        st.session_state["inbox_msg"] = f"Rejected {len(ids)} invoice(s)."
        _clear_selection()
        st.rerun()


@st.dialog("Delete invoices")
def _bulk_delete(ids: list[str]) -> None:
    st.markdown(f"Delete **{len(ids)}** invoice(s) with their checks and activity trail? Amounts counted "
                "against purchase orders are released, and the same files can be processed again as new.")
    c1, c2 = st.columns(2)
    if c1.button("Cancel", key="cancel_bulk_delete", width="stretch"):
        st.rerun()
    if c2.button(f"Delete {len(ids)}", key="confirm_delete_bulk", width="stretch"):
        repo.delete_runs(ids)
        st.session_state["inbox_msg"] = f"Deleted {len(ids)} invoice(s)."
        _clear_selection()
        st.rerun()


def _clear_selection() -> None:
    for k in [k for k in st.session_state if str(k).startswith("sel_")]:
        del st.session_state[k]


def _bulk_bar(selected: list[dict]) -> None:
    ready = [r for r in selected if r["status"] == "READY"]
    rejectable = [r for r in selected if wf.can_reject(r)]
    with card("bulk"):
        c0, c1, c2, c3 = st.columns([2.4, 1.2, 1, 1], vertical_alignment="center")
        c0.markdown(f"**{len(selected)} selected**")
        if c1.button(f"Approve {len(ready)}" if ready else "Approve", key="approve_bulk", disabled=not ready,
                     help="Only invoices that are ready to approve can be approved together.", width="stretch"):
            for r in ready:
                repo.set_approval(r["run_id"], "APPROVED", None)
            st.session_state["inbox_msg"] = f"Approved {len(ready)} invoice(s)."
            _clear_selection()
            st.rerun()
        if c2.button("Reject", key="danger_bulk_reject", disabled=not rejectable, width="stretch"):
            _bulk_reject([r["run_id"] for r in rejectable])
        if c3.button("Delete", key="danger_bulk_delete", width="stretch"):
            _bulk_delete([r["run_id"] for r in selected])


def render() -> None:
    if header("Invoices", action="Upload invoice"):
        st.switch_page(st.session_state["pages"]["upload"])
    if msg := st.session_state.pop("inbox_msg", None):
        st.toast(msg)

    rows = load_rows()
    counts = {k: sum(r["status"] == k for r in rows) for k, _ in TABS}
    counts["ALL"] = len(rows)
    counts["BLOCKED"] += sum(r["status"] == "UNREADABLE" for r in rows)
    labels = {k: f"{lbl}  {counts[k]}" for k, lbl in TABS}
    # Streamlit drops widget values when you leave a page. The tab, search and sort are kept in "inbox_view"
    # and put back here, so returning from an invoice shows the list exactly as it was left.
    view = st.session_state.setdefault("inbox_view", {})
    if st.session_state.get("inbox_tab") not in labels:
        want = view.get("tab") or st.query_params.get("tab") or ("NEEDS_REVIEW" if counts["NEEDS_REVIEW"] else "ALL")
        st.session_state["inbox_tab"] = want if want in labels else "ALL"
    if "inbox_q" not in st.session_state:
        st.session_state["inbox_q"] = view.get("q", "")
    if st.session_state.get("inbox_sort") not in SORTS:
        st.session_state["inbox_sort"] = view.get("sort", SORTS[0])
    tab = st.segmented_control("Status", [k for k, _ in TABS], format_func=lambda k: labels[k],
                               label_visibility="collapsed", key="inbox_tab") or "ALL"
    s1, s2 = st.columns([3, 1])
    q = s1.text_input("Search", placeholder="Search vendor, invoice number or PO", label_visibility="collapsed", key="inbox_q")
    sort = s2.selectbox("Sort", SORTS, label_visibility="collapsed", key="inbox_sort")
    view.update(tab=tab, q=q, sort=sort)

    shown = [r for r in rows if tab == "ALL" or r["status"] == tab or (tab == "BLOCKED" and r["status"] == "UNREADABLE")]
    if q.strip():
        ql = q.lower()
        shown = [r for r in shown if ql in " ".join(str(r.get(k) or "") for k in
                                                    ("vendor_name", "invoice_number", "po_number", "file_name")).lower()]
    if sort == "Due date":
        shown.sort(key=lambda r: (r["due"].date is None, r["due"].date or today()))
    elif sort == "Amount":
        shown.sort(key=lambda r: -(r["total_paise"] or 0))

    if not shown:
        empty("No invoices here", "Nothing matches this view." if rows else "Uploaded invoices will appear here.")
        return

    selected = []
    with st.container(key="inbox_list"):  # scrolls sideways on a narrow window instead of wrapping every cell
        hdr = st.columns(COLS)
        for col, t, right in zip(hdr[1:], ["Vendor and invoice", "Issued", "Due", "PO", "Amount", "Status", "Flags"],
                                 [0, 0, 0, 0, 1, 0, 0]):
            col.markdown(f"<div class='rh' style='text-align:{'right' if right else 'left'}'>{t}</div>", unsafe_allow_html=True)
        hdr[0].markdown("<div class='rh'>&nbsp;</div>", unsafe_allow_html=True)

        for r in shown:
            with st.container(key=f"row_{r['run_id']}"):
                c = st.columns(COLS, vertical_alignment="top")
                if c[0].checkbox("Select", key=f"sel_{r['run_id']}", label_visibility="collapsed"):
                    selected.append(r)
                with c[1]:
                    st.page_link(st.session_state["pages"]["invoice"], label=r["vendor_name"] or r["file_name"],
                                 query_params={"id": r["run_id"]})
                    html(f"<div class='rc' style='padding-top:0;margin-top:-.55rem'><span class='sub'>"
                         f"{escape(r['invoice_number'] or 'Number not read')}</span></div>")
                due = r["due"]
                overdue = due.date is not None and due.date < today() and r["status"] not in ("APPROVED", "REJECTED")
                c[2].markdown(f"<div class='rc'>{day(r['invoice_date'])}</div>", unsafe_allow_html=True)
                c[3].markdown(f"<div class='rc' style='{'color:var(--blocked);font-weight:600' if overdue else ''}'>"
                              f"{escape(due.label(today()) if r['status'] not in ('APPROVED', 'REJECTED') else (due.date.strftime('%d %b') if due.date else '—'))}</div>",
                              unsafe_allow_html=True)
                c[4].markdown(f"<div class='rc'>{escape(r['po_number'] or '—')}</div>", unsafe_allow_html=True)
                c[5].markdown(f"<div class='rc r'>{inr(r['total_paise'])}</div>", unsafe_allow_html=True)
                c[6].markdown(f"<div class='rc'>{badge(r['status'])}</div>", unsafe_allow_html=True)
                c[7].markdown(f"<div class='rc wrap'>{flag_chips(r['flags']) if r['status'] not in ('APPROVED', 'READY') else ''}</div>",
                              unsafe_allow_html=True)
                html("<div class='rr'></div>")
    total = sum(r["total_paise"] or 0 for r in shown)
    st.caption(f"{len(shown)} invoice(s), {inr(total)}")
    if selected:
        _bulk_bar(selected)
