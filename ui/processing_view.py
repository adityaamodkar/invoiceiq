"""Live routing slip: each step updates the moment the pipeline reports it."""
from __future__ import annotations

import streamlit as st

from services.pipeline import STAGES, PipelineResult, StageEvent, run_pipeline
from ui.components import sheet, html, step_row


def run_live(file_name: str, data: bytes, uploaded_at: str, pace_seconds: float) -> PipelineResult:
    with sheet("processing_view_1"):
        head = st.empty()
        head.markdown('<div class="slip-head"><b>Routing slip</b><span>Starting</span></div>',
                      unsafe_allow_html=True)
        slots = [st.empty() for _ in STAGES]

    def on_event(e: StageEvent) -> None:
        slots[e.seq].markdown(step_row(e.seq, e.status, e.name, e.message, e.duration_ms), unsafe_allow_html=True)
        if e.status == "RUNNING":
            head.markdown(f'<div class="slip-head"><b>Routing slip</b><span>Step {e.seq + 1} of {len(STAGES)}'
                          f'</span></div>', unsafe_allow_html=True)

    result = run_pipeline(file_name, data, on_event=on_event, pace_seconds=pace_seconds, uploaded_at=uploaded_at)
    total = sum(e.duration_ms or 0 for e in result.events)
    done = "Finished" if result.run_status == "COMPLETED" else "Stopped"
    head.markdown(f'<div class="slip-head"><b>Routing slip</b><span>{done} in {total} ms</span></div>',
                  unsafe_allow_html=True)
    return result


__all__ = ["run_live", "html"]
