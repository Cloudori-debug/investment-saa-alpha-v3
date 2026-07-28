"""Early Alpha Engine v0.1 acceptance tests."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.alpha.early_alpha_engine import (
    EARLY_ALPHA_DISCLAIMER,
    build_early_alpha_decision,
    load_early_alpha_config,
    score_early_alpha_ticker,
    write_early_alpha_outputs,
)

DATA = Path(__file__).resolve().parents[1] / "data"


def test_config_shadow_pilot_only() -> None:
    cfg = load_early_alpha_config(DATA)
    assert cfg.get("status") == "shadow_pilot_only"
    assert cfg.get("affects_trade_actions") is False
    assert cfg.get("affects_final_execution") is False


def test_e2_is_pilot_not_full_buy() -> None:
    cfg = load_early_alpha_config(DATA)
    px = {
        "close": 2000.0,
        "high_52w": 2100.0,
        "distance_from_52w_high": 0.95,
        "return_1m": 0.12,
        "return_3m": -0.05,
        "trading_value_20d": 6000000000,
        "trading_value_60d": 12000000000,
        "volatility_60d": 0.04,
    }
    events = [{
        "report_title": "공개매수 공고",
        "event_types": "ma_tender",
        "event_date": "2026-06-20",
    }]
    sig = score_early_alpha_ticker(
        ticker="000830",
        name="삼성화재",
        as_of="2026-06-26",
        px=px,
        events=events,
        config=cfg,
    )
    assert sig.early_grade in {"E2", "E3", "E4"}
    if sig.early_grade == "E2":
        assert sig.allowed_action == "pilot_entry_10"
        assert sig.allowed_position_fraction == 0.10
    assert "confirmation" not in sig.allowed_action
    assert sig.pilot_only is True


def test_no_stop_no_pilot() -> None:
    cfg = load_early_alpha_config(DATA)
    sig = score_early_alpha_ticker(
        ticker="999999",
        name="TEST",
        as_of="2026-06-26",
        px=None,
        events=[],
        config=cfg,
    )
    assert sig.allowed_action in {"noise", "watch"}
    assert sig.allowed_position_fraction == 0.0


def test_denial_caps_grade() -> None:
    cfg = load_early_alpha_config(DATA)
    px = {
        "close": 2000.0,
        "high_52w": 2500.0,
        "distance_from_52w_high": 0.8,
        "return_1m": 0.15,
        "return_3m": 0.1,
        "trading_value_20d": 8000000000,
        "trading_value_60d": 10000000000,
        "volatility_60d": 0.03,
    }
    events = [{"report_title": "루머 사실무근 해명", "event_types": "governance", "event_date": "2026-06-25"}]
    sig = score_early_alpha_ticker(
        ticker="000001",
        name="Test",
        as_of="2026-06-26",
        px=px,
        events=events,
        config=cfg,
    )
    assert sig.early_grade == "E0"
    assert sig.catalyst_score == 0
    assert sig.risk_penalty <= -20


def test_no_volume_blocks_e3(tmp_path: Path) -> None:
    cfg = load_early_alpha_config(DATA)
    px = {
        "close": 2000.0,
        "high_52w": 2050.0,
        "distance_from_52w_high": 0.97,
        "return_1m": 0.2,
        "return_3m": -0.1,
        "trading_value_20d": 0,
        "trading_value_60d": 0,
        "volatility_60d": 0.03,
    }
    events = [{"report_title": "공개매수", "event_types": "ma_tender", "event_date": "2026-06-20"}]
    sig = score_early_alpha_ticker(
        ticker="000002",
        name="Test2",
        as_of="2026-06-26",
        px=px,
        events=events,
        config=cfg,
        history=[],
    )
    assert sig.early_grade != "E3"
    assert "volume_ratio" in sig.missing_data


def test_writes_outputs(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    (data / "early_alpha_config.yaml").write_text(
        (DATA / "early_alpha_config.yaml").read_text(encoding="utf-8"),
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

    report = write_early_alpha_outputs(data, out, as_of="2026-06-26")
    assert (out / "early_alpha_signals.csv").exists()
    assert (out / "early_alpha_brief.md").exists()
    assert (out / "early_alpha_decision.json").exists()
    assert report["disclaimer"] == EARLY_ALPHA_DISCLAIMER
    loaded = json.loads((out / "early_alpha_decision.json").read_text(encoding="utf-8"))
    assert loaded["affects_trade_actions"] is False


def test_weak_catalyst_caps_e3() -> None:
    cfg = load_early_alpha_config(DATA)
    px = {
        "close": 2000.0,
        "high_52w": 2020.0,
        "distance_from_52w_high": 0.99,
        "return_1m": 0.25,
        "return_3m": -0.15,
        "trading_value_20d": 15000000000,
        "trading_value_60d": 3000000000,
        "volatility_60d": 0.02,
    }
    sig = score_early_alpha_ticker(
        ticker="000003",
        name="NoCat",
        as_of="2026-06-26",
        px=px,
        events=[],
        config=cfg,
    )
    assert sig.early_grade not in {"E3", "E4"}


def test_build_decision_from_live_outputs() -> None:
    out = DATA.parent / "outputs"
    if not (out / "alpha_shortlist.csv").exists():
        return
    decision = build_early_alpha_decision(DATA, out, as_of="2026-06-26")
    assert decision["mode"] == "shadow_pilot_only"
    for row in decision.get("signals") or []:
        if row.get("allowed_action", "").startswith("pilot_entry"):
            assert row.get("stop_level") not in ("", None)
            assert float(row.get("allowed_position_fraction") or 0) <= 0.25
