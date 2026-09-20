"""Journal timeline — read-only (no discretionary / target write forms)."""

from __future__ import annotations

import streamlit as st

from alpha_system.journal import list_discretionary_warnings, list_entries
from alpha_system.ui.services.approval_chrome import ap_subhead, page_head
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.journal_filters import FILTER_LABELS, categorize, filter_entries
from alpha_system.ui.services.ko_display import (
    format_discretionary_warning,
    format_journal_timeline_line,
)
from alpha_system.ui.services.nav import FOCUS_JOURNAL_DISC, consume_focus
from alpha_system.ui.services.ui_copy import copy_get


def render_journal(ctx: DashboardContext) -> None:
    del ctx  # context reserved for future filters
    focus = consume_focus()
    page_head(
        kicker=copy_get("journal", "page_kicker", default="저널"),
        title=copy_get("journal", "page_title", default="판정 · 승인 기록"),
        lead=copy_get(
            "journal",
            "page_lead",
            default=(
                "승인·갱신·가동 선언이 타임라인에 쌓입니다. "
                "여기서 새로 쓰지 않습니다. 자동매매 없음."
            ),
        ),
    )
    if focus == FOCUS_JOURNAL_DISC:
        st.info(
            "재량 이탈 = 규칙 밖에서 한 판단을 적어 둔 기록입니다. "
            "자동매매·강제 청산은 없고, 조회만 됩니다."
        )

    with st.container(border=True):
        ap_subhead(
            copy_get("journal", "sec_disc", default="재량 이탈 경고"),
            desc=copy_get("journal", "discretion_tooltip"),
        )
        st.caption(copy_get("journal", "append_only"))
        disc = list_discretionary_warnings()
        if not disc:
            st.caption("재량 이탈 기록 없음")
        for e in disc:
            st.warning(format_discretionary_warning(e))

    with st.container(border=True):
        ap_subhead(
            copy_get("journal", "sec_timeline", default="타임라인"),
            desc="최신순 · 유형으로 걸러 봅니다.",
        )
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
            title, body = format_journal_timeline_line(e)
            cat_label = categorize(e.action_kind)
            st.markdown(
                f"{title}  \n"
                f"<span class='alpha-badge-ok'>{cat_label}</span>  \n"
                f"{body}",
                unsafe_allow_html=True,
            )
