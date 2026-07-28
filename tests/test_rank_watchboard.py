"""Tests for eligible-rank watch board (display only)."""

from __future__ import annotations

from alpha_system.ui.services.context import ScoreboardRow
from alpha_system.ui.services.rank_watchboard import build_rank_watchboard


def _row(
    ticker: str,
    score: float,
    *,
    held: bool = False,
    elig: bool | None = True,
    name: str = "",
) -> ScoreboardRow:
    return ScoreboardRow(
        ticker=ticker,
        name=name or ticker,
        total_score=score,
        score_q=None,
        score_v=None,
        score_sr=None,
        score_r=None,
        cecs=None,
        eligibility=elig,
        sector_peer_fallback=False,
        is_held=held,
        status="ok",
        sector="test",
    )


def test_ranks_eligible_by_score_and_marks_held_proposal() -> None:
    board = build_rank_watchboard(
        [
            _row("000001", 90.0),
            _row("000002", 80.0, held=True),
            _row("000003", 70.0),
            _row("000004", 60.0, elig=False),
        ],
        proposal_tickers={"000001", "000002"},
        proposal_band_max=2,
        max_rows=30,
    )
    assert board.eligible_count == 3
    assert [r.ticker for r in board.rows] == ["000001", "000002", "000003"]
    assert board.rows[0].rank == 1 and board.rows[0].in_proposal
    assert board.rows[1].is_held and board.rows[1].in_proposal
    assert not board.rows[2].in_proposal
    assert board.held_outside == ()


def test_held_outside_top_n() -> None:
    rows = [_row(f"{i:06d}", float(100 - i)) for i in range(1, 35)]
    rows[32] = _row("000033", 67.0, held=True)  # rank 33 among 34 eligible
    board = build_rank_watchboard(
        rows,
        proposal_tickers={"000001"},
        held_tickers={"000033"},
        max_rows=30,
    )
    assert len(board.rows) == 30
    assert board.held_outside and board.held_outside[0].ticker == "000033"
    assert board.held_outside[0].rank == 33


def test_provisional_when_no_eligibility_true() -> None:
    board = build_rank_watchboard(
        [
            _row("000001", 50.0, elig=None),
            _row("000002", 40.0, elig=None),
        ],
        max_rows=30,
    )
    assert board.eligible_count == 2
    assert board.warnings
    assert board.rows[0].ticker == "000001"
