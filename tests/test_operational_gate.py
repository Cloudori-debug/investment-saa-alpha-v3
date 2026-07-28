from __future__ import annotations

from src.operational_gate import (
    CRITICAL_HEALTH_NAMES,
    explain_operational_gate,
    gate_from_health_checks,
    resolve_operational_gate,
)
from src.unified_data_gate import merge_data_gates


def test_gate_from_health_fail_on_target_weights():
    from src.validation.system_health import HealthCheck

    checks = [
        HealthCheck("portfolio", "target_weights", "fail", "target 합 85%"),
        HealthCheck("alpha", "prices_coverage", "pass", "ok"),
    ]
    assert gate_from_health_checks(checks) == "RED"


def test_gate_from_health_warn_only():
    from src.validation.system_health import HealthCheck

    checks = [
        HealthCheck("alpha", "fundamentals_quality", "warn", "결측"),
        HealthCheck("portfolio", "target_weights", "pass", "100%"),
    ]
    assert gate_from_health_checks(checks) == "YELLOW"


def test_resolve_operational_gate_merges_health_red():
    gate = resolve_operational_gate("GREEN", "GREEN", "RED", merge_alpha=True)
    assert gate == "RED"


def test_explain_operational_gate_health_yellow_lifts_base():
    detail = explain_operational_gate(
        "GREEN",
        "GREEN",
        "YELLOW",
        health_warns=["fundamentals_quality: 결측"],
    )
    assert detail["data_gate"] == "YELLOW"
    assert detail["base_gate"] == "GREEN"
    assert "health" in detail["summary"]
    assert any("fundamentals" in d for d in detail["drivers"])


def test_consolidate_duplicate_targets():
    from src.models import TargetRow
    from src.portfolio_gap import compute_gaps, consolidate_targets

    rows = [
        TargetRow(ticker="005830", name="A", asset_group="kr_alpha", sector="", role="", target_weight=4.0, min_weight=0, max_weight=10),
        TargetRow(ticker="005830", name="A", asset_group="kr_alpha", sector="", role="", target_weight=2.0, min_weight=0, max_weight=10),
    ]
    merged = consolidate_targets(rows)
    assert len(merged) == 1
    assert merged[0].target_weight == 6.0

    from src.models import PositionRow
    positions = [PositionRow(ticker="005830", name="A", asset_group="kr_alpha", sector="", style="", quantity=1, current_value=100, avg_price=0, current_price=0)]
    gaps = compute_gaps(positions, rows)
    assert gaps[0].target_weight == 6.0
