"""Alpha dashboard home — preparation, one action, result, folded operations."""

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
from alpha_system.ui.services.judgment_snapshot import (
    build_judgment_snapshot,
    next_judgment_hint,
)
from alpha_system.ui.services.nav import (
    FOCUS_DATA_REFRESH,
    FOCUS_JOURNAL_DISC,
    FOCUS_RULES_PREFIX,
    FOCUS_T3_DETAIL,
    FOCUS_WEEKLY_QUAL,
    PAGE_APPROVAL,
    PAGE_JOURNAL,
    navigate,
)
from alpha_system.ui.services.ui_copy import copy_get, format_tranche_label, tranche_display
from alpha_system.ui.styles import status_card_class


def _render_first_run_card(ctx: DashboardContext) -> None:
    """First-run card — uses ops assistant pack when available."""
    from alpha_system.ui.services.nav import PAGE_SETTINGS
    from alpha_system.ui.services.ops_assistant_pack import (
        PRODUCT_NAME,
        needs_first_run_banner,
        setup_status,
    )

    if not needs_first_run_banner(ctx.root) or st.session_state.get("home_setup_dismissed"):
        return
    status = setup_status(ctx.root)
    with st.container(border=True):
        st.markdown("#### 시작하기 — 3분")
        st.caption(f"{PRODUCT_NAME} · 자동매매 아님 · 사람 승인만 target 반영")
        st.markdown(
            f"1. DART API: **{'준비됨' if status['dart_ok'] else '설정에서 키 입력'}**  \n"
            f"2. target_portfolio: **{'있음' if status['target_exists'] else '이식 zip으로 복원'}**  \n"
            "3. 설정 › 이식·백업에서 「첫 설정 완료」"
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("설정 · 이식·백업으로", key="home_to_settings", type="primary"):
                navigate(PAGE_SETTINGS)
        with c2:
            if st.button("오늘은 건너뛰기", key="home_setup_skip"):
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


def _render_system_judgment(ctx: DashboardContext) -> None:
    """Compact 3-metric strip — matches sellable IA mock (not legacy card stack)."""
    snap = build_judgment_snapshot(ctx)
    c1, c2, c3 = st.columns(3)
    c1.metric(
        copy_get("system_judgment", "row_regime", default="시장 레짐"),
        snap.regime_label,
    )
    c2.metric(
        copy_get("system_judgment", "row_t3", default="T3"),
        snap.t3_summary.split("·")[0].strip() if snap.t3_summary else "—",
    )
    c3.metric(
        copy_get("system_judgment", "row_next", default="다음 판정"),
        snap.next_judgment,
    )
    st.caption(
        copy_get(
            "system_judgment",
            "caption",
            default="자동 판정 · 승인 아님 · 조회·참고 · target 불변",
        )
    )


def _render_preparation(overview: HomeOverview) -> None:
    cols = st.columns(len(overview.preparation))
    for col, item in zip(cols, overview.preparation):
        with col:
            level = "ok" if item.status == "ok" else (
                "warn" if item.status == "warn" else "muted"
            )
            label = {
                "ok": "준비",
                "warn": "확인 필요",
                "missing": "미수집",
            }.get(item.status, item.status)
            st.markdown(
                f'<div class="{status_card_class(level)}">'
                f"<strong>{item.title}</strong> — {label}<br/>"
                f"<small>{item.summary}</small></div>",
                unsafe_allow_html=True,
            )


def _fmt_ret(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v * 100:+.1f}%"


def _render_today_line(ctx: DashboardContext, overview: HomeOverview, mom_n: int) -> None:
    """Wireframe: one-line today cue (merged 후보·모멘텀 first)."""
    action = overview.next_action
    n = overview.proposal_count or mom_n
    bits = [f"후보·모멘텀 {n}종", "주간·회차일 참고"]
    if action is not None:
        bits.append(action.title)
    st.markdown(f"**오늘 할 일** — {' · '.join(bits)}")
    if action is not None:
        if st.button(action.cta_label, key="home_next_action", type="secondary"):
            st.session_state["_home_run_next_action"] = True
            st.rerun()


def _run_next_action_if_flagged(ctx: DashboardContext, overview: HomeOverview) -> None:
    if not st.session_state.pop("_home_run_next_action", False):
        return
    action = overview.next_action
    if action is None:
        return
    if action.key == "quant":
        from alpha_system.ui.services.auto_journal import journal_data_refresh
        from alpha_system.ui.services.proposal_freeze import is_freeze_active
        from alpha_system.ui.services.refresh import run_quant_snapshot_refresh

        if is_freeze_active(ctx.root):
            st.error(
                "주간 정성 창으로 제안이 고정되어 정량 재실행이 차단됩니다. "
                "필수 게이트 승인 후 다시 시도하세요."
            )
            return
        with st.spinner("PyKRX·DART 수집과 alpha_scores 재계산 중…"):
            result = run_quant_snapshot_refresh(ctx.root, collect_scope="liquid")
        journal_data_refresh(
            as_of=date.today(),
            ok=result.ok,
            message=result.message,
            detail=result.detail,
        )
        if result.ok:
            ctx.runtime.touch_refresh("alpha_quant_snapshot")
            ctx.runtime.save(ctx.root / "data" / "alpha_dashboard_runtime.json")
            st.success(result.message)
            st.rerun()
        st.error(result.message)
        with st.expander("실패 상세"):
            st.json(result.detail)
        return
    navigate(action.page, focus=action.focus, prefill=action.prefill)


def _render_proposal_momentum_merged(ctx: DashboardContext, overview: HomeOverview, mom_board=None) -> None:
    """A안: 후보(정량순위) + 모멘텀 참고를 한 표로. 실행 버튼 없음."""
    import pandas as pd

    from alpha_system.ui.services.momentum_review import (
        GRADE_KO,
        build_momentum_review_board,
    )

    mom_board = mom_board or build_momentum_review_board(ctx)
    mom_by_tk = {i.ticker: i for i in mom_board.items}
    proposal = list(ctx.portfolio_rows or [])
    ops = list(ctx.ops_portfolio_rows or [])
    proposal_tks = {str(r.ticker).zfill(6) for r in proposal}
    ops_tks = {str(r.ticker).zfill(6) for r in ops}

    with st.container(border=True):
        h1, h2 = st.columns([4, 1])
        with h1:
            st.subheader(f"후보 · 모멘텀 ({len(proposal)}종)")
        with h2:
            show_nums = st.toggle("숫자 보기", key="mom_show_nums", value=False)

        st.caption(
            "순위=정량(QVM) · 모멘텀=참고 · 순위 밖≠자동 매도 · "
            "매도 권고는 익절·테제 신호만 · 자동매매·target 변경 없음"
        )

        rows: list[dict] = []
        for rank, r in enumerate(proposal, start=1):
            tk = str(r.ticker).zfill(6)
            m = mom_by_tk.get(tk)
            status = "보유·제안" if tk in ops_tks else "제안"
            abs_ko = "—"
            if m is not None:
                abs_ko = {"UP": "상승", "DOWN": "하락", "—": "—"}.get(
                    m.absolute, m.absolute
                )
            row = {
                "순위": rank,
                "종목": r.name,
                "모멘텀": GRADE_KO.get(m.grade, "—") if m else "—",
                "권고": m.advice if m else "—",
                "상태": status,
            }
            if show_nums:
                row["12-1"] = _fmt_ret(m.ret_12_1) if m else "—"
                row["교차%"] = (
                    f"{m.cross_pct:.0f}"
                    if m is not None and m.cross_pct is not None
                    else "—"
                )
                row["추세"] = abs_ko
                row["변동성"] = (
                    ("높음" if m.vol_high else "정상") if m else "—"
                )
            rows.append(row)

        if not rows:
            st.caption("제안 후보 없음 — 정량·게이트 후 다시 평가")
        else:
            if show_nums:
                cols = [
                    "순위",
                    "종목",
                    "모멘텀",
                    "권고",
                    "상태",
                    "12-1",
                    "교차%",
                    "추세",
                    "변동성",
                ]
                st.dataframe(
                    pd.DataFrame(rows)[cols],
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.dataframe(
                    pd.DataFrame(rows),
                    hide_index=True,
                    use_container_width=True,
                )

        # Holdings not in proposal band — review cue only (not auto-sell)
        outside = [r for r in ops if str(r.ticker).zfill(6) not in proposal_tks]
        if outside:
            st.markdown("**보유 · 순위 밖** (재검토 단서 · 자동 매도 아님)")
            out_rows = []
            for r in outside:
                tk = str(r.ticker).zfill(6)
                m = mom_by_tk.get(tk)
                out_rows.append(
                    {
                        "종목": r.name,
                        "모멘텀": GRADE_KO.get(m.grade, "—") if m else "—",
                        "권고": m.advice if m else "—",
                        "상태": "순위밖·보유",
                    }
                )
            st.dataframe(
                pd.DataFrame(out_rows),
                hide_index=True,
                use_container_width=True,
            )
            st.caption(
                "물린 종목도 여기 올 수 있음. 추가 매수(물타기) 금지 권고와 별개로, "
                "매도는 익절·논지 훼손 신호를 따르세요."
            )


def _render_monthly_rebal(ctx: DashboardContext) -> None:
    """Operator checklist — collapsed by default (wireframe)."""
    from alpha_system.ui.services.monthly_rebal_board import build_monthly_rebal_board
    from alpha_system.ui.services.nav import PAGE_PORTFOLIO, PAGE_REGIME
    from alpha_system.ui.services.portfolio_widgets import navigate_to_portfolio

    board = build_monthly_rebal_board(ctx)
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
            f"시장 {board.regime_label} · 자동매매 없음"
        )
        for card in board.cards:
            badge = tone_cls.get(card.tone, "alpha-badge-warn")
            flag = "지금" if card.do_now else ("참고" if card.key == "scale_in" else "대기")
            st.markdown(
                f'<div class="alpha-action-item">'
                f'<span class="{badge}">{flag}</span> '
                f"<strong>{card.title}</strong> — {card.status}<br/>"
                f"<small>{card.detail}</small></div>",
                unsafe_allow_html=True,
            )
            if card.items:
                for item in card.items:
                    cols = st.columns([5, 1])
                    with cols[0]:
                        st.markdown(
                            f"- **{item.name} ({item.ticker})** · {item.action}  \n"
                            f"  {item.detail}"
                        )
                    with cols[1]:
                        if st.button(
                            "→",
                            key=f"home_rebal_{card.key}_{item.ticker}",
                            help="보유 리뷰로",
                        ):
                            navigate_to_portfolio(item.ticker)
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
    """Review-only: exit cues from proposal_book only (no holdings consulting)."""
    from alpha_system.ui.services.ops_exit_signal import actionable_ops_signals
    from alpha_system.ui.services.portfolio_widgets import navigate_to_portfolio

    items = actionable_ops_signals(list(ctx.portfolio_rows or []))

    with st.container(border=True):
        st.subheader("익절 점검")
        st.caption(
            "제안 북 기준만 · 실보유 컨설팅 없음 · 읽기 전용 권고 · 자동 매도 없음 · "
            "줄이기 / 환금(절반) / 전량(타임캡·테제)"
        )
        if not items:
            st.markdown(
                '<div class="alpha-empty-queue"><strong>줄이기·환금·전량 없음 — 유지</strong></div>',
                unsafe_allow_html=True,
            )
            return
        for row in items:
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
                    f"<strong>{row.name} ({row.ticker})</strong><br/>"
                    f"{row.ops_signal_detail}</div>",
                    unsafe_allow_html=True,
                )
            with cols[1]:
                if st.button("→", key=f"home_exit_{row.ticker}", help="제안 북으로"):
                    navigate_to_portfolio(row.ticker)


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


