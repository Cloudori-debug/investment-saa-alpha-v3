"""Attach lifecycle fields to dashboard rows (edition only)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from alpha_system.hold_exit_review.config import HoldExitReviewConfig
from alpha_system.hold_exit_review.history import append_proposal_snapshot, weeks_out_of_proposal
from alpha_system.hold_exit_review.lifecycle import LifecycleView, evaluate_lifecycle
from alpha_system.hold_exit_review.ops_card import build_ops_card
from alpha_system.proposal_chart import norm_ticker
from alpha_system.ui.services.context import DashboardContext, PortfolioRow


def _proposal_ticker_set(rows: Iterable[PortfolioRow]) -> set[str]:
    out: set[str] = set()
    for r in rows:
        if (r.extra or {}).get("proposal_eligible") is False:
            continue
        tk = norm_ticker(r.ticker)
        if tk:
            out.add(tk)
    return out


def _best_alternate_score(
    proposal_rows: list[PortfolioRow],
    held: set[str],
) -> float | None:
    best: float | None = None
    for r in proposal_rows:
        tk = norm_ticker(r.ticker)
        if not tk or tk in held:
            continue
        if r.total_score is None:
            continue
        sc = float(r.total_score)
        if best is None or sc > best:
            best = sc
    return best


def _apply_lifecycle_to_row(
    row: PortfolioRow,
    *,
    cfg: HoldExitReviewConfig,
    is_ops: bool,
    in_proposal: bool,
    weeks_out: int,
    alt_score: float | None,
) -> LifecycleView:
    view = evaluate_lifecycle(
        cfg=cfg,
        is_ops_row=is_ops,
        in_proposal=in_proposal,
        weeks_out=weeks_out,
        ops_kind=row.ops_signal or "",
        cap_over=bool(row.cap_over),
        weight_pct=float(row.weight_pct or 0),
        avg_price=row.avg_price,
        current_price=row.current_price,
        total_score=row.total_score,
        best_alternate_score=alt_score,
        extra=row.extra or {},
    )
    extra = dict(row.extra or {})
    extra["hold_exit_state"] = view.state
    extra["hold_exit_label"] = view.label
    extra["hold_exit_why"] = view.why
    extra["hold_exit_weeks_out"] = view.weeks_out
    extra["hold_exit_evidence"] = view.evidence
    extra["hold_exit_rotate_gap_ok"] = view.rotate_gap_ok
    extra["hold_exit_quality_line"] = view.quality_line
    card = build_ops_card(
        cfg=cfg,
        view=view,
        extra=extra,
        current_price=row.current_price,
        ops_kind=row.ops_signal or "",
        total_score=row.total_score,
        in_proposal=in_proposal,
        is_ops=is_ops,
    )
    extra["ops_data_gate"] = card.data_gate
    extra["ops_data_gate_detail"] = card.data_gate_detail
    extra["ops_thesis"] = card.thesis
    extra["ops_thesis_detail"] = card.thesis_detail
    extra["ops_allowed"] = card.allowed
    extra["ops_trigger"] = card.trigger
    row.extra = extra
    return view


def enrich_context_hold_exit(ctx: DashboardContext, cfg: HoldExitReviewConfig) -> None:
    root = ctx.root
    hist = root / cfg.history_relpath
    market = str(getattr(ctx, "screen_market", "KOSPI") or "KOSPI")
    horizon = str(getattr(ctx, "screen_horizon", "mid") or "mid")

    proposal_set = _proposal_ticker_set(ctx.portfolio_rows)
    append_proposal_snapshot(
        hist,
        as_of=ctx.as_of,
        market=market,
        horizon=horizon,
        proposal_tickers=proposal_set,
    )

    held = {norm_ticker(r.ticker) for r in ctx.ops_portfolio_rows if norm_ticker(r.ticker)}
    alt_score = _best_alternate_score(ctx.portfolio_rows, held)

    for row in ctx.portfolio_rows:
        tk = norm_ticker(row.ticker)
        _apply_lifecycle_to_row(
            row,
            cfg=cfg,
            is_ops=False,
            in_proposal=tk in proposal_set,
            weeks_out=0,
            alt_score=alt_score,
        )

    for row in ctx.ops_portfolio_rows:
        tk = norm_ticker(row.ticker)
        wout = weeks_out_of_proposal(
            hist,
            ticker=tk,
            market=market,
            horizon=horizon,
            as_of=ctx.as_of,
        )
        _apply_lifecycle_to_row(
            row,
            cfg=cfg,
            is_ops=True,
            in_proposal=tk in proposal_set,
            weeks_out=wout,
            alt_score=alt_score,
        )

    ctx.extra_hold_exit = {
        "cfg": cfg,
        "proposal_set": proposal_set,
        "alternate_score": alt_score,
    }


def attach_extra_hold_exit_slot(ctx: DashboardContext) -> None:
    if not hasattr(ctx, "extra_hold_exit"):
        ctx.extra_hold_exit = {}
