"""Alpha Opportunity Analytics v0.3 acceptance tests."""
from __future__ import annotations

import json
from pathlib import Path

from src.alpha.opportunity_analytics import (
    ANALYTICS_DISCLAIMER,
    classify_opportunity_type,
    enrich_signals_with_analytics,
    estimate_success_probability,
    load_analytics_config,
    update_ledger_from_signals,
    write_opportunity_analytics,
)

DATA = Path(__file__).resolve().parents[1] / "data"


def _sample_signal(**overrides: object) -> dict:
    base = {
        "ticker": "005830",
        "name": "DB손해보험",
        "total_score": 72,
        "opportunity_grade": "E2",
        "allowed_action": "pilot_entry_15pct",
        "volume_score": 14,
        "price_structure_score": 15,
        "fundamental_momentum_score": 10,
        "valuation_rerating_score": 6,
        "flow_score": 8,
        "sector_momentum_score": 6,
        "risk_penalty": -5,
        "catalyst_type": "none",
        "e3_signals_met": "box_breakout,volume_surge",
        "e3_composite_count": 3,
    }
    base.update(overrides)
    return base


def test_classify_opportunity_type_breakout() -> None:
    row = _sample_signal(price_structure_score=16, volume_score=14, e3_signals_met="box_breakout")
    assert classify_opportunity_type(row) == "breakout"


def test_classify_opportunity_type_re_rating() -> None:
    row = _sample_signal(catalyst_type="buyback", valuation_rerating_score=10)
    assert classify_opportunity_type(row) == "re_rating"


def test_success_probability_decays_with_age() -> None:
    cfg = load_analytics_config(DATA)
    row = _sample_signal()
    row["opportunity_type"] = "breakout"
    fresh = estimate_success_probability(row, opportunity_age_days=0, cfg=cfg)
    aged = estimate_success_probability(row, opportunity_age_days=28, cfg=cfg)
    assert aged < fresh


def test_ledger_tracks_age_across_runs(tmp_path: Path) -> None:
    cfg = load_analytics_config(DATA)
    prices = {"005830": {"close": 50000.0}}
    sig = _sample_signal()

    update_ledger_from_signals([sig], as_of="2026-06-01", output_dir=tmp_path, cfg=cfg, prices=prices)
    enriched = update_ledger_from_signals([sig], as_of="2026-06-15", output_dir=tmp_path, cfg=cfg, prices=prices)

    row = next(r for r in enriched if r["ticker"] == "005830")
    assert row["opportunity_age_days"] > 0
    assert row["first_seen_date"] == "2026-06-01"
    assert row["opportunity_type"] == "breakout"


def test_write_opportunity_analytics_outputs(tmp_path: Path) -> None:
    cfg = load_analytics_config(DATA)
    decision = {
        "signals": [_sample_signal(), _sample_signal(ticker="000660", name="SK하이닉스", total_score=55, opportunity_grade="E1", allowed_action="watch")],
        "pilot_entry_count": 1,
    }
    analytics = write_opportunity_analytics(DATA, tmp_path, decision, as_of="2026-06-26", config=cfg)

    assert analytics["phase"] == "Alpha-Opportunity-Analytics-v0.3"
    assert analytics["mode"] == "shadow_learning_only"
    assert ANALYTICS_DISCLAIMER in analytics["disclaimer"]
    assert (tmp_path / "opportunity_analytics.json").exists()
    assert (tmp_path / "opportunity_failure_database.json").exists()
    assert (tmp_path / "opportunity_post_analysis.csv").exists()
    assert (tmp_path / "opportunity_signal_ledger.jsonl").exists()

    pilot = analytics["top_pilot_analytics"]
    assert len(pilot) >= 1
    p0 = pilot[0]
    assert p0["success_probability_pct"] > 0
    assert p0["expected_alpha_pct"] > 0
    assert p0["expected_holding_days"] > 0
    assert p0["opportunity_type"] in cfg["opportunity_types"]


def test_enrich_signals_includes_probability_fields() -> None:
    cfg = load_analytics_config(DATA)
    row = _sample_signal(opportunity_type="recovery", opportunity_age_days=5)
    enriched = enrich_signals_with_analytics([row], cfg=cfg, failure_db={})
    assert enriched[0]["probability_source"] == "heuristic_model"
    assert "success_probability_pct" in enriched[0]
    assert "expected_alpha_pct" in enriched[0]


def test_failure_database_structure(tmp_path: Path) -> None:
    cfg = load_analytics_config(DATA)
    decision = {"signals": [_sample_signal()]}
    write_opportunity_analytics(DATA, tmp_path, decision, as_of="2026-06-26", config=cfg)
    fdb = json.loads((tmp_path / "opportunity_failure_database.json").read_text(encoding="utf-8"))
    assert fdb["schema_version"] == "0.3"
    assert "by_opportunity_type" in fdb
    assert "failure_reason_counts" in fdb
    assert fdb["total_closed"] == 0
