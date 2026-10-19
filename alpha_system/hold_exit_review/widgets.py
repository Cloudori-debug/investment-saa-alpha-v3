"""Portfolio row HTML for hold/exit edition."""

from __future__ import annotations

from html import escape

from alpha_system.hold_exit_review.cue_merge import unify_with_lifecycle
from alpha_system.proposal_chart import ChartRead, summary_tone
from alpha_system.ui.services.context import PortfolioRow
from alpha_system.ui.services.portfolio_widgets import (
    _chart_cue_active,
    _header_cue,
    _ladder_hint,
    render_price_bar_html,
)
from alpha_system.ui.services.rank_watchboard import naver_name_chart_html


def _unified_cue(row: PortfolioRow, chart: ChartRead | None = None):
    extra = row.extra or {}
    return unify_with_lifecycle(
        ops_kind=row.ops_signal or "",
        ops_label=row.ops_signal_label or "",
        chart=chart,
        ladder=_ladder_hint(row),
        lifecycle_state=str(extra.get("hold_exit_state") or ""),
        lifecycle_label=str(extra.get("hold_exit_label") or ""),
        lifecycle_why=str(extra.get("hold_exit_why") or ""),
        lifecycle_weeks_out=int(extra.get("hold_exit_weeks_out") or 0),
        quality_line=str(extra.get("hold_exit_quality_line") or ""),
    )


def ops_badge_html(row: PortfolioRow, chart: ChartRead | None = None) -> str:
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
    return f'<span class="{tone_cls} ops-cue">{escape(badge_txt)}</span> '


def chart_read_html(row: PortfolioRow, item: ChartRead | None) -> str:
    """Compact hold/exit cue — one line; detail lives in expand."""
    cue = _unified_cue(row, item)
    if not (cue.why or cue.detail or cue.headline):
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
    extra = row.extra or {}
    # Ops-only crumbs (short): gate · allowed — avoid ③ overlap dump.
    crumbs: list[str] = []
    gate = str(extra.get("ops_data_gate") or "").strip()
    if gate and gate != "—":
        crumbs.append(gate)
    allowed = str(extra.get("ops_allowed") or "").strip()
    if allowed and allowed != "—":
        crumbs.append(allowed)
    crumb_s = " · ".join(crumbs[:2])
    why = (cue.why or cue.detail or "").strip()
    if crumb_s and why and crumb_s not in why:
        why = f"{why} · {crumb_s}"
    elif crumb_s and not why:
        why = crumb_s
    return (
        f'<div class="pf-signal pf-signal-{escape(chart_tone)}">'
        f'<div class="pf-signal-headline">{escape(cue.headline)}</div>'
        f'{f"<div class=\"pf-signal-why\">{escape(why)}</div>" if why else ""}'
        f"</div>"
    )


def _quality_inline_html(row: PortfolioRow) -> str:
    extra = row.extra or {}
    if extra.get("book") != "proposal" or extra.get("proposal_eligible") is False:
        return ""
    rank = extra.get("he_quality_rank")
    q_raw = extra.get("he_score_q")
    hits = extra.get("hakedaka_hits")
    hk = str(extra.get("hakedaka_detail") or "").strip()
    if not hk and hits is not None:
        try:
            hk = f"{int(hits)}/4"
        except (TypeError, ValueError):
            hk = ""
    chips: list[str] = []
    if rank is not None:
        chips.append(
            f'<span class="he-quality-chip he-quality-chip-rank">#{int(rank)}</span>'
        )
    if q_raw is not None:
        try:
            chips.append(
                f'<span class="he-quality-chip">Q {float(q_raw):.1f}</span>'
            )
        except (TypeError, ValueError):
            pass
    if hk:
        chips.append(
            f'<span class="he-quality-chip">하케다카 {escape(hk)}</span>'
        )
    if row.total_score is not None:
        chips.append(
            f'<span class="he-quality-chip">총점 {row.total_score:.1f}</span>'
        )
    if not chips:
        return ""
    return f'<div class="he-quality-inline">{"".join(chips)}</div>'


def row_main_html(
    row: PortfolioRow,
    *,
    chart: ChartRead | None = None,
    held: set[str] | None = None,
    proposed: set[str] | None = None,
    blocked: set[str] | None = None,
    phcvs: set[str] | None = None,
    flow_data_dir=None,
    detail: bool = False,
    show_header: bool = True,
) -> str:
    """List row. detail=False → 이름+비중(+품질칩) · True → 1·2·3+사다리.

    show_header=False: 요약 표와 이름·비중·현재가 중복 생략 (품질칩은 유지).
    """
    from pathlib import Path

    from alpha_system.proposal_chart import norm_ticker
    from alpha_system.ui.services.portfolio_widgets import (
        _chart_flow_synth_html,
        _cross_book_chips_html,
        _fmt_price,
    )

    badge = ops_badge_html(row, chart)
    extra = row.extra or {}
    is_blocked = extra.get("proposal_eligible") is False
    is_ops = extra.get("book") == "ops"
    if is_blocked:
        badge = '<span class="alpha-badge-danger">부적격</span> ' + badge
    upside_txt, tone = _header_cue(row)
    in_proposal = is_ops and norm_ticker(row.ticker) in (proposed or set())
    if in_proposal:
        upside_txt, tone = "", "muted"
    if is_ops:
        weight_chip = f"보유 {row.weight_pct:.1f}%"
        weight_cls = "pf-weight-ok"
    elif is_blocked:
        weight_cls = "pf-weight-muted"
        weight_chip = "비중 없음"
    else:
        weight_cls = "pf-weight-ok"
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
    fdir = Path(flow_data_dir) if flow_data_dir else None
    synth_html = ""
    if not is_blocked:
        try:
            # Chart+flow one strip; lifecycle detail stays in expand / badge.
            synth_html = _chart_flow_synth_html(
                row, chart, fdir, compact=not detail
            )
        except Exception:  # noqa: BLE001 — one bad row must not blank the list
            synth_html = ""
    upside_html = (
        f'<span class="pf-upside pf-tone-{tone}">{upside_txt}</span>'
        if upside_txt and detail and show_header
        else ""
    )
    bar_html = ""
    if detail and not is_blocked and not in_proposal:
        bar_html = render_price_bar_html(row)
    quality = _quality_inline_html(row) if detail else ""
    header_html = ""
    if show_header:
        header_html = (
            f'<div class="pf-bullet-top">'
            f'<span class="pf-id">{badge}'
            f"{naver_name_chart_html(row.ticker, row.name)}</span>"
            f"{cross}"
            f'<span class="{weight_cls} pf-wchip">{weight_chip}</span>'
            f"{spot}"
            f"{upside_html}"
            f"</div>"
        )
    return (
        f'<div class="pf-row-main{" pf-row-compact" if not detail else ""}">'
        f"{header_html}"
        f"{synth_html}"
        f"{quality}"
        f"{bar_html}"
        f"</div>"
    )
