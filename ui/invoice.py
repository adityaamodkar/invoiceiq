"""Invoice review: the document with extracted values highlighted, next to the data, PO match, checks and activity."""
from __future__ import annotations

import json
from decimal import Decimal
from html import escape

import streamlit as st

from database import repository as repo
from services import workflow as wf
from services.normalizers import format_inr
from ui import docstore
from ui.components import badge, card, day, empty, html, inr, today, when

FIELD_GROUPS = [
    ("Vendor", [("vendor_name", "Name"), ("vendor_gstin", "GSTIN"), ("vendor_address", "Address")]),
    ("Invoice", [("invoice_number", "Invoice no."), ("invoice_date", "Invoice date"), ("due_date", "Due date"),
                 ("po_number", "PO number"), ("currency", "Currency")]),
    ("Amounts", [("subtotal", "Subtotal"), ("discount", "Discount"), ("other_charges", "Other charges"),
                 ("tax_amount", "Tax"), ("total_amount", "Total")]),
]
SHORT = {"vendor_name": "Vendor", "vendor_gstin": "Vendor GSTIN", "buyer_gstin": "Buyer GSTIN", "vendor_address": "Address", "currency": "Currency", "invoice_number": "Invoice no.",
         "invoice_date": "Date", "due_date": "Due", "po_number": "PO", "subtotal": "Subtotal", "tax_amount": "Tax",
         "total_amount": "Total", "discount": "Discount", "other_charges": "Charges"}
MONEY = ("subtotal", "discount", "other_charges", "tax_amount", "total_amount")
CATEGORY_ORDER = ["Document", "Duplicate", "Vendor", "Purchase order", "Extraction", "Line items", "Financial"]


def _stage_output(run: dict, key: str) -> dict:
    s = next((s for s in run["stages"] if s["stage_key"] == key and s["output_json"]), None)
    return json.loads(s["output_json"]) if s else {}


def _fmt(key: str, v) -> str:
    if v is None:
        return "—"
    if key in MONEY:
        return format_inr(Decimal(v))
    if key in ("invoice_date", "due_date"):
        return day(v)
    return str(v)


# ------------------------------------------------------------------ actions
@st.dialog("Approve invoice")
def _approve_dialog(run: dict) -> None:
    inv = run["invoice"] or {}
    html(f"<div class='small muted'>{escape(inv.get('vendor_name') or '')}</div>"
         f"<div style='font-weight:650;font-size:1.05rem'>{escape(inv.get('invoice_number') or '')} "
         f"&nbsp;{inr(inv.get('total_paise'))}</div>")
    need = wf.note_required_to_approve(run)
    if need:
        st.caption("This invoice has open issues. Record why it can be approved.")
    note = st.text_area("Reason" if need else "Note (optional)", key="appr_note", height=90)
    st.caption("Approval releases the invoice for payment in your payment system. InvoiceIQ does not make payments.")
    c1, c2 = st.columns(2)
    if c1.button("Cancel", key="cancel_approve", width="stretch"):
        st.rerun()
    if c2.button("Approve", type="primary", disabled=need and not note.strip(), key="approve_confirm", width="stretch"):
        repo.set_approval(run["run_id"], "APPROVED", note.strip() or None)
        st.rerun()


@st.dialog("Reject invoice")
def _reject_dialog(run: dict) -> None:
    inv = run["invoice"] or {}
    html(f"<div class='small muted'>{escape(inv.get('vendor_name') or run['file_name'])}</div>"
         f"<div style='font-weight:650;font-size:1.05rem'>{escape(inv.get('invoice_number') or '')} "
         f"&nbsp;{inr(inv.get('total_paise'))}</div>")
    reason = st.text_area("Reason", key="rej_note", height=90,
                          placeholder="e.g. Duplicate of an invoice already received")
    c1, c2 = st.columns(2)
    if c1.button("Cancel", key="cancel_reject", width="stretch"):
        st.rerun()
    if c2.button("Reject", type="primary", disabled=not reason.strip(), key="confirm_reject", width="stretch"):
        repo.set_approval(run["run_id"], "REJECTED", reason.strip())
        st.rerun()


