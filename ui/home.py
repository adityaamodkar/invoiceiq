"""Home: the AP workload at a glance."""
from __future__ import annotations

from datetime import datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import settings
from database import repository as repo
from services import workflow as wf
from services.normalizers import format_inr
from ui.components import badge, card, empty, flag_chips, header, html, inr, today
from ui.inbox import load_rows
from ui.theme import chart_colors

COLOR = {"NEEDS_REVIEW": "#D08A00", "READY": "#3149C9", "BLOCKED": "#B42318", "UNREADABLE": "#9A9AA0",
         "APPROVED": "#2F9E63", "REJECTED": "#C9C9C4"}


def _link(run_id: str, label: str) -> None:
    st.page_link(st.session_state["pages"]["invoice"], label=label, query_params={"id": run_id})


def _kpis(rows: list[dict]) -> None:
    def agg(sts):
        sel = [r for r in rows if r["status"] in sts]
        return len(sel), sum(r["total_paise"] or 0 for r in sel)
    month = today().strftime("%Y-%m")
    appr = [r for r in rows if r["status"] == "APPROVED" and (r.get("approval_at") or "")[:7] == month]
    decided = [r for r in rows if r["run_status"] == "COMPLETED"]
    touchless = sum(r["decision"] == "READY_FOR_APPROVAL" for r in decided)
    rate = f"{100 * touchless / len(decided):.0f}%" if decided else "—"
    cards = [("Needs review", COLOR["NEEDS_REVIEW"], *agg(["NEEDS_REVIEW"])),
             ("Ready to approve", COLOR["READY"], *agg(["READY"])),
             ("Blocked", COLOR["BLOCKED"], *agg(["BLOCKED", "UNREADABLE"])),
             ("Approved this month", COLOR["APPROVED"], len(appr), sum(r["total_paise"] or 0 for r in appr))]
    body = "".join(f'<div class="kpi"><div class="l"><i style="background:{c}"></i>{l}</div><div class="v">{n}</div>'
                   f'<div class="s">{inr(v)}</div></div>' for l, c, n, v in cards)
    body += (f'<div class="kpi"><div class="l">Touchless rate</div><div class="v">{rate}</div>'
             f'<div class="s">{touchless} of {len(decided)} passed all checks</div></div>')
    html(f'<div class="kpi-wrap"><div class="kpis">{body}</div></div>')


def _attention(rows: list[dict]) -> None:
    html("<h3>Needs attention</h3>")
    items = [r for r in rows if r["status"] in ("BLOCKED", "NEEDS_REVIEW", "UNREADABLE")]
    items.sort(key=lambda r: (r["status"] != "BLOCKED", r["due"].date or today()))
    if not items:
        empty("All clear", "No invoice is waiting for review.")
        return
    for r in items[:6]:
        with st.container(key=f"row_att_{r['run_id']}"):
            a, b, c = st.columns([2.2, 1.15, 1.15], vertical_alignment="top")
            with a:
                _link(r["run_id"], r["vendor_name"] or r["file_name"])
                html(f"<div class='rc wrap' style='margin-top:-.55rem;padding-top:0'><span class='sub'>"
                     f"{escape(r['invoice_number'] or '')}</span><div style='margin-top:.25rem'>{flag_chips(r['flags'], 2)}</div></div>")
            b.markdown(f"<div class='rc'>{badge(r['status'])}<div class='sub' style='margin-top:.2rem'>"
                       f"{escape(r['due'].label(today()))}</div></div>", unsafe_allow_html=True)
            c.markdown(f"<div class='rc r'>{inr(r['total_paise'])}</div>", unsafe_allow_html=True)
            html("<div class='rr'></div>")
    if len(items) > 6:
        st.page_link(st.session_state["pages"]["invoices"], label=f"View all {len(items)}")


def _due(rows: list[dict]) -> None:
    html("<h3>Due in the next 14 days</h3>")
    horizon = today() + timedelta(days=14)
    dupes = repo.exact_duplicate_run_ids()  # a second copy of a bill is not a second payment falling due
    items = [r for r in rows if r["due"].date and r["due"].date <= horizon
             and r["status"] not in ("REJECTED", "UNREADABLE") and r["run_id"] not in dupes]
    items.sort(key=lambda r: r["due"].date)
    if not items:
        empty("Nothing due", "No open invoice falls due in the next 14 days.")
        return
    body = "".join(
        f"<tr><td class='main'>{escape(r['vendor_name'] or '')}<div class='sub'>{escape(r['invoice_number'] or '')}</div></td>"
        f"<td class='nw' style='{'color:var(--blocked);font-weight:600' if r['due'].date < today() else ''}'>{escape(r['due'].label(today()))}"
        f"<div class='sub'>{r['due'].date.strftime('%d %b')}</div></td>"
        f"<td class='r'>{inr(r['total_paise'])}</td></tr>" for r in items[:7])
    html(f"<table class='tbl'><tbody>{body}</tbody></table>")


def _value_by_status(rows: list[dict]) -> None:
    html("<h3>Invoice value by status</h3>")
    order = ["NEEDS_REVIEW", "READY", "BLOCKED", "APPROVED", "REJECTED", "UNREADABLE"]
    vals = {s: sum(r["total_paise"] or 0 for r in rows if r["status"] == s) for s in order}
    cnt = {s: sum(r["status"] == s for r in rows) for s in order}
    top = max(vals.values()) or 1
    body = "".join(
        f"<tr><td class='nw' style='width:1%'>{badge(s)}</td><td><div class='bar'><span style='width:{100 * vals[s] / top:.1f}%;"
        f"background:{COLOR[s]}'></span></div></td><td class='r' style='width:1%'>{cnt[s]}</td>"
        f"<td class='r' style='width:1%'>{inr(vals[s])}</td></tr>" for s in order if cnt[s])
    html(f"<table class='tbl'><tbody>{body}</tbody></table>")


