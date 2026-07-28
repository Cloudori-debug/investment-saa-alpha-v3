"""Portfolio bullet list + accordion expand (parent-row extension, no nested cards)."""

from __future__ import annotations

from typing import Optional

import streamlit as st

from alpha_system.journal import list_entries
from alpha_system.ui.services.context import DashboardContext, PortfolioRow, ScoreboardRow
from alpha_system.ui.services.portfolio_metrics import price_bar_view, weight_bar_view
from alpha_system.ui.services.ui_copy import copy_get

SESSION_EXPANDED = "portfolio_expanded_ticker"
SESSION_NAV_EXPAND = "portfolio_nav_expand_ticker"


def navigate_to_portfolio(ticker: str) -> None:
    """Home summary → portfolio page with ticker expanded (accordion)."""
    from alpha_system.ui.services.nav import PAGE_PORTFOLIO, navigate

    st.session_state[SESSION_NAV_EXPAND] = ticker
    st.session_state[SESSION_EXPANDED] = ticker
    navigate(PAGE_PORTFOLIO)


def _fmt_price(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f}"


def render_price_bar_html(row: PortfolioRow, *, show_labels: bool = False) -> str:
    """Price axis only — no weight/cap marker."""
    if not row.has_target:
        if row.target_gap_kind == "legacy_pending":
            badge = copy_get("portfolio", "badge_legacy", default="이행대기")
            msg = copy_get(
                "portfolio",
                "target_missing_legacy",
                default="목표가 없음 — 레거시 보유, 이행 심사 대기",
            )
            return (
                f'<div class="pf-missing pf-missing-legacy">'
                f'<span class="alpha-badge-warn">{badge}</span> {msg}'
                f"</div>"
            )
        if row.target_gap_kind == "screen_pending":
            badge = copy_get("portfolio", "badge_screen", default="스크린")
            msg = copy_get(
                "portfolio",
                "target_missing_screen",
                default="목표가 없음 — 다음 주 통합 보고서(E)까지 대기 · 편입 차단",
            )
            return (
                f'<div class="pf-missing pf-missing-legacy">'
                f'<span class="alpha-badge-warn">{badge}</span> {msg}'
                f"</div>"
            )
        if row.target_gap_kind == "price_missing":
            msg = copy_get(
                "portfolio",
                "price_missing_signal_invalid",
                default="데이터 없음 — 신호 무효 (가격 확인)",
            )
            return (
                f'<div class="pf-missing">'
                f'<span class="alpha-badge-danger">데이터</span> {msg}'
                f"</div>"
            )
        badge = copy_get("portfolio", "badge_violation", default="위반")
        msg = copy_get(
            "portfolio",
            "target_missing_violation",
            default="목표가 없음 — 편입 규칙 위반",
        )
        return (
            f'<div class="pf-missing">'
            f'<span class="alpha-badge-danger">{badge}</span> {msg}'
            f"</div>"
        )

    view = price_bar_view(row.price_progress_pct)
    loss_html = ""
    if view.loss_pct is not None:
        loss_html = f' <span class="pf-tone-danger">손실 {view.loss_pct:.1f}%</span>'

    labels = ""
    if show_labels:
        labels = (
            f'<div class="pf-bar-labels">'
            f"<span>현재 {_fmt_price(row.current_price)}</span>"
            f"<span>목표 {_fmt_price(row.target_price)}</span>"
            f"</div>"
        )
    return (
        f"{labels}"
        f'<div class="pf-bar-block">'
        f'<div class="pf-bar-caption">가격 '
        f'<span class="pf-tone-accent">{view.label}</span>{loss_html}</div>'
        f'<div class="pf-bar-track pf-bar-price">'
        f'<div class="pf-bar-fill pf-fill-accent" style="width:{view.fill_pct:.1f}%"></div>'
        f"</div></div>"
    )


def render_weight_bar_html(row: PortfolioRow, *, thin: bool = True) -> str:
    """Weight axis: 0 → market_value_cap. Independent of price progress."""
    view = weight_bar_view(row.weight_pct, row.cap_pct)
    thin_cls = " pf-bar-thin" if thin else ""
    badge = ""
    if view.tone == "danger":
        badge = ' <span class="alpha-badge-danger">감축</span>'
    elif view.tone == "warn":
        badge = ' <span class="alpha-badge-warn">cap 임박</span>'
    return (
        f'<div class="pf-bar-block">'
        f'<div class="pf-bar-caption">제안 비중 '
        f'<span class="pf-weight-{view.tone}">{view.label}</span>{badge}</div>'
        f'<div class="pf-bar-track{thin_cls}">'
        f'<div class="pf-bar-fill pf-fill-{view.tone}" style="width:{view.fill_pct:.1f}%"></div>'
        f"</div></div>"
    )


