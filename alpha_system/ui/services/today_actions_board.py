"""Today's action board — merge exit + band + MHM into one operator table.

Priority (from alpha_book_ops signal_priority):
  exit_full / cash_half / trim → band_reduce → mhm_trim → band_increase / mhm_enter

Review-only · no auto orders · no target_portfolio writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Sequence

Tone = Literal["ok", "warn", "danger", "muted"]

# Lower = higher priority
_PRIORITY: dict[str, tuple[int, str]] = {
    "exit_full": (1, "1 익절"),
    "cash_half": (1, "1 익절"),
    "trim": (1, "1 익절"),
    "missing": (1, "1 익절"),
    "invalid": (1, "1 익절"),
    "band_reduce": (2, "2 밴드"),
    "band_increase": (3, "3 편입"),
    "mhm_trim": (2, "2 모멘텀"),
    "mhm_exit": (1, "1 모멘텀"),
    "mhm_enter": (3, "3 분할"),
    "hold": (9, "—"),
}


@dataclass(frozen=True)
class TodayActionRow:
    ticker: str
    name: str
    priority: int
    priority_label: str
    action: str
    actual_pct: float | None
    target_pct: float | None
    trend: str
    note: str
    source: str
    tone: Tone = "warn"


@dataclass(frozen=True)
class TodayActionBoard:
    as_of: date
    rows: tuple[TodayActionRow, ...]
    summary: str


def _pri(kind: str) -> tuple[int, str]:
    return _PRIORITY.get(kind, (5, "참고"))


def build_today_action_board(ctx: Any) -> TodayActionBoard:
    """Merge exit / band / MHM into one sorted action list (one row per ticker)."""
    as_of = getattr(ctx, "as_of", None) or date.today()
    by_tk: dict[str, TodayActionRow] = {}

    def _keep(row: TodayActionRow) -> None:
        prev = by_tk.get(row.ticker)
        if prev is None or row.priority < prev.priority:
            by_tk[row.ticker] = row
        elif prev is not None and row.priority == prev.priority:
            # Enrich note / trend if empty
            note = prev.note
            if row.note and row.note not in note:
                note = f"{note} · {row.note}".strip(" ·")
            trend = prev.trend if prev.trend != "—" else row.trend
            actual = prev.actual_pct if prev.actual_pct is not None else row.actual_pct
            target = prev.target_pct if prev.target_pct is not None else row.target_pct
            by_tk[row.ticker] = TodayActionRow(
                ticker=prev.ticker,
                name=prev.name,
                priority=prev.priority,
                priority_label=prev.priority_label,
                action=prev.action,
                actual_pct=actual,
                target_pct=target,
                trend=trend,
                note=note,
                source=f"{prev.source}+{row.source}",
                tone=prev.tone if prev.tone != "muted" else row.tone,
            )

    # --- 1) Exit signals (proposal book, fallback ops) ---
    from alpha_system.ui.services.ops_exit_signal import actionable_ops_signals

    proposal = list(getattr(ctx, "portfolio_rows", None) or [])
    ops = list(getattr(ctx, "ops_portfolio_rows", None) or [])
    sig_rows = actionable_ops_signals(proposal) if proposal else []
    if not sig_rows and ops:
        sig_rows = actionable_ops_signals(ops)
    for r in sig_rows:
        tk = str(getattr(r, "ticker", "") or "").zfill(6)
        kind = str(getattr(r, "ops_signal", "") or "trim")
        p, pl = _pri(kind)
        label = str(getattr(r, "ops_signal_label", None) or kind)
        detail = str(getattr(r, "ops_signal_detail", None) or "")
        _keep(
            TodayActionRow(
                ticker=tk,
                name=str(getattr(r, "name", None) or tk),
                priority=p,
                priority_label=pl,
                action=label,
                actual_pct=_f(getattr(r, "weight_pct", None)),
                target_pct=_f(getattr(r, "initial_weight_pct", None)),
                trend="—",
                note=detail[:80],
                source="exit",
                tone="danger" if kind in ("exit_full", "invalid") else "warn",
            )
        )

    # --- 2) Band breaches (alpha-book %) ---
    from alpha_system.ui.services.monthly_rebal_board import build_monthly_rebal_board

    rebal = build_monthly_rebal_board(ctx, as_of=as_of)
    band_card = next((c for c in rebal.cards if c.key == "band"), None)
    for item in band_card.items if band_card else ():
        tk = item.ticker
        is_reduce = (
            item.actual_pct is not None
            and item.target_pct is not None
            and item.actual_pct > item.target_pct
        )
        kind = "band_reduce" if is_reduce else "band_increase"
        if "목표 없음" in item.action:
            kind = "band_reduce"
        p, pl = _pri(kind)
        _keep(
            TodayActionRow(
                ticker=tk,
                name=item.name,
                priority=p,
                priority_label=pl,
                action=item.action,
                actual_pct=item.actual_pct,
                target_pct=item.target_pct,
                trend="—",
                note=item.detail[:80],
                source="band",
                tone=item.tone if item.tone in ("warn", "danger", "muted", "ok") else "warn",
            )
        )

    # --- 3) MHM actionable bearings ---
    from alpha_system.ui.services.momentum_holding_monitor import (
        build_momentum_holding_board,
    )
    from alpha_system.ui.services.momentum_review import build_momentum_review_board

    mom = build_momentum_review_board(ctx)
    mhm = build_momentum_holding_board(
        ctx, mom_board=mom, include_all_ops=False, persist_log=False
    )
    for r in mhm.rows:
        if r.bearing == "HOLD_UP":
            continue
        if r.bearing == "EXIT_REVIEW":
            kind = "mhm_exit"
        elif r.bearing == "TRIM_PACE":
            kind = "mhm_trim"
        elif r.bearing == "ENTER_OK":
            kind = "mhm_enter"
        else:
            continue
        p, pl = _pri(kind)
        trend = {
            "UP": "상승",
            "DOWN": "하락",
            "—": "—",
        }.get(r.ts_sign, r.ts_sign)
        _keep(
            TodayActionRow(
                ticker=r.ticker,
                name=r.name,
                priority=p,
                priority_label=pl,
                action=r.strategy_action or r.bearing_ko,
                actual_pct=None,
                target_pct=None,
                trend=trend,
                note=(r.strategy_detail or r.reason)[:80],
                source="mhm",
                tone="danger" if r.bearing == "EXIT_REVIEW" else "warn",
            )
        )

    rows = sorted(
        by_tk.values(),
        key=lambda x: (x.priority, x.name),
    )
    n1 = sum(1 for r in rows if r.priority == 1)
    n2 = sum(1 for r in rows if r.priority == 2)
    n3 = sum(1 for r in rows if r.priority == 3)
    if not rows:
        summary = "오늘 손댈 종목 없음 · 밴드·익절·모멘텀 조치 대기"
    else:
        summary = (
            f"오늘 조치 {len(rows)}종 "
            f"(익절·청산 {n1} · 밴드·축소 {n2} · 편입·분할 {n3}) · Review-only"
        )
    return TodayActionBoard(as_of=as_of, rows=tuple(rows), summary=summary)


def today_actions_as_table(rows: Sequence[TodayActionRow]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "우선": r.priority_label,
                "종목": f"{r.name} ({r.ticker})",
                "조치": r.action,
                "실%": f"{r.actual_pct:.1f}" if r.actual_pct is not None else "—",
                "목표%": f"{r.target_pct:.1f}" if r.target_pct is not None else "—",
                "추세": r.trend,
                "비고": r.note,
            }
        )
    return out


def _f(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None
