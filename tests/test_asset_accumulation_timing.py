"""Phase AR-2 asset accumulation timing tests."""
from __future__ import annotations

import json
from pathlib import Path

from src.config import load_trigger_rules
from src.data_loader import load_market_indicators, load_positions, load_target_portfolio
from src.portfolio_gap import compute_gaps
from src.timing.asset_accumulation_timing import (
    AR2_DISCLAIMER,
    build_asset_accumulation_timing,
    build_execution_status,
    load_accumulation_timing_config,
    write_asset_accumulation_timing,
)
from src.trigger_engine import evaluate_triggers

DATA = Path(__file__).resolve().parents[1] / "data"
OUT = DATA.parent / "outputs"


def test_config_shadow_only() -> None:
    cfg = load_accumulation_timing_config(DATA)
    assert cfg.get("status") == "shadow_timing_only"
    assert cfg.get("affects_trade_actions") is False
    assert cfg.get("affects_final_execution") is False


def test_execution_blocked_on_red_gate() -> None:
    ex = build_execution_status(
        data_gate="RED",
        execution_scope="NO_TRADE",
        dry_run_days=5,
        dry_run_required=10,
        throttle_meta={"gate_allowed": False},
        timing_status="Ready",
        underweight_gap=10.0,
    )
    assert ex["executable"] is False
    assert ex["execution_status"] == "blocked"
    assert ex["blocked_by_gate"] is True


def test_ready_does_not_imply_executable_without_green() -> None:
    market = load_market_indicators(DATA / "market_indicators.csv")
    rules = load_trigger_rules(DATA / "trigger_rules.yaml")
    positions = load_positions(DATA / "positions.csv")
    targets = load_target_portfolio(DATA / "target_portfolio.csv")
    gap_rows = compute_gaps(positions, targets)
    alerts = evaluate_triggers(market, rules)

    report = build_asset_accumulation_timing(
        data_dir=DATA,
        output_dir=OUT,
        market=market,
        alerts=alerts,
        rules=rules,
        gap_rows=gap_rows,
        data_gate="YELLOW",
        execution_scope="ETF_ONLY",
        dry_run_days=5,
        dry_run_required=10,
        throttle_meta={"gate_allowed": False, "block_reason": "gate YELLOW"},
    )
    assert report["executable_count"] == 0
    for row in report["rows"]:
        assert row["execution_status"] == "blocked"
        assert row["executable"] is False


def test_kr_alpha_reduce_only() -> None:
    market = load_market_indicators(DATA / "market_indicators.csv")
    rules = load_trigger_rules(DATA / "trigger_rules.yaml")
    positions = load_positions(DATA / "positions.csv")
    targets = load_target_portfolio(DATA / "target_portfolio.csv")
    gap_rows = compute_gaps(positions, targets)
    alerts = evaluate_triggers(market, rules)

    report = build_asset_accumulation_timing(
        data_dir=DATA,
        output_dir=OUT,
        market=market,
        alerts=alerts,
        rules=rules,
        gap_rows=gap_rows,
        data_gate="GREEN",
        execution_scope="ETF_ONLY_ALPHA_REVIEW",
        dry_run_days=10,
        dry_run_required=10,
        throttle_meta={"gate_allowed": True, "limits": {"per_trade_max_pct": 3.0}, "usage": {"weekly_remaining_pct": 5.0}},
    )
    alpha = next(r for r in report["rows"] if r["asset_group"] == "kr_alpha")
    assert alpha["timing_status"] == "ReduceOnly"
    assert alpha["executable"] is False
    assert alpha["max_buy_pct_after_throttle"] == 0.0


def test_ar21_input_quality_fields() -> None:
    market = load_market_indicators(DATA / "market_indicators.csv")
    rules = load_trigger_rules(DATA / "trigger_rules.yaml")
    positions = load_positions(DATA / "positions.csv")
    targets = load_target_portfolio(DATA / "target_portfolio.csv")
    gap_rows = compute_gaps(positions, targets)
    alerts = evaluate_triggers(market, rules)

    report = build_asset_accumulation_timing(
        data_dir=DATA,
        output_dir=OUT,
        market=market,
        alerts=alerts,
        rules=rules,
        gap_rows=gap_rows,
        data_gate="YELLOW",
        execution_scope="ETF_ONLY",
        dry_run_days=5,
        dry_run_required=10,
        throttle_meta={"gate_allowed": False},
    )
    assert report.get("phase") == "AR-2.1"
    assert "ar21_qa" in report
    assert report["ar21_qa"]["all_execution_blocked"] is True
    for row in report["rows"]:
        assert "input_quality" in row
        assert "stale_inputs" in row
        assert "timing_execution_note" in row
        if row.get("timing_status") in {"Watch", "Ready"}:
            assert "≠ Buy" in row["timing_execution_note"]
    duration = next(r for r in report["rows"] if r["asset_group"] == "duration_bond")
    assert "duration_components" in duration
    assert "duration_kr" in duration["duration_components"]
    assert "duration_us" in duration["duration_components"]


def test_ar21_ready_but_blocked_count() -> None:
    market = load_market_indicators(DATA / "market_indicators.csv")
    rules = load_trigger_rules(DATA / "trigger_rules.yaml")
    positions = load_positions(DATA / "positions.csv")
    targets = load_target_portfolio(DATA / "target_portfolio.csv")
    gap_rows = compute_gaps(positions, targets)
    alerts = evaluate_triggers(market, rules)

    report = build_asset_accumulation_timing(
        data_dir=DATA,
        output_dir=OUT,
        market=market,
        alerts=alerts,
        rules=rules,
        gap_rows=gap_rows,
        data_gate="YELLOW",
        execution_scope="NO_TRADE",
        dry_run_days=5,
        dry_run_required=10,
        throttle_meta={"gate_allowed": False},
    )
    qa = report["ar21_qa"]
    assert qa["ready_but_blocked_count"] + qa["watch_but_blocked_count"] >= 0
    assert report["executable_count"] == 0


def test_writes_outputs(tmp_path: Path) -> None:
    market = load_market_indicators(DATA / "market_indicators.csv")
    rules = load_trigger_rules(DATA / "trigger_rules.yaml")
    positions = load_positions(DATA / "positions.csv")
    targets = load_target_portfolio(DATA / "target_portfolio.csv")
    gap_rows = compute_gaps(positions, targets)
    alerts = evaluate_triggers(market, rules)

    out = tmp_path / "outputs"
    out.mkdir()
    (out / "portfolio_gap.csv").write_text(
        (OUT / "portfolio_gap.csv").read_text(encoding="utf-8-sig"),
        encoding="utf-8-sig",
    )

    report = write_asset_accumulation_timing(
        data_dir=DATA,
        output_dir=out,
        market=market,
        alerts=alerts,
        rules=rules,
        gap_rows=gap_rows,
        data_gate="RED",
        execution_scope="NO_TRADE",
        dry_run_days=5,
    )
    assert (out / "asset_accumulation_timing.json").exists()
    assert (out / "asset_accumulation_timing.csv").exists()
    assert report["disclaimer"] == AR2_DISCLAIMER
    loaded = json.loads((out / "ar2_accumulation_timing_report.json").read_text(encoding="utf-8"))
    assert loaded["mode"] == "shadow_timing_only"
