"""Eligible-rank watch board — display only (not proposal sizing).

Rank = eligibility==True names by total_score descending.
Sector cap is NOT applied (reference rank for 'how far did a holding fall').
Does not write target_portfolio or change selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from alpha_system.ui.services.context import ScoreboardRow

DEFAULT_WATCH_MAX = 30


@dataclass(frozen=True)
class RankWatchRow:
    rank: int
    ticker: str
    name: str
    total_score: float
    sector: str
    is_held: bool
    in_proposal: bool
    eligibility: Optional[bool]


@dataclass(frozen=True)
class RankWatchBoard:
    rows: tuple[RankWatchRow, ...]
    held_outside: tuple[RankWatchRow, ...]
    eligible_count: int
    proposal_band_max: int
    max_rows: int
    basis: str
    warnings: tuple[str, ...] = ()


def build_rank_watchboard(
    scoreboard: Sequence[ScoreboardRow],
    *,
    proposal_tickers: set[str] | None = None,
    held_tickers: set[str] | None = None,
    proposal_band_max: int = 8,
    max_rows: int = DEFAULT_WATCH_MAX,
) -> RankWatchBoard:
    """Build top-N eligible score ranks for monitoring.

    Parameters
    ----------
    proposal_tickers
        Current proposal_book tickers (highlight).
    held_tickers
        Ops holdings; if None, use ScoreboardRow.is_held.
    proposal_band_max
        UI hint for 'inside proposal band' (usually sizing.target_names).
    max_rows
        Cap board length (default 30 = CECS shortlist scale).
    """
    prop = {
        str(t).zfill(6) if str(t).isdigit() else str(t)
        for t in (proposal_tickers or set())
    }
    held_override = None
    if held_tickers is not None:
        held_override = {
            str(t).zfill(6) if str(t).isdigit() else str(t) for t in held_tickers
        }

    warnings: list[str] = []
    scored: list[tuple[ScoreboardRow, float]] = []
    for row in scoreboard:
        if row.total_score is None:
            continue
        try:
            score = float(row.total_score)
        except (TypeError, ValueError):
            continue
        scored.append((row, score))

    eligible = [(r, s) for r, s in scored if r.eligibility is True]
    if not eligible and scored:
        # Cutoff unset / provisional — still show score order with warning
        eligible = scored
        warnings.append(
            "eligibility=True 종목이 없어 점수 있는 전 종목 순위로 표시합니다 "
            "(score_cutoff·CECS를 확인하세요)."
        )
    elif not eligible:
        return RankWatchBoard(
            rows=(),
            held_outside=(),
            eligible_count=0,
            proposal_band_max=int(proposal_band_max),
            max_rows=int(max_rows),
            basis="eligibility==True · total_score 내림차순 · 섹터캡 미적용",
            warnings=("표시할 스코어가 없습니다.",),
        )

    eligible.sort(key=lambda x: (-x[1], str(x[0].ticker).zfill(6)))
    ranked: list[RankWatchRow] = []
    for i, (row, score) in enumerate(eligible, start=1):
        ticker = str(row.ticker).zfill(6) if str(row.ticker).isdigit() else str(row.ticker)
        is_held = (
            ticker in held_override
            if held_override is not None
            else bool(row.is_held)
        )
        ranked.append(
            RankWatchRow(
                rank=i,
                ticker=ticker,
                name=(row.name or ticker).strip() or ticker,
                total_score=round(score, 2),
                sector=(row.sector or "").strip(),
                is_held=is_held,
                in_proposal=ticker in prop,
                eligibility=row.eligibility,
            )
        )

    max_n = max(1, int(max_rows))
    board = tuple(ranked[:max_n])
    board_tickers = {r.ticker for r in board}
    held_outside = tuple(
        r for r in ranked if r.is_held and r.ticker not in board_tickers
    )

    return RankWatchBoard(
        rows=board,
        held_outside=held_outside,
        eligible_count=len(ranked),
        proposal_band_max=int(proposal_band_max),
        max_rows=max_n,
        basis="eligibility==True · total_score 내림차순 · 섹터캡 미적용 (참고 순위)",
        warnings=tuple(warnings),
    )
