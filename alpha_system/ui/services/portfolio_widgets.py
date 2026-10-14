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
    flow_data_dir: Path | None = None,
    detail: bool = False,
) -> str:
    """List row. detail=False → 이름+오늘 비중만 · True → 1·2·3+사다리."""
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
    synth_html = ""
    if not is_blocked:
        synth_html = _chart_flow_synth_html(
            row, chart, flow_data_dir, compact=not detail
        )
    upside_html = (
        f'<span class="pf-upside pf-tone-{tone}">{upside_txt}</span>'
        if upside_txt and detail
        else ""
    )
    bar_html = ""
    if detail and not is_blocked and not in_proposal:
        bar_html = render_price_bar_html(row)
    return (
        f'<div class="pf-row-main{" pf-row-compact" if not detail else ""}">'
        f'<div class="pf-bullet-top">'
        f'<span class="pf-id">{badge}'
        f"{naver_name_chart_html(row.ticker, row.name)}</span>"
        f"{cross}"
        f'<span class="{weight_cls} pf-wchip">{weight_chip}</span>'
        f"{spot}"
        f"{upside_html}"
        f"</div>"
        f"{synth_html}"
        f"{bar_html}"
        f"</div>"
    )


def _earn_mom_chip_html(extra: dict) -> str:
    """Optional earnings-momentum chip when row already has a direction field."""
    raw = (
        extra.get("earn_mom_label")
        or extra.get("earnings_mom_label")
        or extra.get("earn_revision")
        or extra.get("earnings_surprise_dir")
    )
    if raw in (None, ""):
        # Derive from YoY-ish fields if both present (display-only).
        cur = extra.get("net_income")
        prev = extra.get("net_income_y1")
        if cur not in (None, "") and prev not in (None, ""):
            try:
                c, p = float(cur), float(prev)
                if p == 0:
                    return ""
                delta = (c - p) / abs(p)
                if delta > 0.03:
                    raw = "상향"
                elif delta < -0.03:
                    raw = "하향"
                else:
                    raw = "보합"
            except (TypeError, ValueError):
                return ""
        else:
            return ""
    label = str(raw).strip()
    if not label:
        return ""
    tone = "flat"
    if any(x in label for x in ("상향", "개선", "서프라이즈+", "beat", "UP")):
        tone = "up"
    elif any(x in label for x in ("하향", "악화", "miss", "DOWN")):
        tone = "down"
    cls = {"up": "pf-earn-up", "down": "pf-earn-down"}.get(tone, "")
    return (
        f'<span class="pf-earn-chip {cls}">실적 · {escape(label)}</span>'
    )


def _mid_exit_parts(row: PortfolioRow) -> dict[str, str]:
    """Exit side of mid book cue: hold / trim / cash / exit / missing."""
    kind = str(row.ops_signal or "").strip()
    label = (row.ops_signal_label or "").strip()
    detail = (row.ops_signal_detail or "").strip()
    missing_target = (not row.has_target) or kind == "missing"
    if missing_target and not label:
        label = "목표없음"
        kind = kind or "missing"
    tone = {
        "cash_half": "hot",
        "trim": "warn",
        "exit_full": "hot",
        "missing": "danger",
        "invalid": "muted",
        "hold": "ok",
    }.get(kind, "muted")
    trim = row.ops_trim_pct
    trim_s = f" {int(trim)}%" if trim is not None else ""

    if missing_target or kind == "missing":
        banner = copy_get(
            "portfolio",
            "exit_missing_banner",
            default="익절 불가 · 목표가 없음 — 상승해도 환금 신호가 안 납니다",
        )
        return {
            "kind": "missing",
            "tone": "danger",
            "label": label or "목표없음",
            "why": f"{banner} · E에서 목표가 채우기",
        }
    if not label:
        return {"kind": "", "tone": "muted", "label": "", "why": ""}
    if kind == "cash_half":
        why = detail or "목표가 도달 · 보유 절반 환금 Review"
    elif kind == "trim":
        why = detail or "목표가 근접 · 보유 ¼ 줄이기 Review"
    elif kind == "exit_full":
        why = detail or "전량 환금 Review"
    elif kind == "hold":
        why = detail or "보유분 유지 · 하락 %=손절 아님"
    else:
        why = detail or "목표가 기준 Review"
    return {
        "kind": kind or "hold",
        "tone": tone,
        "label": f"{label}{trim_s}".strip(),
        "why": why,
    }


