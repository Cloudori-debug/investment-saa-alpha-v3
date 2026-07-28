"""Acceptance Check A–F — core/alpha price gate 운용 분리 검증."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.action_planner import plan_actions
from src.execution_scope import apply_execution_scope_to_actions, derive_execution_scope
from src.models import GapRow
from src.risk_limits import RiskReport
from src.operational_gate import (
    apply_alpha_price_action_to_permissions,
    gate_from_health_checks,
    operational_overall_status,
    restricted_modes_from_checks,
)
from src.validation.system_health import HealthCheck
from src.validation.tier_a_price_coverage import evaluate_tier_a_price_coverage


def _write_prices(data: Path, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_csv(data / "prices.csv", index=False)


def _positions(data: Path) -> None:
    pd.DataFrame([
        {
            "ticker": "005830", "name": "DB손해보험", "asset_group": "kr_alpha",
            "sector": "insurance", "style": "", "quantity": "1", "current_value": "1000",
            "avg_price": "", "current_price": "100",
        },
        {
            "ticker": "157450", "name": "TIGER 단기통안채", "asset_group": "cash_short_bond",
            "sector": "bond", "style": "", "quantity": "1", "current_value": "5000",
            "avg_price": "", "current_price": "100",
        },
    ]).to_csv(data / "positions.csv", index=False)


def _targets(data: Path) -> None:
    pd.DataFrame([
        {
            "ticker": "005830", "name": "DB손해보험", "asset_group": "kr_alpha",
            "target_weight": "5", "min_weight": "0", "max_weight": "10",
            "sector": "insurance", "role": "",
        },
        {
            "ticker": "157450", "name": "TIGER 단기통안채", "asset_group": "cash_short_bond",
            "target_weight": "30", "min_weight": "25", "max_weight": "40",
            "sector": "bond", "role": "",
        },
    ]).to_csv(data / "target_portfolio.csv", index=False)


def _checks_from_coverage(data: Path, out: Path, as_of: str) -> tuple[list[HealthCheck], object]:
    from src.data_refresh.tier_b_refresh import write_tier_b_state
    from src.validation.tier_a_price_coverage import evaluate_tier_b_refresh_health

    cov = evaluate_tier_a_price_coverage(data, out, as_of)
    tb_status, tb_msg, tb_detail = evaluate_tier_b_refresh_health(data, as_of)
    checks = [
        HealthCheck("alpha", "core_price_gate", cov.core.status, cov.core.reasons[0], cov.core.to_dict()),
        HealthCheck("alpha", "alpha_price_gate", cov.alpha.status, cov.alpha.reasons[0], cov.alpha.to_dict()),
        HealthCheck("alpha", "tier_b_refresh", tb_status, tb_msg, tb_detail),
    ]
    return checks, cov


def _simulate_trade_paths(
    checks: list[HealthCheck],
    *,
    portfolio_gate: str = "GREEN",
    alpha_gate: str = "GREEN",
) -> tuple[str, str, list, list]:
    health_gate = gate_from_health_checks(checks)
    data_gate = health_gate if portfolio_gate == "GREEN" and alpha_gate == "GREEN" else "YELLOW"
    if health_gate == "RED" or portfolio_gate == "RED":
        data_gate = "RED"

    scope = derive_execution_scope(
        data_gate=data_gate,
        portfolio_gate=portfolio_gate,
        alpha_data_gate=alpha_gate,
        health_gate=health_gate,
    )
    gaps = [
        GapRow(
            ticker="005830", name="DB손해보험", asset_group="kr_alpha",
            current_weight=10.0, target_weight=5.0, gap=-5.0,
            min_weight=0, max_weight=10, status="Overweight", in_target=True,
        ),
        GapRow(
            ticker="157450", name="TIGER", asset_group="cash_short_bond",
            current_weight=20.0, target_weight=30.0, gap=10.0,
            min_weight=25, max_weight=40, status="Underweight", in_target=True,
        ),
    ]
    risk = RiskReport(violations=[], hard_stop_count=0)
    actions = plan_actions(gaps, [], risk, data_gate, {}, execution_scope=scope)
    executable, _review = apply_execution_scope_to_actions(actions, gaps, scope)
    return health_gate, scope, actions, executable


def test_acceptance_a_core_missing_red(tmp_path):
    """A — 보유 가격 누락 → core fail → RED → NO_TRADE."""
    data, out = tmp_path / "data", tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _positions(data)
    _targets(data)
    _write_prices(data, [{"date": "2026-06-24", "ticker": "157450", "close": "100"}])

    checks, cov = _checks_from_coverage(data, out, "2026-06-24")
    assert cov.core.status == "fail"
    assert operational_overall_status(checks) == "fail"
    assert gate_from_health_checks(checks) == "RED"

    health_gate, scope, _, executable = _simulate_trade_paths(checks)
    assert health_gate == "RED"
    assert scope == "NO_TRADE"
    assert any(a.action == "No trade" for a in executable)


def test_acceptance_b_trade_action_stale_red(tmp_path):
    """B — trade_actions stale → core fail → RED."""
    data, out = tmp_path / "data", tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _positions(data)
    _targets(data)
    pd.DataFrame([{"ticker": "005830", "action": "Trim"}]).to_csv(out / "trade_actions.csv", index=False)
    _write_prices(data, [
        {"date": "2026-06-10", "ticker": "005830", "close": "90"},
        {"date": "2026-06-24", "ticker": "157450", "close": "100"},
    ])

    checks, cov = _checks_from_coverage(data, out, "2026-06-24")
    assert cov.core.status == "fail"
    assert any(s["ticker"] == "005830" for s in cov.core.stale_core)
    assert gate_from_health_checks(checks) == "RED"


def test_acceptance_c_alpha_top30_low_yellow_etf_ok(tmp_path):
    """C — Alpha top30 55% → YELLOW, ETF 허용, Alpha buy 차단."""
    data, out = tmp_path / "data", tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _positions(data)
    _targets(data)
    shortlist = [{"ticker": "005830", "rank": "1"}]
    shortlist += [{"ticker": f"{i:06d}", "rank": str(i + 1)} for i in range(1, 20)]
    pd.DataFrame(shortlist).to_csv(out / "alpha_shortlist.csv", index=False)
    prices = [{"date": "2026-06-24", "ticker": "005830", "close": "100"},
              {"date": "2026-06-24", "ticker": "157450", "close": "100"}]
    prices += [{"date": "2026-06-24", "ticker": f"{i:06d}", "close": "100"} for i in range(1, 11)]
    _write_prices(data, prices)

    checks, cov = _checks_from_coverage(data, out, "2026-06-24")
    assert cov.core.status == "pass"
    assert cov.alpha.status == "fail"
    assert cov.alpha.action == "ALPHA_DISABLED"
    assert operational_overall_status(checks) == "warn"
    assert gate_from_health_checks(checks) == "YELLOW"
    assert "ALPHA_DISABLED" in restricted_modes_from_checks(checks)

    health_gate, scope, actions, executable = _simulate_trade_paths(checks, alpha_gate="YELLOW")
    assert health_gate == "YELLOW"
    assert scope == "ETF_ONLY"
    kr_actions = [a for a in actions if a.ticker == "005830"]
    assert kr_actions and kr_actions[0].action in {"Wait", "Trim", "Review-only"}
    assert not any(a.action == "Buy-allowed" and a.ticker == "005830" for a in executable)
    bond = [a for a in executable if a.ticker == "157450"]
    assert bond and bond[0].action != "No trade"


def test_acceptance_d_alpha_top30_review_only(tmp_path):
    """D — Alpha top30 70% → REVIEW_ONLY, YELLOW."""
    data, out = tmp_path / "data", tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _positions(data)
    _targets(data)
    shortlist = [{"ticker": "005830", "rank": "1"}]
    shortlist += [{"ticker": f"{i:06d}", "rank": str(i + 1)} for i in range(1, 10)]
    pd.DataFrame(shortlist).to_csv(out / "alpha_shortlist.csv", index=False)
    prices = [{"date": "2026-06-24", "ticker": "005830", "close": "100"},
              {"date": "2026-06-24", "ticker": "157450", "close": "100"}]
    prices += [{"date": "2026-06-24", "ticker": f"{i:06d}", "close": "100"} for i in range(1, 7)]
    _write_prices(data, prices)

    checks, cov = _checks_from_coverage(data, out, "2026-06-24")
    assert cov.alpha.status == "warn"
    assert cov.alpha.action == "ALPHA_REVIEW_ONLY"
    perm, pos = apply_alpha_price_action_to_permissions("ALPHA_REVIEW_ONLY", "ALLOW_NEW", "EXECUTABLE")
    assert perm == "BLOCK_NEW_BUY"
    assert pos == "REVIEW_ONLY"


def test_acceptance_e_tier_b_stale_warn_no_block(tmp_path):
    """E — Tier B 15영업일+ → WARN, 실행 차단 없음."""
    from src.data_refresh.tier_b_refresh import write_tier_b_state

    data, out = tmp_path / "data", tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _positions(data)
    _targets(data)
    write_tier_b_state(data, "2026-06-01", prices_count=300)
    _write_prices(data, [
        {"date": "2026-06-24", "ticker": "005830", "close": "100"},
        {"date": "2026-06-24", "ticker": "157450", "close": "100"},
    ])

    checks, _ = _checks_from_coverage(data, out, "2026-06-24")
    tb = next(c for c in checks if c.name == "tier_b_refresh")
    assert tb.status == "warn"
    assert operational_overall_status(checks) == "warn"
    assert gate_from_health_checks(checks) == "YELLOW"
    _, scope, _, _ = _simulate_trade_paths(checks)
    assert scope != "NO_TRADE"
    assert "RESEARCH_QUALITY_WARN" in restricted_modes_from_checks(checks)


def test_acceptance_f_all_pass_green_or_yellow_stable(tmp_path):
    """F — core/alpha pass → GREEN (tier_b pass 시)."""
    from src.data_refresh.tier_b_refresh import write_tier_b_state

    data, out = tmp_path / "data", tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _positions(data)
    _targets(data)
    pd.DataFrame([{"ticker": "005830", "rank": "1"}]).to_csv(out / "alpha_shortlist.csv", index=False)
    write_tier_b_state(data, "2026-06-23", prices_count=300)
    _write_prices(data, [
        {"date": "2026-06-24", "ticker": "005830", "close": "100"},
        {"date": "2026-06-24", "ticker": "157450", "close": "100"},
    ])

    checks, cov = _checks_from_coverage(data, out, "2026-06-24")
    assert cov.core.status == "pass"
    assert cov.alpha.status == "pass"
    assert operational_overall_status(checks) == "pass"
    assert gate_from_health_checks(checks) == "GREEN"
