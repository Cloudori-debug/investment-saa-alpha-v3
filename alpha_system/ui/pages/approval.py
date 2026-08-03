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
    FOCUS_WEEKLY_APPROVE,
    FOCUS_WEEKLY_QUAL,
    consume_focus,
)

_TAB_QUANT = "① 숫자"
_TAB_WEEKLY = "② 이번 주"
_TAB_LIVE = "③ 가동"
_TABS = (_TAB_QUANT, _TAB_WEEKLY, _TAB_LIVE)
_SESSION_TAB = "approval_section"
_LEGACY_TAB = {
    "정량·스코어": _TAB_QUANT,
    "주간 정성 승인": _TAB_WEEKLY,
    "가동·체크리스트": _TAB_LIVE,
    "① 숫자": _TAB_QUANT,
    "② 이번 주": _TAB_WEEKLY,
    "③ 이번 달": _TAB_LIVE,  # legacy monthly tab → 가동 (CECS는 접힌 원장)
    "④ 가동": _TAB_LIVE,
    "월간 CECS": _TAB_WEEKLY,  # deep-link opens weekly + expander
}


def render_approval(ctx: DashboardContext) -> None:
    focus = consume_focus()

    weekly_focus = focus in {FOCUS_WEEKLY_QUAL, FOCUS_T2, FOCUS_WEEKLY_APPROVE}
    prefer_approve = focus == FOCUS_WEEKLY_APPROVE
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
        elif weekly_focus or monthly_focus:
            st.session_state[_SESSION_TAB] = _TAB_WEEKLY
        elif live_focus:
            st.session_state[_SESSION_TAB] = _TAB_LIVE
    if st.session_state.get(_SESSION_TAB) not in _TABS:
        st.session_state[_SESSION_TAB] = _TAB_QUANT

    st.markdown(
        """
<div class="ap-page-head">
  <p class="ap-page-lead">
    ①숫자 → ②공적 브레이크(선택) → ③가동. 순위·target은 여기서 안 바뀝니다.
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
        _panel_weekly(ctx, focused=weekly_focus, prefer_approve=prefer_approve)
        _panel_monthly_folded(ctx, focused=monthly_focus)
    else:
        _panel_live(ctx, focus=focus, live_focus=live_focus)


def _panel_weekly(
    ctx: DashboardContext,
    *,
    focused: bool,
    prefer_approve: bool = False,
) -> None:
    st.markdown(
        """
<div class="ap-panel">
  <div class="ap-panel-kicker">2 · 이번 주</div>
  <div class="ap-panel-title">공적 브레이크 (선택)</div>
  <p class="ap-panel-desc">
    요청서 → 업로드 → 출처 확인 → T2·논지·목표가(실측 앵커).
    홈 필수 아님 · 증권사 SoT 금지 · CECS는 아래 접힌 원장(스킵).
  </p>
</div>
""",
        unsafe_allow_html=True,
    )
    if focused and prefer_approve:
        st.info("승인할 영역이 있습니다 — 승인판이 위에 열려 있습니다.")
    elif focused:
        st.info("오늘 할 일에서 연결됨 — 출처 확인 후 해당 영역만 승인하세요.")
    events._render_weekly_qual(
        ctx, focused=focused, prefer_approve=prefer_approve
    )


def _panel_monthly_folded(ctx: DashboardContext, *, focused: bool) -> None:
    """CECS ledger — skipped by default (REAL_INVEST_SCOPE_CHECKLIST)."""
    with st.expander(
        "원장 · 월간 CECS (스킵 기본 · 순위·편입 무관)",
        expanded=focused,
    ):
        st.caption(
            "실투 루틴에서는 돌리지 않아도 됩니다. "
            "환원 순위는 score_sr SR4 · 승인해도 제안 종목이 바뀌지 않습니다."
        )
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
  <div class="ap-panel-kicker">3 · 가동</div>
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
