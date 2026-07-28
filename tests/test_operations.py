from __future__ import annotations

from pathlib import Path

from src.compass.regime_engine import compute_compass
from src.config import load_yaml
from src.data_loader import load_market_indicators
from src.validation.acceptance_check import run_acceptance_check

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def test_regime_expires_uses_computed():
    market = load_market_indicators(DATA / "market_indicators.csv")
    rules = load_yaml(DATA / "compass_rules.yaml")
    r_ok = compute_compass(market, rules)
    market.regime_expires_date = "2020-01-01"
    r_exp = compute_compass(market, rules)
    assert r_exp.applied_regime == r_exp.computed_regime or not r_exp.override.active


def test_acceptance_report_runs():
    report = run_acceptance_check(DATA, ROOT / "outputs")
    assert report.overall in ("GREEN", "YELLOW", "RED")
    assert report.execution_scope in ("NO_TRADE", "ETF_ONLY", "ETF_AND_BETA", "FULL_WITH_ALPHA")
    assert report.alpha_approval in ("APPROVED", "RESTRICTED", "BLOCKED")
    assert len(report.items) >= 8
