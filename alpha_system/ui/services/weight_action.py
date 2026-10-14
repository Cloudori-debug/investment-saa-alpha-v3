"""Ratio-investing Review: merge 운영/모멘텀/지금 → one weight action.

Review-only — never writes scores or target_portfolio.
Priority: 운영(exit) > 모멘텀(add gate) > 지금(same-day soften).

「오늘 비중」= 종목 단위 100% 절대 비율 (보유 CSV·상대 채움 비율 사용 안 함).
  매수1 → 누적 상한 67% (오늘≤약 33%) · 매수2 → 누적 상한 100% (오늘≤약 33%)
  유지 → 채울 0% · 줄이기/환금/전량 → 매도할 25/50/100%
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Literal, Optional, Sequence

from alpha_system.entry.scale_in import DEFAULT_LEGS
from alpha_system.proposal_chart import ChartRead, norm_ticker
from alpha_system.ui.services.context import PortfolioRow

WeightKind = Literal[
    "exit_full",
    "cash_half",
    "trim",
    "missing",
    "cap_trim",
    "hold",
    "add_ready",
    "add_wait",
    "short_exit",
    "short_trim",
    "short_hold",
    "idle",
]

Stance = Literal["매수", "매도", "유지"]


@dataclass(frozen=True)
class WeightAction:
    kind: WeightKind
    primary: str
    body: str
    tone: str  # ok | warn | hot | danger | muted
    priority: int  # lower = more urgent; >=100 = board skip
    delta_pct: float | None
    board_line: str
    stance: Stance = "유지"
    fill_pct: float | None = None  # unused in absolute mode (compat)
    move_pct: float | None = None  # 절대 채울% or 매도할%


def _is_short(row: PortfolioRow) -> bool:
    return str((row.extra or {}).get("ops_book") or "") == "short"


def _mom_weak(mom_label: str) -> bool:
    return "약함" in (mom_label or "")


# Hard same-day blocks only. Do NOT match substrings like "축소" inside
# "축소·교체 검토" — that collapsed every name to the same 추가 보류.
_NOW_HARD_BLOCK = frozenset({"추매금지", "추가금지"})


def _now_hard_blocks_add(now_action: str) -> bool:
    return (now_action or "").strip() in _NOW_HARD_BLOCK


def _sell_frac(row: PortfolioRow, default: float) -> float:
    if row.ops_trim_pct is not None:
        try:
            return max(0.0, min(1.0, float(row.ops_trim_pct) / 100.0))
        except (TypeError, ValueError):
            pass
    return default


def _day_leg_pct() -> float:
    """오늘 분할 한도(종목=100% 기준 1/n_legs). 금액은 사람."""
    return round(100.0 / float(max(int(DEFAULT_LEGS), 2)), 0)


def _abs_buy_fill_pct(buy_label: str) -> float:
    """종목=100% 절대 누적 상한. 매수1=2/3 · 매수2=전량 (SCALE_IN cum)."""
    if "매수2" in buy_label:
        return 100.0
    if "매수1" in buy_label:
        legs = max(int(DEFAULT_LEGS), 2)
        # 3-leg: buy1 cum = 2/3
        return round(100.0 * (legs - 1) / float(legs), 0)
    return _day_leg_pct()


def _ratio_primary(
    *,
    move: float | None,
    stance: Stance,
    buy_ceiling: bool = False,
) -> str:
    if stance == "매도":
        rem = 0.0 if move is None else float(move)
        return f"매도할 {rem:.0f}%"
    if move is None or float(move) <= 0:
        return "채울 0%"
    if buy_ceiling:
        day = _day_leg_pct()
        return f"누적 상한 {float(move):.0f}% (오늘≤약 {day:.0f}%)"
    return f"채울 {float(move):.0f}%"


def _make(
    *,
    kind: WeightKind,
    stance: Stance,
    move: float | None,
    body: str,
    tone: str,
    priority: int,
    board_line: str,
    buy_ceiling: bool = False,
) -> WeightAction:
    return WeightAction(
        kind=kind,
        primary=_ratio_primary(move=move, stance=stance, buy_ceiling=buy_ceiling),
        body=body,
        tone=tone,
        priority=priority,
        delta_pct=None,  # 절대 %만 — 보유 대비 %p 없음
        board_line=board_line,
        stance=stance,
        fill_pct=None,
        move_pct=move,
    )


def resolve_weight_action(
    row: PortfolioRow,
    *,
    mom_label: str = "",
    now_action: str = "",
    exit_parts: Optional[dict[str, str]] = None,
    buy_parts: Optional[dict[str, str]] = None,
) -> WeightAction:
    """Map three layers → absolute name-unit % (no holdings CSV ratio)."""
    name = (row.name or row.ticker or "").strip()
    tk = norm_ticker(row.ticker)

    if _is_short(row):
        kind = str(row.ops_signal or "").strip()
        label = (row.ops_signal_label or "").strip() or "유지"
        if kind in {"exit_full", "exit"} or label in {"교체", "전량"}:
            return _make(
                kind="short_exit",
                stance="매도",
                move=100.0,
                body="절대 100% · 단기 교체 · Review-only",
                tone="hot",
                priority=15,
                board_line=f"매도 {name} {tk} · 매도할 100%",
            )
        if kind == "trim" or label == "축소":
            sell_pct = round(_sell_frac(row, 0.25) * 100.0, 0)
            return _make(
                kind="short_trim",
                stance="매도",
                move=sell_pct,
                body=f"절대 {sell_pct:.0f}% · 단기 축소 · Review-only",
                tone="warn",
                priority=35,
                board_line=f"매도 {name} {tk} · 매도할 {sell_pct:.0f}%",
            )
        return _make(
            kind="short_hold",
            stance="유지",
            move=0.0,
            body="절대 0% · 단기 유지",
            tone="ok",
            priority=100,
            board_line="",
        )

    exit_p = exit_parts or {}
    buy_p = buy_parts or {}
    ek = str(exit_p.get("kind") or row.ops_signal or "").strip()
    elabel = (exit_p.get("label") or row.ops_signal_label or "").strip()

    if ek == "exit_full" or (elabel.startswith("전량")):
        return _make(
            kind="exit_full",
            stance="매도",
            move=100.0,
            body="절대 100% · 운영 전량 · Review-only",
            tone="hot",
            priority=10,
            board_line=f"매도 {name} {tk} · 매도할 100%",
        )

    if ek == "cash_half" or elabel.startswith("환금"):
        sell_pct = round(_sell_frac(row, 0.5) * 100.0, 0)
        return _make(
            kind="cash_half",
            stance="매도",
            move=sell_pct,
            body=f"절대 {sell_pct:.0f}% · 목표가 환금 · Review-only",
            tone="hot",
            priority=20,
            board_line=f"매도 {name} {tk} · 매도할 {sell_pct:.0f}%",
        )

    if ek == "trim" or elabel.startswith("줄이기"):
        sell_pct = round(_sell_frac(row, 0.25) * 100.0, 0)
        return _make(
            kind="trim",
            stance="매도",
            move=sell_pct,
            body=f"절대 {sell_pct:.0f}% · 목표가 줄이기 · Review-only",
            tone="warn",
            priority=30,
            board_line=f"매도 {name} {tk} · 매도할 {sell_pct:.0f}%",
        )

    if ek == "missing" or (not row.has_target):
        return _make(
            kind="missing",
            stance="유지",
            move=0.0,
            body="절대 0% · 목표가(익절) 없음 · E에서 채우기",
            tone="danger",
            priority=40,
            board_line=f"목표없음 {name} {tk}",
        )

    if bool(getattr(row, "cap_near", False)):
        return _make(
            kind="cap_trim",
            stance="유지",
            move=0.0,
            body="절대 0% · 상한 근접 · 추가 금지",
            tone="warn",
            priority=50,
            board_line=f"상한근접 {name} {tk} · 채울 0%",
        )

    buy_label = (buy_p.get("label") or "").strip()
    is_add = buy_label.startswith("추가만")
    rung_ko = buy_label.replace("추가만 ", "").strip() or "매수1"

    if is_add:
        rem = _abs_buy_fill_pct(buy_label)
        day = _day_leg_pct()
        if _mom_weak(mom_label) or _now_hard_blocks_add(now_action):
            return _make(
                kind="add_wait",
                stance="유지",
                move=rem,
                body=(
                    f"누적 상한 {rem:.0f}% · 오늘≤약 {day:.0f}% · {rung_ko} · "
                    f"추가 보류 · 금액은 사람"
                ),
                tone="muted",
                priority=100,
                board_line="",
                buy_ceiling=True,
            )
        return _make(
            kind="add_ready",
            stance="매수",
            move=rem,
            body=(
                f"누적 상한 {rem:.0f}% · 오늘≤약 {day:.0f}% · {rung_ko} 구간 · "
                f"종목=100% · 금액은 사람 · Review-only"
            ),
            tone="ok",
            priority=60,
            board_line=(
                f"매수 {name} {tk} · 누적 상한 {rem:.0f}% (오늘≤약 {day:.0f}%)"
            ),
            buy_ceiling=True,
        )

    return _make(
        kind="hold",
        stance="유지",
        move=0.0,
        body="절대 0% · 손볼 신호 없음",
        tone="ok",
        priority=100,
        board_line="",
    )


def weight_action_html(action: WeightAction) -> str:
    """누적 상한/매도할 절대% · 유지|매수|매도 (오늘 한도 명시)."""
    stance = action.stance or "유지"
    return (
        f'<div class="pf-review-card pf-review-0 pf-wact-{escape(action.tone)}" '
        f'title="누적 상한≠오늘 매수량 · 오늘≤약 1/3 · 금액은 사람 · target 없음">'
        f'<div class="pf-review-top">'
        f'<span class="pf-review-kicker">오늘 비중</span>'
        f'<span class="pf-review-hint">누적·오늘</span>'
        f"</div>"
        f'<div class="pf-review-main">'
        f'<span class="pf-review-primary">{escape(action.primary)}</span>'
        f'<span class="pf-review-sep">·</span>'
        f'<span class="pf-review-secondary">{escape(stance)}</span>'
        f"</div>"
        f'<div class="pf-review-body">{escape(action.body)}</div>'
        f"</div>"
    )


def build_weight_actions_for_rows(
    rows: Sequence[PortfolioRow],
    *,
    chart_map: Optional[dict[str, ChartRead]] = None,
    flow_data_dir: Path | None = None,
    exit_buy_fn: Any = None,
    mom_label_fn: Any = None,
) -> list[tuple[PortfolioRow, WeightAction]]:
    """Compute actions; optional callables avoid circular imports in tests."""
    from alpha_system.ui.services.chart_flow_merge import unify_chart_and_flow
    from alpha_system.ui.services.flow_review_board import flow_info_for_ticker
    from alpha_system.ui.services.portfolio_widgets import (
        _mid_buy_parts,
        _mid_exit_parts,
        _mom_flow_label,
        _is_short_ops_row,
    )

    out: list[tuple[PortfolioRow, WeightAction]] = []
    charts = chart_map or {}
    for row in rows:
        extra = row.extra or {}
        if extra.get("proposal_eligible") is False:
            continue
        exit_p = _mid_exit_parts(row) if not _is_short_ops_row(row) else {}
        buy_p = _mid_buy_parts(row) if not _is_short_ops_row(row) else {}
        if exit_buy_fn is not None:
            exit_p, buy_p = exit_buy_fn(row)

        label, _why = _mom_flow_label(
            r6=extra.get("return_6m"),
            r121=extra.get("return_12m_ex_1m"),
            xs=extra.get("mom_xs_pct"),
            sm=extra.get("score_m"),
            trend=str(extra.get("trend_sign") or ""),
        )
        if mom_label_fn is not None:
            label = mom_label_fn(row)

        info = flow_info_for_ticker(flow_data_dir, row.ticker)
        cue = unify_chart_and_flow(
            chart=charts.get(norm_ticker(row.ticker)),
            flow_info=info,
        )
        now_action = cue.action if cue is not None else ""
        act = resolve_weight_action(
            row,
            mom_label=label,
            now_action=now_action,
            exit_parts=exit_p,
            buy_parts=buy_p,
        )
        out.append((row, act))
    return out


def board_items(
    pairs: Sequence[tuple[PortfolioRow, WeightAction]],
) -> list[WeightAction]:
    """Actionable only, sorted by priority then move size."""
    items = [a for _r, a in pairs if a.priority < 100 and a.board_line]
    items.sort(key=lambda a: (a.priority, -(abs(a.move_pct or 0))))
    return items


def weight_action_board_html(actions: Sequence[WeightAction]) -> str:
    if not actions:
        return (
            '<div class="pf-wact-board pf-wact-board-empty">'
            '<div class="pf-wact-board-kicker">오늘 손볼 종목</div>'
            '<div class="pf-wact-board-body">손볼 비중 없음 · 유지만 · Review-only</div>'
            "</div>"
        )
    lis = "".join(
        f'<li class="pf-wact-li pf-wact-{escape(a.tone)}">'
        f"{escape(a.board_line)}</li>"
        for a in actions
    )
    return (
        '<div class="pf-wact-board">'
        '<div class="pf-wact-board-kicker">오늘 손볼 종목</div>'
        '<div class="pf-wact-board-hint">누적 상한 · 오늘≤약 1/3 · 금액은 사람 · Review-only</div>'
        f"<ol class=\"pf-wact-ol\">{lis}</ol>"
        "</div>"
    )
