from __future__ import annotations

from src.operational_checklist import regime_expiry_check


def test_regime_expiry_pass_when_three_plus_days():
    assert regime_expiry_check("2026-06-24", "2026-07-01")[0] == "pass"


def test_regime_expiry_warn_when_one_day_left():
    assert regime_expiry_check("2026-06-23", "2026-06-24")[0] == "warn"


def test_regime_expiry_fail_when_past():
    assert regime_expiry_check("2026-06-25", "2026-06-24")[0] == "fail"