def _ops_badge_html(row: PortfolioRow) -> str:
    """Simple ops cue badge — only when ops_signal is set."""
    kind = (row.ops_signal or "").strip()
    label = (row.ops_signal_label or "").strip()
    if not kind or not label:
        return ""
    cls = {
        "hold": "alpha-badge-ok",
        "trim": "alpha-badge-warn",
        "cash_half": "alpha-badge-warn",
        "exit_full": "alpha-badge-danger",
        "missing": "alpha-badge-warn",
        # legacy
        "review": "alpha-badge-danger",
    }.get(kind, "alpha-badge-warn")
    return f'<span class="{cls} ops-cue">{label}</span> '


def _row_main_html(row: PortfolioRow) -> str:
    badge = _ops_badge_html(row)
    if row.ops_signal and row.ops_signal_detail:
        upside_txt = row.ops_signal_detail
        tone = {
            "hold": "accent",
            "trim": "danger",
            "cash_half": "danger",
            "exit_full": "danger",
            "missing": "muted",
            "review": "danger",
        }.get(row.ops_signal, "muted")
    else:
        upside = row.remaining_upside_pct
        if not row.has_target:
            if row.target_gap_kind == "legacy_pending":
                upside_txt = "레거시·이행대기"
                tone = "muted"
            elif row.target_gap_kind == "screen_pending":
                upside_txt = "스크린 제안"
                tone = "muted"
            else:
                upside_txt = "목표가 없음"
                tone = "danger"
        elif upside is None:
            upside_txt = "—"
            tone = "muted"
        else:
            upside_txt = f"목표까지 {upside:+.1f}%"
            tone = "accent"

    wview = weight_bar_view(row.weight_pct, row.cap_pct)
    weight_cls = f"pf-weight-{wview.tone}"
    weight_prefix = "보유" if (row.extra or {}).get("book") == "ops" else "제안"
    return (
        f'<div class="pf-row-main">'
        f'<div class="pf-bullet-top">'
        f"{badge}<strong>{row.name} ({row.ticker})</strong> "
        f'<span class="{weight_cls}">{weight_prefix} {row.weight_pct:.1f}%</span>'
        f'<span class="pf-upside pf-tone-{tone}">{upside_txt}</span>'
        f"</div>"
        f"{render_price_bar_html(row)}"
        f"{render_weight_bar_html(row, thin=True)}"
        f"</div>"
    )


def _cecs_subs(sc: Optional[ScoreboardRow], cecs_df_row: Optional[dict]) -> dict[str, Optional[float]]:
    keys = ("execution_continuity", "pension_flow_score", "investment_purpose_flag")
    out: dict[str, Optional[float]] = {k: None for k in keys}
    if cecs_df_row:
        for k in keys:
            raw = cecs_df_row.get(k)
            try:
                if raw is not None and str(raw).strip() != "":
                    out[k] = float(raw)
            except (TypeError, ValueError):
                pass
    return out


def _load_cecs_row(ctx: DashboardContext, ticker: str) -> Optional[dict]:
    path = ctx.root / "data" / "cecs_manual_scoring_template.csv"
    if not path.exists():
        return None
    import pandas as pd

    df = pd.read_csv(path, dtype=str)
    if df.empty or "ticker" not in df.columns:
        return None
    hit = df[df["ticker"].astype(str).str.zfill(6) == ticker]
    if hit.empty:
        return None
    return hit.iloc[0].to_dict()


def _section(title: str, body_html: str = "") -> str:
    return f'<div class="pf-sec"><div class="pf-sec-title">{title}</div>{body_html}</div>'


