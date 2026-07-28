from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.alpha.alpha_pipeline import run_alpha_pipeline
from src.alpha.data_gate import apply_data_gate
from src.alpha.loaders import load_fundamentals, load_universe, load_universe_filter_config
from src.alpha.schemas import FundamentalRecord
from src.alpha.universe_filter import filter_universe
from src.full_pipeline import run_full_pipeline


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_alpha_main_produces_outputs(tmp_path):
    out = run_alpha_pipeline(DATA_DIR, tmp_path)
    assert (tmp_path / "alpha_candidates.csv").exists()
    assert (tmp_path / "alpha_shortlist.csv").exists()
    assert (tmp_path / "alpha_portfolio_proposal.csv").exists()
    assert (tmp_path / "alpha_pillar_leaderboard.csv").exists()
    assert (tmp_path / "excluded.csv").exists()
    assert (tmp_path / "holdings_review.csv").exists()
    assert (tmp_path / "alpha_report.md").exists()
    assert (tmp_path / "gpt_context.json").exists()
    from src.data_loader import load_market_indicators

    expected_as_of = load_market_indicators(DATA_DIR / "market_indicators.csv").date
    assert out.result.as_of == expected_as_of


def test_preferred_stock_excluded(tmp_path):
    run_alpha_pipeline(DATA_DIR, tmp_path)
    excluded = pd.read_csv(tmp_path / "excluded.csv", dtype=str)
    pref = excluded[excluded["ticker"] == "005935"]
    assert not pref.empty
    assert pref.iloc[0]["failed_rule"] == "preferred_stock"


def test_etf_reit_excluded():
    from src.alpha.loaders import load_universe_filter_config
    from src.alpha.schemas import UniverseRecord
    from src.alpha.universe_filter import filter_universe

    cfg = load_universe_filter_config(DATA_DIR / "universe_filter.yaml")
    universe = [
        UniverseRecord(ticker="069500", name="KODEX 200", is_etf_etn=True, listed_date="2010-01-01"),
        UniverseRecord(ticker="365550", name="ESR켄달스퀘어리츠", is_reit=True, listed_date="2010-01-01"),
    ]
    _, excluded = filter_universe(universe, {}, cfg, "2026-06-17")
    etf = [e for e in excluded if e.ticker == "069500"]
    reit = [e for e in excluded if e.ticker == "365550"]
    assert etf and etf[0].failed_rule == "etf_etn"
    assert reit and reit[0].failed_rule == "reit"


def test_trading_halt_excluded():
    from src.alpha.loaders import load_universe_filter_config
    from src.alpha.schemas import UniverseRecord
    from src.alpha.universe_filter import filter_universe

    cfg = load_universe_filter_config(DATA_DIR / "universe_filter.yaml")
    universe = [
        UniverseRecord(
            ticker="999001",
            name="거래정지샘플",
            is_trading_halt=True,
            listed_date="2010-01-01",
        )
    ]
    _, excluded = filter_universe(universe, {}, cfg, "2026-06-17")
    halt = [e for e in excluded if e.ticker == "999001"]
    assert halt and halt[0].failed_rule == "trading_halt"


def test_point_in_time_blocks_future_fundamentals():
    fund = [
        FundamentalRecord(
            ticker="TEST",
            usable_from_date="2026-12-01",
            report_date="2026-11-01",
            roe=10.0,
        )
    ]
    cfg = load_universe_filter_config(DATA_DIR / "universe_filter.yaml")
    usable, excluded, status, _ = apply_data_gate(fund, cfg, "2026-06-17")
    assert "TEST" not in usable
    assert any(e.failed_rule == "point_in_time" for e in excluded)


def test_candidates_have_qvm_scores(tmp_path):
    run_alpha_pipeline(DATA_DIR, tmp_path)
    df = pd.read_csv(tmp_path / "alpha_candidates.csv")
    assert not df.empty
    for col in (
        "quality_score", "valuation_score", "momentum_score",
        "shareholder_return_score", "base_score", "total_score", "rank",
    ):
        assert col in df.columns
    assert (df["base_score"] >= df["total_score"]).all()


def test_max_candidates_limit(tmp_path):
    run_alpha_pipeline(DATA_DIR, tmp_path)
    df = pd.read_csv(tmp_path / "alpha_candidates.csv")
    assert len(df) <= 30


def test_holdings_review_generated(tmp_path):
    run_alpha_pipeline(DATA_DIR, tmp_path)
    df = pd.read_csv(tmp_path / "holdings_review.csv", dtype=str)
    assert not df.empty
    assert "review_action" in df.columns
    kr = df[df["ticker"].isin(["005830", "021240"])]
    assert len(kr) >= 2


def test_deterministic_output(tmp_path):
    out1 = run_alpha_pipeline(DATA_DIR, tmp_path / "a")
    out2 = run_alpha_pipeline(DATA_DIR, tmp_path / "b")
    c1 = pd.read_csv(tmp_path / "a" / "alpha_candidates.csv")
    c2 = pd.read_csv(tmp_path / "b" / "alpha_candidates.csv")
    pd.testing.assert_frame_equal(c1, c2)


def test_gpt_context_schema(tmp_path):
    run_alpha_pipeline(DATA_DIR, tmp_path)
    ctx = json.loads((tmp_path / "gpt_context.json").read_text(encoding="utf-8"))
    assert ctx["schema_version"] == "1.0"
    assert "top_candidates" in ctx
    assert "holdings_review" in ctx
    assert "action_constraints" in ctx
    assert "kr_alpha_meta" in ctx


def test_full_pipeline_includes_alpha(tmp_path):
    out = tmp_path / "out"
    result = run_full_pipeline(DATA_DIR, out, run_backtest=False)
    assert result.alpha_candidate_count > 0
    assert (out / "alpha_candidates.csv").exists()
    assert (out / "gpt_context.json").exists()
    assert (out / "holdings_review.csv").exists()
    assert result.alpha_backtest_ran
    assert (out / "alpha_backtest_summary.csv").exists()
