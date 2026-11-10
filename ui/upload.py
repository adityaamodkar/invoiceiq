"""Upload: add an invoice, watch it being processed, then open it."""
from __future__ import annotations

import hashlib
from html import escape

import streamlit as st

from config import settings
from database import repository as repo
from scripts.generate_samples import SPECS
from services import ocr_service
from services import workflow as wf
from services.pipeline import STAGES, StageEvent, run_pipeline
from ui import docstore
from ui.components import badge, card, empty, flag_chips, header, html, inr

SAMPLES = {s["file"]: s for s in SPECS}


def _step(seq: int, status: str, name: str, msg: str, ms: int | None) -> str:
    icon = {"COMPLETED": "✓", "FAILED": "✕"}.get(status, "")
    t = f"{ms} ms" if ms is not None and status in ("COMPLETED", "FAILED") else ""
    m = f'<div class="m">{escape(msg)}</div>' if msg and status not in ("PENDING",) else ""
    return (f'<div class="st {status}"><div class="i">{icon}</div><div><div class="n">{escape(name)}</div>{m}</div>'
            f'<div class="ms">{t}</div></div>')


def _process(name: str, data: bytes) -> str:
    docstore.remember(hashlib.sha256(data).hexdigest(), data)
    with card("live"):
        head = st.empty()
        head.markdown("<h3>Processing</h3>", unsafe_allow_html=True)
        slots = [st.empty() for _ in STAGES]
        for i, (_, n) in enumerate(STAGES):
            slots[i].markdown(_step(i, "PENDING", n, "", None), unsafe_allow_html=True)

        def on_event(e: StageEvent) -> None:
            slots[e.seq].markdown(_step(e.seq, e.status, e.name, e.message, e.duration_ms), unsafe_allow_html=True)
            if e.status == "RUNNING":
                head.markdown(f"<h3>Processing <span class='muted small'>step {e.seq + 1} of {len(STAGES)}</span></h3>",
                              unsafe_allow_html=True)

        r = run_pipeline(name, data, on_event=on_event, pace_seconds=settings.DEMO_PACE_SECONDS,
                         uploaded_at=repo.now_iso())
    return r.run_id


def _result(run_id: str) -> None:
    run = repo.get_run(run_id)
    if not run:
        return
    inv = run.get("invoice") or {}
    status = wf.status_of(run)
    flags = [(x["check_key"], x["outcome"]) for x in run["results"] if x["outcome"] != "PASS"]
    with card("result"):
        a, b = st.columns([3, 1.2], vertical_alignment="center")
        with a:
            html(f"<div style='display:flex;gap:.6rem;align-items:center'><b style='font-size:1.05rem'>"
                 f"{escape(inv.get('vendor_name') or run['file_name'])}</b>{badge(status)}</div>"
                 f"<div class='small muted' style='margin-top:.15rem'>{escape(inv.get('invoice_number') or '')}"
                 f"&nbsp;&nbsp;{inr(inv.get('total_paise'))}</div>"
                 f"<div style='margin-top:.4rem'>{flag_chips(flags, 4)}</div>")
        with b:
            st.page_link(st.session_state["pages"]["invoice"], label="Open invoice", icon=":material/arrow_outward:",
                         query_params={"id": run_id})


def _batch() -> None:
    ids = []
    prog = st.progress(0.0)
    for i, spec in enumerate(SPECS):
        prog.progress(i / len(SPECS), text=f"Processing {spec['label']}")
        if spec["render"] != "pdf" and not ocr_service.is_available():
            continue
        data = (settings.SAMPLE_DIR / spec["file"]).read_bytes()
        docstore.remember(hashlib.sha256(data).hexdigest(), data)
        ids.append(run_pipeline(spec["file"], data, uploaded_at=repo.now_iso()).run_id)
    prog.empty()
    st.session_state["batch_ids"] = ids