def render_home(ctx: DashboardContext) -> None:
    """Ops assistant home — wireframe: 오늘 → 모멘텀 → 월리밸·후보 접힘."""
    from alpha_system.ui.services.momentum_review import build_momentum_review_board

    frozen = ctx.runtime.effective_thesis_damage()
    past_window = ctx.as_of >= ctx.window_end
    overview = build_home_overview(ctx)
    blocker = overview.next_action
    mom_board = build_momentum_review_board(ctx)

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

    _render_today_line(ctx, overview, len(mom_board.items))
    _run_next_action_if_flagged(ctx, overview)
    _render_proposal_momentum_merged(ctx, overview, mom_board=mom_board)
    _render_monthly_rebal(ctx)

    with st.expander("접힌 운용 · 레짐 · 익절 · 자동 준비 · 트랜치", expanded=False):
        st.caption("첫 화면은 「오늘 → 후보·모멘텀 → 월 리밸(접힘)」.")
        _render_system_judgment(ctx)
        _render_holdings_cues(ctx)
        st.markdown("#### 자동 준비")
        _render_preparation(overview)

        m1, m2, m3 = st.columns(3)
        m1.metric("집행률", f"{ctx.execution_rate_pct or 0}%")
        m2.metric(
            "제안/보유/목표",
            f"{overview.proposal_count} / {ctx.held_kr_alpha} / {ctx.target_kr_alpha}",
        )
        with m3:
            st.metric("재량 이탈 누적", ctx.discretionary_count)
            if st.button("재량 이탈 보기", key="home_disc"):
                navigate(PAGE_JOURNAL, focus=FOCUS_JOURNAL_DISC)

        if not ctx.pre_launch:
            st.markdown("#### 액션 큐")
            if ctx.action_queue:
                for item in ctx.action_queue:
                    badge = {
                        "danger": "alpha-badge-danger",
                        "warn": "alpha-badge-warn",
                        "info": "alpha-badge-ok",
                    }.get(item.severity.value, "alpha-badge-warn")
                    cols = st.columns([5, 1])
                    with cols[0]:
                        st.markdown(
                            f'<div class="alpha-action-item"><span class="{badge}">'
                            f"{item.severity.value}</span> <strong>{item.title}</strong>"
                            f"<br/>{item.detail}</div>",
                            unsafe_allow_html=True,
                        )
                    with cols[1]:
                        if st.button("열기", key=f"aq_{item.key}"):
                            open_panel(item.key)
            else:
                st.caption(f"오늘 할 일 없음 — 다음 판정: {next_judgment_hint(ctx)}")
            render_active_panel(ctx)

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
        st.caption(f"window_end {ctx.window_end.isoformat()} — D-{max(0, days_left)}")

        st.markdown("#### 데이터 상세")
        for src in ctx.source_status:
            stale_badge = (
                '<span class="alpha-badge-danger">갱신 필요</span>'
                if src.stale
                else '<span class="alpha-badge-ok">정상</span>'
            )
            as_of_s = src.as_of.isoformat() if src.as_of else "—"
            st.markdown(
                f"**{src.label}** {stale_badge} — as_of {as_of_s} "
                f"({src.path}) {src.detail}",
                unsafe_allow_html=True,
            )
        st.markdown(
            f"**CECS 검토(선택)** — final {ctx.cecs_final_count} / {ctx.cecs_total}종 · 순위 미반영"
        )
        st.markdown(f"**sector_peer_fallback** — {ctx.sector_peer_fallback_count}종")
        st.markdown(f"**gate_pass** — {ctx.gate_pass_count}종")
