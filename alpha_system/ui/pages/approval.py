"""결재함 — 자동 수집 결과 검토·영역별 승인만 (직접 점수/이벤트 기입 없음)."""

from __future__ import annotations

import streamlit as st

from alpha_system.ui.pages import events, rules, scores
from alpha_system.ui.services.context import DashboardContext
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
    consume_focus,
)

_TAB_QUANT = "① 숫자"
_TAB_WEEKLY = "② 이번 주"
_TAB_MONTHLY = "③ 이번 달"
_TAB_LIVE = "④ 가동"
_TABS = (_TAB_QUANT, _TAB_WEEKLY, _TAB_MONTHLY, _TAB_LIVE)
_SESSION_TAB = "approval_section"
_LEGACY_TAB = {
    "정량·스코어": _TAB_QUANT,
    "주간 정성 승인": _TAB_WEEKLY,
    "가동·체크리스트": _TAB_LIVE,
    "월간 CECS": _TAB_MONTHLY,
}


def render_approval(ctx: DashboardContext) -> None:
    focus = consume_focus()

    weekly_focus = focus in {FOCUS_WEEKLY_QUAL, FOCUS_T2}
    monthly_focus = focus in {FOCUS_MONTHLY_CECS, FOCUS_CECS_SCORE}
    quant_focus = focus in {FOCUS_DATA_REFRESH, FOCUS_SCORES, FOCUS_T3_DETAIL}
    live_focus = focus == FOCUS_GO_LIVE or (
        bool(focus) and str(focus).startswith(FOCUS_RULES_PREFIX)
    )

    raw_tab = st.session_state.get(_SESSION_TAB)
    if raw_tab in _LEGACY_TAB:
        st.session_state[_SESSION_TAB] = _LEGACY_TAB[raw_tab]

    if focus:
        if quant_focus:
            st.session_state[_SESSION_TAB] = _TAB_QUANT
        elif weekly_focus:
            st.session_state[_SESSION_TAB] = _TAB_WEEKLY
        elif monthly_focus:
            st.session_state[_SESSION_TAB] = _TAB_MONTHLY
        elif live_focus:
            st.session_state[_SESSION_TAB] = _TAB_LIVE
    if st.session_state.get(_SESSION_TAB) not in _TABS:
        st.session_state[_SESSION_TAB] = _TAB_QUANT

    st.markdown(
        """
<div class="ap-page-head">
  <p class="ap-page-lead">
    확인 센터 — ①숫자 → ②이번 주(게이트) → ③이번 달(CECS 선택) → ④가동.
    출처만 보고 영역별로 승인합니다. 제안 순위·target은 여기서 안 바꿉니다.
  </p>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="ap-tab-label">확인 단계</div>', unsafe_allow_html=True)
    if st.session_state.get(_SESSION_TAB) not in _TABS:
        st.session_state[_SESSION_TAB] = _TAB_QUANT
    section = st.segmented_control(
        "확인 단계",
        list(_TABS),
        selection_mode="single",
        required=True,
        label_visibility="collapsed",
        key=_SESSION_TAB,
        width="stretch",
    )
    if section is None:
        section = _TAB_QUANT

    if section == _TAB_QUANT:
        _panel_quant(ctx, focus=focus)
    elif section == _TAB_WEEKLY:
        _panel_weekly(ctx, focused=weekly_focus)
    elif section == _TAB_MONTHLY:
        _panel_monthly(ctx, focused=monthly_focus)
    else:
        _panel_live(ctx, focus=focus, live_focus=live_focus)


def _panel_weekly(ctx: DashboardContext, *, focused: bool) -> None:
    st.markdown(
        """
<div class="ap-panel">
  <div class="ap-panel-kicker">2 · 이번 주</div>
  <div class="ap-panel-title">이번 주 확인</div>
  <p class="ap-panel-desc">
    숫자 준비가 끝난 뒤. 요청서 → 조사본 업로드 → 출처 확인 → C/D/E 승인.
    논지·목표가만 엔진이 씁니다. CECS는 「이번 달」에서 따로 올립니다.
  </p>
</div>
""",
        unsafe_allow_html=True,
    )
    if focused:
        st.info("오늘 할 일에서 연결됨 — 출처 확인 후 해당 영역만 승인하세요.")
    events._render_weekly_qual(ctx, focused=focused)


def _panel_monthly(ctx: DashboardContext, *, focused: bool) -> None:
    st.markdown(
        """
<div class="ap-panel">
  <div class="ap-panel-kicker">3 · 이번 달</div>
  <div class="ap-panel-title">월간 CECS (선택)</div>
  <p class="ap-panel-desc">
    주간 C/D/E와 저장소가 분리됩니다. 여기 업로드는 주간 승인을 덮어쓰지 않습니다.
    CECS는 순위·편입에 반영되지 않습니다 (Ops A).
  </p>
</div>
""",
        unsafe_allow_html=True,
    )
    if focused:
        st.info("월간 CECS 확인 — 출처 확인 후 CECS만 승인하세요.")
    events._render_monthly_cecs(ctx, focused=focused)


def _panel_quant(ctx: DashboardContext, *, focus: str | None) -> None:
    st.markdown(
        """
<div class="ap-panel">
  <div class="ap-panel-kicker">1 · 숫자</div>
  <div class="ap-panel-title">숫자 준비</div>
  <p class="ap-panel-desc">
    가격·펀더멘털·스냅샷 갱신과 스코어보드 조회.
    끝난 뒤 「이번 주」로 넘어가세요. 여기서 제안 순위는 바뀌지 않습니다.
  </p>
</div>
""",
        unsafe_allow_html=True,
    )
    if focus == FOCUS_DATA_REFRESH:
        st.info("정량 스냅샷 갱신 섹션입니다.")

    with st.container(border=True):
        st.markdown(
            '<div class="ap-subblock-title">① 정량 전체 갱신</div>',
            unsafe_allow_html=True,
        )
        events._render_data_refresh(ctx)

    with st.container(border=True):
        st.markdown(
            '<div class="ap-subblock-title">② T3 판정 상세</div>',
            unsafe_allow_html=True,
        )
        if focus == FOCUS_T3_DETAIL:
            st.info("T3 판정 상세입니다.")
        events._render_t3_detail(ctx)

    with st.container(border=True):
        st.markdown(
            '<div class="ap-subblock-title">③ 스코어보드 (조회)</div>',
            unsafe_allow_html=True,
        )
        if focus == FOCUS_SCORES:
            st.info("스코어 검토용 조회 화면입니다.")
        scores.render_scores(ctx)


def _panel_live(ctx: DashboardContext, *, focus: str | None, live_focus: bool) -> None:
    st.markdown(
        """
<div class="ap-panel">
  <div class="ap-panel-kicker">4 · 가동</div>
  <div class="ap-panel-title">가동 확인</div>
  <p class="ap-panel-desc">
    숫자·이번 주 확인이 끝난 뒤. go-live와 읽기 전용 규칙만 봅니다.
  </p>
</div>
""",
        unsafe_allow_html=True,
    )
    if live_focus:
        st.info("가동 선언·체크리스트 구간입니다.")

    with st.container(border=True):
        st.markdown(
            '<div class="ap-subblock-title">① 가동 선언</div>',
            unsafe_allow_html=True,
        )
        events._render_go_live(ctx, expand=(focus == FOCUS_GO_LIVE))

    with st.container(border=True):
        st.markdown(
            '<div class="ap-subblock-title">② 규칙·체크리스트 (읽기 전용)</div>',
            unsafe_allow_html=True,
        )
        with st.expander("펼쳐 보기", expanded=live_focus):
            if focus and str(focus).startswith(FOCUS_RULES_PREFIX):
                st.session_state["nav_focus"] = focus
            rules.render_rules(ctx)