def _forget_delete() -> None:
    st.session_state.pop("ask_delete", None)


@st.dialog("Delete invoice", on_dismiss=_forget_delete)
def _delete_dialog(run: dict) -> None:
    inv = run["invoice"] or {}
    html(f"<div style='font-weight:650'>{escape(inv.get('vendor_name') or run['file_name'])}</div>"
         f"<div class='small muted'>{escape(inv.get('invoice_number') or '')}&nbsp;&nbsp;{inr(inv.get('total_paise'))}</div>")
    st.write("")
    st.markdown("This removes the invoice, its checks and its activity trail. If the invoice was counted against "
                "a purchase order, that amount is released. Processing the same file again will be treated as new.")
    c1, c2 = st.columns(2)
    if c1.button("Cancel", key="cancel_delete", width="stretch"):
        _forget_delete()
        st.rerun()
    if c2.button("Delete invoice", key="confirm_delete", width="stretch"):
        _forget_delete()
        repo.delete_runs([run["run_id"]])
        st.session_state["inbox_msg"] = "Invoice deleted."
        st.switch_page(st.session_state["pages"]["invoices"])


def _actions(run: dict) -> None:
    ok, why = wf.can_approve(run)
    # Buttons are sized to their labels and right-aligned under the amount, so no label is ever cut off.
    with st.container(horizontal=True, horizontal_alignment="right", gap="small", key="inv_actions"):
        if st.button("Approve", key="approve_btn", disabled=not ok, help=why or None):
            _approve_dialog(run)
        if st.button("Reject", key="danger_reject", disabled=not wf.can_reject(run)):
            _reject_dialog(run)
        # The menu gets a new key after each use: Streamlit then draws it closed again. Without that it stayed
        # open on top of the confirmation dialog.
        with st.popover("More", key=f"more_{st.session_state.get('more_n', 0)}"):
            if st.button("Delete invoice", key="danger_delete", icon=":material/delete:", width="stretch"):
                st.session_state["more_n"] = st.session_state.get("more_n", 0) + 1
                st.session_state["ask_delete"] = run["run_id"]
                st.rerun()
    # Stays set until the dialog is cancelled, confirmed or closed, so the dialog survives its own reruns.
    if st.session_state.get("ask_delete") == run["run_id"]:
        _delete_dialog(run)


# ------------------------------------------------------------------ banner
def _banner(run: dict, status: str) -> None:
    issues = [r for r in run["results"] if r["outcome"] != "PASS"]
    order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    issues.sort(key=lambda r: (r["outcome"] != "FAIL", order.get(r["category"], 99)))
    if status == "APPROVED":
        t, d = f"Approved {when(run['approval_at'])}", run.get("approval_note") or "Approved without a note."
    elif status == "REJECTED":
        t, d = f"Rejected {when(run['approval_at'])}", run.get("approval_note") or ""
    elif status == "UNREADABLE":
        t, d = "Document could not be read", f"{run['failure_reason']} Ask the vendor for a readable copy."
    elif status == "READY":
        t, d = "Ready to approve", f"All {len(run['results'])} checks passed."
    else:
        t = ("Blocked" if status == "BLOCKED" else "Needs review") + f": {len(issues)} issue{'s' * (len(issues) != 1)}"
        lines = "".join(f"<div>{escape(r['message'])}</div>" for r in issues[:3])
        more = f"<div class='muted'>{len(issues) - 3} more under Checks.</div>" if len(issues) > 3 else ""
        act = issues[0].get("recommended_action") if issues else None
        html(f'<div class="alert a-{status}"><div class="t">{escape(t)}</div><div class="d">{lines}{more}'
             + (f'<div style="margin-top:.35rem;font-weight:600">{escape(act)}</div>' if act else "") + "</div></div>")
        return
    html(f'<div class="alert a-{status}"><div class="t">{escape(t)}</div><div class="d">{escape(d)}</div></div>')


