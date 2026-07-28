"""Screen book portfolio replaces purchase-weight holdings in UI."""

from __future__ import annotations

from alpha_system.loader import load_config
from alpha_system.ui.services.context import (
    ScoreboardRow,
    _build_screen_portfolio,
)


def _board(*rows: tuple[str, str, float, bool]) -> list[ScoreboardRow]:
    out: list[ScoreboardRow] = []
    for ticker, name, score, eligible in rows:
        out.append(
            ScoreboardRow(
                ticker=ticker,
                name=name,
                total_score=score,
                score_q=score,
                score_v=score,
                score_sr=score,
                score_r=score,
                cecs=score,
                eligibility=eligible,
                sector_peer_fallback=False,
                is_held=False,
                status="final",
            )
        )
    return out


def test_screen_portfolio_takes_top_eligible_not_purchase_book(tmp_path) -> None:
    cfg = load_config()
    cfg = cfg.model_copy(
        update={
            "scoring": cfg.scoring.model_copy(update={"score_cutoff": 80.0}),
            "sizing": cfg.sizing.model_copy(update={"target_names": 3}),
        }
    )
    board = _board(
        ("000001", "A", 90.0, True),
        ("000002", "B", 88.0, True),
        ("000003", "C", 85.0, True),
        ("000004", "D", 84.0, True),
        ("000005", "E", 70.0, False),
    )
    rows = _build_screen_portfolio(
        cfg,
        board,
        prices_df=__import__("pandas").DataFrame(),
        fundamentals_df=__import__("pandas").DataFrame(),
        exit_targets_path=tmp_path / "missing.yaml",
    )

    assert [row.ticker for row in rows] == ["000001", "000002", "000003"]
    assert all(row.avg_price is None for row in rows)
    assert all(row.extra.get("book") == "proposal" for row in rows)
    assert sum(row.weight_pct for row in rows) > 0
    assert all(row.weight_pct <= cfg.sizing.initial_weight_cap * 100.0 + 0.01 for row in rows)
    assert all(row.target_gap_kind == "screen_pending" for row in rows)