def _ladder_fill_hint(extra: dict) -> str:
    """Short slider fill cue — amount is human-decided."""
    try:
        fill = float(extra.get("ladder_fill_pct") or 0.0)
    except (TypeError, ValueError):
        return "슬라이더 참고 · 금액은 사람"
    fill = max(0.0, min(100.0, fill))
    return f"슬라이더 {fill:.0f}% · 금액은 사람"


def _mid_buy_parts(row: PortfolioRow) -> dict[str, str]:
    """Add-on buy side: 매수1/2 price zone only — qty from slider + human."""
    extra = row.extra or {}
    kind = str(row.ops_signal or "").strip()
    if kind in {"cash_half", "trim", "exit_full"}:
        return {
            "tone": "holdoff",
            "label": "추가 매수 보류",
            "why": "익절·축소가 우선 · 추격 매수 금지",
        }
    if (not row.has_target) or kind == "missing":
        return {
            "tone": "muted",
            "label": "추가 매수 대기",
            "why": "목표가·사다리 없음",
        }
    if not bool(extra.get("ladder_ok")):
        return {
            "tone": "muted",
            "label": "추가 매수 대기",
            "why": "사다리 데이터 부족",
        }

    rungs = list(extra.get("ladder_rungs") or [])
    labels = list(extra.get("ladder_labels") or ("매수1", "매수2", "줄이기", "절반", "전량"))
    now_idx = _rung_now_idx(row.current_price, rungs)
    buy1_px = _won(rungs[0]) if len(rungs) > 0 else "—"
    buy2_px = _won(rungs[1]) if len(rungs) > 1 else "—"
    buy1_s = f"{buy1_px}원" if buy1_px != "—" else "—"
    buy2_s = f"{buy2_px}원" if buy2_px != "—" else "—"
    fill_h = _ladder_fill_hint(extra)

    if extra.get("ladder_under_low") or now_idx <= 0:
        name = labels[0] if labels else "매수1"
        return {
            "tone": "ok",
            "label": f"추가만 {name}",
            "why": f"≤{buy1_s} · {fill_h} · 보유분 유지",
        }
    if now_idx == 1:
        name = labels[1] if len(labels) > 1 else "매수2"
        return {
            "tone": "ok",
            "label": f"추가만 {name}",
            "why": f"≤{buy2_s} · 1차 {buy1_s} · {fill_h} · 보유분 유지",
        }
    if extra.get("ladder_over_high"):
        return {
            "tone": "holdoff",
            "label": "추가 매수 없음",
            "why": f"상한 위 · 신규·추가 금지 · {fill_h}",
        }
    rung_name = labels[now_idx] if now_idx < len(labels) else "상단"
    return {
        "tone": "holdoff",
        "label": "추가 매수 없음",
        "why": f"지금은 {rung_name} 구간 · 매수1 {buy1_s} · 매수2 {buy2_s} · {fill_h}",
    }


def _mid_book_cue_html(row: PortfolioRow) -> str:
    """One mid cue: 보유처분 | 추가매수 — no competing 유지 vs 매수 strips."""
    if _is_short_ops_row(row):
        return ""
    exit_p = _mid_exit_parts(row)
    buy_p = _mid_buy_parts(row)
    if not exit_p.get("label") and not buy_p.get("label"):
        return ""

    # Exit tone wins when actionable; else buy ok can tint mildly.
    tone = exit_p.get("tone") or "muted"
    if exit_p.get("kind") in {"", "hold"} and buy_p.get("tone") == "ok":
        tone = "ok"

    primary = exit_p.get("label") or "—"
    secondary = buy_p.get("label") or "—"
    why_bits = [exit_p.get("why") or "", buy_p.get("why") or ""]
    why = " · ".join(b for b in why_bits if b)

    return (
        f'<div class="pf-review-card pf-review-1 pf-book-{escape(tone)}" '
        f'title="1순위 · 보유 처분 | 추가 매수 · 자동매매 없음">'
        f'<div class="pf-review-top">'
        f'<span class="pf-review-kicker">1 · 운영</span>'
        f'<span class="pf-review-hint">보유 · 추가</span>'
        f"</div>"
        f'<div class="pf-review-main">'
        f'<span class="pf-review-primary">{escape(primary)}</span>'
        f'<span class="pf-review-sep">|</span>'
        f'<span class="pf-review-secondary">{escape(secondary)}</span>'
        f"</div>"
        f'<div class="pf-review-body">{escape(why)}</div>'
        f"</div>"
    )


