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

    board, _ = _build_scoreboard(
        cfg,
        cecs_df,
        scores_df,
        fundamentals_df,
        kr_positions,
        data_dir=ROOT / "data",
    )
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
        data_dir=ROOT / "data",
    )
    dry_tickers = [
        str(r["ticker"]).zfill(6)
        for _, r in dry.rows[dry.rows["selected"] == True].iterrows()  # noqa: E712
    ]

    assert set(ui_tickers) == set(dry_tickers)
    scored = set(scores_df["ticker"].astype(str).str.zfill(6))
    assert set(ui_tickers) <= scored
    assert set(dry_tickers) <= scored
    if ui_tickers:
        assert len(ui_tickers) <= int(cfg.sizing.target_names)
        assert all(row.extra.get("book") == "proposal" for row in proposal)


def test_scoreboard_from_alpha_scores_without_cecs() -> None:
    cfg = load_config(ROOT / "alpha_system" / "config" / "alpha_system.yaml")
    cfg = cfg.model_copy(
        update={"scoring": cfg.scoring.model_copy(update={"score_cutoff": 50.0})}
    )
    scores_df = pd.DataFrame(
        [
            {
                "ticker": "247540",
                "name": "에코프로비엠",
                "score_q": 60,
                "score_v": 55,
                "score_sr": 50,
                "score_r": 40,
                "gate_pass": True,
            }
        ]
    )
    board, _ = _build_scoreboard(
        cfg, pd.DataFrame(), scores_df, pd.DataFrame(), pd.DataFrame()
    )
    assert len(board) == 1
    assert board[0].ticker == "247540"
    assert board[0].total_score is not None
    assert board[0].eligibility is True


def test_quality_gate_uses_collect_fundamentals_not_ops_stubs(tmp_path: Path) -> None:
    """Ops ledger ROE is often empty; eligibility must follow collect-time ROE."""
    cfg = load_config(ROOT / "alpha_system" / "config" / "alpha_system.yaml")
    cfg = cfg.model_copy(
        update={"scoring": cfg.scoring.model_copy(update={"score_cutoff": 50.0})}
    )
    ops = tmp_path / "data"
    ops.mkdir()
    (ops / "fundamentals.csv").write_text(
        "ticker,roe,roe_3y_avg\n000660,\n", encoding="utf-8"
    )
    alpha_raw = tmp_path / "alpha_portfolio" / "data" / "raw"
    alpha_raw.mkdir(parents=True)
    (alpha_raw / "fundamentals.csv").write_text(
        "ticker,roe,roe_3y_avg\n000660,22.0,18.0\n", encoding="utf-8"
    )
    scores_df = pd.DataFrame(
        [
            {
                "ticker": "000660",
                "name": "SK하이닉스",
                "score_q": 92.0,
                "score_v": 40.0,
                "score_sr": 50.0,
                "score_r": 40.0,
                "gate_pass": True,
            }
        ]
    )
    ops_fund = pd.read_csv(ops / "fundamentals.csv", dtype=str)
    board, _ = _build_scoreboard(
        cfg,
        pd.DataFrame(),
        scores_df,
        ops_fund,
        pd.DataFrame(),
        data_dir=ops,
    )
    assert board[0].eligibility is True
