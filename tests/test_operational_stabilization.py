from __future__ import annotations

from src.execution_permissions import build_execution_permissions
from src.models import MarketIndicators
from src.policy_cap import (
    apply_policy_cap_to_approval,
    derive_technical_system_status,
    resolve_policy_cap,
)
from src.trigger_reviews import build_kospi_trigger_reviews
from src.config import load_trigger_rules
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_expired_policy_cap_stays_active_yellow():
    market = MarketIndicators(
        date="2026-09-25",
        regime="YELLOW_STABLE",
        regime_override_reason="BOK FSR Jun-2026",
        regime_expires_date="2026-09-24",
    )
    cap = resolve_policy_cap(
        market,
        technical_scope="FULL_WITH_ALPHA",
        data_gate="GREEN",
        health_gate="GREEN",
    )
    assert cap.active is True
    assert cap.is_expired is True
    assert cap.expiry_status == "EXPIRED_REVIEW_REQUIRED"
    assert cap.capped_execution_scope == "ETF_ONLY"
    assert apply_policy_cap_to_approval("GREEN", cap) == "YELLOW"


def test_policy_permissions_under_yellow_stable_cap():
    perms = build_execution_permissions(
        execution_scope="ETF_ONLY",
        alpha_trade_permission="BLOCK_NEW_BUY",
        alpha_position_action="RISK_REDUCE_ONLY",
        alpha_price_action="ALPHA_OK",
        restricted_modes=[],
        health_gate="GREEN",
        core_price_gate_status="pass",
        alpha_price_gate_status="pass",
        data_gate="GREEN",
        portfolio_gate="GREEN",
        alpha_gate="GREEN",
        policy_cap_active=True,
        max_operational_approval="YELLOW",
        cap_regime="YELLOW_STABLE",
    )
    assert perms["operating_mode"] == "YELLOW"
    pp = perms["policy_permissions"]
    assert pp["etf_chase_buy"] == "BLOCKED"
    assert pp["etf_new_buy"] == "REVIEW_ONLY"
    assert pp["kr_alpha_new_buy"] == "BLOCKED"


def test_kospi_trigger_review_json_gated():
    market = MarketIndicators(
        date="2026-06-24",
        kospi=8471,
        kospi_recent_high=9114,
        regime="YELLOW_STABLE",
    )
    rules = load_trigger_rules(ROOT / "data" / "trigger_rules.yaml")
    reviews = build_kospi_trigger_reviews(
        market, rules, dry_run_days=3,
    )
    active = [r for r in reviews if r.get("signal_detected")]
    assert active
    assert active[0]["review_status"] == "GATED"
    assert "dry_run_days" in active[0]["gated_reasons"][0]


def test_technical_vs_operational_green_split():
    tech = derive_technical_system_status(
        data_gate="GREEN",
        health_gate="GREEN",
        portfolio_gate="GREEN",
        technical_scope="FULL_WITH_ALPHA",
    )
    assert tech == "GREEN"
    market = MarketIndicators(
        date="2026-06-24",
        regime="YELLOW_STABLE",
        regime_expires_date="2026-09-24",
    )
    cap = resolve_policy_cap(market, technical_scope="FULL_WITH_ALPHA", data_gate="GREEN", health_gate="GREEN")
    assert apply_policy_cap_to_approval(tech, cap) == "YELLOW"
