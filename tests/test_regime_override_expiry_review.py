"""Override expiry review — early triggers + AC-05 age escalation."""

from __future__ import annotations

import json
from pathlib import Path

from src.models import MarketIndicators
from src.policy_cap import resolve_policy_cap
from src.validation.acceptance_check import (
    _check_regime_early_review,
    _check_regime_override,
)
from src.validation.regime_override_divergence import (
    assess_early_regime_review,
    kospi_drawdown_pct,
)


def test_kospi_drawdown_pct():
    assert kospi_drawdown_pct(75.0, 100.0) == -25.0


def test_early_review_worsening_warns():
    a = assess_early_regime_review(
        override_active=True,
        regime_set_date="2026-06-24",
        current_drawdown_pct=-30.0,
        set_date_drawdown_pct=-20.0,
        worsening_delta_pct=-5.0,
        recovery_threshold_pct=-15.0,
    )
    assert a.status == "warn"
    assert a.trigger == "worsening"
    assert "추가 악화" in a.message
    assert "자동 변경 없음" in a.message


def test_early_review_recovery_info_not_auto_ease():
    a = assess_early_regime_review(
        override_active=True,
        regime_set_date="2026-06-24",
        current_drawdown_pct=-10.0,
        set_date_drawdown_pct=-20.0,
        worsening_delta_pct=-5.0,
        recovery_threshold_pct=-15.0,
    )
    assert a.status == "info"
    assert a.trigger == "recovery"
    assert "완화 검토 후보" in a.message
    assert "자동 완화 아님" in a.message
    # policy_cap 값은 이 함수가 건드리지 않음 — 호출부에서 별도 검증


def test_early_review_recovery_does_not_change_policy_cap():
    market = MarketIndicators(
        date="2026-07-14",
        kospi=8200.0,
        kospi_recent_high=9114.0,
        regime="YELLOW_STABLE",
        regime_override_reason="BOK FSR",
        regime_expires_date="2026-09-24",
    )
    before = resolve_policy_cap(
        market,
        technical_scope="FULL_WITH_ALPHA",
        data_gate="GREEN",
        health_gate="GREEN",
        computed_regime="CRISIS",
    )
    assess_early_regime_review(
        override_active=True,
        regime_set_date="2026-06-24",
        current_drawdown_pct=-10.0,
        set_date_drawdown_pct=-20.0,
    )
    after = resolve_policy_cap(
        market,
        technical_scope="FULL_WITH_ALPHA",
        data_gate="GREEN",
        health_gate="GREEN",
        computed_regime="CRISIS",
    )
    assert before.capped_execution_scope == after.capped_execution_scope == "ETF_ONLY"
    assert before.cap_regime == after.cap_regime == "YELLOW_STABLE"


def test_ac05_age_escalation_message(tmp_path: Path):
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    (out / "compass_regime.json").write_text(
        json.dumps(
            {
                "computed_regime": "CRISIS",
                "applied_regime": "YELLOW_STABLE",
                "override": {"active": True, "reason": "BOK FSR"},
            }
        ),
        encoding="utf-8",
    )
    # 6영업일: set Mon 2026-06-01 → as_of Tue 2026-06-09 = 6 business days
    (data / "market_indicators.csv").write_text(
        "date,regime,regime_set_date,regime_expires_date,regime_override_reason,"
        "kospi,kospi_recent_high,kospi_200ma,vix,usdkrw\n"
        "2026-06-09,YELLOW_STABLE,2026-06-01,2026-09-24,test,"
        "8000,9000,7500,15,1300\n",
        encoding="utf-8-sig",
    )
    item6 = _check_regime_override(data, out, as_of="2026-06-09")
    assert item6.id == "AC-05"
    assert item6.status == "warn"
    assert "장기 미검토" not in item6.message
    assert "갱신 또는 만료" in item6.message

    # 16영업일: 2026-06-01 → 2026-06-23
    (data / "market_indicators.csv").write_text(
        "date,regime,regime_set_date,regime_expires_date,regime_override_reason,"
        "kospi,kospi_recent_high,kospi_200ma,vix,usdkrw\n"
        "2026-06-23,YELLOW_STABLE,2026-06-01,2026-09-24,test,"
        "8000,9000,7500,15,1300\n",
        encoding="utf-8-sig",
    )
    item16 = _check_regime_override(data, out, as_of="2026-06-23")
    assert item16.status == "warn"
    assert "장기 미검토" in item16.message
    assert item16.detail.get("escalated") is True


def test_ac05c_worsening_from_history(tmp_path: Path):
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    (out / "compass_regime.json").write_text(
        json.dumps({"override": {"active": True}, "computed_regime": "CRISIS", "applied_regime": "YELLOW_STABLE"}),
        encoding="utf-8",
    )
    # set_date 낙폭 -10%, 현재 -18% → Δ -8%p ≤ -5
    (data / "market_indicators_history.csv").write_text(
        "date,kospi,kospi_recent_high\n"
        "2026-06-24,9000,10000\n"
        "2026-07-14,8200,10000\n",
        encoding="utf-8",
    )
    (data / "market_indicators.csv").write_text(
        "date,regime,regime_set_date,regime_expires_date,regime_override_reason,"
        "kospi,kospi_recent_high,kospi_200ma,vix,usdkrw\n"
        "2026-07-14,YELLOW_STABLE,2026-06-24,2026-09-24,BOK FSR,"
        "8200,10000,7500,15,1300\n",
        encoding="utf-8-sig",
    )
    item = _check_regime_early_review(data, out)
    assert item.id == "AC-05c"
    assert item.status == "warn"
    assert item.detail.get("trigger") == "worsening"