def _batch_results() -> None:
    runs = [r for r in (repo.get_run(i) for i in st.session_state.get("batch_ids", [])) if r]
    if not runs:
        return
    with card("batch"):
        with st.container(horizontal=True, vertical_alignment="center", key="batch_head"):
            html(f"<h3 style='margin:0 !important'>Test set processed <span class='muted small'>{len(runs)} invoices</span></h3>")
            if st.button("Clear", key="batch_clear"):
                st.session_state.pop("batch_ids", None)
                st.rerun()
        for r in runs:
            inv = r.get("invoice") or {}
            flags = [(x["check_key"], x["outcome"]) for x in r["results"] if x["outcome"] != "PASS"]
            with st.container(key=f"row_b_{r['run_id']}"):
                c = st.columns([2.8, 1.2, 1.3, 2.4], vertical_alignment="top")
                with c[0]:
                    st.page_link(st.session_state["pages"]["invoice"], label=inv.get("vendor_name") or r["file_name"],
                                 query_params={"id": r["run_id"]})
                    html(f"<div class='rc' style='margin-top:-.55rem;padding-top:0'><span class='sub'>"
                         f"{escape(inv.get('invoice_number') or '')}</span></div>")
                c[1].markdown(f"<div class='rc r'>{inr(inv.get('total_paise'))}</div>", unsafe_allow_html=True)
                c[2].markdown(f"<div class='rc'>{badge(wf.status_of(r))}</div>", unsafe_allow_html=True)
                c[3].markdown(f"<div class='rc wrap'>{flag_chips(flags, 3)}</div>", unsafe_allow_html=True)
                html("<div class='rr'></div>")


def render() -> None:
    header("Upload")
    if not ocr_service.is_available():
        st.warning("Tesseract OCR is not installed, so scanned PDFs and photos can't be read. Digital PDFs work.")
    if st.session_state.pop("run_batch", False):
        _batch()
    _batch_results()

    if st.session_state.get("done") and not repo.get_run(st.session_state["done"]):
        st.session_state.pop("done", None)  # the processed invoice was deleted since

    left, right = st.container(key="stack_upload").columns([1, 1.1], gap="large")
    with left:
        # The key changes on "Upload another", which is the only way to empty Streamlit's uploader.
        up = st.file_uploader("Invoice", type=["pdf", "png", "jpg", "jpeg"], label_visibility="collapsed",
                              help=f"PDF, PNG or JPG up to {settings.MAX_UPLOAD_MB} MB",
                              key=f"uploader_{st.session_state.get('uploader_n', 0)}")
        if up is not None and st.session_state.get("doc", {}).get("key") != f"u:{up.file_id}":
            st.session_state["doc"] = {"key": f"u:{up.file_id}", "name": up.name, "data": up.getvalue()}
            st.session_state.pop("done", None)
        with st.expander("Test invoices"):
            choice = st.selectbox("Test invoice", list(SAMPLES), label_visibility="collapsed",
                                  format_func=lambda f: f"{SAMPLES[f]['label']}  ({SAMPLES[f]['medium']})")
            c1, c2 = st.columns(2)
            if c1.button("Use this file", width="stretch"):
                st.session_state["doc"] = {"key": f"s:{choice}:{repo.now_iso()}", "name": choice,
                                           "data": (settings.SAMPLE_DIR / choice).read_bytes()}
                st.session_state.pop("done", None)
                # Empty the uploader, otherwise a file still sitting in it would replace this choice on the next run.
                st.session_state["uploader_n"] = st.session_state.get("uploader_n", 0) + 1
                st.rerun()
            if c2.button(f"Process all {len(SPECS)}", width="stretch"):
                st.session_state["run_batch"] = True
                st.rerun()
        doc = st.session_state.get("doc")
        if doc:
            done = st.session_state.get("done")
            html(f"<div class='small' style='margin:.6rem 0 .5rem'><b>{escape(doc['name'])}</b>"
                 f"<span class='muted'>&nbsp;&nbsp;{len(doc['data']) / 1024:.0f} KB</span></div>")
            if done:
                if st.button("Upload another", icon=":material/add:", width="stretch", key="upload_another"):
                    for k in ("doc", "done"):
                        st.session_state.pop(k, None)
                    st.session_state["uploader_n"] = st.session_state.get("uploader_n", 0) + 1
                    st.rerun()
            elif st.button("Process invoice", type="primary", width="stretch", key="process_btn"):
                st.session_state["go"] = True
                st.rerun()
    with right:
        if doc and st.session_state.pop("go", False):
            st.session_state["done"] = _process(doc["name"], doc["data"])
            st.rerun()
        elif doc and st.session_state.get("done"):
            _result(st.session_state["done"])
            run = repo.get_run(st.session_state["done"])
            if run:
                with st.expander("Processing steps"):
                    html("".join(_step(s["seq"], s["status"], s["stage_name"], s["message"] or "", s["duration_ms"])
                                 for s in run["stages"]))
        elif doc:
            b64, _ = docstore.page_image_b64(hashlib.sha256(doc["data"]).hexdigest(), doc["data"], 1)
            html(f'<div class="doc"><img src="data:image/jpeg;base64,{b64}"></div>')
        else:
            empty("No file selected", "Drop a PDF or image, or pick a test invoice.")
