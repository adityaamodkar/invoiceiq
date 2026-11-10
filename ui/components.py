"""Shared UI pieces. All dynamic text is HTML-escaped."""
from __future__ import annotations

from datetime import date, datetime
from html import escape
from zoneinfo import ZoneInfo

import streamlit as st

from config import settings
from services import workflow as wf
from services.normalizers import format_inr, from_paise


def html(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def inr(p) -> str:
    return format_inr(from_paise(int(p))) if p is not None else "—"


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(ZoneInfo(settings.DISPLAY_TZ))


def when(iso: str | None) -> str:
    return _dt(iso).strftime("%d %b %Y, %H:%M") if iso else "—"


def day(iso: str | None) -> str:
    return date.fromisoformat(iso[:10]).strftime("%d %b %Y") if iso else "—"


def today() -> date:
    return datetime.now(ZoneInfo(settings.DISPLAY_TZ)).date()


def badge(status: str) -> str:
    return f'<span class="badge b-{escape(status)}">{escape(wf.STATUS_LABEL.get(status, status))}</span>'


def flag_chips(items: list[tuple[str, str]], limit: int = 3) -> str:
    chips = wf.flags(items)
    out = "".join(f'<span class="flag f-{o}">{escape(lbl)}</span>' for lbl, o in chips[:limit])
    if len(chips) > limit:
        out += f'<span class="flag f-WARN">+{len(chips) - limit}</span>'
    return out


def header(title: str, sub: str | None = None, crumb: str | None = None, action: str | None = None) -> bool:
    """Page title. With `action`, a primary button sits on the same line, right-aligned and sized to its label;
    returns True when it is clicked."""
    if crumb:
        html(f'<div class="crumb">{crumb}</div>')
    body = f'<div class="ph"><h1>{escape(title)}</h1></div>' + (f'<div class="ph-sub">{escape(sub)}</div>' if sub else "")
    if not action:
        html(body)
        return False
    slug = title.lower().replace(" ", "_")
    with st.container(horizontal=True, vertical_alignment="center", key=f"head_{slug}"):
        html(body)
        return st.button(action, type="primary", key=f"head_action_{slug}")


def empty(title: str, body: str = "") -> None:
    html(f'<div class="empty"><b>{escape(title)}</b>{escape(body)}</div>')


def card(name: str):
    return st.container(border=True, key=f"card_{name}")


def open_invoice(run_id: str) -> None:
    st.switch_page(st.session_state["pages"]["invoice"], query_params={"id": run_id})


def invoice_link(run_id: str, label: str, key: str) -> None:
    st.page_link(st.session_state["pages"]["invoice"], label=label, query_params={"id": run_id})
