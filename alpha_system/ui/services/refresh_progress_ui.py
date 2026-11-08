"""갱신 버튼 옆·아래 인라인 진행도 (백그라운드 job · Soft/target 불변)."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Optional

import streamlit as st

from alpha_system.ui.services.background_job import (
    elapsed_sec,
    progress_fraction,
    reap_job,
)


def _root() -> Path:
    raw = st.session_state.get("_dashboard_root")
    if raw:
        return Path(str(raw))
    return Path(__file__).resolve().parents[3]


def _fmt_elapsed(sec: int) -> str:
    sec = max(0, int(sec))
    if sec < 60:
        return f"{sec}초"
    mins, rem = divmod(sec, 60)
    if mins < 60:
        return f"{mins}분 {rem}초" if rem else f"{mins}분"
    hours, mins = divmod(mins, 60)
    return f"{hours}시간 {mins}분"


def _pct_label(frac: float) -> str:
    return f"{int(round(min(1.0, max(0.0, frac)) * 100))}%"


def render_inline_job_progress(
    root: Path,
    *,
    kind: Optional[str] = None,
) -> bool:
    """버튼 바로 아래. 해당 kind(또는 아무) 작업 중이면 True."""
    st.session_state["_dashboard_root"] = str(Path(root))
    if kind:
        st.session_state["_inline_job_kind_filter"] = str(kind)
    else:
        st.session_state.pop("_inline_job_kind_filter", None)
    job = reap_job(Path(root))
    if job is None or not job.busy:
        return False
    if kind and str(job.kind or "") != str(kind):
        return False
    _render_running_inline_fragment()
    return True


@st.fragment(run_every=2.0)
def _render_running_inline_fragment() -> None:
    root = _root()
    job = reap_job(root)
    kind_filter = st.session_state.get("_inline_job_kind_filter")
    if job is None or not job.busy:
        st.rerun(scope="app")
        return
    if kind_filter and str(job.kind or "") != str(kind_filter):
        st.rerun(scope="app")
        return
    frac = progress_fraction(job)
    elapsed = elapsed_sec(job)
    phase = (job.phase or "실행").strip()
    st.markdown(
        f'<div class="saa-refresh-prog" role="status" aria-live="polite">'
        f'<div class="saa-refresh-prog-h">'
        f'<span class="saa-refresh-prog-lab">{escape(str(job.label))}</span>'
        f'<span class="saa-refresh-prog-pct">{_pct_label(frac)}</span>'
        f"</div>"
        f'<div class="saa-refresh-prog-phase">{escape(phase)}</div>'
        f'<div class="saa-refresh-prog-meta">'
        f"경과 {_fmt_elapsed(elapsed)} · 예상 약 {max(1, int(job.typical_sec or 600) // 60)}분"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.progress(min(1.0, max(0.0, frac)), text=f"{phase} · {_pct_label(frac)}")


__all__ = [
    "render_inline_job_progress",
]
