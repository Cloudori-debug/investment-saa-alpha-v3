"""Ratio-investing Review: merge 운영/모멘텀/지금 → one weight action.

Review-only — never writes scores or target_portfolio.
Priority: 운영(exit) > 모멘텀(add gate) > 지금(same-day soften).
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Literal, Optional, Sequence

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


@dataclass(frozen=True)
class WeightAction:
    kind: WeightKind
    primary: str
    body: str
    tone: str  # ok | warn | hot | danger | muted
    priority: int  # lower = more urgent; >=100 = board skip
    delta_pct: float | None
    board_line: str


def _is_short(row: PortfolioRow) -> bool:
    return str((row.extra or {}).get("ops_book") or "") == "short"


def _approx_delta(weight_pct: float, frac: float) -> float:
    try:
        w = float(weight_pct)
    except (TypeError, ValueError):
        return 0.0
    return round(-abs(w) * float(frac), 1)


def _mom_weak(mom_label: str) -> bool:
    return "약함" in (mom_label or "")


# Hard same-day blocks only. Do NOT match substrings like "축소" inside
# "축소·교체 검토" — that collapsed every name to the same 추가 보류.
_NOW_HARD_BLOCK = frozenset({"추매금지", "추가금지"})


def _now_hard_blocks_add(now_action: str) -> bool:
    return (now_action or "").strip() in _NOW_HARD_BLOCK


def _now_soft_note(now_action: str) -> str:
    """Lowest-rank layer: annotate only, never override 운영/모멘텀 primary."""
    a = (now_action or "").strip()
    if not a:
        return ""
    if a in _NOW_HARD_BLOCK:
        return f"오늘={a} · 분할 미룸 권고"
    if a in {"축소·교체 검토", "축소 검토", "관망", "보유·관망"}:
        return f"오늘={a} · 당일만 참고 · 비중 결론은 운영·모멘텀"
    if a in {"보유·소량만", "보유·관망"}:
        return ""
    return f"오늘={a}"


def resolve_weight_action(
    row: PortfolioRow,
    *,
    mom_label: str = "",
    now_action: str = "",
    exit_parts: Optional[dict[str, str]] = None,
    buy_parts: Optional[dict[str, str]] = None,
) -> WeightAction:
    """Map three layers → one ratio action (no score mix)."""
    w = float(row.weight_pct or 0.0)
    name = (row.name or row.ticker or "").strip()
    tk = norm_ticker(row.ticker)

    if _is_short(row):
        kind = str(row.ops_signal or "").strip()
        label = (row.ops_signal_label or "").strip() or "유지"
        if kind in {"exit_full", "exit"} or label in {"교체", "전량"}:
            return WeightAction(
                kind="short_exit",
                primary="교체·비중 비우기 검토",
                body="단기 테스트 · 중기 목표가 익절 미적용 · Review-only",
                tone="hot",
                priority=15,
                delta_pct=_approx_delta(w, 1.0) if w else None,
                board_line=f"교체 {name} {tk} · 보유 {w:.1f}%",
            )
        if kind == "trim" or label == "축소":
            frac = 0.25
            if row.ops_trim_pct is not None:
                try:
                    frac = float(row.ops_trim_pct) / 100.0
                except (TypeError, ValueError):
                    frac = 0.25
            d = _approx_delta(w, frac)
            return WeightAction(
                kind="short_trim",
                primary=f"비중 축소 ≈{abs(d):.1f}%p",
                body="단기 모멘텀 약화 · Review-only · 자동매도 없음",
                tone="warn",
                priority=35,
                delta_pct=d,
                board_line=f"축소 {name} {tk} · {w:.1f}% → ≈{max(w + d, 0):.1f}%",
            )
        return WeightAction(
            kind="short_hold",
            primary="비중 유지",
            body="단기 테스트 · 손볼 신호 없음",
            tone="ok",
            priority=100,
            delta_pct=0.0,
            board_line="",
        )

    # Mid book — prefer precomputed parts from portfolio_widgets.
    exit_p = exit_parts or {}
    buy_p = buy_parts or {}
    ek = str(exit_p.get("kind") or row.ops_signal or "").strip()
    elabel = (exit_p.get("label") or row.ops_signal_label or "").strip()

    if ek == "exit_full" or (elabel.startswith("전량")):
        d = _approx_delta(w, 1.0)
        return WeightAction(
            kind="exit_full",
            primary="전량 환금 · 비중 → 0",
            body=exit_p.get("why") or "운영 전량 · 추가매수 없음 · Review-only",
            tone="hot",
            priority=10,
            delta_pct=d,
            board_line=f"전량 {name} {tk} · 보유 {w:.1f}% → 0",
        )

    if ek == "cash_half" or elabel.startswith("환금"):
        frac = 0.5
        if row.ops_trim_pct is not None:
            try:
                frac = float(row.ops_trim_pct) / 100.0
            except (TypeError, ValueError):
                frac = 0.5
        d = _approx_delta(w, frac)
        return WeightAction(
            kind="cash_half",
            primary=f"보유 절반↓ ≈{abs(d):.1f}%p",
            body=exit_p.get("why") or "목표가 도달 · 추가매수 보류",
            tone="hot",
            priority=20,
            delta_pct=d,
            board_line=f"환금 {name} {tk} · {w:.1f}% → ≈{max(w + d, 0):.1f}%",
        )

    if ek == "trim" or elabel.startswith("줄이기"):
        frac = 0.25
        if row.ops_trim_pct is not None:
            try:
                frac = float(row.ops_trim_pct) / 100.0
            except (TypeError, ValueError):
                frac = 0.25
        d = _approx_delta(w, frac)
        return WeightAction(
            kind="trim",
            primary=f"보유 ¼↓ ≈{abs(d):.1f}%p",
            body=exit_p.get("why") or "목표가 근접 · 추가매수 보류",
            tone="warn",
            priority=30,
            delta_pct=d,
            board_line=f"줄이기 {name} {tk} · {w:.1f}% → ≈{max(w + d, 0):.1f}%",
        )

    if ek == "missing" or (not row.has_target):
        return WeightAction(
            kind="missing",
            primary="비중 유지 · 익절 불가",
            body=exit_p.get("why") or "목표가 없음 · E에서 채우기 · 추격 추가 금지",
            tone="danger",
            priority=40,
            delta_pct=0.0,
            board_line=f"목표없음 {name} {tk} · 보유 {w:.1f}% · 목표가 채우기",
        )

    if bool(getattr(row, "cap_near", False)):
        return WeightAction(
            kind="cap_trim",
            primary="상한 근접 · 추가 금지",
            body=f"보유 {w:.1f}% · 개별 캡 점검 · 비중만 Review",
            tone="warn",
            priority=50,
            delta_pct=0.0,
            board_line=f"상한근접 {name} {tk} · 보유 {w:.1f}%",
        )

    buy_label = (buy_p.get("label") or "").strip()
    buy_why = buy_p.get("why") or ""
    is_add = buy_label.startswith("추가만")

    if is_add:
        # Gate add on 모멘텀 (rank 2). 지금 (rank 3) only hard-blocks 추매/추가금지.
        if _mom_weak(mom_label):
            return WeightAction(
                kind="add_wait",
                primary="비중 유지 · 추가 보류",
                body="모멘텀 약함 · 사다리는 유지 · 추격 금지",
                tone="muted",
                priority=100,
                delta_pct=0.0,
                board_line="",
            )
        if _now_hard_blocks_add(now_action):
            return WeightAction(
                kind="add_wait",
                primary="비중 유지 · 추가 보류",
                body=f"오늘={now_action} · 사다리는 유지 · 추격 금지",
                tone="muted",
                priority=100,
                delta_pct=0.0,
                board_line="",
            )
        rung = buy_label.replace("추가만 ", "").strip() or "매수1"
        body = (buy_why or "싸게만 분할") + " · 개별 캡까지 · Review-only"
        soft = _now_soft_note(now_action)
        if soft:
            body = f"{body} · {soft}"
        return WeightAction(
            kind="add_ready",
            primary=f"비중 유지 · {rung}만 분할",
            body=body,
            tone="ok",
            priority=60,
            delta_pct=None,
            board_line=f"추가 {name} {tk} · {rung} 분할 · 보유 {w:.1f}% 유지",
        )

    # hold + no add — 지금 does not invent a reduce when 운영 says hold
    body = "손볼 신호 없음"
    if buy_label:
        body = f"{buy_label} · {buy_why}".strip(" ·")
    soft = _now_soft_note(now_action)
    if soft and "당일만 참고" in soft:
        body = f"{body} · {soft}"
    return WeightAction(
        kind="hold",
        primary="비중 유지",
        body=body,
        tone="ok",
        priority=100,
        delta_pct=0.0,
        board_line="",
    )


def weight_action_html(action: WeightAction) -> str:
    """Top synthesis card — conclusion for ratio investor."""
    delta = ""
    if action.delta_pct is not None and abs(action.delta_pct) >= 0.05:
        sign = "+" if action.delta_pct > 0 else ""
        delta = (
            f'<span class="pf-review-chip">{escape(f"{sign}{action.delta_pct:.1f}%p")}</span>'
        )
    elif action.kind == "add_ready":
        delta = '<span class="pf-review-chip">분할+</span>'
    return (
        f'<div class="pf-review-card pf-review-0 pf-wact-{escape(action.tone)}" '
        f'title="비율 결론 · 1운영>2모멘텀>3지금 · 자동매매·target 없음">'
        f'<div class="pf-review-top">'
        f'<span class="pf-review-kicker">오늘 비중</span>'
        f'<span class="pf-review-hint">비율 결론</span>'
        f"{delta}"
        f"</div>"
        f'<div class="pf-review-main">'
        f'<span class="pf-review-primary">{escape(action.primary)}</span>'
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

        if _is_short_ops_row(row) and (row.ops_signal_label or "").strip():
            # Short badge already encodes stance; keep mom for gate only.
            pass

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
    """Actionable only, sorted by priority then weight."""
    items = [a for _r, a in pairs if a.priority < 100 and a.board_line]
    items.sort(key=lambda a: (a.priority, -(abs(a.delta_pct or 0))))
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
        '<div class="pf-wact-board-hint">운영 우선 · 모멘텀은 추가 게이트 · 지금은 당일만 · 자동매매·target 없음</div>'
        f"<ol class=\"pf-wact-ol\">{lis}</ol>"
        "</div>"
    )