def _mid_exit_layer_html(row: PortfolioRow) -> str:
    """Backward-compatible alias — unified book cue only."""
    return _mid_book_cue_html(row) if not _is_short_ops_row(row) else ""


def _mid_buy_layer_html(row: PortfolioRow) -> str:
    """Merged into book cue; keep empty so callers do not double-render."""
    return ""


def _mom_pct_plain(val: object) -> str | None:
    try:
        if val in (None, ""):
            return None
        return f"{float(val) * 100:+.0f}%"
    except (TypeError, ValueError):
        return None


def _mom_flow_label(
    *,
    r6: object = None,
    r121: object = None,
    xs: object = None,
    sm: object = None,
    trend: str = "",
) -> tuple[str, str]:
    """Human label + short why for momentum (no score_m / 12-1 jargon)."""
    r6_f = None
    r121_f = None
    xs_f = None
    sm_f = None
    try:
        if r6 not in (None, ""):
            r6_f = float(r6)
    except (TypeError, ValueError):
        pass
    try:
        if r121 not in (None, ""):
            r121_f = float(r121)
    except (TypeError, ValueError):
        pass
    try:
        if xs not in (None, ""):
            xs_f = float(xs)
    except (TypeError, ValueError):
        pass
    try:
        if sm not in (None, ""):
            sm_f = float(sm)
    except (TypeError, ValueError):
        pass

    # Rank strength: cross-percentile preferred, else score_m as 0–100-ish.
    strength = ""
    if xs_f is not None:
        if xs_f >= 60:
            strength = "장부 안에서도 센 편"
        elif xs_f < 40:
            strength = "장부 안에서는 약한 편"
        else:
            strength = "장부 안에서는 중간"
    elif sm_f is not None:
        if sm_f >= 60:
            strength = "중기 점수 좋은 편"
        elif sm_f < 40:
            strength = "중기 점수 약한 편"
        else:
            strength = "중기 점수 보통"

    up = (r6_f is not None and r6_f > 0.02) or (r121_f is not None and r121_f > 0.05)
    down = (r6_f is not None and r6_f < -0.02) or (r121_f is not None and r121_f < -0.05)
    if trend.upper() == "UP":
        up = True
    if trend.upper() == "DOWN":
        down = True

    if up and not down:
        label = "흐름 좋음"
    elif down and not up:
        label = "흐름 약함"
    elif r6_f is None and r121_f is None and not strength:
        label = "데이터 부족"
    else:
        label = "흐름 보통"

    bits: list[str] = []
    r6_s = _mom_pct_plain(r6_f) if r6_f is not None else None
    r121_s = _mom_pct_plain(r121_f) if r121_f is not None else None
    if r6_s:
        bits.append(f"최근 반년 {r6_s}")
    if r121_s:
        bits.append(f"최근 1년(한 달 제외) {r121_s}")
    if strength:
        bits.append(strength)
    if label == "데이터 부족":
        why = "가격 추세 숫자가 없어 참고만"
    elif not bits:
        why = "추세 참고 · 순위는 바꾸지 않음"
    else:
        why = " · ".join(bits)
    return label, why


