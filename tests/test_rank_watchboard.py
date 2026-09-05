"""Tests for observation-pool watch board (display only)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from alpha_system.ui.services.context import ScoreboardRow
from alpha_system.ui.services.rank_watchboard import (
    TONE_ELIGIBLE,
    TONE_PROPOSAL,
    TONE_WATCH,
    build_rank_watchboard,
    build_watch_table_rows,
    load_watch_metrics,
    watch_preview_tone,
)


def _row(
    ticker: str,
    score: float,
    *,
    held: bool = False,
    elig: bool | None = True,
    name: str = "",
    sector: str = "test",
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
        sector=sector,
    )


def test_ranks_scored_pool_keeps_below_cutoff() -> None:
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
    assert [r.ticker for r in board.rows] == [
        "000001",
        "000002",
        "000003",
        "000004",
    ]
    assert board.rows[0].rank == 1 and board.rows[0].in_proposal
    assert board.rows[1].is_held and board.rows[1].in_proposal
    assert not board.rows[2].in_proposal
    assert board.rows[3].eligibility is False
    assert board.held_outside == ()


def test_held_outside_top_n() -> None:
    rows = [_row(f"{i:06d}", float(100 - i)) for i in range(1, 35)]
    rows[32] = _row("000033", 67.0, held=True)  # rank 33 among 34 scored
    board = build_rank_watchboard(
        rows,
        proposal_tickers={"000001"},
        held_tickers={"000033"},
        max_rows=30,
    )
    assert len(board.rows) == 30
    assert board.held_outside and board.held_outside[0].ticker == "000033"
    assert board.held_outside[0].rank == 33


def test_watch_pool_is_wider_than_proposal_band() -> None:
    """Observation cap 30 ≠ live book 5–8."""
    rows = [_row(f"{i:06d}", float(100 - i)) for i in range(1, 40)]
    board = build_rank_watchboard(
        rows,
        proposal_tickers={"000001", "000002", "000003", "000004", "000005", "000006"},
        proposal_band_max=6,
        max_rows=30,
    )
    assert len(board.rows) == 30
    assert board.proposal_band_max == 6
    in_prop = [r for r in board.rows if r.in_proposal]
    assert len(in_prop) == 6
    assert in_prop[-1].rank == 6
    assert board.rows[-1].rank == 30
    assert not board.rows[-1].in_proposal


def test_below_cutoff_names_remain_in_watch_pool() -> None:
    rows = [_row(f"{i:06d}", float(100 - i), elig=(i <= 6)) for i in range(1, 40)]
    board = build_rank_watchboard(rows, max_rows=30)
    assert len(board.rows) == 30
    assert board.eligible_count == 6
    assert board.rows[5].eligibility is True
    assert board.rows[6].eligibility is False


def test_provisional_when_no_eligibility_true() -> None:
    board = build_rank_watchboard(
        [
            _row("000001", 50.0, elig=None),
            _row("000002", 40.0, elig=None),
        ],
        max_rows=30,
    )
    assert board.eligible_count == 0
    assert board.warnings
    assert board.rows[0].ticker == "000001"
    assert len(board.rows) == 2


def test_preview_tone_cutoff_then_book_size() -> None:
    assert (
        watch_preview_tone(score=90, cutoff=70, eligible_rank=1, target_n=6)
        == TONE_PROPOSAL
    )
    assert (
        watch_preview_tone(score=80, cutoff=70, eligible_rank=7, target_n=6)
        == TONE_ELIGIBLE
    )
    assert (
        watch_preview_tone(score=60, cutoff=70, eligible_rank=None, target_n=6)
        == TONE_WATCH
    )
    assert (
        watch_preview_tone(score=50, cutoff=None, eligible_rank=2, target_n=6)
        == TONE_PROPOSAL
    )
    assert (
        watch_preview_tone(score=None, cutoff=70, eligible_rank=None, target_n=6)
        == TONE_WATCH
    )


def test_watch_table_rows_join_metrics_and_tone() -> None:
    board = build_rank_watchboard(
        [
            _row("000001", 90.0, sector="보험"),
            _row("000002", 80.0, elig=False, sector="반도체"),
        ],
        proposal_tickers={"000001"},
        max_rows=30,
    )
    table = build_watch_table_rows(
        board,
        metrics={
            "000001": {
                "per": 8.1,
                "pbr": 0.7,
                "roe": 12.5,
                "price": 50000,
                "target": 62000,
            },
            "000002": {"per": 20.0, "pbr": 1.1, "roe": 5.0, "price": 10000},
        },
        extra_by_ticker={"000002": {"quant_price_mid": 13000}},
        cutoff=85.0,
        target_n=6,
    )
    assert table[0].tone == TONE_PROPOSAL
    assert table[0].sector == "보험"
    assert table[0].target_price == 62000
    assert table[1].tone == TONE_WATCH
    assert table[1].target_price == 13000
    assert "부적격" in table[1].judgment


def test_unscored_names_stay_in_watch_pool() -> None:
    board = build_rank_watchboard(
        [
            _row("000001", 90.0),
            _row("000002", 80.0),
            ScoreboardRow(
                ticker="000003",
                name="빈점수",
                total_score=None,
                score_q=None,
                score_v=None,
                score_sr=None,
                score_r=None,
                cecs=None,
                eligibility=False,
                sector_peer_fallback=False,
                is_held=False,
                status="final",
                sector="auto",
            ),
        ],
        max_rows=30,
    )
    assert [r.ticker for r in board.rows] == ["000001", "000002", "000003"]
    assert board.rows[2].total_score is None
    table = build_watch_table_rows(board, cutoff=85.0, target_n=6)
    assert table[2].tone == TONE_WATCH


def test_sector_labels_override_concentration_key() -> None:
    board = build_rank_watchboard(
        [_row("000001", 90.0, sector="consumer_staples")],
        max_rows=30,
    )
    table = build_watch_table_rows(
        board,
        sector_labels={"000001": "음식료·담배"},
        cutoff=50.0,
        target_n=6,
    )
    assert table[0].sector == "음식료·담배"


def test_load_watch_metrics_latest_fundamentals(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame(
        [
            {
                "ticker": "1",
                "period_end": "2025-12-31",
                "per": 10.0,
                "pbr": 1.0,
                "roe": 8.0,
            },
            {
                "ticker": "000001",
                "period_end": "2026-12-31",
                "per": 8.5,
                "pbr": 0.9,
                "roe": 11.0,
            },
        ]
    ).to_csv(data / "fundamentals.csv", index=False)
    pd.DataFrame(
        [
            {"ticker": "000001", "date": "2026-08-01", "close": 10000},
            {"ticker": "000001", "date": "2026-08-20", "close": 12000},
        ]
    ).to_csv(data / "prices.csv", index=False)
    (data / "kr_alpha_exit_targets.yaml").write_text(
        "tickers:\n  '000001':\n    target_price: 15000\n",
        encoding="utf-8",
    )
    met = load_watch_metrics(tmp_path)
    assert met["000001"]["per"] == 8.5
    assert met["000001"]["price"] == 12000
    assert met["000001"]["target"] == 15000


def test_load_watch_metrics_fills_roe_from_collect_when_ops_blank(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame(
        [{"ticker": "000660", "per": 26.6, "pbr": 9.62, "roe": ""}]
    ).to_csv(data / "fundamentals.csv", index=False)
    raw = tmp_path / "alpha_portfolio" / "data" / "raw"
    raw.mkdir(parents=True)
    pd.DataFrame(
        [{"ticker": "000660", "name": "SK하이닉스", "roe": 22.0, "roe_3y_avg": 18.0}]
    ).to_csv(raw / "fundamentals.csv", index=False)
    met = load_watch_metrics(tmp_path, data_dir=data)
    assert met["000660"]["roe"] == 22.0
    assert met["000660"]["pbr"] == 9.62


def test_naver_fchart_link_shows_name_in_fragment() -> None:
    from alpha_system.ui.services.rank_watchboard import (
        naver_fchart_link,
        naver_fchart_url,
    )

    url = naver_fchart_url("005930")
    assert url == "https://finance.naver.com/item/fchart.naver?code=005930"
    link = naver_fchart_link("5930", "삼성전자")
    assert link.startswith(url + "#")
    assert link.endswith("#삼성전자")
