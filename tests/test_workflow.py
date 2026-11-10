"""Human approval workflow: statuses, permissions, PO balance effect, due dates, flags."""
from datetime import date
from decimal import Decimal as D

from config import settings
from database import repository as repo
from services import workflow as wf
from services.pipeline import run_pipeline


def _run(name):
    return run_pipeline(name, (settings.SAMPLE_DIR / name).read_bytes())


def test_status_mapping_and_permissions():
    ready = {"run_status": "COMPLETED", "decision": "READY_FOR_APPROVAL"}
    review = {"run_status": "COMPLETED", "decision": "NEEDS_REVIEW"}
    blocked = {"run_status": "COMPLETED", "decision": "BLOCKED"}
    assert [wf.status_of(r) for r in (ready, review, blocked)] == ["READY", "NEEDS_REVIEW", "BLOCKED"]
    assert wf.can_approve(ready)[0] and wf.can_approve(review)[0] and not wf.can_approve(blocked)[0]
    assert wf.note_required_to_approve(review) and not wf.note_required_to_approve(ready)
    assert wf.status_of({**ready, "approval_status": "REJECTED"}) == "REJECTED"
    assert not wf.can_reject({**ready, "approval_status": "APPROVED"})


def test_rejecting_a_ready_invoice_returns_po_balance(fresh_db):
    r = _run("dell_inv_00418.pdf")
    assert repo.get_purchase_order("PO-2026-0001").remaining_balance == 0
    repo.set_approval(r.run_id, "REJECTED", "Goods returned")
    assert repo.get_purchase_order("PO-2026-0001").remaining_balance == D("945000.00")
    assert wf.status_of(repo.get_run(r.run_id)) == "REJECTED"


def test_approving_a_review_invoice_draws_down_po_and_closes_exceptions(fresh_db):
    r = _run("hp_inv_77104.pdf")
    before = repo.get_purchase_order("PO-2026-0003").remaining_balance
    assert repo.list_open_exceptions()
    repo.set_approval(r.run_id, "APPROVED", "Price increase agreed by buyer")
    assert repo.get_purchase_order("PO-2026-0003").remaining_balance == before - D("124800.00")
    assert repo.list_open_exceptions() == []
    actions = [a["action"] for a in repo.get_run(r.run_id)["reviews"]]
    assert actions == ["APPROVE"]


def test_notes_are_logged(fresh_db):
    r = _run("dell_inv_00418.pdf")
    repo.add_note(r.run_id, "Checked with stores")
    assert repo.get_run(r.run_id)["reviews"][0]["reason"] == "Checked with stores"


def test_due_dates():
    assert wf.due_of("2026-10-14", "2026-11-13", "Net 30").source == "invoice"
    d = wf.due_of("2026-10-16", None, "Net 45")
    assert d.date == date(2026, 11, 30) and d.source == "terms"
    assert d.label(date(2026, 11, 25)) == "Due in 5d" and d.label(date(2026, 12, 2)) == "Overdue 2d"


def test_flags_are_short_and_blocking_first():
    out = wf.flags([("line1_price", "WARN"), ("po_balance", "WARN"), ("duplicate", "FAIL"), ("line2_price", "WARN")])
    assert out == [("Duplicate", "FAIL"), ("Price variance", "WARN"), ("Over PO value", "WARN")]


def test_field_positions_are_recorded(fresh_db):
    r = _run("dell_inv_00418.pdf")
    box = r.draft.header["invoice_number"].bbox
    assert box and 0 < box[0] < box[2] < 1 and 0 < box[1] < box[3] < 1
    assert all(li.bbox for li in r.draft.line_items)
