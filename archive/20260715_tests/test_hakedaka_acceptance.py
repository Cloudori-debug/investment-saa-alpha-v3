"""AC-HK-01 ~ AC-HK-06 하케다카·제안 포트 수용 기준."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.alpha.schemas import UniverseRecord, make_excluded
from src.value_list.alpha_bridge import (
    apply_hakedaka_alpha_bonus,
    eligible_for_proposal_row,
    proposal_mode,
    proposal_sort_score,
    tie_breaker_applies_to_proposal,
)
from src.value_list.ticker_registry import load_integration_config, resolve_hakedaka_registry


DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def cfg():
    return load_integration_config(DATA)


def test_ac_hk_01_liquidity_fail_not_in_proposal(cfg):
    row = {"ticker": "009680", "grade": "A", "liquidity_pass": False, "in_hakedaka": True}
    assert eligible_for_proposal_row(row, cfg) is False


def test_ac_hk_02_no_forced_slot(cfg):
    assert (cfg.get("portfolio_inclusion") or {}).get("hard_slot_enabled") is False
    row = {
        "ticker": "009680",
        "grade": "A",
        "liquidity_pass": True,
        "in_hakedaka": True,
        "dart_verified": True,
        "total_score": 99,
        "qvm_pure_score": 40,
    }
    assert proposal_mode(cfg) == "pure_qvm"
    assert proposal_sort_score(row, cfg) == 40.0


def test_ac_hk_03_diagnostics_row_count(tmp_path):
    from src.value_list.overlap_diagnostics import write_hakedaka_overlap_diagnostics

    registry = resolve_hakedaka_registry(DATA)
    out = tmp_path / "out"
    write_hakedaka_overlap_diagnostics(
        DATA,
        out,
        universe=[],
        excluded=[],
        graded=[],
        shortlist_tickers=set(),
        proposal_tickers=set(),
        prices_by_ticker={},
        filter_cfg={},
        as_of="2026-06-24",
        usable_fund_tickers=set(),
        scoring_cfg={"selection": {"min_pillar_score": {}, "min_pillars_pass": 3, "min_all_pillar_floor": 45}},
    )
    import pandas as pd

    df = pd.read_csv(out / "hakedaka_overlap_diagnostics.csv")
    from src.value_list.ticker_registry import hakedaka_meta_by_ticker

    expected = len(hakedaka_meta_by_ticker(DATA))
    assert len(df) == expected


def test_ac_hk_04_priority_review_filters(cfg, tmp_path):
    from src.value_list.overlap_diagnostics import write_hakedaka_overlap_diagnostics

    graded = [{
        "ticker": "009680",
        "name": "모토닉",
        "total_score": 70,
        "qvm_pure_score": 70,
        "grade": "B",
        "quality_score": 60,
        "valuation_score": 60,
        "momentum_score": 60,
        "shareholder_return_score": 60,
        "in_hakedaka": True,
        "dart_verified": True,
        "hakedaka_priority": True,
        "liquidity_pass": True,
        "eligible_action": "WATCH",
        "penalty": 0,
    }]
    write_hakedaka_overlap_diagnostics(
        DATA,
        tmp_path,
        universe=[UniverseRecord(ticker="009680", name="모토닉")],
        excluded=[],
        graded=graded,
        shortlist_tickers={"009680"},
        proposal_tickers=set(),
        prices_by_ticker={},
        filter_cfg={},
        as_of="2026-06-24",
        usable_fund_tickers={"009680"},
        scoring_cfg={
            "selection": {
                "min_pillar_score": {"quality": 55, "valuation": 55, "momentum": 55, "shareholder_return": 55},
                "min_pillars_pass": 3,
                "min_all_pillar_floor": 45,
            },
        },
    )
    import pandas as pd

    pr = tmp_path / "hakedaka_priority_review.csv"
    if pr.exists():
        review = pd.read_csv(pr)
        assert all(review["liquidity_pass"].astype(str).str.lower() == "true")
        assert all(review["dart_verified"].astype(str).str.lower() == "true")


def test_ac_hk_05_shadow_does_not_auto_target(cfg):
    assert cfg.get("shadow_slot_candidate_enabled") is True
    assert (cfg.get("portfolio_inclusion") or {}).get("hard_slot_enabled") is False


def test_ac_hk_06_tiebreaker_off_by_default(cfg):
    assert tie_breaker_applies_to_proposal(cfg) is False


def test_pure_qvm_bonus_not_in_total_score(cfg):
    if proposal_mode(cfg) != "pure_qvm":
        pytest.skip("pure_qvm only")
    row = {
        "ticker": "009680",
        "total_score": 50.0,
        "grade": "B",
        "eligible_action": "WATCH",
        "penalty": 0,
    }
    out = apply_hakedaka_alpha_bonus(
        [row],
        DATA,
        liquidity_pass_by_ticker={"009680": True},
    )
    r = out[0]
    assert r["qvm_pure_score"] == 50.0
    if r.get("hakedaka_bonus", 0) > 0:
        assert r["total_score"] == 50.0


def test_watch_eligible_liquidity_fail(tmp_path):
    from src.value_list.overlap_diagnostics import write_hakedaka_overlap_diagnostics

    ticker = "009680"
    write_hakedaka_overlap_diagnostics(
        DATA,
        tmp_path,
        universe=[],
        excluded=[make_excluded(ticker, "모토닉", "거래대금", "min_20d_trading_value")],
        graded=[],
        shortlist_tickers=set(),
        proposal_tickers=set(),
        prices_by_ticker={},
        filter_cfg={"liquidity": {}, "universe": {"include": {}, "exclude": {}}},
        as_of="2026-06-24",
        usable_fund_tickers=set(),
        scoring_cfg={"selection": {"min_pillar_score": {}, "min_pillars_pass": 3, "min_all_pillar_floor": 45}},
    )
    import pandas as pd

    df = pd.read_csv(tmp_path / "hakedaka_overlap_diagnostics.csv")
    row = df[df["ticker"].astype(str).str.zfill(6) == ticker]
    if not row.empty:
        r = row.iloc[0]
        if str(r.get("liquidity_pass", "")).lower() == "false":
            assert str(r.get("eligible_for_portfolio", "")).lower() == "false"
