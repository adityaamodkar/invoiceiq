"""A ledger-style list of runs. Every row can be opened in full; rows can optionally be selected."""
from __future__ import annotations

from html import escape

import streamlit as st

from ui.invoice_details import open_run_dialog


def register(rows: list[dict], columns: list[tuple[str, float, str]], key: str,
             selectable: bool = False) -> list[str]:
    """
    rows:    dicts with "run_id" and one pre-rendered HTML cell per column key
    columns: (heading, width, column key); a heading ending in ">" is right-aligned
    Returns the run_ids of selected rows (empty when not selectable).
    """
    widths = ([0.35] if selectable else []) + [w for _, w, _ in columns] + [1.0]
    head = st.columns(widths, vertical_alignment="bottom")
    offset = 1 if selectable else 0
    for i, (title, _, _) in enumerate(columns):
        right = title.endswith(">")
        head[i + offset].markdown(
            f"<div class='reg-head' style='text-align:{'right' if right else 'left'}'>{escape(title.rstrip('>'))}</div>",
            unsafe_allow_html=True)
    head[-1].markdown("<div class='reg-head'>&nbsp;</div>", unsafe_allow_html=True)
    if selectable:
        head[0].markdown("<div class='reg-head'>&nbsp;</div>", unsafe_allow_html=True)

    selected = []
    for r in rows:
        cols = st.columns(widths, vertical_alignment="top")
        if selectable and cols[0].checkbox("Select", key=f"{key}_sel_{r['run_id']}", label_visibility="collapsed"):
            selected.append(r["run_id"])
        for i, (title, _, ck) in enumerate(columns):
            cls = "reg-cell r" if title.endswith(">") else "reg-cell"
            cols[i + offset].markdown(f"<div class='{cls}'>{r[ck]}</div>", unsafe_allow_html=True)
        if cols[-1].button("Open", key=f"{key}_open_{r['run_id']}", width="stretch"):
            open_run_dialog(r["run_id"])
        st.markdown("<div class='reg-rule'></div>", unsafe_allow_html=True)
    return selected


def cell(main: str, sub: str | None = None) -> str:
    return escape(main) + (f"<div class='sub'>{escape(sub)}</div>" if sub else "")
