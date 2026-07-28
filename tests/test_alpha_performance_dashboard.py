from __future__ import annotations

from pathlib import Path

import yaml

from src.alpha.performance_dashboard import (
    ALPHA_DASHBOARD_DISCLAIMER,
    build_alpha_performance_dashboard,
    write_alpha_performance_outputs,
)
from src.compass.portfolio_builder import build_portfolio_allocation
from src.compass.regime_engine import compute_compass
from src.compass.saa_engine import load_saa_profiles
from src.compass.target_decomposer import decompose_target_portfolio
from src.config import load_yaml
from src.data_loader import load_market_indicators, load_target_portfolio


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs"


def test_alpha_dashboard_builds_from_outputs() -> None:
    if not OUTPUT_DIR.exists():
        return
    doc = build_alpha_performance_dashboard(
        DATA_DIR, OUTPUT_DIR, as_of="2026-06-26", run_id="test",
    )
    assert doc["mode"] == "shadow_diagnostic_only"
    assert doc["authority"] == "none"
    assert doc["diagnostic_only"] is True
    assert "metrics" in doc
    assert doc["metrics"]["executable_buy_count"] == 0


def test_alpha_dashboard_does_not_change_targets() -> None:
    market = load_market_indicators(DATA_DIR / "market_indicators.csv")
    rules = load_yaml(DATA_DIR / "compass_rules.yaml")
    profiles = load_saa_profiles(DATA_DIR / "saa_profiles.yaml")
    template = load_target_portfolio(DATA_DIR / "target_portfolio.csv")
    compass = compute_compass(market, rules)
    allocation = build_portfolio_allocation(compass, profiles)
    before = decompose_target_portfolio(allocation, template)

    if OUTPUT_DIR.exists():
        write_alpha_performance_outputs(
            DATA_DIR, OUTPUT_DIR, as_of=market.date, run_id="test-no-exec-change",
        )

    after = decompose_target_portfolio(allocation, template)
    assert [(r.ticker, r.target_weight) for r in before] == [(r.ticker, r.target_weight) for r in after]


def test_reject_affects_flags_still_blocks_core_loader(tmp_path: Path) -> None:
    from src.exposure.core_saa_reference import load_core_saa_reference

    data = tmp_path / "data"
    data.mkdir()
    bad = {
        "status": "shadow_reference_only",
        "authority": "none",
        "affects_target_portfolio": True,
        "affects_trade_actions": False,
        "affects_execution_scope": False,
        "assets": [],
    }
    (data / "core_saa_reference.yaml").write_text(yaml.dump(bad), encoding="utf-8")
    assert load_core_saa_reference(data) is None


def test_disclaimer_present() -> None:
    assert "not a buy/sell recommendation" in ALPHA_DASHBOARD_DISCLAIMER
    assert "Core SAA benchmark" in ALPHA_DASHBOARD_DISCLAIMER
