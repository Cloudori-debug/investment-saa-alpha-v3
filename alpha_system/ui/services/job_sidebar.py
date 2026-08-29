"""Sidebar long-job gauge — visible on every page."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from alpha_system.ui.services.background_job import (
    JobStatus,
    ended_age_sec,
    elapsed_sec,
    progress_fraction,
    reap_job,
    request_cancel,
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


def render_job_sidebar() -> None:
    root = _root()
    job = reap_job(root)
    if job is None:
        return
    if job.busy:
        _render_running_fragment()
        return
    _render_finished(job)


@st.fragment(run_every=2.0)
def _render_running_fragment() -> None:
    root = _root()
    job = reap_job(root)
    if job is None or not job.busy:
        st.rerun(scope="app")
        return
    frac = progress_fraction(job)
    elapsed = elapsed_sec(job)
    typical = int(job.typical_sec or 600)
    st.markdown(f"**{job.label}**")
    st.caption(f"진행 중 · {job.phase or '실행'} · {_fmt_elapsed(elapsed)}")
    st.progress(min(1.0, max(0.0, frac)))
    st.caption(
        f"예상 {typical // 60}분 안팎 · 다른 메뉴로 옮겨도 계속됩니다. "
        "일시정지·이어서 실행은 없습니다."
    )
    if st.button("작업 중단", key="saa_job_cancel", use_container_width=True):
        err = request_cancel(root)
        if err:
            st.warning(err)
        else:
            st.rerun(scope="app")


def _render_finished(job: JobStatus) -> None:
    if job.ended_at and ended_age_sec(job) > 180:
        return
    if job.state == "cancelled":
        st.warning(f"{job.label} 중단됨")
        return
    if job.ok:
        st.success(f"{job.label} 완료")
        if job.message:
            st.caption(job.message)
        return
    st.error(f"{job.label} 실패")
    if job.message:
        st.caption(job.message)
