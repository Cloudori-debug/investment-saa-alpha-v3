"""결재함 — 자동 수집 결과 조회 (직접 점수/이벤트 기입 없음)."""

from __future__ import annotations

import streamlit as st

from alpha_system.ui.pages import events, scores
from alpha_system.ui.services.approval_chrome import ap_copy, ap_head, page_head, page_tabs
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.screen_market import render_screen_market_nav
from alpha_system.ui.services.nav import (
    FOCUS_CECS_SCORE,
    FOCUS_DATA_REFRESH,
    FOCUS_GO_LIVE,
    FOCUS_MONTHLY_CECS,
    FOCUS_RULES_PREFIX,
    FOCUS_SCORES,
    FOCUS_T2,
    FOCUS_T3_DETAIL,
    FOCUS_WEEKLY_QUAL,
    PAGE_PORTFOLIO,
    consume_focus,
    navigate,
)


def _tabs() -> tuple[str, str, str]:
    return (
        ap_copy("tab_quant", default="① 숫자"),
        ap_copy("tab_weekly", default="② 이번 주"),
        ap_copy("tab_live", default="③ 가동"),
    )


_SESSION_TAB = "approval_section"
_LEGACY_TAB = {
    "정량·스코어": "① 숫자",
    "주간 정성 승인": "② 이번 주",
    "가동·체크리스트": "③ 가동",
    "④ 가동": "③ 가동",
}
_RETIRED_MONTHLY_TABS = frozenset({"월간 CECS", "③ 이번 달"})


def render_approval(ctx: DashboardContext) -> None:
    focus = consume_focus()
    if focus in {FOCUS_MONTHLY_CECS, FOCUS_CECS_SCORE}:
        navigate(PAGE_PORTFOLIO)
        return

    tab_quant, tab_weekly, tab_live = _tabs()
    tabs = (tab_quant, tab_weekly, tab_live)

    weekly_focus = focus in {FOCUS_WEEKLY_QUAL, FOCUS_T2}
    quant_focus = focus in {FOCUS_DATA_REFRESH, FOCUS_SCORES, FOCUS_T3_DETAIL}
    live_focus = focus == FOCUS_GO_LIVE or (
        bool(focus) and str(focus).startswith(FOCUS_RULES_PREFIX)
    )

    raw_tab = st.session_state.get(_SESSION_TAB)
    if raw_tab in _RETIRED_MONTHLY_TABS:
        st.session_state[_SESSION_TAB] = tab_quant
    elif raw_tab in _LEGACY_TAB:
        st.session_state[_SESSION_TAB] = _LEGACY_TAB[raw_tab]

    if focus:
        if quant_focus:
            st.session_state[_SESSION_TAB] = tab_quant
        elif weekly_focus:
            st.session_state[_SESSION_TAB] = tab_weekly
        elif live_focus:
            st.session_state[_SESSION_TAB] = tab_live
    if st.session_state.get(_SESSION_TAB) not in tabs:
        st.session_state[_SESSION_TAB] = tab_quant

    page_head(
        kicker=ap_copy("page_kicker", default="확인"),
        title=ap_copy("page_title", default="숫자 · 이번 주 · 가동"),
        lead=ap_copy("lead"),
    )
    render_screen_market_nav(ctx.root)

    section = page_tabs(
        ap_copy("tab_label", default="확인 단계"),
        tabs,
        key=_SESSION_TAB,
    )

    if section == tab_quant:
        _panel_quant(ctx, focus=focus)
    elif section == tab_weekly:
        _panel_weekly(ctx, focused=weekly_focus)
    else:
        _panel_live(ctx, focus=focus, live_focus=live_focus)


def _panel_weekly(ctx: DashboardContext, *, focused: bool) -> None:
    ap_head(
        kicker=ap_copy("weekly_kicker"),
        title=ap_copy("weekly_title"),
        desc=ap_copy("weekly_desc"),
    )
    if focused:
        st.info(ap_copy("focus_weekly"))
    events._render_weekly_qual(ctx, focused=False)


def _panel_quant(ctx: DashboardContext, *, focus: str | None) -> None:
    ap_head(
        kicker=ap_copy("quant_kicker"),
        title=ap_copy("quant_title"),
        desc=ap_copy("quant_desc"),
    )
    if focus == FOCUS_DATA_REFRESH:
        st.info(ap_copy("focus_quant"))

    with st.container(border=True):
        events._render_data_refresh(ctx)

    with st.container(border=True):
        from alpha_system.ui.services.approval_chrome import ap_subhead

        ap_subhead(
            ap_copy("quant_board_title"),
            desc=ap_copy("quant_board_desc"),
        )
        if focus == FOCUS_SCORES:
            st.info(ap_copy("focus_scores"))
        scores.render_scores(ctx)


def _panel_live(ctx: DashboardContext, *, focus: str | None, live_focus: bool) -> None:
    ap_head(
        kicker=ap_copy("live_kicker"),
        title=ap_copy("live_title"),
        desc=ap_copy("live_desc"),
    )
    if live_focus:
        st.info(ap_copy("focus_live"))

    with st.container(border=True):
        events._render_go_live(ctx)
