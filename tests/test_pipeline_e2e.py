"""End-to-end: the real sample PDF through all ten stages into SQLite."""
from database import repository as repo
from services.pipeline import run_pipeline


def test_happy_path_end_to_end(fresh_db, sample_bytes):
    seen = []
    r = run_pipeline("dell_invoice_00418.pdf", sample_bytes, on_event=lambda e: seen.append((e.key, e.status)))
    assert r.run_status == "COMPLETED"
    assert r.decision.status.value == "READY_FOR_APPROVAL"
    # Every stage reported RUNNING before COMPLETED (live execution, not a replay)
    for key in ("received", "text", "vendor", "po", "financial", "duplicate", "decision", "audit"):
        assert seen.index((key, "RUNNING")) < seen.index((key, "COMPLETED"))

    stored = repo.get_run(r.run_id)
    assert stored["decision"] == "READY_FOR_APPROVAL"
    assert stored["invoice"]["invoice_number"] == "DELL/INV/2026/00418"
    assert stored["invoice"]["total_paise"] == 111510000
    assert len(stored["stages"]) == 10 and all(s["status"] == "COMPLETED" for s in stored["stages"])
    assert len(stored["line_items"]) == 2 and stored["line_items"][0]["matched_po_line"] == 1
    assert stored["exceptions"] == []

    # The PO balance is now consumed by this invoice
    po = repo.get_purchase_order("PO-2026-0001")
    assert po.remaining_balance == 0


def test_reupload_does_not_create_second_approval(fresh_db, sample_bytes):
    first = run_pipeline("dell_invoice_00418.pdf", sample_bytes)
    second = run_pipeline("dell_invoice_00418.pdf", sample_bytes)
    assert second.decision.status.value == "BLOCKED"
    assert second.decision.reason.startswith("Exact duplicate")
    ready = [r for r in repo.list_runs() if r["decision"] == "READY_FOR_APPROVAL"]
    assert [r["run_id"] for r in ready] == [first.run_id]
    assert repo.list_open_exceptions()                     # blocked run lands in the queue


def test_corrupt_document_fails_visibly_and_is_recorded(fresh_db):
    r = run_pipeline("broken.pdf", b"%PDF-1.4 not really a pdf")
    assert r.run_status == "FAILED"
    stages = {e.key: e.status for e in r.events}
    assert stages["validation"] == "FAILED" and stages["decision"] == "SKIPPED"
    stored = repo.get_run(r.run_id)
    assert stored["run_status"] == "FAILED" and stored["failure_stage"] == "Document validation"
    assert [s["status"] for s in stored["stages"]][1:3] == ["FAILED", "SKIPPED"]   # skips are audited too
    queue = repo.list_open_exceptions()                    # a person must act on it
    assert queue and queue[0]["category"] == "Document"


def test_deleting_a_run_removes_its_records_and_frees_po_balance(fresh_db, sample_bytes):
    first = run_pipeline("dell.pdf", sample_bytes)
    second = run_pipeline("dell.pdf", sample_bytes)                       # blocked duplicate
    assert repo.get_purchase_order("PO-2026-0001").remaining_balance == 0
    assert repo.delete_runs([second.run_id]) == 1
    assert repo.get_run(second.run_id) is None and repo.list_open_exceptions() == []
    assert repo.get_run(first.run_id) is not None                         # others untouched
    repo.delete_runs([first.run_id])
    assert repo.get_purchase_order("PO-2026-0001").remaining_balance == 945000
    # after deleting the original, the same invoice is no longer a duplicate
    assert run_pipeline("dell.pdf", sample_bytes).decision.status.value == "READY_FOR_APPROVAL"
