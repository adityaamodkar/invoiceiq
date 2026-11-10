"""Exceptions: invoices waiting for a person, blocking first, each with the reason and the action."""
from __future__ import annotations

from html import escape

import streamlit as st

from database import repository as repo
from services.decision_engine import CATEGORY_PRIORITY
from ui.components import CATEGORY_LABEL, sheet, empty_state, inr_paise, mark, page_header, when_short
from ui.register import cell, register


def exception_queue(ex: list[dict] | None = None) -> list[dict]:
    """One entry per invoice needing a person, led by its root-cause issue."""
    ex = repo.list_open_exceptions() if ex is None else ex
    rank = {c: i for i, c in enumerate(CATEGORY_PRIORITY)}
    by_run: dict[str, list[dict]] = {}
    for e in ex:
        by_run.setdefault(e["run_id"], []).append(e)
    out = []
    for run_id, items in by_run.items():
        items.sort(key=lambda e: (e["severity"] != "CRITICAL", rank.get(e["category"], 99)))
        top = items[0]
        out.append({"run_id": run_id, "invoice": top["invoice_number"] or top["file_name"],
                    "vendor": top["vendor_name"] or "Vendor not read", "amount": inr_paise(top["total_paise"]),
                    "category": CATEGORY_LABEL.get(top["category"], top["category"]),
                    "blocking": top["severity"] == "CRITICAL", "issues": len(items),
                    "received": top["uploaded_at"], "summary": top["summary"] or "",
                    "action": top["suggested_action"] or ""})
    out.sort(key=lambda q: not q["blocking"])
    return out


def render() -> None:
    page_header("Exceptions", "Invoices that need a person. Blocking problems come first; each one says what "
                              "went wrong and what to do about it.")
    queue = exception_queue()
    if not queue:
        empty_state("Nothing is waiting", "Invoices that need review or are blocked will queue here with the action to take.")
        return
    blocking = sum(q["blocking"] for q in queue)
    st.caption(f"{len(queue)} invoice(s) waiting: {blocking} blocked, {len(queue) - blocking} on hold for review.")
    rows = [{
        "run_id": q["run_id"],
        "inv": cell(q["invoice"], q["vendor"]),
        "amt": escape(q["amount"]),
        "out": mark("BLOCKED" if q["blocking"] else "NEEDS_REVIEW"),
        "why": (f"<b>{escape(q['category'])}</b>"
                + (f" <span class='sub'>({q['issues']} findings)</span>" if q["issues"] > 1 else "")
                + f"<div class='reason'>{escape(q['summary'])}</div>"
                + f"<div class='reason' style='color:var(--ink);font-weight:600'>{escape(q['action'])}</div>"),
        "when": when_short(q["received"]),
    } for q in queue]
    with sheet("exceptions_list"):
        register(rows, [("Invoice", 2.0, "inv"), ("Amount>", 1.2, "amt"), ("Status", 1.3, "out"),
                        ("Why it stopped and what to do", 4.4, "why"), ("Received", 1.1, "when")], key="exc")
