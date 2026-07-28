"""UI scoreboard top-N must match dry CLI when reading alpha_scores.csv."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from alpha_system.loader import load_config
from alpha_system.report.screen_dry import build_screen_dry
from alpha_system.ui.services.context import _build_scoreboard, _build_screen_portfolio


ROOT = Path(__file__).resolve().parents[1]


def test_scoreboard_top6_matches_dry_proposal() -> None:
    cfg = load_config(ROOT / "alpha_system" / "config" / "alpha_system.yaml")
    # Use a cutoff inside the live score band so both paths produce a book.
    # Identity is about source parity (alpha_scores+CECS), not the absolute cutoff value.
    cfg = cfg.model_copy(
        update={
            "scoring": cfg.scoring.model_copy(update={"score_cutoff": 60.0}),
            "sizing": cfg.sizing.model_copy(update={"target_names": 6}),
        }
    )

    scores_path = ROOT / "alpha_portfolio" / "data" / "output" / "alpha_scores.csv"
    cecs_path = ROOT / "data" / "cecs_manual_scoring_template.csv"
    positions_path = ROOT / "data" / "positions.csv"
    fundamentals_path = ROOT / "data" / "fundamentals.csv"
    assert scores_path.exists()
    assert cecs_path.exists()

    scores_df = pd.read_csv(scores_path, dtype=str)
    cecs_df = pd.read_csv(cecs_path, dtype=str)
    positions_df = (
        pd.read_csv(positions_path, dtype=str) if positions_path.exists() else pd.DataFrame()
    )
    fundamentals_df = (
        pd.read_csv(fundamentals_path, dtype=str)
        if fundamentals_path.exists()
        else pd.DataFrame()
    )
    kr_positions = (
        positions_df[positions_df["asset_group"] == "kr_alpha"]
        if not positions_df.empty and "asset_group" in positions_df.columns
        else positions_df
    )

    board, _ = _build_scoreboard(cfg, cecs_df, scores_df, fundamentals_df, kr_positions)
    proposal = _build_screen_portfolio(
        cfg,
        board,
        prices_df=pd.DataFrame(),
        fundamentals_df=fundamentals_df,
        exit_targets_path=ROOT / "data" / "kr_alpha_exit_targets.yaml",
    )
    ui_tickers = [row.ticker for row in proposal]

    dry = build_screen_dry(
        cfg=cfg,
        scores_df=scores_df,
        cecs_df=cecs_df,
        positions_df=positions_df,
        as_of=date.today(),
    )
    dry_tickers = [
        str(r["ticker"]).zfill(6)
        for _, r in dry.rows[dry.rows["selected"] == True].iterrows()  # noqa: E712
    ]

    assert ui_tickers, "UI proposal_book이 비어 있으면 동일성 검수 불가"
    assert dry_tickers, "dry selected가 비어 있으면 동일성 검수 불가"
    assert ui_tickers == dry_tickers
    assert all(row.extra.get("book") == "proposal" for row in proposal)
