from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.alpha.alpha_pipeline import run_alpha_pipeline
from src.alpha.loaders import load_alpha_scoring_config
from src.alpha.portfolio_selector import build_shortlist_and_proposal
from src.position_lookup import lookup_ticker_metadata

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_portfolio_selector_pillar_filter():
    cfg = load_alpha_scoring_config(DATA_DIR / "alpha_scoring.yaml")
    scored = [
        {
            "ticker": "AAA",
            "name": "A",
            "sector": "tech",
            "quality_score": 80,
            "valuation_score": 20,
            "momentum_score": 70,
            "shareholder_return_score": 30,
            "total_score": 55,
            "penalty": 0,
            "grade": "B",
            "eligible_action": "WATCH",
        },
        {
            "ticker": "BBB",
            "name": "B",
            "sector": "insurance",
            "quality_score": 70,
            "valuation_score": 75,
            "momentum_score": 60,
            "shareholder_return_score": 80,
            "total_score": 72,
            "penalty": 0,
            "grade": "A",
            "eligible_action": "BUY_CANDIDATE",
        },
    ]
    result = build_shortlist_and_proposal(scored, cfg, kr_alpha_budget=15.0)
    tickers = {s.ticker for s in result.shortlist}
    assert "BBB" in tickers
    assert "AAA" not in tickers
    assert len(result.proposal) >= 1
    assert result.proposal[0].role in {"core", "satellite", "value", "balanced"}


def test_alpha_pipeline_writes_proposal(tmp_path):
    out = run_alpha_pipeline(DATA_DIR, tmp_path)
    assert (tmp_path / "alpha_portfolio_proposal.csv").exists()
    assert (tmp_path / "alpha_shortlist.csv").exists()
    assert out.result.candidates


def test_lookup_ticker_metadata():
    meta = lookup_ticker_metadata(DATA_DIR, "005830")
    assert meta["ticker"] == "005830"
    assert meta["name"]
    assert meta["sources"]


def test_satellite_proposed_cap_tracks_kr_alpha_budget():
    """위성 제안 캡은 target_matrix 슬리브% × budget — 예산이 바뀌면 같이 움직임."""
    from src.alpha.portfolio_selector import (
        build_shortlist_and_proposal,
        load_satellite_single_name_sleeve_pct,
        resolve_proposed_weight_cap,
        sleeve_pct_to_portfolio,
    )

    sleeve = load_satellite_single_name_sleeve_pct()
    assert sleeve == pytest.approx(5.0)

    for budget in (15.0, 21.85, 25.0):
        expected = sleeve_pct_to_portfolio(sleeve, budget)
        cap, src = resolve_proposed_weight_cap(
            "satellite",
            kr_alpha_budget=budget,
            legacy_max_proposed_pct=8.0,
            satellite_sleeve_pct=sleeve,
        )
        assert src == "target_matrix.satellite_cap"
        assert cap == pytest.approx(expected)
        assert cap == pytest.approx(round(sleeve * budget / 100.0, 2))

    # 동일 scored 풀에서 budget만 바꿔도 satellite 제안 비중이 예산에 비례
    cfg = load_alpha_scoring_config(DATA_DIR / "alpha_scoring.yaml")
    scored = [
        {
            "ticker": f"{i:06d}",
            "name": f"N{i}",
            "sector": "tech" if i % 2 == 0 else "consumer",
            "quality_score": 62,
            "valuation_score": 56,
            "momentum_score": 95,  # → satellite role (momentum dominant)
            "shareholder_return_score": 56,
            "total_score": 70,
            "penalty": 0,
            "grade": "A",
            "eligible_action": "BUY_CANDIDATE",
        }
        for i in range(1, 9)
    ]
    caps = []
    for budget in (15.0, 25.0):
        result = build_shortlist_and_proposal(scored, cfg, kr_alpha_budget=budget)
        sats = [p for p in result.proposal if p.role == "satellite"]
        assert sats, "momentum-dominant rows should be satellite"
        for p in sats:
            assert p.proposed_weight_pct <= sleeve_pct_to_portfolio(sleeve, budget) + 1e-9
        caps.append(max(p.proposed_weight_pct for p in sats))
    assert caps[1] > caps[0]


def test_non_satellite_still_uses_max_proposed_weight_pct():
    from src.alpha.portfolio_selector import resolve_proposed_weight_cap

    cap, src = resolve_proposed_weight_cap(
        "core",
        kr_alpha_budget=21.85,
        legacy_max_proposed_pct=8.0,
    )
    assert cap == 8.0
    assert src == "max_proposed_weight_pct"


def test_saa_taa_ticker_tables():
    from src.ui.allocation_tickers import build_saa_ticker_targets, build_taa_ticker_targets

    saa = build_saa_ticker_targets(DATA_DIR, "defensive_balanced")
    assert not saa.empty
    assert "ticker" in saa.columns
    assert saa["SAA목표(%)"].sum() == pytest.approx(100.0, abs=2.0)
    taa = build_taa_ticker_targets(DATA_DIR / ".." / "outputs", DATA_DIR)
    if (DATA_DIR.parent / "outputs" / "generated_target_portfolio.csv").exists():
        assert not taa.empty
