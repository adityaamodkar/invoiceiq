"""The full, explainable record of one processing run. Used inline and in the run dialog."""
from __future__ import annotations

import json
from decimal import Decimal
from html import escape

import pandas as pd
import streamlit as st

from database import repository as repo
from services.invoice_extractor import FIELD_LABELS
from services.normalizers import format_inr
from ui.components import sheet, check_row, facts, html, inr_paise, run_status_key, stamp, step_row, when

CATEGORY_ORDER = ["Document", "Duplicate", "Vendor", "Purchase order", "Extraction", "Line items", "Financial"]
MONEY_FIELDS = ("subtotal", "tax_amount", "total_amount", "discount", "other_charges")


def render_run_detail(run_id: str, key: str = "inline") -> None:
    run = repo.get_run(run_id)
    if not run:
        st.warning("This processing run has been deleted.")
        return
    status = run_status_key(run)
    inv = run.get("invoice") or {}
    if status == "FAILED":
        why = f"Processing stopped at {run['failure_stage']}: {run['failure_reason']}"
        nxt = "Ask the vendor for a readable copy and upload it again. The failed attempt stays in the register."
    else:
        why, nxt = run["decision_reason"], run["next_action"]

    with sheet(f"verdict_{key}_{run_id}"):
        html(f'<div class="stampbox">{stamp(status)}<div class="verdict-text"><div class="why">{escape(why or "")}'
             f'</div><div class="next"><b>Next step.</b> {escape(nxt or "")}</div></div></div>')
        st.write("")
        left, right = st.columns(2, gap="large")
        with left:
            facts([("Invoice", inv.get("invoice_number") or "Not read"),
                   ("Vendor", (inv.get("vendor_name") or "Not read") + (f" ({inv['vendor_id']})" if inv.get("vendor_id") else "")),
                   ("Purchase order", inv.get("po_number") or "None matched")])
        with right:
            facts([("Invoice total", inr_paise(inv.get("total_paise"))),
                   ("File", run["file_name"]),
                   ("Processed", when(run["finished_at"] or run["started_at"]))])

    tabs = st.tabs(["Checks", "What was read", "Vendor and PO", "Processing log"])
    with tabs[0]:
        _checks(run)
    with tabs[1]:
        _extracted(run, key)
    with tabs[2]:
        _vendor_po(run, key)
    with tabs[3]:
        _log(run)


def _checks(run: dict) -> None:
    results = run["results"]
    if not results:
        st.caption("No checks ran because the document could not be read.")
        return
    order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    issues = sorted([r for r in results if r["outcome"] != "PASS"],
                    key=lambda r: (r["outcome"] != "FAIL", order.get(r["category"], 99)))
    passed = [r for r in results if r["outcome"] == "PASS"]
    st.caption(f"{len(results)} checks: {len(passed)} passed, {sum(r['outcome'] == 'WARN' for r in results)} "
               f"to review, {sum(r['outcome'] == 'FAIL' for r in results)} blocking.")
    if issues:
        html("".join(check_row(r) for r in issues))
    with st.expander(f"Passed checks ({len(passed)})", expanded=not issues):
        for cat in CATEGORY_ORDER:
            rows = [r for r in passed if r["category"] == cat]
            if rows:
                html(f"<h4 style='margin-top:.6rem !important'>{cat}</h4>" + "".join(check_row(r) for r in rows))


def _extracted(run: dict, key: str) -> None:
    inv = run.get("invoice")
    if not inv:
        st.caption("Nothing was read from this document.")
        return
    raw = json.loads(inv["raw_extraction_json"] or "{}")
    norm = json.loads(inv["normalized_json"] or "{}")
    rows = []
    for k, label in FIELD_LABELS.items():
        r, v = raw.get(k, {}), norm.get(k)
        if v is None and k in ("discount", "other_charges", "buyer_gstin", "vendor_address"):
            continue
        shown = "Not on invoice" if v is None else (format_inr(Decimal(v)) if k in MONEY_FIELDS else str(v))
        rows.append({"Field": label, "Value": shown, "As printed": r.get("raw") or "",
                     "Confidence": float(r["confidence"]) if r.get("confidence") and v is not None else None,
                     "Page": str(r["page"]) if r.get("page") and v is not None else ""})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=35 * (len(rows) + 1) + 3,
                 key=f"fields_{key}_{run['run_id']}",
                 column_config={"Confidence": st.column_config.ProgressColumn(
                     "Confidence", min_value=0.0, max_value=1.0, format="%.2f")})
    if run["line_items"]:
        body = "".join(
            f"<tr><td>{li['line_no']}</td><td>{escape(li['item_code'] or '')}</td><td>{escape(li['description'] or '')}</td>"
            f"<td class='r'>{escape(li['quantity'] or '')} {escape(li['uom'] or '')}</td>"
            f"<td class='r'>{inr_paise(li['unit_price_paise'])}</td><td class='r'>{inr_paise(li['amount_paise'])}</td>"
            f"<td class='r'>{li['matched_po_line'] or 'not matched'}</td></tr>" for li in run["line_items"])
        html("<h4 style='margin-top:1rem !important'>Line items</h4><table class='ledger'><thead><tr><th>#</th>"
             "<th>Item code</th><th>Description</th><th class='r'>Quantity</th><th class='r'>Unit price</th>"
             f"<th class='r'>Amount</th><th class='r'>PO line</th></tr></thead><tbody>{body}</tbody></table>")
    st.caption("Printed values are kept exactly as read, next to the normalized values the checks use.")


