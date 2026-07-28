from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.operational_gate import CRITICAL_HEALTH_NAMES, gate_from_health_checks, operational_overall_status
from src.validation.system_health import HealthCheck
from src.validation.tier_a_price_coverage import (
    AlphaPriceGateResult,
    apply_alpha_price_gate_to_data_gate,
    evaluate_tier_a_price_coverage,
    evaluate_tier_b_refresh_health,
)


def _write_prices(tmp_path: Path, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_csv(tmp_path / "prices.csv", index=False)


def _minimal_core_files(data: Path, out: Path) -> None:
    pd.DataFrame([
        {
            "ticker": "005830", "name": "DB손해보험", "asset_group": "kr_alpha",
            "sector": "insurance", "style": "", "quantity": "1", "current_value": "1000",
            "avg_price": "", "current_price": "100",
        },
    ]).to_csv(data / "positions.csv", index=False)
    pd.DataFrame([
        {
            "ticker": "005830", "name": "DB손해보험", "asset_group": "kr_alpha",
            "target_weight": "2", "min_weight": "0", "max_weight": "5",
            "sector": "insurance", "role": "",
        },
    ]).to_csv(data / "target_portfolio.csv", index=False)


def test_tier_a_gate_pass_core_100(tmp_path):
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _minimal_core_files(data, out)
    pd.DataFrame([
        {"ticker": "005830", "name": "DB손해보험", "rank": "1"},
    ]).to_csv(out / "alpha_shortlist.csv", index=False)
    _write_prices(data, [{"date": "2026-06-24", "ticker": "005830", "close": "100"}])

    result = evaluate_tier_a_price_coverage(data, out, "2026-06-24")
    assert result.core.status == "pass"
    assert result.alpha.status == "pass"
    assert result.alpha.action == "ALPHA_OK"


def test_tier_a_gate_fail_trade_actions_missing(tmp_path):
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _minimal_core_files(data, out)
    pd.DataFrame([
        {"ticker": "005830", "action": "Trim"},
        {"ticker": "999999", "action": "Buy"},
    ]).to_csv(out / "trade_actions.csv", index=False)
    _write_prices(data, [{"date": "2026-06-24", "ticker": "005830", "close": "100"}])

    result = evaluate_tier_a_price_coverage(data, out, "2026-06-24")
    assert result.core.status == "fail"
    assert "999999" in result.missing_trade_actions


def test_alpha_gate_warn_core_pass(tmp_path):
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _minimal_core_files(data, out)

    shortlist = [{"ticker": "005830", "name": "DB손해보험", "rank": "1"}]
    shortlist += [{"ticker": f"{i:06d}", "name": f"T{i}", "rank": str(i + 1)} for i in range(1, 10)]
    pd.DataFrame(shortlist).to_csv(out / "alpha_shortlist.csv", index=False)

    price_rows = [{"date": "2026-06-24", "ticker": "005830", "close": "100"}]
    price_rows += [{"date": "2026-06-24", "ticker": f"{i:06d}", "close": "100"} for i in range(1, 7)]
    _write_prices(data, price_rows)

    result = evaluate_tier_a_price_coverage(data, out, "2026-06-24")
    assert result.core.status == "pass"
    assert result.alpha.status == "warn"
    assert result.alpha.action == "ALPHA_REVIEW_ONLY"
    assert result.alpha.alpha_top30_coverage == 0.7


def test_alpha_gate_fail_does_not_critical_red():
    checks = [
        HealthCheck("alpha", "core_price_gate", "pass", "ok"),
        HealthCheck("alpha", "alpha_price_gate", "fail", "top30 low"),
    ]
    assert "core_price_gate" in CRITICAL_HEALTH_NAMES
    assert "alpha_price_gate" not in CRITICAL_HEALTH_NAMES
    assert gate_from_health_checks(checks) == "YELLOW"
    assert operational_overall_status(checks) == "warn"


def test_core_gate_fail_is_red():
    checks = [
        HealthCheck("alpha", "core_price_gate", "fail", "trade missing"),
        HealthCheck("alpha", "alpha_price_gate", "pass", "ok"),
    ]
    assert gate_from_health_checks(checks) == "RED"


def test_apply_alpha_price_gate_downgrades_to_yellow():
    alpha = AlphaPriceGateResult(
        status="fail",
        action="ALPHA_DISABLED",
        alpha_top30_coverage=0.5,
        alpha_top50_coverage=0.5,
    )
    assert apply_alpha_price_gate_to_data_gate("GREEN", alpha) == "YELLOW"
    assert apply_alpha_price_gate_to_data_gate("GREEN", AlphaPriceGateResult(
        status="warn", action="ALPHA_REVIEW_ONLY",
        alpha_top30_coverage=0.75, alpha_top50_coverage=0.7,
    )) == "YELLOW"


def test_system_health_split_gates(tmp_path):
    from src.validation.system_health import run_system_health

    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _minimal_core_files(data, out)
    _write_prices(data, [{"date": "2026-06-24", "ticker": "005830", "close": "100"}])

    report = run_system_health(data, out, as_of="2026-06-24")
    names = {c.name for c in report.checks}
    assert "core_price_gate" in names
    assert "alpha_price_gate" in names
    assert "tier_b_refresh" in names
    assert (out / "price_coverage_report.json").exists()
    detail = json.loads((out / "price_coverage_report.json").read_text(encoding="utf-8"))
    assert "core_price_gate" in detail
    assert "alpha_price_gate" in detail


def test_tier_a_gate_pass_when_snapshot_date_after_as_of(tmp_path):
    """Snapshot prices stamped after market.as_of still count for coverage."""
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _minimal_core_files(data, out)
    _write_prices(data, [{"date": "2026-06-29", "ticker": "005830", "close": "100"}])

    result = evaluate_tier_a_price_coverage(data, out, "2026-06-26")
    assert result.core.held_coverage == 1.0
    assert result.core.target_coverage == 1.0
    assert result.core.status == "pass"


def test_tier_b_refresh_health_warn_when_stale(tmp_path):
    from src.data_refresh.tier_b_refresh import write_tier_b_state

    data = tmp_path / "data"
    data.mkdir()
    write_tier_b_state(data, "2026-06-01", prices_count=300)
    status, msg, _ = evaluate_tier_b_refresh_health(data, "2026-06-24")
    assert status == "warn"
    assert "Tier B" in msg
