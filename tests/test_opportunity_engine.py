"""Alpha Opportunity Engine v0.2 acceptance tests."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.alpha.opportunity_engine import (
    OPPORTUNITY_DISCLAIMER,
    load_opportunity_config,
    score_opportunity_ticker,
    write_opportunity_outputs,
)

DATA = Path(__file__).resolve().parents[1] / "data"


def test_config_shadow_pilot_only() -> None:
    cfg = load_opportunity_config(DATA)
    assert cfg.get("status") == "shadow_pilot_only"
    assert cfg.get("affects_trade_actions") is False


def test_no_catalyst_can_reach_e2_e3() -> None:
    cfg = load_opportunity_config(DATA)
    px = {
        "close": 50000.0,
        "high_52w": 52000.0,
        "distance_from_52w_high": 0.96,
        "return_1m": 0.15,
        "return_3m": -0.08,
        "trading_value_20d": 15000000000,
        "trading_value_60d": 3000000000,
        "volatility_60d": 0.03,
    }
    alpha = {
        "momentum_score": 68.0,
        "quality_score": 58.0,
        "valuation_score": 55.0,
        "shareholder_return_score": 52.0,
    }
    history = [{"close": str(45000 + i * 500), "trading_value_20d": "3000000000"} for i in range(60)]
    sig = score_opportunity_ticker(
        ticker="005830",
        name="DB손해보험",
        sector="insurance",
        as_of="2026-06-26",
        px=px,
        alpha=alpha,
        fund=None,
        events=[],
        config=cfg,
        history=history,
        alpha_meta={"005830": alpha},
    )
    assert sig.catalyst_type == "none"
    assert sig.opportunity_grade in {"E2", "E3", "E4"}
    if sig.opportunity_grade in {"E2", "E3"}:
        assert sig.allowed_action.startswith("pilot_entry") or sig.opportunity_grade == "E2"


def test_denial_does_not_force_e0() -> None:
    cfg = load_opportunity_config(DATA)
    px = {
        "close": 50000.0,
        "high_52w": 52000.0,
        "distance_from_52w_high": 0.96,
        "return_1m": 0.12,
        "return_3m": -0.05,
        "trading_value_20d": 12000000000,
        "trading_value_60d": 4000000000,
        "volatility_60d": 0.03,
    }
    alpha = {"momentum_score": 65.0, "valuation_score": 50.0, "shareholder_return_score": 50.0}
    events = [{"report_title": "M&A 루머 사실무근 해명", "event_types": "ma_tender", "event_date": "2026-06-25"}]
    sig = score_opportunity_ticker(
        ticker="000001",
        name="Test",
        sector="insurance",
        as_of="2026-06-26",
        px=px,
        alpha=alpha,
        fund=None,
        events=events,
        config=cfg,
        history=[],
        alpha_meta={"000001": alpha},
    )
    assert sig.catalyst_denied is True
    assert sig.opportunity_grade != "E0" or sig.total_score < 40


def test_no_volume_blocks_e3() -> None:
    cfg = load_opportunity_config(DATA)
    px = {
        "close": 50000.0,
        "high_52w": 52000.0,
        "distance_from_52w_high": 0.99,
        "return_1m": 0.2,
        "return_3m": -0.1,
        "trading_value_20d": 0,
        "trading_value_60d": 0,
        "volatility_60d": 0.02,
    }
    alpha = {"momentum_score": 70.0, "valuation_score": 55.0, "shareholder_return_score": 55.0}
    sig = score_opportunity_ticker(
        ticker="000002",
        name="Test2",
        sector="tech",
        as_of="2026-06-26",
        px=px,
        alpha=alpha,
        fund=None,
        events=[],
        config=cfg,
        history=[],
    )
    assert sig.opportunity_grade != "E3"
    assert "volume_ratio" in sig.missing_data


def test_stop_required_for_pilot(tmp_path: Path) -> None:
    cfg = load_opportunity_config(DATA)
    sig = score_opportunity_ticker(
        ticker="999999",
        name="X",
        sector="",
        as_of="2026-06-26",
        px=None,
        alpha={},
        fund=None,
        events=[],
        config=cfg,
    )
    assert sig.allowed_action in {"noise", "watch"}
    assert sig.allowed_position_fraction == 0.0


def test_writes_opportunity_outputs(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    (data / "opportunity_engine_config.yaml").write_text(
        (DATA / "opportunity_engine_config.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    pd.DataFrame([{
        "ticker": "005830", "name": "DB손해보험", "asset_group": "kr_alpha",
        "sector": "insurance", "style": "", "quantity": "1", "current_value": "1000",
        "avg_price": "", "current_price": "100",
    }]).to_csv(data / "positions.csv", index=False)
    pd.DataFrame([{
        "date": "2026-06-26", "ticker": "005830", "close": "100000",
        "market_cap": "0", "trading_value_20d": "5000000000", "trading_value_60d": "8000000000",
        "return_1m": "0.1", "return_3m": "-0.05", "return_6m": "0", "return_12m": "0",
        "return_12m_ex_1m": "0", "high_52w": "110000", "distance_from_52w_high": "0.9",
        "volatility_60d": "0.03",
    }]).to_csv(data / "prices.csv", index=False)
    pd.DataFrame([{
        "ticker": "005830", "name": "DB손해보험", "sector": "insurance",
        "quality_score": "55", "valuation_score": "50", "momentum_score": "60",
        "shareholder_return_score": "50", "total_score": "55", "grade": "B",
    }]).to_csv(out / "alpha_candidates.csv", index=False)

    report = write_opportunity_outputs(data, out, as_of="2026-06-26")
    assert (out / "opportunity_signals.csv").exists()
    assert (out / "opportunity_brief.md").exists()
    assert (out / "opportunity_decision.json").exists()
    assert (out / "opportunity_reason_breakdown.csv").exists()
    assert report["disclaimer"] == OPPORTUNITY_DISCLAIMER
    loaded = json.loads((out / "opportunity_decision.json").read_text(encoding="utf-8"))
    assert loaded["affects_trade_actions"] is False