# ------------------------------------------------------------------ document viewer
def _viewer(run: dict, raw: dict) -> None:
    data = docstore.get(run["file_sha256"])
    if not data:
        html('<div class="doc-empty">The original file is not kept after the session that uploaded it.<br>'
             'Extracted values are shown on the right.</div>')
        return
    b64, pages = docstore.page_image_b64(run["file_sha256"], data, 1)
    c1, c2 = st.columns([1, 1])
    show = c1.toggle("Highlight fields", value=True, key=f"hl_{run['run_id']}")
    page = 1
    if pages > 1:
        page = c2.selectbox("Page", list(range(1, pages + 1)), key=f"pg_{run['run_id']}", label_visibility="collapsed")
        b64, _ = docstore.page_image_b64(run["file_sha256"], data, page)
    boxes = ""
    if show:
        for k, f in raw.items():
            if k.startswith("_") or not isinstance(f, dict) or not f.get("bbox") or f.get("page") != page:
                continue
            x0, y0, x1, y1 = f["bbox"]
            low = (f.get("confidence") is not None and float(f["confidence"]) < 0.8) or f.get("warning")
            boxes += (f'<div class="hl{" low" if low else ""}" title="{escape(SHORT.get(k, k))}" style="left:{x0*100:.2f}%;'
                      f'top:{y0*100:.2f}%;width:{(x1-x0)*100:.2f}%;height:{(y1-y0)*100:.2f}%"><span>{escape(SHORT.get(k, k))}</span></div>')
        for li in raw.get("_lines", []):
            if li.get("bbox") and li.get("page") == page:
                x0, y0, x1, y1 = li["bbox"]
                boxes += (f'<div class="hl line" style="left:{x0*100:.2f}%;top:{y0*100:.2f}%;width:{(x1-x0)*100:.2f}%;'
                          f'height:{(y1-y0)*100:.2f}%"><span>Line {li["line_no"]}</span></div>')
    html(f'<div class="doc"><img src="data:image/jpeg;base64,{b64}">{boxes}</div>')
    if show:
        st.caption("Hover a box to see the field. Green: high confidence. Amber: check. Blue: line items.")


# ------------------------------------------------------------------ tabs
def _same_text(a: str, b: str) -> bool:
    """True when two strings differ only in case, spacing or punctuation ("As printed" would add nothing)."""
    squash = lambda s: "".join(ch for ch in str(s).lower() if ch.isalnum())  # noqa: E731
    return squash(a) == squash(b)


def _details(run: dict, raw: dict, norm: dict, due: wf.Due) -> None:
    out = ""
    for group, fields in FIELD_GROUPS:
        rows = ""
        for k, label in fields:
            f, v = raw.get(k, {}), norm.get(k)
            if v is None and k in ("discount", "other_charges", "vendor_address"):
                continue
            shown = _fmt(k, v)
            sub = ""
            if k == "due_date" and v is None and due.date:
                shown, sub = due.date.strftime("%d %b %Y"), "Calculated from payment terms"
                icon = '<span class="ic ok">✓</span>'
            elif v is None:
                icon, shown = '<span class="ic no">–</span>', "Not found"
            else:
                low = (f.get("confidence") is not None and float(f["confidence"]) < 0.8) or f.get("warning")
                icon = f'<span class="ic {"low" if low else "ok"}">{"!" if low else "✓"}</span>'
                if f.get("warning"):
                    sub = f["warning"]
                elif f.get("raw") and not _same_text(f["raw"], shown):
                    sub = f"As printed: {f['raw']}"
            conf = f"{float(f['confidence']):.0%}" if v is not None and f.get("confidence") else ""
            rows += (f'<div class="fld">{icon}<span class="k">{escape(label)}</span><span class="v">{escape(shown)}</span>'
                     f'<span class="c">{conf}</span>' + (f'<span class="p">{escape(sub)}</span>' if sub else "") + "</div>")
        out += f"<h3 class='grp'>{group}</h3>{rows}"
    html(f"<div class='flds'>{out}</div>")
    if run["line_items"]:
        body = "".join(
            f"<tr><td>{li['line_no']}</td><td class='main'>{escape(li['description'] or '')}<div class='sub'>{escape(li['item_code'] or '')}</div></td>"
            f"<td class='r'>{escape(li['quantity'] or '')} {escape(li['uom'] or '')}</td><td class='r'>{inr(li['unit_price_paise'])}</td>"
            f"<td class='r'>{inr(li['amount_paise'])}</td></tr>" for li in run["line_items"])
        html("<h3 class='grp'>Line items</h3><table class='tbl'><thead><tr><th>#</th><th>Item</th>"
             f"<th class='r'>Qty</th><th class='r'>Unit price</th><th class='r'>Amount</th></tr></thead><tbody>{body}</tbody></table>")


