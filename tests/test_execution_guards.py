from __future__ import annotations

from src.execution_guards import build_hard_stops_detail
from src.risk_limits import RiskReport, RiskViolation


def test_hard_stops_detail_splits_risk_and_policy():
    risk = RiskReport(
        violations=[
            RiskViolation("KR_ALPHA_MAX", None, "kr_alpha 46% > 35%", "HARD"),
        ],
        hard_stop_count=1,
    )
    detail = build_hard_stops_detail(
        risk,
        execution_scope="ETF_ONLY_ALPHA_REVIEW",
        dry_run_days=2,
    )
    assert detail["risk_hard_stop_count"] == 1
    assert detail["risk_hard_stops"][0]["code"] == "KR_ALPHA_MAX"
    assert "dry_run_incomplete" in detail["policy_guards"]
    assert "alpha_new_buy_blocked" in detail["policy_guards"]