def render_expanded_html(ctx: DashboardContext, row: PortfolioRow) -> str:
    """Expanded area as parent-row extension — no nested card boxes."""
    wview = weight_bar_view(row.weight_pct, row.cap_pct)
    book = (row.extra or {}).get("book")
    weight_word = "보유 비중" if book == "ops" else "제안 비중"
    step = (row.extra or {}).get("ops_step_id") or ""
    step_line = ""
    if row.ops_signal == "cash_half":
        step_line = (
            "<br/>스텝 S1: 수량 절반(내림) → 잔여는 탈락·신규매수·4주 미상향 시 전량"
        )
    elif row.ops_signal == "exit_full":
        step_line = f"<br/>스텝 {step or 'S2/S0'}: 잔여·전량 환금 · 로테이션/테제"
    elif row.ops_signal == "trim":
        step_line = "<br/>스텝 S근접: ¼만 줄이기(도달 전)"
    nums = (
        f'<div class="pf-sec-body">'
        f"{weight_word} {row.weight_pct:.1f}% "
        f"(상한 {row.cap_pct:.0f}%) · total_score "
        f"{row.total_score if row.total_score is not None else '—'}<br/>"
        f"현재 {_fmt_price(row.current_price)} · "
        f"목표 {_fmt_price(row.target_price)}"
        + (
            f"<br/>운영 신호: <strong>{row.ops_signal_label}</strong> — {row.ops_signal_detail}"
            if row.ops_signal_label
            else ""
        )
        + step_line
        + f"</div>"
    )
    bars = render_price_bar_html(row, show_labels=True) + render_weight_bar_html(row, thin=False)

    sc = next((s for s in ctx.scoreboard_rows if s.ticker == row.ticker), None)
    score_bits = (
        f"트랜치 {row.tranche_source} · total_score "
        f"{row.total_score if row.total_score is not None else '—'}"
    )
    if wview.reduce_signal:
        score_bits += ' · <span class="alpha-badge-danger">비중 한도 초과 · 감축 신호</span>'

    rescores = [
        e
        for e in list_entries()
        if e.subject == row.ticker
        and e.action_kind in {"RESCORE", "TARGET_VALUATION_MODIFY", "WARN_TARGET_VALUATION_MODIFY"}
    ]
    rescores = sorted(rescores, key=lambda e: e.recorded_at, reverse=True)
    if rescores:
        trend = " → ".join(
            f"{e.recorded_at[:10]}:{e.score_snapshot.get('total_score', e.action_kind)}"
            for e in rescores[:5]
        )
        trend_html = f'<div class="pf-sec-body">{trend}</div>'
    else:
        trend_html = '<div class="pf-sec-body muted">재채점 이력 없음</div>'

    entries = [
        e
        for e in list_entries()
        if e.subject == row.ticker
        and e.action_kind in {
            "ENTRY_JOURNAL",
            "TARGET_VALUATION_MODIFY",
            "WARN_TARGET_VALUATION_MODIFY",
        }
    ]
    entry_j = [e for e in entries if e.action_kind == "ENTRY_JOURNAL"]
    modify_j = [e for e in entries if e.action_kind != "ENTRY_JOURNAL"]

    if entry_j:
        journal_html = "".join(
            f'<div class="pf-sec-body">{j.recorded_at[:10]} — '
            f"{(j.rationale or '(내용 없음)')[:240]}</div>"
            for j in entry_j[-3:]
        )
    elif row.target_gap_kind == "legacy_pending":
        journal_html = (
            f'<div class="pf-sec-body muted">'
            f'{copy_get("portfolio", "entry_journal_legacy", default="신규 시스템 편입 절차 미경유 (레거시 보유)")}'
            f"</div>"
        )
    else:
        journal_html = (
            f'<div class="pf-sec-body muted">'
            f'{copy_get("portfolio", "entry_journal_empty", default="편입 저널 없음")}'
            f"</div>"
        )

    cecs_raw = _load_cecs_row(ctx, row.ticker)
    subs = _cecs_subs(sc, cecs_raw)

    def _sub(v: Optional[float]) -> str:
        return f"{v:.2f}" if v is not None else "—"

    cecs_html = (
        f'<div class="pf-sec-body">'
        f"execution {_sub(subs['execution_continuity'])} · "
        f"pension {_sub(subs['pension_flow_score'])} · "
        f"purpose {_sub(subs['investment_purpose_flag'])}"
        f"</div>"
    )

    modify_html = ""
    if modify_j:
        modify_html = _section(
            "목표가 수정 이력",
            "".join(
                f'<div class="pf-sec-body">{j.recorded_at[:10]}'
                f'{" (WARN)" if "WARN" in j.action_kind else ""}: '
                f"{(j.rationale or j.discretionary_reason or '')[:240]}</div>"
                for j in sorted(modify_j, key=lambda x: x.recorded_at, reverse=True)[:5]
            ),
        )

    return (
        f'<div class="pf-extend">'
        f"{_section('수치', nums)}"
        f"{_section('게이지', bars)}"
        f"{_section('스코어', f'<div class=\"pf-sec-body\">{score_bits}</div>')}"
        f"{_section('재채점 추이', trend_html)}"
        f"{_section('편입 근거', journal_html)}"
        f"{_section('CECS 하위지표', cecs_html)}"
        f"{modify_html}"
        f"</div>"
    )


def render_portfolio_bullets(
    ctx: DashboardContext,
    *,
    mode: str = "full",
    key_prefix: str = "pf",
) -> None:
    """
    mode:
      - full: accordion expand on portfolio page
      - summary: compact home widget; click navigates to portfolio
    """
    rows = ctx.portfolio_rows
    if not rows:
        st.info("kr_alpha 보유 종목이 없습니다.")
        return

    nav = st.session_state.pop(SESSION_NAV_EXPAND, None)
    if nav and mode == "full":
        st.session_state[SESSION_EXPANDED] = nav

    expanded = st.session_state.get(SESSION_EXPANDED)

    st.markdown('<div class="pf-list">', unsafe_allow_html=True)

    for row in rows:
        is_open = mode == "full" and expanded == row.ticker
        # Fixed column ratio always — prevents horizontal jump on expand/collapse
        left, right = st.columns([6, 1])
        with left:
            st.markdown(_row_main_html(row), unsafe_allow_html=True)
        with right:
            if mode == "summary":
                if st.button("→", key=f"{key_prefix}_go_{row.ticker}", help=f"{row.name} 상세"):
                    navigate_to_portfolio(row.ticker)
            else:
                toggle_label = "접기" if is_open else "펼침"
                if st.button(toggle_label, key=f"{key_prefix}_tog_{row.ticker}"):
                    st.session_state[SESSION_EXPANDED] = None if is_open else row.ticker
                    st.rerun()

        if is_open:
            st.markdown(render_expanded_html(ctx, row), unsafe_allow_html=True)

        st.markdown('<div class="pf-hairline"></div>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)
