"""Alpha dashboard home — today status, decision boards, compact ops."""

from __future__ import annotations

from datetime import date

import streamlit as st

from alpha_system.entry.models import TrancheState
from alpha_system.ui.services.action_panels import open_panel, render_active_panel
from alpha_system.ui.services.context import DashboardContext
from alpha_system.ui.services.home_pipeline import (
    HomeOverview,
    PipelineStage,
    build_home_overview,
)
from alpha_system.ui.services.judgment_copy import explain_tranche
from alpha_system.ui.services.judgment_snapshot import next_judgment_hint
from alpha_system.ui.services.home_status import freshness_line, status_line
from alpha_system.ui.services.nav import (
    FOCUS_DATA_REFRESH,
    FOCUS_GO_LIVE,
    FOCUS_RULES_PREFIX,
    FOCUS_T3_DETAIL,
    FOCUS_WEEKLY_QUAL,
    PAGE_APPROVAL,
    PAGE_REGIME,
    navigate,
)
from alpha_system.ui.services.ui_copy import copy_get, format_tranche_label, tranche_display
from alpha_system.ui.styles import status_card_class


def _render_first_run_card(ctx: DashboardContext) -> None:
    """First screen: use the app now. Setup/backup is optional later."""
    from alpha_system.ui.services.nav import (
        FOCUS_HOLDINGS_INPUT,
        PAGE_PORTFOLIO,
        PAGE_SETTINGS,
    )
    from alpha_system.ui.services.ops_assistant_pack import (
        PRODUCT_NAME,
        needs_first_run_banner,
        setup_status,
    )

    dismissed_holdings = bool(st.session_state.get("home_holdings_cta_dismissed"))
    dismissed_setup = bool(st.session_state.get("home_setup_dismissed"))
    has_alpha = int(getattr(ctx, "held_kr_alpha", 0) or 0) > 0 or bool(
        ctx.ops_portfolio_rows
    )

    # Primary product path: no alpha book yet → go register holdings.
    if not has_alpha and not dismissed_holdings:
        with st.container(border=True):
            st.markdown("#### 바로 시작")
            st.caption(
                f"{PRODUCT_NAME} · 자동매매 없음 · "
                "후보에서 고르거나 붙여넣기만 하면 종목별 안내가 켜집니다"
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button(
                    "실보유 입력",
                    key="home_to_holdings",
                    type="primary",
                    use_container_width=True,
                ):
                    navigate(PAGE_PORTFOLIO, focus=FOCUS_HOLDINGS_INPUT)
            with c2:
                if st.button(
                    "나중에",
                    key="home_holdings_skip",
                    use_container_width=True,
                ):
                    st.session_state["home_holdings_cta_dismissed"] = True
                    st.rerun()
        return

    # Optional: DART / target transplant — not a gate to using the app.
    if not needs_first_run_banner(ctx.root) or dismissed_setup:
        return
    status = setup_status(ctx.root)
    with st.container(border=True):
        st.markdown("#### 선택 — 데이터·키 (나중에 해도 됨)")
        st.caption(
            f"DART: {'준비됨' if status['dart_ok'] else '설정에서 입력'} · "
            f"target: {'있음' if status['target_exists'] else '이식 zip 또는 직접 유지'}"
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("설정 열기", key="home_to_settings", use_container_width=True):
                navigate(PAGE_SETTINGS)
        with c2:
            if st.button("닫기", key="home_setup_skip", use_container_width=True):
                st.session_state["home_setup_dismissed"] = True
                st.rerun()


def _state_level(state: TrancheState, *, pre_launch: bool, data_unknown: bool = False) -> str:
    if pre_launch:
        return "muted"
    if data_unknown:
        return "muted"
    if state in (TrancheState.EXECUTED, TrancheState.PARTIAL_EXECUTED):
        return "ok"
    if state == TrancheState.READY:
        return "warn"
    if state in (TrancheState.FROZEN, TrancheState.EXPIRED):
        return "danger"
    return "muted"


def _state_label(state: TrancheState, *, pre_launch: bool) -> str:
    if pre_launch:
        return "잠김"
    mapping = {
        TrancheState.EXECUTED: "집행완료",
        TrancheState.PARTIAL_EXECUTED: "부분집행",
        TrancheState.READY: "대기",
        TrancheState.PENDING: "대기",
        TrancheState.FROZEN: "동결",
        TrancheState.EXPIRED: "소멸",
    }
    return mapping.get(state, state.value)


def _open_tranche(ctx: DashboardContext, tid: str) -> None:
    if tid == "T2":
        navigate(PAGE_APPROVAL, focus=FOCUS_WEEKLY_QUAL)
        return
    if tid == "T3":
        hist = ctx.root / "data" / "kospi_market_pbr_history.csv"
        if hist.exists() and ctx.t3_pbr.available:
            navigate(PAGE_APPROVAL, focus=FOCUS_T3_DETAIL)
        else:
            navigate(PAGE_APPROVAL, focus=FOCUS_DATA_REFRESH)
        return
    navigate(PAGE_APPROVAL, focus=f"{FOCUS_RULES_PREFIX}{tid}")


def _open_stage(stage: PipelineStage) -> None:
    navigate(stage.page, focus=stage.focus, prefill=stage.prefill)


def _render_status_strip(ctx: DashboardContext, overview: HomeOverview) -> None:
    """가동/보유/오늘 할 일 — 관제탑 대신 한 줄."""
    action = overview.next_action
    line = status_line(
        pre_launch=ctx.pre_launch,
        held_n=int(ctx.held_kr_alpha or 0),
        next_title=action.title if action is not None else None,
    )
    st.markdown(f"**오늘** — {line}")
    st.caption("바젤 테마·시장 레짐은 사이드바「레짐」. 데이터 표는「확인」")
    if action is not None:
        from alpha_system.ui.services.background_job import job_is_busy

        if st.button(
            action.cta_label,
            key="home_next_action",
            type="primary",
            disabled=job_is_busy(ctx.root),
        ):
            st.session_state["_home_run_next_action"] = True
            st.rerun()


def _render_data_line(ctx: DashboardContext) -> None:
    line, attention = freshness_line(ctx.source_status or [], ctx.as_of)
    level = "warn" if attention else "ok"
    tone = "확인 필요" if attention else "정상"
    st.markdown(
        f'<div class="{status_card_class(level)}">'
        f'<span class="alpha-badge-{level}">{tone}</span> '
        f"<strong>데이터</strong> — {line}"
        f"</div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    with cols[0]:
        if st.button("데이터 갱신", key="home_data_refresh", use_container_width=True):
            navigate(PAGE_APPROVAL, focus=FOCUS_DATA_REFRESH)
    with cols[1]:
        if st.button("레짐 보기", key="home_to_regime", use_container_width=True):
            navigate(PAGE_REGIME)


def _style_trend_column(df: "pd.DataFrame", cols: str | list[str] = "추세"):
    """상승=빨강, 하락=파랑 (국내 시세 관례)."""
    import pandas as pd

    if df.empty:
        return df
    targets = [cols] if isinstance(cols, str) else list(cols)
    targets = [c for c in targets if c in df.columns]
    if not targets:
        return df

    def _paint(val: object) -> str:
        s = str(val)
        if s == "상승":
            return "color: #dc2626; font-weight: 700"
        if s == "하락":
            return "color: #2563eb; font-weight: 700"
        return ""

    try:
        return df.style.map(_paint, subset=targets)
    except Exception:
        return df


def _render_alpha_ratio_bar(ctx: DashboardContext) -> None:
    """Colored badge card showing alpha 9:1 drift (equity vs 214980)."""
    from alpha_system.ui.services.alpha_book_ops import (
        build_alpha_actual_map,
        load_alpha_book_ops,
    )
    from alpha_system.ui.styles import status_card_class

    policy = load_alpha_book_ops(ctx.root)
    actual = build_alpha_actual_map(ctx.root, list(ctx.ops_portfolio_rows or []), policy)
    if not actual:
        return
    cash_pct = actual.get(policy.cash_ticker, (0.0, policy.cash_name))[0]
    equity_pct = max(0.0, 100.0 - cash_pct)
    n_equity = sum(1 for tk in actual if tk != policy.cash_ticker)
    tgt_cash = policy.cash_share * 100.0
    tgt_equity = policy.equity_share * 100.0
    gap_cash = cash_pct - tgt_cash
    gap_equity = equity_pct - tgt_equity

    if abs(gap_cash) >= 20.0:
        level = "danger"
        tone = "경보"
    elif abs(gap_cash) >= 10.0:
        level = "warn"
        tone = "주의"
    else:
        level = "ok"
        tone = "정상"

    st.markdown(
        f'<div class="{status_card_class(level)}">'
        f'<span class="alpha-badge-{level}">{tone}</span> '
        f"<strong>알파 9:1</strong> — "
        f"개별주 {equity_pct:.1f}% ({n_equity}종, 목표 {tgt_equity:.0f}%) "
        f"· {policy.cash_name} {cash_pct:.1f}% (목표 {tgt_cash:.0f}%) "
        f"· 괴리 주식 {gap_equity:+.1f}%p / 단기채 {gap_cash:+.1f}%p"
        f"<br/><small>Review-only · target 자동변경 없음</small>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _run_next_action_if_flagged(ctx: DashboardContext, overview: HomeOverview) -> None:
    if not st.session_state.pop("_home_run_next_action", False):
        return
    action = overview.next_action
    if action is None:
        return
    if action.key == "quant":
        from alpha_system.ui.services.background_job import start_dashboard_job

        err = start_dashboard_job(ctx.root, "quant", collect_scope="liquid")
        if err:
            st.error(err)
        else:
            st.rerun()
        return
    navigate(action.page, focus=action.focus, prefill=action.prefill)


def _render_decision_boards(ctx: DashboardContext) -> None:
    """① 비중표 → ② 보유 분석 → ③ 제안 분석 (의사결정 본문)."""
    import pandas as pd

    from alpha_system.ui.services.home_decision_boards import (
        build_home_decision_boards,
        combined_as_table,
        holdings_as_table,
        proposals_as_table,
    )
    from alpha_system.ui.services.momentum_holding_monitor import (
        BEARING_HELP_KO,
        BEARING_KO,
        STRATEGY_ACTION_KO,
    )
    from alpha_system.ui.services.portfolio_widgets import navigate_to_portfolio

    boards = build_home_decision_boards(ctx)

    # ① Combined portfolio ratio — primary decision surface
    with st.container(border=True):
        st.subheader("① 포트폴리오 비중")
        st.caption(
            f"{boards.summary} · "
            "보유+제안 한눈에 · 실%/제안%/목표% · 조치로 매매 전략 잡기"
        )
        if not boards.combined:
            st.markdown(
                '<div class="alpha-empty-queue"><strong>'
                "보유·제안 없음 — 포트폴리오에서 실보유 입력 또는 정량 실행"
                "</strong></div>",
                unsafe_allow_html=True,
            )
        else:
            st.dataframe(
                pd.DataFrame(combined_as_table(boards.combined)),
                use_container_width=True,
                hide_index=True,
            )
            pick_opts = [""] + [
                f"{r.name} ({r.ticker})" for r in boards.combined if r.action != "유지"
            ]
            if len(pick_opts) > 1:
                pick = st.selectbox(
                    "조치 종목 → 포트폴리오",
                    options=pick_opts,
                    key="home_decision_pick",
                )
                if pick and st.button(
                    "선택한 종목 열기", key="home_decision_go"
                ):
                    tk = pick.rsplit("(", 1)[-1].rstrip(")")
                    navigate_to_portfolio(tk)

    # ② Holdings analysis
    with st.container(border=True):
        st.subheader(f"② 보유 분석 ({boards.n_held}종)")
        st.caption(
            "보유 자산 근거 · 추세·바늘·익절 · ① 조치의 뒷받침 · Review-only"
        )
        if not boards.holdings:
            st.caption("실보유 없음 — 포트폴리오에서 입력")
        else:
            st.dataframe(
                _style_trend_column(
                    pd.DataFrame(holdings_as_table(boards.holdings)),
                    ["중기", "1개월", "3개월"],
                ),
                use_container_width=True,
                hide_index=True,
            )
            with st.expander("바늘·전략 대응표", expanded=False):
                for code, label in BEARING_KO.items():
                    help_txt = BEARING_HELP_KO.get(code, "")
                    act = STRATEGY_ACTION_KO.get(code, "")
                    st.markdown(f"- **{label}** → **{act}** — {help_txt}")

    # ③ Proposal analysis
    with st.container(border=True):
        st.subheader(f"③ 제안 후보 분석 ({boards.n_proposal}종)")
        st.caption(
            "스크리닝 제안 근거 · Q/V/SR·모멘텀 · 편입·교체 판단용 · "
            "자동주문·target 기입 없음"
        )
        if not boards.proposals:
            st.caption("제안 후보 없음 — 정량 스냅샷 실행")
        else:
            st.dataframe(
                pd.DataFrame(proposals_as_table(boards.proposals)),
                use_container_width=True,
                hide_index=True,
            )


def _render_monthly_rebal(ctx: DashboardContext) -> None:
    """Checklist only — band detail lives in 「오늘 조치」."""
    import pandas as pd

    from alpha_system.ui.services.alpha_book_ops import (
        guidance_rows,
        load_alpha_book_ops,
    )
    from alpha_system.ui.services.monthly_rebal_board import build_monthly_rebal_board
    from alpha_system.ui.services.nav import PAGE_PORTFOLIO, PAGE_REGIME

    board = build_monthly_rebal_board(ctx)
    if not board.do_now_count:
        return
    tone_cls = {
        "ok": "alpha-badge-ok",
        "warn": "alpha-badge-warn",
        "danger": "alpha-badge-danger",
        "muted": "alpha-badge-warn",
    }
    title = "월 리밸 · 참고"
    if board.do_now_count:
        title = f"월 리밸 · 참고 ({board.do_now_count}건 지금)"
    with st.expander(title, expanded=False):
        st.caption(
            f"{board.summary} · {board.as_of.isoformat()} · "
            f"시장 {board.regime_label} · "
            "규칙 상태 참고 · 종목 매매는 위 ① 비중표 조치 열"
        )
        policy = load_alpha_book_ops(ctx.root)
        st.dataframe(
            pd.DataFrame(guidance_rows(policy, board.regime_label)),
            use_container_width=True,
            hide_index=True,
        )
        for card in board.cards:
            badge = tone_cls.get(card.tone, "alpha-badge-warn")
            flag = (
                "지금"
                if card.do_now
                else ("참고" if card.key == "scale_in" else "대기")
            )
            extra = ""
            if card.key == "band" and card.items:
                extra = f" · {len(card.items)}종 → ① 비중표"
            elif card.key == "signal" and card.items:
                extra = " · ① 비중표 조치"
            st.markdown(
                f'<div class="alpha-action-item">'
                f'<span class="{badge}">{flag}</span> '
                f"<strong>{card.title}</strong> — {card.status}{extra}<br/>"
                f"<small>{card.detail}</small></div>",
                unsafe_allow_html=True,
            )
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("보유 리뷰", key="home_rebal_to_pf", use_container_width=True):
                navigate(PAGE_PORTFOLIO)
        with c2:
            if st.button("레짐", key="home_rebal_to_regime", use_container_width=True):
                navigate(PAGE_REGIME)
        with c3:
            if st.button(
                "확인 · 이번 주",
                key="home_rebal_to_weekly",
                use_container_width=True,
            ):
                navigate(PAGE_APPROVAL, focus=FOCUS_WEEKLY_QUAL)


def _render_holdings_cues(ctx: DashboardContext) -> None:
    """제안 북 익절 — 짧게. 실보유 컨설팅 아님."""
    from alpha_system.ui.services.ops_exit_signal import actionable_ops_signals
    from alpha_system.ui.services.portfolio_widgets import navigate_to_portfolio

    items = actionable_ops_signals(list(ctx.portfolio_rows or []))
    held_n = int(ctx.held_kr_alpha or 0)
    if not items:
        return

    show = items[:3]
    extra = len(items) - len(show)
    with st.container(border=True):
        st.subheader("익절 권고")
        st.caption(
            "제안 북 기준입니다. 실보유 컨설팅이 아니며 자동 매도 없습니다."
            + (" · 지금 실보유 없음" if held_n <= 0 else "")
        )
        for row in show:
            badge_cls = {
                "exit_full": "alpha-badge-danger",
                "cash_half": "alpha-badge-warn",
                "trim": "alpha-badge-warn",
                "missing": "alpha-badge-warn",
                "review": "alpha-badge-danger",
            }.get(row.ops_signal, "alpha-badge-warn")
            cols = st.columns([5, 1])
            with cols[0]:
                st.markdown(
                    f'<div class="alpha-action-item">'
                    f'<span class="{badge_cls}">{row.ops_signal_label}</span> '
                    f"<strong>{row.name}</strong> — {row.ops_signal_detail}</div>",
                    unsafe_allow_html=True,
                )
            with cols[1]:
                if st.button("열기", key=f"home_exit_{row.ticker}", help="제안 북"):
                    navigate_to_portfolio(row.ticker)
        if extra > 0:
            st.caption(f"외 {extra}건은 포트폴리오 제안 북에서 봅니다.")


def _render_tranche_card(
    ctx: DashboardContext,
    st_status,
    *,
    blocker: PipelineStage | None,
    key_suffix: str = "",
) -> None:
    tid = (
        st_status.tranche_id.value
        if hasattr(st_status.tranche_id, "value")
        else str(st_status.tranche_id)
    )
    label = format_tranche_label(tid)
    _, short_desc = tranche_display(tid)
    judgment = explain_tranche(st_status, pre_launch=ctx.pre_launch)
    data_unknown = (not judgment.mapped) or (
        "판단할 수 없" in judgment.headline or "데이터가 없어" in judgment.headline
    )
    level = _state_level(
        st_status.state, pre_launch=ctx.pre_launch, data_unknown=data_unknown
    )

    if ctx.pre_launch and blocker is not None:
        headline = (
            f"잠긴 이유: 가동 전 — 선행 단계 「{blocker.step}. {blocker.title}」미해결. "
            f"{blocker.reason}"
        )
        next_line = f"해결: {blocker.cta_label}"
    else:
        headline = judgment.headline
        next_line = judgment.next_check

    st.markdown(
        f'<div class="{status_card_class(level)}">'
        f"<strong>{label}</strong> — {_state_label(st_status.state, pre_launch=ctx.pre_launch)}<br/>"
        f"<small>{short_desc}</small><br/>"
        f"<em>시스템은 지금 이렇게 판단 중</em><br/>"
        f"{headline}"
        + (f"<br/><small>{next_line}</small>" if next_line else "")
        + "</div>",
        unsafe_allow_html=True,
    )
    if ctx.pre_launch and blocker is not None:
        if st.button("해결하러 가기", key=f"tr_fix_{tid}{key_suffix}"):
            _open_stage(blocker)
    elif st.button("자세히", key=f"tr_open_{tid}{key_suffix}"):
        _open_tranche(ctx, tid)
    if not judgment.mapped and judgment.raw_detail:
        with st.expander("원문 상세", expanded=False):
            st.code(judgment.raw_detail)


def _render_capital_lock(ctx: DashboardContext, blocker: PipelineStage | None) -> None:
    """가동 전엔 한 문장. 가동 후에만 트랜치·액션 큐."""
    if ctx.pre_launch:
        st.markdown(
            f'<div class="{status_card_class("muted")}">'
            "<strong>자본 집행</strong> — 잠김<br/>"
            "<small>T1~T4 트랜치는 가동 선언 전까지 트리거를 보지 않습니다. "
            "Core 순위·목표 포트는 그대로입니다.</small></div>",
            unsafe_allow_html=True,
        )
        if st.button("가동(go-live) 안내", key="home_to_golive"):
            navigate(PAGE_APPROVAL, focus=FOCUS_GO_LIVE)
        return

    with st.expander("자본 집행 · 트랜치", expanded=False):
        st.caption("가동 후 자본을 언제 넣을지. 자동주문 없음.")
        if ctx.action_queue:
            st.markdown("#### 액션 큐")
            for item in ctx.action_queue:
                badge = {
                    "danger": "alpha-badge-danger",
                    "warn": "alpha-badge-warn",
                    "info": "alpha-badge-ok",
                }.get(item.severity.value, "alpha-badge-warn")
                cols = st.columns([5, 1])
                with cols[0]:
                    sev = {
                        "danger": "긴급",
                        "warn": "주의",
                        "info": "안내",
                    }.get(item.severity.value, "주의")
                    st.markdown(
                        f'<div class="alpha-action-item"><span class="{badge}">'
                        f"{sev}</span> <strong>{item.title}</strong>"
                        f"<br/>{item.detail}</div>",
                        unsafe_allow_html=True,
                    )
                with cols[1]:
                    if st.button("열기", key=f"aq_{item.key}"):
                        open_panel(item.key)
            render_active_panel(ctx)
        else:
            st.caption(f"집행 할 일 없음 — 다음 판정: {next_judgment_hint(ctx)}")

        st.markdown("#### 트랜치")
        statuses = list(ctx.entry_eval.statuses)
        for row in range(0, len(statuses), 2):
            cols = st.columns(2)
            for j, col in enumerate(cols):
                idx = row + j
                if idx >= len(statuses):
                    break
                with col:
                    _render_tranche_card(ctx, statuses[idx], blocker=blocker)
        days_left = (ctx.window_end - ctx.as_of).days
        st.caption(
            f"논지 창 종료일 {ctx.window_end.isoformat()} — 남은 일수 D-{max(0, days_left)}"
        )


def render_home(ctx: DashboardContext) -> None:
    """오늘 판단 홈: 상태 한 줄 → ① 비중 → 익절 짧게 → 데이터 한 줄."""
    frozen = ctx.runtime.effective_thesis_damage()
    past_window = ctx.as_of >= ctx.window_end
    overview = build_home_overview(ctx)
    blocker = overview.next_action

    _render_first_run_card(ctx)

    if frozen:
        st.markdown(
            f'<div class="alpha-banner-danger"><strong>'
            f'{copy_get("system_states", "FROZEN", "banner")}'
            f"</strong><br/>{copy_get('system_states', 'FROZEN', 'banner_detail')}</div>",
            unsafe_allow_html=True,
        )
    elif past_window:
        st.markdown(
            f'<div class="alpha-banner-danger"><strong>'
            f'{copy_get("system_states", "WINDOW_END", "banner")}'
            f"</strong><br/>{copy_get('system_states', 'WINDOW_END', 'banner_detail')}</div>",
            unsafe_allow_html=True,
        )

    _render_status_strip(ctx, overview)
    if int(ctx.held_kr_alpha or 0) > 0:
        _render_alpha_ratio_bar(ctx)
    _run_next_action_if_flagged(ctx, overview)

    _render_decision_boards(ctx)
    _render_holdings_cues(ctx)
    _render_monthly_rebal(ctx)
    _render_data_line(ctx)
    _render_capital_lock(ctx, blocker)