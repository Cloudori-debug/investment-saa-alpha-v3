from __future__ import annotations

from pathlib import Path

import yaml

from src.compass.portfolio_builder import build_portfolio_allocation
from src.compass.regime_engine import compute_compass
from src.compass.saa_engine import load_saa_profiles
from src.compass.target_decomposer import decompose_target_portfolio
from src.config import load_yaml
from src.data_loader import load_market_indicators, load_target_portfolio
from src.exposure.core_saa_reference import (
    build_core_saa_reference_diagnostic,
    load_core_saa_reference,
    validate_core_saa_reference,
)


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_core_saa_reference_v02_loads() -> None:
    doc = load_core_saa_reference(DATA_DIR)
    assert doc is not None
    assert doc["schema_version"] == "core_saa_reference.v0.2"
    assert doc["status"] == "primary_absolute_return_benchmark"
    assert doc["authority"] == "benchmark"
    assert doc.get("benchmark_mode") == "benchmark_reference_only"
    assert doc["affects_target_portfolio"] is False
    assert doc["affects_trade_actions"] is False
    assert doc["affects_execution_scope"] is False
    assert doc["reference_slot_count"] == 14
    assert len(doc.get("assets") or []) == 14


def test_target_weight_sum_100() -> None:
    doc = load_core_saa_reference(DATA_DIR)
    assert doc is not None
    total = sum(float(a.get("target_weight_pct") or 0) for a in doc["assets"])
    assert abs(total - 100.0) < 0.01


def test_unresolved_usd_short_bond_warn_only() -> None:
    doc = load_core_saa_reference(DATA_DIR)
    assert doc is not None
    usd_short = next(a for a in doc["assets"] if a.get("name") == "미국달러단기채")
    assert usd_short["ticker"] is None
    assert usd_short["tradable"] is False
    assert usd_short["mapping_status"] == "unresolved"
    warnings = doc.get("_validation_warnings") or []
    assert any("미국달러단기채" in w for w in warnings)


def test_reject_non_none_authority(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    bad = {
        "status": "shadow_reference_only",
        "authority": "v1.0.2",
        "affects_target_portfolio": False,
        "affects_trade_actions": False,
        "affects_execution_scope": False,
        "assets": [],
    }
    errors, _ = validate_core_saa_reference(bad)
    assert any("authority" in e for e in errors)
    (data / "core_saa_reference.yaml").write_text(yaml.dump(bad), encoding="utf-8")
    assert load_core_saa_reference(data) is None


def test_reject_affects_target_true(tmp_path: Path) -> None:
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
    errors, _ = validate_core_saa_reference(bad)
    assert any("affects_target_portfolio" in e for e in errors)


def test_core_etfs_in_target_portfolio_when_absolute_return_enabled() -> None:
    ref = load_core_saa_reference(DATA_DIR)
    assert ref is not None
    targets = load_target_portfolio(DATA_DIR / "target_portfolio.csv")
    target_tickers = {t.ticker for t in targets if t.ticker != "CASH"}
    core_tickers = {
        str(a["ticker"]).zfill(6) for a in ref["assets"] if a.get("ticker")
    }
    assert "360750" in target_tickers
    assert "195930" in target_tickers
    assert core_tickers.intersection(target_tickers)


def test_core_diagnostic_does_not_change_generated_targets() -> None:
    market = load_market_indicators(DATA_DIR / "market_indicators.csv")
    rules = load_yaml(DATA_DIR / "compass_rules.yaml")
    profiles = load_saa_profiles(DATA_DIR / "saa_profiles.yaml")
    template = load_target_portfolio(DATA_DIR / "target_portfolio.csv")

    compass = compute_compass(market, rules)
    allocation = build_portfolio_allocation(compass, profiles)
    before = decompose_target_portfolio(allocation, template)

    doc = build_core_saa_reference_diagnostic(DATA_DIR, as_of=market.date)
    assert doc is not None
    assert doc["diagnostic_only"] is True
    assert doc["authority"] == "benchmark"
    assert doc["mode"] == "benchmark_reference_only"

    after = decompose_target_portfolio(allocation, template)
    assert [(r.ticker, r.target_weight) for r in before] == [(r.ticker, r.target_weight) for r in after]


def test_core_diagnostic_gap_fields(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "core_saa_reference.yaml").write_text(
        DATA_DIR.joinpath("core_saa_reference.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (data / "positions.csv").write_text(
        "ticker,name,asset_group,sector,style,quantity,current_value\n"
        "157450,TIGER 단기통안채,cash_short_bond,bond,short_duration,100,50000000\n"
        "005440,현대지에프홀딩스,kr_alpha,holding,value,10,30000000\n",
        encoding="utf-8",
    )
    (data / "target_portfolio.csv").write_text(
        DATA_DIR.joinpath("target_portfolio.csv").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    doc = build_core_saa_reference_diagnostic(data, as_of="2026-06-26")
    assert doc is not None
    row = next(r for r in doc["core_assets"] if r.get("ticker") == "157450")
    assert row["core_target_weight_pct"] == 10.0
    assert row["gap_pct"] == round(row["current_weight_pct"] - 10.0, 2)
    unresolved = next(r for r in doc["core_assets"] if r.get("name") == "미국달러단기채")
    assert unresolved["mapping_status"] == "unresolved"
    assert unresolved["tradable"] is False
