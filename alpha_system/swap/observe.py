"""Swap observation mode — report-only SWAP_CANDIDATE, no auto trade."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from alpha_system.journal.recorder import append_record
from alpha_system.schema import AlphaSystemConfig


@dataclass(frozen=True)
class SwapObserveInput:
    ticker: str
    total_score: float
    is_held: bool
    eligible: bool = True


@dataclass(frozen=True)
class SwapCandidate:
    held_ticker: str
    candidate_ticker: str
    held_score: float
    candidate_score: float
    score_gap_pct: float
    consecutive_hits: int


@dataclass
class SwapObserveEvaluation:
    as_of: date
    candidates: list[SwapCandidate] = field(default_factory=list)
    mode: str = "observe_only"
    journal_ids: list[str] = field(default_factory=list)


def _gap_pct(candidate: float, held: float) -> float:
    if held <= 0:
        return 0.0
    return 100.0 * (candidate - held) / held


def evaluate_swap_observe(
    cfg: AlphaSystemConfig,
    rows: list[SwapObserveInput],
    *,
    as_of: date,
    prior_hits: dict[tuple[str, str], int] | None = None,
    journal: bool = True,
) -> SwapObserveEvaluation:
    """
    When non-held eligible beats lowest held by >= score_gap_pct for
    consecutive_hits rescores → SWAP_CANDIDATE (observe_only — no action).
    """
    mode = cfg.swap_rule.mode
    gap_req = float(cfg.swap_rule.score_gap_pct)
    hits_req = int(cfg.swap_rule.consecutive_hits)
    prior = dict(prior_hits or {})

    held = [r for r in rows if r.is_held and r.eligible]
    pool = [r for r in rows if not r.is_held and r.eligible]
    if not held or not pool:
        return SwapObserveEvaluation(as_of=as_of, mode=mode)

    lowest = min(held, key=lambda r: r.total_score)
    best = max(pool, key=lambda r: r.total_score)
    gap = _gap_pct(best.total_score, lowest.total_score)
    key = (lowest.ticker, best.ticker)
    hits = prior.get(key, 0)
    if gap >= gap_req:
        hits += 1
    else:
        hits = 0

    out: list[SwapCandidate] = []
    journal_ids: list[str] = []
    if hits >= hits_req:
        cand = SwapCandidate(
            held_ticker=lowest.ticker,
            candidate_ticker=best.ticker,
            held_score=lowest.total_score,
            candidate_score=best.total_score,
            score_gap_pct=round(gap, 2),
            consecutive_hits=hits,
        )
        out.append(cand)
        if journal and mode == "observe_only":
            rec = append_record(
                action_kind="SWAP_CANDIDATE",
                as_of=as_of,
                subject=f"{lowest.ticker}->{best.ticker}",
                rationale=(
                    f"observe_only: held={lowest.ticker} score={lowest.total_score} "
                    f"candidate={best.ticker} score={best.total_score} "
                    f"gap={gap:.1f}% hits={hits}/{hits_req}"
                ),
                trigger_snapshot={"mode": mode, "gap_pct": gap},
                score_snapshot={
                    "held_score": lowest.total_score,
                    "candidate_score": best.total_score,
                },
                payload={"action_signal": False},
            )
            journal_ids.append(rec.entry_id)

    return SwapObserveEvaluation(
        as_of=as_of,
        candidates=out,
        mode=mode,
        journal_ids=journal_ids,
    )
