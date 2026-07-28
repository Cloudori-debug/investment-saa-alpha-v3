from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.decision.shadow_diagnostic import (
    EXECUTION_AUTHORITY,
    SHADOW_MODE,
    append_ops_shadow_log,
    build_daily_report_shadow_section,
    build_shadow_diagnostic,
    collect_blocked_by,
    compute_reviewable_amount_krw,
    derive_dip_ladder_stage,
    write_shadow_diagnostic,
)
from src.models import GapRow, MarketIndicators, TradeAction, TriggerAlert, TriggerStatus


def test_collect_blocked_by_dry_run_and_policy_cap() -> None:
    blocked = collect_blocked_by(
        data_gate="YELLOW",
        health_gate="GREEN",
        portfolio_gate="GREEN",
        alpha_gate="GREEN",
        execution_scope="ETF_ONLY",
        core_price_gate="pass",
        dry_run_days=3,
        dry_run_required=10,
        policy_cap_active=True,
        cap_regime="YELLOW_STABLE",
        alpha_trade_permission="BLOCK_NEW_BUY",
        stop_buy=False,
        systemic_stress=False,
    )
    assert "dry_run" in blocked
    assert "policy_cap" in blocked
    assert "execution_scope_etf_only" in blocked
    assert "alpha_trade_blocked" in blocked


def test_dip_ladder_stages() -> None:
    assert derive_dip_ladder_stage(-3.0, systemic_stress=False)[0] == "WATCH"
    assert derive_dip_ladder_stage(-8.0, systemic_stress=False)[0] == "L1"
    assert derive_dip_ladder_stage(-12.0, systemic_stress=False)[0] == "L2"
    assert derive_dip_ladder_stage(-18.0, systemic_stress=False)[0] == "L3"
    assert derive_dip_ladder_stage(-25.0, systemic_stress=False)[0] == "L4"
    assert derive_dip_ladder_stage(-12.0, systemic_stress=True)[0] == "INACTIVE"


def test_reviewable_zero_on_red_data_gate() -> None:
    amount = compute_reviewable_amount_krw(
        portfolio_value=100_000_000,
        cash_short_target_pct=40.0,
        dip_stage="L2",
        systemic_stress=False,
        blocked_by=["data_gate_red"],
    )
    assert amount == 0


def test_shadow_diagnostic_signal_execution_mismatch(tmp_path: Path) -> None:
    market = MarketIndicators(
        date="2026-06-19",
        kospi=2400,
        kospi_recent_high=2700,
        regime="YELLOW_STABLE",
    )
    gap_rows = [
        GapRow(
            ticker="069500",
            name="KODEX200",
            asset_group="domestic_beta",
            current_weight=8.0,
            target_weight=10.0,
            gap=2.0,
            min_weight=5.0,
            max_weight=15.0,
            status="Underweight",
            in_target=True,
        ),
    ]
    alerts = [
        TriggerAlert(
            key="kospi_pullback",
            label="KOSPI Pullback",
            status=TriggerStatus.ACTIVE,
            detail="test",
        ),
    ]
    theoretical = [
        TradeAction(
            ticker="069500",
            name="KODEX200",
            action="Buy-allowed",
            reason="theoretical",
            allowed_size_pct=2.0,
            priority="Medium",
        ),
    ]
    actions: list[TradeAction] = []

    class Pos:
        current_value = 100_000_000

    doc = build_shadow_diagnostic(
        run_id="test-run",
        as_of="2026-06-19",
        market=market,
        positions=[Pos()],
        gap_rows=gap_rows,
        alerts=alerts,
        actions=actions,
        theoretical_actions=theoretical,
        rules={},
        data_gate="YELLOW",
        health_gate="GREEN",
        portfolio_gate="YELLOW",
        alpha_gate="GREEN",
        execution_scope="NO_TRADE",
        core_price_gate="pass",
        dry_run_days=5,
        policy_cap={"active": True, "cap_regime": "YELLOW_STABLE"},
        alpha_trade_permission="BLOCK_NEW_BUY",
        operational_status="YELLOW",
    )

    assert doc["mode"] == SHADOW_MODE
    assert doc["execution_authority"] == EXECUTION_AUTHORITY
    assert doc["observations"]["signal_execution_mismatch"] is True
    assert doc["amounts"]["actual_allowed_krw"] == 0
    assert doc["amounts"]["theoretical_gap_krw"] > 0
    assert "dry_run" in doc["execution"]["blocked_by"]
    assert doc["execution"]["primary_blocker"] == "execution_scope_no_trade"
    assert "performance" in doc

    out = tmp_path / "shadow_diagnostic.json"
    write_shadow_diagnostic(out, doc)
    assert out.exists()

    log = tmp_path / "ops_shadow_log.csv"
    append_ops_shadow_log(log, doc)
    assert log.exists()
    text = log.read_text(encoding="utf-8-sig")
    assert "2026-06-19" in text
    assert "dry_run" in text

    lines = build_daily_report_shadow_section(out)
    assert any("Shadow 진단" in line for line in lines)
    assert any("SAA baseline" in line for line in lines)


def test_shadow_report_section_missing_file() -> None:
    assert build_daily_report_shadow_section(Path("/nonexistent/shadow.json")) == []