def _momentum_layer_html(row: PortfolioRow) -> str:
    """Plain-language momentum card — Review-only, never changes QV rank."""
    extra = row.extra or {}
    earn = _earn_mom_chip_html(extra)
    if _is_short_ops_row(row):
        badge = (row.ops_signal_label or "").strip()
        label, why = _mom_flow_label(
            r6=extra.get("return_6m"),
            r121=extra.get("return_12m_ex_1m"),
            xs=extra.get("mom_xs_pct"),
            sm=extra.get("score_m"),
            trend=str(extra.get("trend_sign") or ""),
        )
        primary = badge or label
        body = why
        if badge and label and label != "데이터 부족":
            body = f"{label} · {why}" if why else label
    else:
        label, why = _mom_flow_label(
            r6=extra.get("return_6m"),
            r121=extra.get("return_12m_ex_1m"),
            xs=extra.get("mom_xs_pct"),
            sm=extra.get("score_m"),
        )
        primary = label
        body = why

    tone = "ok"
    if "약함" in primary or "약함" in (body or ""):
        tone = "warn"
    elif "부족" in primary:
        tone = "muted"
    elif "보통" in primary:
        tone = "muted"

    return (
        f'<div class="pf-review-card pf-review-2 pf-mom-{escape(tone)}" '
        f'title="2순위 · 중기 흐름(들어가도 되나) · 순위 불변">'
        f'<div class="pf-review-top">'
        f'<span class="pf-review-kicker">2 · 모멘텀</span>'
        f'<span class="pf-review-hint">중기 타이밍</span>'
        f"{earn}"
        f"</div>"
        f'<div class="pf-review-main">'
        f'<span class="pf-review-primary">{escape(primary)}</span>'
        f"</div>"
        f'<div class="pf-review-body">{escape(body or "")}</div>'
        f"</div>"
    )


def _chart_flow_synth_html(
    row: PortfolioRow,
    chart: ChartRead | None,
    flow_data_dir: Path | None,
    *,
    compact: bool = False,
) -> str:
    """오늘 비중 → (펼침 시) 1운영 → 2모멘텀 → 3지금. Review-only."""
    from alpha_system.ui.services.chart_flow_merge import (
        chart_flow_strip_html,
        unify_chart_and_flow,
    )
    from alpha_system.ui.services.flow_review_board import (
        flow_info_for_ticker,
        flow_inline_html,
    )
    from alpha_system.ui.services.weight_action import (
        resolve_weight_action,
        weight_action_html,
    )

    info = flow_info_for_ticker(flow_data_dir, row.ticker)
    cue = unify_chart_and_flow(chart=chart, flow_info=info)
    if cue is not None:
        now = chart_flow_strip_html(cue)
        now_action = cue.action
    else:
        flow = flow_inline_html(flow_data_dir, row.ticker)
        now_action = ""
        if flow and 'class="pf-flow-kicker">' in flow:
            now = (
                f'<div class="pf-review-card pf-review-3 pf-mom-muted" '
                f'title="3순위 · 오늘 컨디션">'
                f'<div class="pf-review-top">'
                f'<span class="pf-review-kicker">3 · 지금</span>'
                f'<span class="pf-review-hint">오늘 컨디션</span>'
                f"</div>"
                f'<div class="pf-review-body pf-review-flow-fallback">{flow}</div>'
                f"</div>"
            )
        else:
            now = flow or ""

    extra = row.extra or {}
    mom_label, _ = _mom_flow_label(
        r6=extra.get("return_6m"),
        r121=extra.get("return_12m_ex_1m"),
        xs=extra.get("mom_xs_pct"),
        sm=extra.get("score_m"),
        trend=str(extra.get("trend_sign") or ""),
    )
    if _is_short_ops_row(row) and (row.ops_signal_label or "").strip():
        # Short primary already in momentum card; gate still uses flow label.
        pass
    wact = resolve_weight_action(
        row,
        mom_label=mom_label,
        now_action=now_action,
        exit_parts=_mid_exit_parts(row) if not _is_short_ops_row(row) else {},
        buy_parts=_mid_buy_parts(row) if not _is_short_ops_row(row) else {},
    )
    top = weight_action_html(wact)
    if compact:
        if not top.strip():
            return ""
        return f'<div class="pf-review-stack pf-review-compact">{top}</div>'

    head = _mid_book_cue_html(row)
    mom = _momentum_layer_html(row)
    inner = top + head + mom + now
    if not inner.strip():
        return ""
    return f'<div class="pf-review-stack">{inner}</div>'


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
    # Proposal + holdings both need chart for chart×flow Review strip.
    if str(key_prefix).startswith("pf_"):
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

    flow_data_dir = Path(
        getattr(ctx, "source_data_dir", None) or (Path(ctx.root) / "data")
    )

    st.markdown('<div class="pf-list">', unsafe_allow_html=True)

    for row in rows:
        is_open = mode == "full" and expanded == row.ticker
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
                    flow_data_dir=flow_data_dir,
                    detail=bool(is_open),
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
