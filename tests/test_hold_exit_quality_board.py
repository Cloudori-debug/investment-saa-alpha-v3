"""Hold/exit edition — quality-only board."""

from __future__ import annotations

from alpha_system.hold_exit_review.quality_board import (
    build_quality_rows,
    order_proposal_rows_by_quality,
    render_quality_board_html,
)
from alpha_system.ui.services.context import PortfolioRow, ScoreboardRow


def _row(
    ticker: str,
    name: str,
    *,
    total: float,
    hits: int,
    eligible: bool = True,
) -> PortfolioRow:
    return PortfolioRow(
        ticker=ticker,
        name=name,
        weight_pct=5.0,
        initial_weight_pct=5.0,
        avg_price=None,
        current_price=10000.0,
        target_price=12000.0,
        target_progress=None,
        remaining_upside_pct=20.0,
        has_target=True,
        target_detail="",
        cap_pct=25.0,
        cap_headroom_pct=20.0,
        cap_near=False,
        total_score=total,
        extra={
            "proposal_eligible": eligible,
            "hakedaka_hits": hits,
            "hakedaka_detail": f"{hits}/4",
            "book": "proposal",
        },
    )


def _sc(ticker: str, q: float) -> ScoreboardRow:
    return ScoreboardRow(
        ticker=ticker,
        name=ticker,
        total_score=q,
        score_q=q,
        score_v=50.0,
        score_sr=50.0,
        score_r=50.0,
        cecs=None,
        eligibility=True,
        sector_peer_fallback=False,
        is_held=False,
        status="ok",
    )


def test_order_proposal_annotates_rank_and_sorts() -> None:
    rows = [
        _row("000001", "A", total=80.0, hits=3),
        _row("000002", "B", total=90.0, hits=2),
        _row("000003", "C", total=70.0, hits=4),
    ]
    ordered = order_proposal_rows_by_quality(
        rows,
        scoreboard=[
            _sc("000001", 60.0),
            _sc("000002", 70.0),
            _sc("000003", 70.0),
        ],
    )
    assert [r.ticker for r in ordered] == ["000003", "000002", "000001"]
    assert ordered[0].extra.get("he_quality_rank") == 1
    assert ordered[0].extra.get("he_score_q") == 70.0


def test_sorts_by_score_q_then_hakedaka() -> None:
    rows = build_quality_rows(
        [
            _row("000001", "A", total=80.0, hits=3),
            _row("000002", "B", total=90.0, hits=2),
            _row("000003", "C", total=70.0, hits=4),
        ],
        scoreboard=[
            _sc("000001", 60.0),
            _sc("000002", 70.0),
            _sc("000003", 70.0),
        ],
    )
    assert [r.ticker for r in rows] == ["000003", "000002", "000001"]


def test_skips_ineligible() -> None:
    rows = build_quality_rows(
        [
            _row("000001", "A", total=80.0, hits=3, eligible=False),
            _row("000002", "B", total=70.0, hits=2),
        ],
        scoreboard=[_sc("000001", 90.0), _sc("000002", 50.0)],
    )
    assert [r.ticker for r in rows] == ["000002"]


def test_empty_html() -> None:
    html = render_quality_board_html([], scoreboard=[])
    assert "품질만" in html
    assert "최종 제안이 없습니다" in html


def test_html_lists_q_and_hakedaka() -> None:
    html = render_quality_board_html(
        [_row("005930", "삼성전자", total=72.0, hits=3)],
        scoreboard=[_sc("005930", 68.5)],
    )
    assert "품질만" in html
    assert "Q 68.5" in html
    assert "하케다카" in html
    assert "삼성전자" in html
    assert "순위·target 불변" in html
