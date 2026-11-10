"""Overview, laid out as an AP daybook. Every figure is computed from stored processing runs."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import settings
from database import repository as repo
from services.normalizers import format_inr, from_paise
from ui.components import sheet, STATUS_LABELS, empty_state, html, inr_paise, mark, run_status_key, when_short
from ui.exceptions import exception_queue
from ui.register import cell, register

STATUS = ["READY_FOR_APPROVAL", "NEEDS_REVIEW", "BLOCKED", "FAILED"]
INK = {"READY_FOR_APPROVAL": "#1C6B3F", "NEEDS_REVIEW": "#9A5B00", "BLOCKED": "#A8231A", "FAILED": "#C46A63"}


def _short(v: Decimal) -> str:
    if v >= 10_000_000:
        return f"₹{v / 10_000_000:.2f} Cr"
    if v >= 100_000:
        return f"₹{v / 100_000:.2f} L"
    return format_inr(v).split(".")[0]


def _load() -> pd.DataFrame | None:
    runs = [r for r in repo.list_runs(current_only=True) if r["run_status"] != "RUNNING"]
    if not runs:
        return None
    df = pd.DataFrame(runs)
    df["status"] = df.apply(run_status_key, axis=1)
    df["dupe"] = df["run_id"].isin(repo.exact_duplicate_run_ids())
    df["value"] = df["total_paise"].map(lambda p: from_paise(int(p)) if pd.notna(p) else Decimal("0"))
    ms = repo.processing_ms_by_run()
    df["ms"] = df["run_id"].map(lambda r: ms.get(r, 0))
    return df


def _daybook(df: pd.DataFrame) -> None:
    uniq = df[~df["dupe"]]
    def n(s): return int((df["status"] == s).sum())
    def v(s): return sum(uniq[uniq["status"] == s]["value"], Decimal("0"))
    decided = int((df["status"] != "FAILED").sum())
    stp = round(100 * n("READY_FOR_APPROVAL") / decided) if decided else 0
    cells = [("Received", None, len(df), sum(uniq["value"], Decimal("0")), "")]
    cells += [(STATUS_LABELS[s], INK[s], n(s), v(s), "") for s in ("READY_FOR_APPROVAL", "NEEDS_REVIEW", "BLOCKED")]
    body = "".join(
        f'<div><div class="lbl">{f"<i style=background:{c}></i>" if c else ""}{escape(lbl)}</div>'
        f'<div class="n">{cnt}</div><div class="val">{_short(val)}</div></div>' for lbl, c, cnt, val, _ in cells)
    body += (f'<div class="stp"><div class="lbl">Straight-through</div><div class="n">{stp}%</div>'
             f'<div class="val">{n("READY_FOR_APPROVAL")} of {decided} needed no person</div></div>')
    html(f'<div class="daybook">{body}</div>')
    notes = []
    if df["dupe"].any():
        notes.append(f"Values leave out {int(df['dupe'].sum())} exact duplicate submission(s).")
    if n("FAILED"):
        notes.append(f"{n('FAILED')} document(s) could not be read.")
    if notes:
        st.caption(" ".join(notes))


def _waiting() -> None:
    html("<h4>Waiting for a decision</h4>")
    queue = exception_queue()
    if not queue:
        st.caption("Nothing is waiting. Every processed invoice passed its checks.")
        return
    rows = [{"run_id": q["run_id"], "inv": cell(q["invoice"], q["vendor"]),
             "out": mark("BLOCKED" if q["blocking"] else "NEEDS_REVIEW") + f"<div class='sub'>{escape(q['amount'])}</div>",
             "why": f"<b>{escape(q['category'])}</b><div class='reason'>{escape(q['action'])}</div>"}
            for q in queue[:4]]
    register(rows, [("Invoice", 2.1, "inv"), ("Status", 1.5, "out"), ("Reason and action", 3.6, "why")], key="dash_wait")
    if len(queue) > 4:
        st.caption(f"{len(queue) - 4} more on the Exceptions page.")


def _bars(items: list[tuple[str, float, str, str]], color: str | None = None) -> str:
    """(label, fraction 0..1, right text, sub text)"""
    out = ""
    for label, frac, right, sub, *c in items:
        col = c[0] if c else color
        out += (f'<div class="barrow"><div class="top"><b>{escape(label)}</b><span class="num">{escape(right)}</span></div>'
                f'<div class="track"><span style="width:{max(0, min(frac, 1)) * 100:.1f}%;background:{col}"></span></div>'
                + (f'<div class="sub">{escape(sub)}</div>' if sub else "") + "</div>")
    return out


def _outcomes(df: pd.DataFrame) -> None:
    html("<h4>Outcomes</h4>")
    uniq = df[~df["dupe"]]
    total = len(df)
    items = []
    for s in STATUS:
        k = int((df["status"] == s).sum())
        if k:
            val = sum(uniq[uniq["status"] == s]["value"], Decimal("0"))
            items.append((STATUS_LABELS[s], k / total, f"{k} of {total}", f"{format_inr(val)} invoice value", INK[s]))
    html(_bars(items))


def _reasons() -> None:
    html("<h4 style='margin-top:1.1rem !important'>Why invoices stop</h4>")
    queue = exception_queue()
    if not queue:
        st.caption("No invoices are waiting.")
        return
    counts = pd.Series([q["category"] for q in queue]).value_counts()
    top = int(counts.max())
    html(_bars([(cat, k / top, str(k), "") for cat, k in counts.items()], "#141B2D"))
    st.caption("Invoices waiting, counted once each by their root cause.")


def _po_drawdown() -> None:
    html("<h4>Purchase orders drawn down</h4>")
    pos = [p for p in repo.list_purchase_orders() if p.invoiced_in_system > 0]
    if not pos:
        st.caption("No purchase order has been drawn down by an approved invoice yet.")
        return
    rows = ""
    for p in pos:
        before = float(p.baseline_invoiced / p.subtotal)
        now = float(p.invoiced_in_system / p.subtotal)
        rows += (f'<div class="barrow"><div class="top"><b>{escape(p.po_number)}</b>'
                 f'<span class="num">{min(before + now, 1):.0%} used</span></div>'
                 f'<div class="track"><span style="width:{before * 100:.1f}%;background:#A9B3C4"></span>'
                 f'<span style="width:{min(now, 1 - before) * 100:.1f}%;background:#2A44A8"></span></div>'
                 f'<div class="sub">{format_inr(p.amount_already_invoiced)} of {format_inr(p.subtotal)} invoiced, '
                 f'{format_inr(p.remaining_balance)} left</div></div>')
    html(rows + '<div class="key"><span><i style="background:#A9B3C4"></i>Invoiced before InvoiceIQ</span>'
                '<span><i style="background:#2A44A8"></i>Approved through InvoiceIQ</span></div>')


def _activity(df: pd.DataFrame) -> None:
    html("<h4>Processing activity</h4>")
    tz = ZoneInfo(settings.DISPLAY_TZ)
    t = df.assign(ts=df["started_at"].map(lambda s: datetime.fromisoformat(s).astimezone(tz)))
    by_day = (t["ts"].max() - t["ts"].min()).days >= 2
    t["bucket"] = t["ts"].map(lambda x: x.strftime("%d %b" if by_day else "%H:00"))
    order = sorted(t["bucket"].unique(), key=lambda b: t[t["bucket"] == b]["ts"].min())
    fig = go.Figure()
    for s in STATUS:
        c = t[t["status"] == s].groupby("bucket").size().reindex(order, fill_value=0)
        if c.sum():
            fig.add_bar(x=order, y=c.values, name=STATUS_LABELS[s], marker_color=INK[s], marker_line_width=0,
                        hovertemplate=f"{STATUS_LABELS[s]}: %{{y}}<extra></extra>")
    fig.update_layout(barmode="stack", bargap=0.6, height=210, margin=dict(l=0, r=0, t=6, b=0),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
                      font=dict(family="Hanken Grotesk, system-ui, sans-serif", color="#141B2D", size=12))
    fig.update_yaxes(gridcolor="#E8EBF0", dtick=1, zeroline=False)
    fig.update_xaxes(showline=True, linecolor="#141B2D")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.caption(f"Invoices per {'day' if by_day else 'hour'}, by outcome. Average processing time "
               f"{df['ms'].mean() / 1000:.1f} s per invoice; scans take longest.")


def _latest(df: pd.DataFrame) -> None:
    html("<h4>Latest entries</h4>")
    head = df.head(10)
    body = "".join(
        f"<tr><td>{escape(when_short(r['started_at']))}</td><td>{escape(r['invoice_number'] or r['file_name'])}</td>"
        f"<td>{escape(r['vendor_name'] or '—')}</td><td>{mark(r['status'])}</td>"
        f"<td class='r'>{inr_paise(r['total_paise'])}{' <span class=muted>(dup.)</span>' if r['dupe'] else ''}</td></tr>"
        for _, r in head.iterrows())
    total = sum(head[~head["dupe"]]["value"], Decimal("0"))
    html("<table class='ledger'><thead><tr><th>Processed</th><th>Invoice</th><th>Vendor</th><th>Outcome</th>"
         f"<th class='r'>Amount</th></tr></thead><tbody>{body}"
         f"<tr class='total'><td colspan='4'>Total of these entries, duplicates excluded</td>"
         f"<td class='r'>{format_inr(total)}</td></tr></tbody></table>")


def render() -> None:
    today = datetime.now(ZoneInfo(settings.DISPLAY_TZ)).strftime("%A %d %B %Y")
    st.markdown("# Overview")
    html(f'<p class="lede">The accounts payable daybook for {today}: what came in, what can be approved, '
         'and what needs a person.</p>')
    df = _load()
    if df is None:
        empty_state("The daybook is empty",
                    "Process an invoice, or run the six test invoices, and this page fills in from the results.")
        st.write("")
        c1, c2, _ = st.columns([1, 1, 2])
        if c1.button("Process an invoice", type="primary", width="stretch"):
            st.switch_page(st.session_state["pages"]["process"])
        if c2.button("Process the six test invoices", width="stretch"):
            st.session_state["batch"] = True
            st.switch_page(st.session_state["pages"]["process"])
        return

    _daybook(df)
    st.write("")
    a, b = st.columns([1.75, 1], gap="medium")
    with a, sheet("dashboard_1"):
        _waiting()
    with b, sheet("dashboard_2"):
        _outcomes(df)
        _reasons()
    a, b = st.columns([1, 1], gap="medium")
    with a, sheet("dashboard_3"):
        _po_drawdown()
    with b, sheet("dashboard_4"):
        _activity(df)
    with sheet("dashboard_5"):
        _latest(df)