def _by_vendor(rows: list[dict]) -> None:
    html("<h3>Billed by vendor</h3>")
    dupes = repo.exact_duplicate_run_ids()
    df = pd.DataFrame([r for r in rows if r["vendor_name"] and r["status"] != "REJECTED" and r["run_id"] not in dupes])
    if df.empty:
        empty("No vendor activity yet")
        return
    g = df.groupby("vendor_name")["total_paise"].agg(["sum", "count"]).sort_values("sum", ascending=False).head(6)
    top = g["sum"].max() or 1
    body = "".join(
        f"<tr><td class='main'>{escape(v)}<div class='sub'>{int(c)} invoice{'s' * (c != 1)}</div></td><td style='width:35%'>"
        f"<div class='bar'><span style='width:{100 * s / top:.1f}%'></span></div></td><td class='r'>{inr(int(s))}</td></tr>"
        for v, (s, c) in g.iterrows())
    html(f"<table class='tbl'><tbody>{body}</tbody></table>")
    st.caption("Excludes rejected invoices and duplicate submissions.")


def _po_util() -> None:
    html("<h3>Purchase order utilisation</h3>")
    pos = [p for p in repo.list_purchase_orders() if p.po_status.lower() != "closed"]
    body = ""
    for p in pos:
        before = float(p.baseline_invoiced / p.subtotal) if p.subtotal else 0
        here = float(p.invoiced_in_system / p.subtotal) if p.subtotal else 0
        used = before + here
        body += (f"<tr><td class='nw'>{escape(p.po_number)}<div class='sub'>{escape(p.vendor_id)}</div></td><td style='width:38%'>"
                 f"<div class='bar'><span class='before' style='width:{min(before, 1) * 100:.0f}%'></span>"
                 f"<span style='width:{max(0, min(here, 1 - before)) * 100:.0f}%'></span></div></td>"
                 f"<td class='r'>{used:.0%}</td><td class='r'>{format_inr(abs(p.remaining_balance))}<div class='sub'>{'over' if p.remaining_balance < 0 else 'left'}</div></td></tr>")
    html(f"<table class='tbl'><tbody>{body}</tbody></table>"
         "<div class='key'><span><i style='background:var(--bar-before)'></i>Before InvoiceIQ</span>"
         "<span><i style='background:var(--bar)'></i>In InvoiceIQ</span></div>")


def _volume(rows: list[dict]) -> None:
    html("<h3>Invoices processed, last 14 days</h3>")
    tz = ZoneInfo(settings.DISPLAY_TZ)
    days = [today() - timedelta(days=i) for i in range(13, -1, -1)]
    df = pd.DataFrame([{"d": datetime.fromisoformat(r["started_at"]).astimezone(tz).date(), "s": r["status"]} for r in rows])
    fig = go.Figure()
    busiest = max((int((df["d"] == d).sum()) for d in days), default=0) if not df.empty else 0
    for s in ["APPROVED", "READY", "NEEDS_REVIEW", "BLOCKED", "REJECTED", "UNREADABLE"]:
        y = [int(((df["d"] == d) & (df["s"] == s)).sum()) for d in days] if not df.empty else [0] * len(days)
        if any(y):
            fig.add_bar(x=[d.strftime("%d %b") for d in days], y=y, name=wf.STATUS_LABEL[s], marker_color=COLOR[s],
                        hovertemplate=f"{wf.STATUS_LABEL[s]}: %{{y}}<extra></extra>")
    fig.update_layout(barmode="stack", height=230, margin=dict(l=0, r=0, t=4, b=0), bargap=0.45,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Hanken Grotesk, system-ui, sans-serif", size=12, color=chart_colors()["font"]),
                      legend=dict(orientation="h", y=-0.22, x=0, font=dict(size=11)))
    # whole-number ticks, at most about six of them however busy the day was
    fig.update_yaxes(gridcolor=chart_colors()["grid"], dtick=max(1, -(-busiest // 6)), zeroline=False)
    fig.update_xaxes(tickfont=dict(size=10))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def render() -> None:
    if header("Home", today().strftime("%A, %d %B %Y"), action="Upload invoice"):
        st.switch_page(st.session_state["pages"]["upload"])
    rows = load_rows()
    if not rows:
        empty("No invoices yet", "Upload an invoice or process the test set to get started.")
        return
    _kpis(rows)
    # "stack_" containers: their columns sit side by side on a wide screen and one under the other on a narrow one.
    with st.container(key="stack_home_a"):
        a, b = st.columns([1.35, 1], gap="medium")
        with a, card("attention"):
            _attention(rows)
        with b, card("due"):
            _due(rows)
    with st.container(key="stack_home_b"):
        a, b = st.columns(2, gap="medium")
        with a, card("status"):
            _value_by_status(rows)
        with b, card("vendor"):
            _by_vendor(rows)
    with st.container(key="stack_home_c"):
        a, b = st.columns(2, gap="medium")
        with a, card("po"):
            _po_util()
        with b, card("volume"):
            _volume(rows)
