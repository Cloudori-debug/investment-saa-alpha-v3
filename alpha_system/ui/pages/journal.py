"""Journal timeline — read-only (no discretionary / target write forms)."""

from __future__ import annotations

import streamlit as st

from alpha_system.journal import list_discretionary_warnings, list_entries
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.journal_filters import FILTER_LABELS, categorize, filter_entries
from alpha_system.ui.services.nav import FOCUS_JOURNAL_DISC, consume_focus
from alpha_system.ui.services.ui_copy import copy_get


def render_journal(ctx: DashboardContext) -> None:
    del ctx  # context reserved for future filters
    focus = consume_focus()
    if focus == FOCUS_JOURNAL_DISC:
        st.info("재량 이탈 기록을 조회합니다. 신규 기입 화면은 없습니다.")

    with st.container(border=True):
        st.subheader("저널 (조회 전용)")
        st.caption(copy_get("journal", "append_only"))
        st.caption(
            "재량 청산·목표가 수정은 직접 기입하지 않습니다. "
            "승인·갱신·가동 선언·RESCORE_TRIGGER 등 시스템 기록이 타임라인에 쌓입니다."
        )

        st.markdown("#### 재량 이탈 경고")
        st.caption(copy_get("journal", "discretion_tooltip"))
        disc = list_discretionary_warnings()
        if not disc:
            st.caption("재량 이탈 기록 없음")
        for e in disc:
            st.warning(
                f"{e.recorded_at[:10]} {e.subject}: {e.discretionary_reason or e.rationale}"
            )

    with st.container(border=True):
        st.subheader("타임라인 (최신순)")
        cat = st.selectbox(
            "유형 필터",
            list(FILTER_LABELS.keys()),
            key="journal_filter",
        )
        entries = sorted(list_entries(), key=lambda e: e.recorded_at, reverse=True)
        shown = filter_entries(entries, cat)
        if not shown:
            st.caption("해당 유형 기록 없음")
        for e in shown[:120]:
            st.markdown(
                f"**{e.recorded_at[:19]}** `{e.action_kind}` "
                f"<span class='alpha-badge-ok'>{categorize(e.action_kind)}</span> · {e.subject}  \n"
                f"{(e.rationale or '')[:300]}",
                unsafe_allow_html=True,
            )
