"""Portfolio bullet list + accordion expand (parent-row extension, no nested cards)."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Optional

import streamlit as st

from alpha_system.proposal_chart import ChartRead, norm_ticker, summary_tone
from alpha_system.ui.services.context import DashboardContext, PortfolioRow
from alpha_system.ui.services.portfolio_metrics import price_bar_view, weight_bar_view
from alpha_system.ui.services.rank_watchboard import naver_name_chart_html
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


def _is_short_ops_row(row: PortfolioRow) -> bool:
    return str((row.extra or {}).get("ops_book") or "") == "short"


def _quant_caption_html(row: PortfolioRow) -> str:
    if _is_short_ops_row(row):
        return ""
    extra = row.extra or {}
    if not extra.get("quant_ok"):
        return ""
    pbr = extra.get("quant_pbr_draft")
    mid = extra.get("quant_price_mid")
    pbr_s = f"{float(pbr):.2f}" if pbr not in (None, "") else "—"
    if mid not in (None, ""):
        try:
            mid_s = f"{int(round(float(mid))):,}원"
        except (TypeError, ValueError):
            mid_s = "—"
    else:
        mid_s = "—"
    approved = "승인목표와 별개" if row.has_target else "E 승인 전"
    return (
        f'<div class="pf-bar-caption pf-quant-note">'
        f"정량초안 P/B {pbr_s} · {mid_s} · {approved}</div>"
    )


def _won(v) -> str:
    if v is None or v == "":
        return "—"
    try:
        return f"{int(round(float(v))):,}"
    except (TypeError, ValueError):
        return "—"


def _rung_now_idx(current: Optional[float], rungs: list) -> int:
    """Last rung whose price the spot has reached (0–4)."""
    if current is None or not rungs:
        return 0
    try:
        cur = float(current)
    except (TypeError, ValueError):
        return 0
    idx = 0
    for i, px in enumerate(rungs[:5]):
        try:
            if cur + 1e-9 >= float(px):
                idx = i
        except (TypeError, ValueError):
            continue
    return idx


def _header_cue(row: PortfolioRow) -> tuple[str, str]:
    """Short right-side cue + tone. Badge already carries 유지/줄이기/환금."""
    extra = row.extra or {}
    if extra.get("proposal_eligible") is False:
        reason = str(extra.get("ineligible_reason") or row.target_detail or "부적격")
        return reason, "danger"
    if row.ops_signal and row.ops_signal_detail:
        t = str(row.ops_signal_detail)
        for junk in (
            " · 권고(사람 집행)",
            " · 권고",
            "목표가 근접 · ",
            "목표가 도달 · ",
            "수량 절반(내림) · ",
        ):
            t = t.replace(junk, "")
        t = t.strip(" ·")
        label = (row.ops_signal_label or "").strip()
        if label and t.startswith(label):
            t = t[len(label) :].strip(" ·")
        tone = {
            "hold": "accent",
            "trim": "warn",
            "cash_half": "warn",
            "exit_full": "danger",
            "missing": "muted",
            "review": "danger",
        }.get(row.ops_signal, "muted")
        return t, tone
    upside = row.remaining_upside_pct
    if not row.has_target:
        if row.target_gap_kind == "legacy_pending":
            return "레거시·이행대기", "muted"
        if row.target_gap_kind == "screen_pending":
            return "스크린 제안", "muted"
        return "목표가 없음", "danger"
    if upside is None:
        return "—", "muted"
    return f"목표까지 {upside:+.1f}%", "accent"


def _missing_target_banner(row: PortfolioRow) -> str:
    if _is_short_ops_row(row):
        return ""
    if (row.extra or {}).get("proposal_eligible") is False:
        reason = str(
            (row.extra or {}).get("ineligible_reason") or row.target_detail or "부적격"
        )
        return (
            f'<div class="pf-missing">'
            f'<span class="alpha-badge-danger">부적격</span> {reason}'
            f"</div>"
        )
    if row.has_target:
        return ""
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
            default="목표가 없음 — 제안 종목에서 정량초안 승인 · 편입 차단",
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


def _ladder_bar_html(row: PortfolioRow, *, show_labels: bool) -> str:
    extra = row.extra or {}
    fill = float(extra.get("ladder_fill_pct") or 0.0)
    fill = min(100.0, max(0.0, fill))
    rungs = extra.get("ladder_rungs") or []
    labels = extra.get("ladder_labels") or ("매수1", "매수2", "줄이기", "절반", "전량")
    high_src = extra.get("ladder_high_source") or "approved"
    ceiling_word = "상한(초안)" if high_src == "quant_draft" else "상한"
    if extra.get("ladder_over_high"):
        pct_label = "상한 위"
    elif extra.get("ladder_under_low"):
        pct_label = "하한 아래"
    else:
        pct_label = f"{fill:.0f}%"
    now_idx = _rung_now_idx(row.current_price, list(rungs))
    lo_s = f"{_won(extra.get('ladder_low'))}원"
    hi_s = f"{_won(extra.get('ladder_high'))}원"
    axis = (
        f'<div class="pf-bar-labels pf-ladder-axis">'
        f'<span><span class="pf-kicker">하한</span>'
        f'<span class="pf-num">{lo_s}</span></span>'
        f'<span class="pf-axis-now"><span class="pf-kicker">현재 · {pct_label}</span></span>'
        f'<span><span class="pf-kicker">{ceiling_word}</span>'
        f'<span class="pf-num">{hi_s}</span></span>'
        f"</div>"
    )
    ticks = []
    for i in range(5):
        left = i * 25.0
        ticks.append(
            f'<span class="pf-bar-tick pf-bar-tick-{i}" style="left:{left:.0f}%"></span>'
        )
    ticks.append(
        f'<span class="pf-bar-now" style="left:{fill:.1f}%" title="현재"></span>'
    )
    rung_bits = []
    for i, name in enumerate(labels[:5]):
        px = _won(rungs[i]) if i < len(rungs) else "—"
        px_s = f"{px}원" if px != "—" else "—"
        state = "pf-rung-now" if i == now_idx else ("pf-rung-past" if i < now_idx else "pf-rung-next")
        rung_bits.append(
            f'<span class="{state}">'
            f'<span class="pf-ladder-rung-name">{name}</span>'
            f'<span class="pf-ladder-rung-px">{px_s}</span></span>'
        )
    rungs_html = f'<div class="pf-ladder-rungs">{"".join(rung_bits)}</div>'
    note = extra.get("ladder_note") or ""
    note_html = f'<div class="pf-bar-caption">{note}</div>' if (show_labels and note) else ""
    return (
        f'<div class="pf-ladder">'
        f"{axis}"
        f'<div class="pf-bar-block">'
        f'<div class="pf-bar-track pf-bar-price pf-bar-ladder">'
        f'<div class="pf-bar-fill pf-fill-accent" style="width:{fill:.1f}%"></div>'
        f"{''.join(ticks)}"
        f"</div></div>"
        f"{rungs_html}"
        f"{note_html}"
        f"</div>"
    )


def render_price_bar_html(row: PortfolioRow, *, show_labels: bool = False) -> str:
    """Price axis only — no weight/cap marker."""
    if _is_short_ops_row(row):
        # Momentum sleeve: badge carries the cue; no mid P/B ladder.
        return ""
    extra = row.extra or {}
    if extra.get("proposal_eligible") is False:
        return _missing_target_banner(row)
    ladder_ok = bool(extra.get("ladder_ok"))
    missing = _missing_target_banner(row)
    if ladder_ok:
        return f"{missing}{_ladder_bar_html(row, show_labels=show_labels)}{_quant_caption_html(row)}"
    if not row.has_target:
        return f"{missing}{_quant_caption_html(row)}"

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
        f"{_quant_caption_html(row)}"
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
        f'<div class="pf-bar-caption">제안 {row.weight_pct:.1f}%'
        f'<span class="pf-weight-{view.tone}"> · 상한 {row.cap_pct:.0f}%</span>{badge}</div>'
        f'<div class="pf-bar-track{thin_cls}">'
        f'<div class="pf-bar-fill pf-fill-{view.tone}" style="width:{view.fill_pct:.1f}%"></div>'
        f"</div></div>"
    )


def _unified_cue(row: PortfolioRow, chart: ChartRead | None = None):
    from alpha_system.ui.services.trade_cue_merge import unify_ops_and_chart

    return unify_ops_and_chart(
        ops_kind=row.ops_signal or "",
        ops_label=row.ops_signal_label or "",
        chart=chart,
        ladder=_ladder_hint(row),
    )


def _chart_cue_active(item: ChartRead | None) -> bool:
    if item is None:
        return False
    if (item.note or "").strip():
        return True
    return bool(item.ma_label or item.rsi_label or item.bb_label or item.macd_label)


def _ops_badge_html(row: PortfolioRow, chart: ChartRead | None = None) -> str:
    """Unified action badge (+ optional short absorb chip)."""
    cue = _unified_cue(row, chart)
    tone_cls = {
        "ok": "alpha-badge-ok",
        "accent": "alpha-badge-ok",
        "warn": "alpha-badge-warn",
        "hot": "alpha-badge-warn",
        "weak": "alpha-badge-warn",
        "danger": "alpha-badge-danger",
        "muted": "alpha-badge-warn",
    }.get(cue.tone, "alpha-badge-warn")
    badge_txt = cue.ops_part if _chart_cue_active(chart) else cue.action
    parts = [f'<span class="{tone_cls} ops-cue">{escape(badge_txt)}</span>']
    extra = row.extra or {}
    if extra.get("absorb_review"):
        alabel = escape(str(extra.get("absorb_label") or "흡수검토"))
        parts.append(f'<span class="alpha-badge-warn ops-cue absorb-cue">{alabel}</span>')
    return " ".join(parts) + " "


def _ladder_hint(row: PortfolioRow) -> str:
    extra = row.extra or {}
    rungs = extra.get("ladder_rungs") or []
    labels = extra.get("ladder_labels") or ("매수1", "매수2", "줄이기", "절반", "전량")
    cur = row.current_price
    if cur is None or not rungs:
        return ""
    idx = 0
    try:
        price = float(cur)
        for i, px in enumerate(list(rungs)[:5]):
            if price + 1e-9 >= float(px):
                idx = i
    except (TypeError, ValueError):
        return ""
    name = labels[idx] if idx < len(labels) else ""
    return f"지금 {name}" if name else ""


def _chart_read_html(row: PortfolioRow, item: ChartRead | None) -> str:
    """Signal headline + why + evidence (book / chart / indicator chips)."""
    cue = _unified_cue(row, item)
    if not (cue.why or cue.detail):
        return ""
    chart_tone = {
        "hot": "hot",
        "danger": "hot",
        "warn": "weak",
        "weak": "weak",
        "ok": "ok",
        "accent": "ok",
        "muted": "ok",
    }.get(cue.tone, "ok")
    if item is not None:
        st = summary_tone(item)
        if st == "hot":
            chart_tone = "hot"
        elif st == "weak" and chart_tone == "ok":
            chart_tone = "weak"
    chart_ev = cue.evidence_chart
    if cue.chart_reason and chart_ev not in ("일봉 미읽음", "차트미읽음"):
        if cue.chart_reason not in chart_ev:
            chart_ev = f"{chart_ev} — {cue.chart_reason}"
    chips = "".join(
        f'<span class="pf-signal-chip">{escape(c)}</span>' for c in cue.chips
    )
    chips_blk = (
        f'<div class="pf-signal-chips">{chips}</div>' if chips else ""
    )
    return (
        f'<div class="pf-signal pf-signal-{escape(chart_tone)}">'
        f'<div class="pf-signal-headline">{escape(cue.headline)}</div>'
        f'<div class="pf-signal-why">{escape(cue.why)}</div>'
        f'<div class="pf-signal-evidence">'
        f'<div class="pf-signal-row">'
        f'<span class="pf-signal-lbl">장부</span>'
        f"<span>{escape(cue.evidence_ops)}</span></div>"
        f'<div class="pf-signal-row">'
        f'<span class="pf-signal-lbl">차트</span>'
        f"<span>{escape(chart_ev)}</span></div>"
        f"</div>"
        f"{chips_blk}"
        f"</div>"
    )


def _cross_book_chips_html(
    row: PortfolioRow,
    *,
    held: set[str],
    proposed: set[str],
    blocked: set[str],
    phcvs: set[str] | None = None,
) -> str:
    """③↔④ overlap chips — same ticker once in the other book, no duplicate body."""
    tk = norm_ticker(row.ticker)
    book = str((row.extra or {}).get("book") or "")
    chips: list[str] = []
    if book == "ops":
        if tk in proposed:
            chips.append(
                '<span class="pf-xchip pf-xchip-prop">'
                f'{escape(copy_get("portfolio", "chip_in_proposal", default="제안중"))}'
                "</span>"
            )
        elif tk in blocked:
            chips.append(
                '<span class="pf-xchip pf-xchip-wait">'
                f'{escape(copy_get("portfolio", "chip_in_blocked", default="대기중"))}'
                "</span>"
            )
    else:
        if tk in held:
            chips.append(
                '<span class="pf-xchip pf-xchip-hold">'
                f'{escape(copy_get("portfolio", "chip_in_holdings", default="보유중"))}'
                "</span>"
            )
    if phcvs and tk in phcvs:
        chips.append(
            '<span class="pf-xchip pf-xchip-phcvs">'
            f'{escape(copy_get("portfolio", "chip_in_phcvs", default="PH추적"))}'
            "</span>"
        )
    return "".join(chips)


def _row_main_html(
    row: PortfolioRow,
    *,
    chart: ChartRead | None = None,
    held: set[str] | None = None,
    proposed: set[str] | None = None,
    blocked: set[str] | None = None,
    phcvs: set[str] | None = None,
) -> str:
    badge = _ops_badge_html(row, chart)
    extra = row.extra or {}
    is_blocked = extra.get("proposal_eligible") is False
    is_ops = extra.get("book") == "ops"
    if is_blocked:
        badge = '<span class="alpha-badge-danger">부적격</span> ' + badge
    upside_txt, tone = _header_cue(row)
    # Holdings overlapping ③: keep cue to badge + chip; drop long upside text.
    in_proposal = is_ops and norm_ticker(row.ticker) in (proposed or set())
    if in_proposal:
        upside_txt, tone = "", "muted"
    wview = weight_bar_view(row.weight_pct, row.cap_pct)
    weight_cls = f"pf-weight-{wview.tone}"
    if is_ops:
        weight_cls = "pf-weight-ok"
        weight_chip = f"보유 {row.weight_pct:.1f}%"
    elif is_blocked:
        weight_cls = "pf-weight-muted"
        weight_chip = "비중 없음"
    else:
        weight_chip = f"제안 {row.weight_pct:.1f}%"
    spot = ""
    if not is_blocked and row.current_price is not None:
        spot = f'<span class="pf-spot">{_fmt_price(row.current_price)}원</span>'
    cross = _cross_book_chips_html(
        row,
        held=held or set(),
        proposed=proposed or set(),
        blocked=blocked or set(),
        phcvs=phcvs,
    )
    upside_html = (
        f'<span class="pf-upside pf-tone-{tone}">{upside_txt}</span>'
        if upside_txt
        else ""
    )
    # Ops collapsed: proposal-like chrome; skip dense signal dump (expand has it).
    signal_html = ""
    if not is_blocked and not is_ops:
        signal_html = _chart_read_html(row, chart)
    bar_html = ""
    if not is_blocked and not in_proposal:
        bar_html = render_price_bar_html(row)
    return (
        f'<div class="pf-row-main">'
        f'<div class="pf-bullet-top">'
        f'<span class="pf-id">{badge}'
        f"{naver_name_chart_html(row.ticker, row.name)}</span>"
        f"{cross}"
        f'<span class="{weight_cls} pf-wchip">{weight_chip}</span>'
        f"{spot}"
        f"{upside_html}"
        f"</div>"
        f"{signal_html}"
        f"{bar_html}"
        f"</div>"
    )


def _section(title: str, body_html: str = "") -> str:
    return f'<div class="pf-sec"><div class="pf-sec-title">{title}</div>{body_html}</div>'


def _proposal_expand_html(row: PortfolioRow) -> str:
    """Short expand for the screen book — score, gate, target. No CECS dump."""
    extra = row.extra or {}
    blocked = extra.get("proposal_eligible") is False
    score = row.total_score
    score_s = f"{float(score):.2f}" if score is not None else "—"
    bits: list[str] = []
    if _is_short_ops_row(row):
        sm = extra.get("score_m")
        r6 = extra.get("return_6m")
        dd = extra.get("drawdown_52w_pct")
        xs = extra.get("mom_xs_pct")
        trend = extra.get("trend_sign") or "—"
        sm_s = f"{float(sm):g}" if sm not in (None, "") else "—"
        r6_s = f"{float(r6)*100:.1f}%" if r6 not in (None, "") else "—"
        dd_s = f"{float(dd):+.1f}%" if dd not in (None, "") else "—"
        xs_s = f"{float(xs):.0f}%ile" if xs not in (None, "") else "—"
        bits.append(
            _section(
                "단기 제안",
                f'<div class="pf-sec-body">'
                f"비중 {row.weight_pct:.1f}% · 점수 {score_s}<br/>"
                f"현재 {_fmt_price(row.current_price)}원 · "
                f"배지 {row.ops_signal_label or '—'}<br/>"
                f"추세 {trend} · score_m {sm_s} · 6M {r6_s} · "
                f"상대 {xs_s} · 고가대비 {dd_s}"
                f"</div>",
            )
        )
        if row.ops_signal_detail:
            bits.append(
                _section(
                    "운영 신호",
                    f'<div class="pf-sec-body">{escape(str(row.ops_signal_detail))}</div>',
                )
            )
        return "".join(bits)
    if blocked:
        reason = str(extra.get("ineligible_reason") or row.target_detail or "부적격")
        bits.append(
            _section(
                "편입하지 않은 이유",
                f'<div class="pf-sec-body">{reason}</div>',
            )
        )
        bits.append(
            _section("점수", f'<div class="pf-sec-body">total_score {score_s}</div>')
        )
    else:
        bits.append(
            _section(
                "제안",
                f'<div class="pf-sec-body">'
                f"비중 {row.weight_pct:.1f}% · 점수 {score_s}<br/>"
                f"현재 {_fmt_price(row.current_price)} · 목표 {_fmt_price(row.target_price)}"
                f"</div>",
            )
        )
        if extra.get("quant_ok"):
            pbr_d = extra.get("quant_pbr_draft")
            mid = extra.get("quant_price_mid")
            d_s = f"{float(pbr_d):.2f}" if pbr_d not in (None, "") else "—"
            mid_s = _won(mid)
            mid_s = f"{mid_s}원" if mid_s != "—" else "—"
            note = extra.get("quant_note") or extra.get("quant_method") or ""
            bits.append(
                _section(
                    "혼합 목표가",
                    f'<div class="pf-sec-body">PBR {d_s} · {mid_s}'
                    f"{'<br/>' + str(note) if note else ''}</div>",
                )
            )
    hk = extra.get("hakedaka_detail")
    if hk:
        theme = " · 경기민감 테마" if extra.get("cyclical_theme") else ""
        bits.append(
            _section(
                "하케다카",
                f'<div class="pf-sec-body">{hk}{theme}</div>',
            )
        )
    return f'<div class="pf-extend">{"".join(bits)}</div>'


def _ops_expand_html(row: PortfolioRow) -> str:
    """Short expand for holdings — ops-only cues; no CECS/journal dump."""
    extra = row.extra or {}
    score = row.total_score
    score_s = f"{float(score):.2f}" if score is not None else "—"
    bits: list[str] = []

    if _is_short_ops_row(row):
        sm = extra.get("score_m")
        r6 = extra.get("return_6m")
        dd = extra.get("drawdown_52w_pct")
        xs = extra.get("mom_xs_pct")
        trend = extra.get("trend_sign") or "—"
        sm_s = f"{float(sm):g}" if sm not in (None, "") else "—"
        r6_s = f"{float(r6)*100:.1f}%" if r6 not in (None, "") else "—"
        dd_s = f"{float(dd):+.1f}%" if dd not in (None, "") else "—"
        xs_s = f"{float(xs):.0f}%ile" if xs not in (None, "") else "—"
        bits.append(
            _section(
                "단기 보유",
                f'<div class="pf-sec-body">'
                f"비중 {row.weight_pct:.1f}% · 점수 {score_s}<br/>"
                f"현재 {_fmt_price(row.current_price)}원 · "
                f"배지 {row.ops_signal_label or '—'}<br/>"
                f"추세 {trend} · score_m {sm_s} · 6M {r6_s} · "
                f"상대 {xs_s} · 고가대비 {dd_s}"
                f"</div>",
            )
        )
    else:
        cue_line = ""
        if row.ops_signal_label:
            detail = (row.ops_signal_detail or "").strip()
            cue_line = f"<br/>{escape(str(row.ops_signal_label))}"
            if detail and detail != row.ops_signal_label:
                # Keep one short clause — full dump lives in ③ when overlapping.
                cue_line += f" · {escape(detail[:80])}"
        bits.append(
            _section(
                "보유",
                f'<div class="pf-sec-body">'
                f"비중 {row.weight_pct:.1f}% · 점수 {score_s}<br/>"
                f"현재 {_fmt_price(row.current_price)} · 목표 {_fmt_price(row.target_price)}"
                f"{cue_line}"
                f"</div>",
            )
        )
        if extra.get("quant_ok") and not row.has_target:
            pbr_d = extra.get("quant_pbr_draft")
            mid = extra.get("quant_price_mid")
            d_s = f"{float(pbr_d):.2f}" if pbr_d not in (None, "") else "—"
            mid_s = _won(mid)
            mid_s = f"{mid_s}원" if mid_s != "—" else "—"
            bits.append(
                _section(
                    "혼합 목표가",
                    f'<div class="pf-sec-body">PBR {d_s} · {mid_s}</div>',
                )
            )

    he_state = str(extra.get("hold_exit_label") or "").strip()
    he_why = str(extra.get("hold_exit_why") or "").strip()
    if he_state or he_why:
        bits.append(
            _section(
                "보유 Review",
                f'<div class="pf-sec-body">'
                f"{escape(he_state or '—')}"
                f"{(' · ' + escape(he_why)) if he_why else ''}"
                f"</div>",
            )
        )

    allowed = str(extra.get("ops_allowed") or "").strip()
    trigger = str(extra.get("ops_trigger") or "").strip()
    if allowed or trigger:
        bits.append(
            _section(
                "허용·트리거",
                f'<div class="pf-sec-body">'
                f"{escape(allowed or '—')}"
                f"{(' · ' + escape(trigger)) if trigger else ''}"
                f"</div>",
            )
        )

    if row.ops_signal_detail and _is_short_ops_row(row):
        bits.append(
            _section(
                "운영 신호",
                f'<div class="pf-sec-body">{escape(str(row.ops_signal_detail))}</div>',
            )
        )
    return f'<div class="pf-extend">{"".join(bits)}</div>'


def render_expanded_html(ctx: DashboardContext, row: PortfolioRow) -> str:
    """Expanded area as parent-row extension — no nested card boxes."""
    _ = ctx
    extra = row.extra or {}
    if extra.get("book") == "proposal":
        return _proposal_expand_html(row)
    return _ops_expand_html(row)


def render_portfolio_bullets(
    ctx: DashboardContext,
    *,
    mode: str = "full",
    key_prefix: str = "pf",
    rows: Optional[list[PortfolioRow]] = None,
    empty_hint: Optional[str] = None,
) -> None:
    """
    mode:
      - full: accordion expand on portfolio page
      - summary: compact home widget; click navigates to portfolio
    rows:
      override the bullet list (proposal vs ops holdings).
    """
    rows = list(rows if rows is not None else ctx.portfolio_rows)
    if not rows:
        st.info(empty_hint or "표시할 종목이 없습니다.")
        return

    nav = st.session_state.pop(SESSION_NAV_EXPAND, None)
    if nav and mode == "full":
        st.session_state[SESSION_EXPANDED] = nav

    expanded = st.session_state.get(SESSION_EXPANDED)
    chart_map: dict = {}
    if str(key_prefix).startswith("pf_proposal"):
        from alpha_system.ui.services.proposal_chart_board import reads_by_ticker

        chart_map = reads_by_ticker(ctx)

    held_set = {
        norm_ticker(r.ticker) for r in (getattr(ctx, "ops_portfolio_rows", None) or [])
    }
    proposed_set = {
        norm_ticker(r.ticker) for r in (getattr(ctx, "portfolio_rows", None) or [])
    }
    blocked_set = {
        norm_ticker(r.ticker)
        for r in (getattr(ctx, "proposal_blocked_rows", None) or [])
    }
    phcvs_set: set[str] = set()
    try:
        from alpha_system.ui.services.phcvs_watch_board import load_phcvs_watch

        phcvs_board = load_phcvs_watch(Path(ctx.root))
        phcvs_set = {r.ticker for r in phcvs_board.rows}
    except Exception:  # noqa: BLE001 — chip enrichment must not break portfolio
        phcvs_set = set()

    st.markdown('<div class="pf-list">', unsafe_allow_html=True)

    for row in rows:
        is_open = mode == "full" and expanded == row.ticker
        # Fixed column ratio always — prevents horizontal jump on expand/collapse
        left, right = st.columns([6, 1])
        with left:
            tk = norm_ticker(row.ticker)
            st.markdown(
                _row_main_html(
                    row,
                    chart=chart_map.get(tk),
                    held=held_set,
                    proposed=proposed_set,
                    blocked=blocked_set,
                    phcvs=phcvs_set,
                ),
                unsafe_allow_html=True,
            )
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