def _cell(outcome: str | None, text: str, sub: str = "") -> str:
    cls = {"PASS": "cell-ok", "WARN": "cell-warn", "FAIL": "cell-fail"}.get(outcome or "", "")
    return f"<td class='r {cls}'>{escape(text)}" + (f"<div class='sub'>{escape(sub)}</div>" if sub else "") + "</td>"


def _po_match(run: dict, norm: dict) -> None:
    inv = run["invoice"] or {}
    po = repo.get_purchase_order(inv["po_number"]) if inv.get("po_number") else None
    vendor = repo.get_vendor(inv["vendor_id"]) if inv.get("vendor_id") else None
    res = {r["check_key"]: r for r in run["results"]}
    if not po:
        empty("No purchase order matched", res.get("po_exists", {}).get("message", ""))
        return
    out = lambda k: res.get(k, {}).get("outcome")  # noqa: E731
    fin = _stage_output(run, "financial")
    left = fin.get("remaining_before")
    head = [
        ("Vendor", inv.get("vendor_name") or "—", vendor.legal_vendor_name if vendor else "—", out("vendor_identity"), ""),
        ("Vendor status", "", vendor.status if vendor else "—", out("vendor_status"), ""),
        ("PO number", inv.get("po_number") or "—", po.po_number, out("po_exists"), ""),
        ("PO belongs to", inv.get("vendor_id") or "—", po.vendor_id, out("po_vendor"), ""),
        ("PO status", "", po.po_status, out("po_status"), ""),
        ("Currency", norm.get("currency") or "—", po.currency, out("po_currency"), ""),
        ("Value before tax", _fmt("subtotal", norm.get("subtotal")),
         f"{format_inr(Decimal(left))} left" if left else format_inr(po.subtotal),
         out("po_balance"), f"of {format_inr(po.subtotal)}" if left else ""),
    ]
    body = "".join(f"<tr><td class='nw'>{escape(a)}</td>{_cell(o, b)}{_cell(None, c, s)}"
                   f"<td class='r'>{'✓' if o == 'PASS' else ('Review' if o == 'WARN' else ('Block' if o == 'FAIL' else ''))}</td></tr>"
                   for a, b, c, o, s in head)
    html("<h3 style='margin-top:.9rem !important'>Header</h3><table class='tbl'><thead><tr><th></th><th class='r'>Invoice</th>"
         f"<th class='r'>Purchase order</th><th class='r'>Result</th></tr></thead><tbody>{body}</tbody></table>")

    by_po = {li["matched_po_line"]: li for li in run["line_items"] if li["matched_po_line"]}
    rows = ""
    for pl in po.lines:
        li = by_po.get(pl.line_no)
        n = li["line_no"] if li else None
        rows += (f"<tr><td class='main'>{escape(pl.item_description)}<div class='sub'>{escape(pl.item_code or '')}</div></td>"
                 + _cell(out(f"line{n}_qty") if li else None, f"{li['quantity']} / {pl.quantity_ordered}" if li else f"— / {pl.quantity_ordered}")
                 + _cell(out(f"line{n}_price") if li else None, f"{inr(li['unit_price_paise'])}" if li else "—",
                         f"PO {format_inr(pl.unit_price)}")
                 + _cell(None, inr(li["amount_paise"]) if li else "Not invoiced") + "</tr>")
    for li in run["line_items"]:
        if not li["matched_po_line"]:
            rows += (f"<tr><td class='main'>{escape(li['description'] or '')}<div class='sub'>Not on the PO</div></td>"
                     + _cell("WARN", li["quantity"] or "") + _cell("WARN", inr(li["unit_price_paise"]))
                     + _cell(None, inr(li["amount_paise"])) + "</tr>")
    html("<h3 style='margin-top:1.1rem !important'>Lines</h3><table class='tbl'><thead><tr><th>PO line</th>"
         "<th class='r'>Qty<div class='sub'>invoiced / ordered</div></th><th class='r'>Unit price<div class='sub'>invoice, PO below</div></th>"
         f"<th class='r'>Amount</th></tr></thead><tbody>{rows}</tbody></table>")
    if fin:
        html("<h3 style='margin-top:1.1rem !important'>PO balance</h3><table class='tbl'><tbody>"
             f"<tr><td>PO value before tax</td><td class='r'>{format_inr(Decimal(fin['po_subtotal']))}</td></tr>"
             f"<tr><td>Previously invoiced</td><td class='r'>{format_inr(Decimal(fin['previously_invoiced']))}</td></tr>"
             f"<tr><td>This invoice before tax</td><td class='r'>{format_inr(Decimal(fin['this_invoice_pre_tax']))}</td></tr>"
             f"<tr><td><b>Remaining after this invoice</b></td><td class='r'><b>{format_inr(Decimal(fin['remaining_after']))}</b></td></tr>"
             "</tbody></table>")
        st.caption(f"Tolerance: up to {fin.get('tolerance_pass_pct')}% over passes, up to "
                   f"{fin.get('review_upper_pct')}% needs review, above that is blocked.")


