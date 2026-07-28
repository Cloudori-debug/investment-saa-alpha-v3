from __future__ import annotations

from src.models import MarketIndicators
from src.policy_cap import apply_policy_cap_to_approval, resolve_policy_cap


def test_policy_cap_limits_full_with_alpha():
    market = MarketIndicators(
        date="2026-06-24",
        kospi=8471.0,
        kospi_recent_high=9114.0,
        vix=18.6,
        usdkrw=1540.0,
        regime="YELLOW_STABLE",
        regime_override_reason="BOK FSR Jun-2026: FSI 17.2 warning stage",
        regime_expires_date="2026-09-24",
    )
    cap = resolve_policy_cap(
        market,
        technical_scope="FULL_WITH_ALPHA",
        data_gate="GREEN",
        health_gate="GREEN",
    )
    assert cap.active is True
    assert cap.technical_execution_scope == "FULL_WITH_ALPHA"
    assert cap.capped_execution_scope == "ETF_ONLY"
    assert cap.max_operational_approval == "YELLOW"
    assert apply_policy_cap_to_approval("GREEN", cap) == "YELLOW"


def test_policy_cap_inactive_without_manual_regime():
    market = MarketIndicators(
        date="2026-06-24",
        regime="AUTO",
    )
    cap = resolve_policy_cap(
        market,
        technical_scope="FULL_WITH_ALPHA",
        data_gate="GREEN",
        health_gate="GREEN",
    )
    assert cap.active is False
    assert cap.capped_execution_scope == "FULL_WITH_ALPHA"
    assert apply_policy_cap_to_approval("GREEN", cap) == "GREEN"


def test_policy_cap_expired_manual_regime_without_computed_keeps_manual_key():
    """computed_regime 미전달 시(하위호환) — 만료여도 기존처럼 수동 키로 캡(버그 잔존 경로)."""
    market = MarketIndicators(
        date="2026-06-25",
        regime="YELLOW_STABLE",
        regime_expires_date="2026-06-01",
    )
    cap = resolve_policy_cap(
        market,
        technical_scope="FULL_WITH_ALPHA",
        data_gate="GREEN",
        health_gate="GREEN",
    )
    assert cap.active is True
    assert cap.expiry_status == "EXPIRED_REVIEW_REQUIRED"
    assert cap.capped_execution_scope == "ETF_ONLY"


def test_policy_cap_expired_falls_back_to_computed_crisis():
    """만료 + computed=CRISIS → regime_engine과 같이 NO_TRADE로 수렴."""
    market = MarketIndicators(
        date="2026-09-25",
        kospi=7000.0,
        kospi_recent_high=9114.0,
        regime="YELLOW_STABLE",
        regime_override_reason="BOK FSR",
        regime_expires_date="2026-09-24",
    )
    cap = resolve_policy_cap(
        market,
        technical_scope="FULL_WITH_ALPHA",
        data_gate="GREEN",
        health_gate="GREEN",
        computed_regime="CRISIS",
    )
    assert cap.is_expired is True
    assert cap.expiry_status == "EXPIRED_REVIEW_REQUIRED"
    assert cap.cap_regime == "CRISIS"
    assert cap.cap_source == "computed_after_manual_expiry"
    assert cap.max_execution_scope == "NO_TRADE"
    assert cap.capped_execution_scope == "NO_TRADE"
    assert cap.max_operational_approval == "RED"
    # 자동 해제 아님 — 수동 CSV regime는 그대로 남아 있어도 캡만 컴퓨티드 기준
    assert market.regime == "YELLOW_STABLE"


def test_policy_cap_active_unexpired_ignores_computed():
    """만료 전: computed가 CRISIS여도 수동 YELLOW 캡(ETF_ONLY) 유지."""
    market = MarketIndicators(
        date="2026-07-14",
        regime="YELLOW_STABLE",
        regime_override_reason="BOK FSR",
        regime_expires_date="2026-09-24",
    )
    cap = resolve_policy_cap(
        market,
        technical_scope="FULL_WITH_ALPHA",
        data_gate="GREEN",
        health_gate="GREEN",
        computed_regime="CRISIS",
    )
    assert cap.is_expired is False
    assert cap.cap_regime == "YELLOW_STABLE"
    assert cap.capped_execution_scope == "ETF_ONLY"
    assert cap.cap_source == "manual_regime"


def test_fsr_policy_permissions_caution_matches_yellow():
    from src.policy_cap import fsr_policy_permissions

    yellow = fsr_policy_permissions("YELLOW_STABLE")
    caution = fsr_policy_permissions("CAUTION")
    assert caution == yellow
    assert caution.get("etf_chase_buy") == "BLOCKED"
    assert caution.get("kr_alpha_new_buy") == "BLOCKED"
    assert fsr_policy_permissions("CRISIS") == {}