def _stage_output(run: dict, key: str) -> dict:
    s = next((s for s in run["stages"] if s["stage_key"] == key and s["output_json"]), None)
    return json.loads(s["output_json"]) if s else {}


def _dec(v) -> str:
    return format_inr(Decimal(v)) if v not in (None, "") else "—"


def _vendor_po(run: dict, key: str) -> None:
    inv = run.get("invoice") or {}
    v = repo.get_vendor(inv["vendor_id"]) if inv.get("vendor_id") else None
    po = repo.get_purchase_order(inv["po_number"]) if inv.get("po_number") else None
    left, right = st.columns(2, gap="large")
    with left:
        html("<h4>Approved vendor record</h4>")
        if v:
            facts([("Vendor ID", v.vendor_id), ("Legal name", v.legal_vendor_name),
                   ("Also known as", ", ".join(v.aliases) or "—"), ("GSTIN", v.gstin or "—"),
                   ("Status", v.status), ("Payment terms", v.payment_terms)])
        else:
            st.caption("No approved vendor record matched this invoice.")
    with right:
        html("<h4>Purchase order</h4>")
        if po:
            facts([("PO number", po.po_number), ("Vendor", po.vendor_id), ("PO date", po.po_date),
                   ("Status", po.po_status), ("Value before tax", format_inr(po.subtotal)),
                   ("Value with tax", format_inr(po.total_po_amount)),
                   ("Tolerance", f"Pass up to {po.tolerance_pct}%, review up to 10%, block above")])
        else:
            st.caption("No purchase order matched this invoice.")
    if not po:
        return
    fin = _stage_output(run, "financial")
    if fin:
        html("<h4 style='margin-top:1.2rem !important'>PO balance when this invoice was checked</h4>"
             "<table class='ledger' style='max-width:560px'><tbody>"
             f"<tr><td>PO value before tax</td><td class='r'>{_dec(fin.get('po_subtotal'))}</td></tr>"
             f"<tr><td>Less: previously invoiced</td><td class='r'>{_dec(fin.get('previously_invoiced'))}</td></tr>"
             f"<tr><td>Less: this invoice before tax</td><td class='r'>{_dec(fin.get('this_invoice_pre_tax'))}</td></tr>"
             f"<tr class='total'><td>Remaining after this invoice</td><td class='r'>{_dec(fin.get('remaining_after'))}</td></tr>"
             "</tbody></table>")
        st.caption("Amounts before tax are compared with the PO's value before tax; tax is checked separately.")
    inv_by_po = {li["matched_po_line"]: li for li in run["line_items"] if li["matched_po_line"]}
    body = ""
    for pl in po.lines:
        li = inv_by_po.get(pl.line_no)
        body += (f"<tr><td>{pl.line_no}</td><td>{escape(pl.item_description)}</td>"
                 f"<td class='r'>{pl.quantity_ordered}</td><td class='r'>{escape(li['quantity']) if li else '—'}</td>"
                 f"<td class='r'>{format_inr(pl.unit_price)}</td><td class='r'>{inr_paise(li['unit_price_paise']) if li else '—'}</td>"
                 f"<td class='r'>{inr_paise(li['amount_paise']) if li else '—'}</td></tr>")
    html("<h4 style='margin-top:1.2rem !important'>Invoice lines against PO lines</h4><table class='ledger'>"
         "<thead><tr><th>PO line</th><th>Item</th><th class='r'>Ordered</th><th class='r'>Invoiced</th>"
         "<th class='r'>PO price</th><th class='r'>Invoice price</th><th class='r'>Invoice amount</th></tr></thead>"
         f"<tbody>{body}</tbody></table>")


def _log(run: dict) -> None:
    total = sum(s["duration_ms"] or 0 for s in run["stages"])
    html(f'<div class="slip-head"><b>Routing slip</b><span>{total} ms processing time</span></div>'
         + "".join(step_row(s["seq"], s["status"], s["stage_name"], s["message"], s["duration_ms"])
                   for s in run["stages"]))
    st.caption(f"Run {run['run_id']}. The uploaded file is not stored; only its fingerprint is kept for "
               f"duplicate detection ({run['file_sha256'][:16]}…).")
    with st.expander("Technical details for each stage"):
        for s in run["stages"]:
            if s["output_json"]:
                st.markdown(f"**{s['stage_name']}**")
                st.json(json.loads(s["output_json"]), expanded=False)


@st.dialog("Invoice record", width="large")
def open_run_dialog(run_id: str) -> None:
    render_run_detail(run_id, key="dialog")