def _checks(run: dict) -> None:
    res = run["results"]
    if not res:
        st.caption("No checks ran because the document could not be read.")
        return
    order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    issues = sorted([r for r in res if r["outcome"] != "PASS"],
                    key=lambda r: (r["outcome"] != "FAIL", order.get(r["category"], 99)))
    passed = [r for r in res if r["outcome"] == "PASS"]

    def row(r):
        lab = {"PASS": "Pass", "WARN": "Review", "FAIL": "Block"}[r["outcome"]]
        extra = ""
        if r["outcome"] != "PASS":
            if r.get("expected") or r.get("actual"):
                extra += f"<div class='e'>Expected {escape(r.get('expected') or '—')}, found {escape(r.get('actual') or '—')}</div>"
            if r.get("recommended_action"):
                extra += f"<div class='a'>{escape(r['recommended_action'])}</div>"
        return f"<div class='chk'><span class='o {r['outcome']}'>{lab}</span><div>{escape(r['message'])}{extra}</div></div>"

    if issues:
        html("".join(row(r) for r in issues))
    with st.expander(f"{len(passed)} passed", expanded=not issues):
        html("".join(row(r) for r in sorted(passed, key=lambda r: order.get(r["category"], 99))))


def _activity(run: dict) -> None:
    status_txt = {"READY_FOR_APPROVAL": "Checks passed: ready to approve", "NEEDS_REVIEW": "Sent to review",
                  "BLOCKED": "Blocked by checks"}.get(run.get("decision") or "", "Could not be read")
    events = [("sys", run["uploaded_at"], "Received", f"{run['file_name']}", None),
              ("sys" if run["run_status"] == "COMPLETED" else "bad", run["finished_at"] or run["started_at"],
               status_txt, f"{len(run['results'])} checks in {sum(s['duration_ms'] or 0 for s in run['stages'])} ms", None)]
    for a in run["reviews"]:
        kind = {"APPROVE": ("ok", "Approved"), "REJECT": ("bad", "Rejected"), "NOTE": ("", "Note")}.get(a["action"], ("", a["action"]))
        events.append((kind[0], a["created_at"], f"{kind[1]} by {a['reviewer'] or 'AP user'}", None, a["reason"]))
    events.sort(key=lambda e: e[1] or "")
    html('<div class="tl">' + "".join(
        f'<div class="ev {k}"><div class="w">{escape(when(w))}</div><div class="t">{escape(t)}</div>'
        + (f'<div class="d">{escape(d)}</div>' if d else "") + (f'<div class="note">{escape(n)}</div>' if n else "") + "</div>"
        for k, w, t, d, n in events) + "</div>")
    with st.form(f"note_{run['run_id']}", clear_on_submit=True, border=False):
        text = st.text_area("Add a note", height=70, label_visibility="collapsed", placeholder="Add a note")
        if st.form_submit_button("Add note") and text.strip():
            repo.add_note(run["run_id"], text.strip())
            st.rerun()
    with st.expander("Processing steps"):
        html("".join(
            f'<div class="st {s["status"]}"><div class="i">{"✓" if s["status"] == "COMPLETED" else ("✕" if s["status"] == "FAILED" else "")}</div>'
            f'<div><div class="n">{escape(s["stage_name"])}</div><div class="m">{escape(s["message"] or "")}</div></div>'
            f'<div class="ms">{s["duration_ms"] if s["duration_ms"] is not None else ""}{" ms" if s["duration_ms"] is not None else ""}</div></div>'
            for s in run["stages"]))
        st.caption(f"Run {run['run_id']}. File fingerprint {run['file_sha256'][:16]}.")


# ------------------------------------------------------------------ page
def _origin() -> str:
    """The screen the user opened this invoice from (tracked in app.py); Invoices when unknown."""
    origin = st.session_state.get("came_from", "invoices")
    return origin if origin in st.session_state["pages"] and origin != "invoice" else "invoices"


def _back_bar(current: str | None) -> None:
    """Back returns to the previous screen; the breadcrumb always shows where the invoice lives.
    Both navigate inside the session (a plain link would reload the page and drop session state)."""
    pages = st.session_state["pages"]
    origin = _origin()
    with st.container(horizontal=True, vertical_alignment="center", gap="small", key="backbar"):
        if st.button(f"Back to {pages[origin].title}", icon=":material/arrow_back:", key="back_btn"):
            st.switch_page(pages[origin])
        st.page_link(pages["invoices"], label="Invoices")
        if current:
            html(f'<div class="crumb">/&nbsp;&nbsp;{escape(current)}</div>')


def render() -> None:
    run_id = st.query_params.get("id")
    run = repo.get_run(run_id) if run_id else None
    if not run:
        _back_bar(None)
        empty("Invoice not found", "It may have been deleted.")
        return
    inv = run.get("invoice") or {}
    status = wf.status_of(run)
    raw = json.loads(inv.get("raw_extraction_json") or "{}") if inv else {}
    norm = json.loads(inv.get("normalized_json") or "{}") if inv else {}
    vendor = repo.get_vendor(inv["vendor_id"]) if inv.get("vendor_id") else None
    due = wf.due_of(inv.get("invoice_date"), norm.get("due_date"), vendor.payment_terms if vendor else None)

    _back_bar(inv.get("invoice_number") or run["file_name"])
    top_l, top_r = st.columns([2, 1.3], vertical_alignment="bottom")
    with top_l:
        facts = [("Invoice", inv.get("invoice_number") or "—"), ("Issued", day(inv.get("invoice_date"))),
                 ("Due", (due.date.strftime('%d %b %Y') + ("" if due.label(today()) == due.date.strftime('%d %b') else f" ({due.label(today())})")) if due.date else "—"),
                 ("PO", inv.get("po_number") or "—")]
        html(f'<div class="ph"><h1>{escape(inv.get("vendor_name") or "Unreadable document")}</h1>{badge(status)}</div>'
             '<div class="ph-sub facts">' + "".join(
                 f'<span class="fact"><span class="muted">{k}</span> <span style="color:var(--ink)">{escape(v)}</span></span>'
                 for k, v in facts) + "</div>")
    with top_r:
        total = inr(inv.get("total_paise")) if inv.get("total_paise") is not None else "Total not found"
        size = "1.6rem" if inv.get("total_paise") is not None else "1rem"
        html(f"<div style='text-align:right;font-size:{size};font-weight:650' class='num'>{total}</div>")
        _actions(run)

    _banner(run, status)
    left, right = st.container(key="stack_invoice").columns([1.05, 1], gap="large")
    with left:
        _viewer(run, raw)
    with right:
        n_issues = sum(r["outcome"] != "PASS" for r in run["results"])
        t1, t2, t3, t4 = st.tabs(["Details", "PO match", f"Checks ({n_issues})" if n_issues else "Checks", "Activity"])
        with t1:
            _details(run, raw, norm, due)
        with t2:
            _po_match(run, norm)
        with t3:
            _checks(run)
        with t4:
            _activity(run)
