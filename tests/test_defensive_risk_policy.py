from __future__ import annotations

from src.action_planner import plan_actions
from src.execution_scope import apply_execution_scope_to_actions
from src.models import GapRow, PositionRow, TradeAction
from src.risk_limits import RiskReport, RiskViolation, check_risk_limits


def _position(ticker: str, group: str, sector: str, value: float) -> PositionRow:
    return PositionRow(
        ticker=ticker,
        name=ticker,
        asset_group=group,
        sector=sector,
        quantity=1,
        current_value=value,
    )


def test_defensive_overweight_is_warn_not_hard():
    positions = [
        _position("157450", "cash_short_bond", "bond", 300_000),
        _position("CASH", "cash_short_bond", "cash", 700_000),
    ]
    policy = {
        "risk_limits": {
            "single_stock_hard_max": 15,
            "single_stock_normal_max": 8,
            "sector_max": 30,
            "kr_alpha_max": 35,
            "cash_short_bond_min": 25,
        },
        "execution_policy": {"cash_short_bond_hard_stop_action": "park"},
    }
    risk = check_risk_limits(positions, [], policy)
    codes = [v.code for v in risk.violations]
    assert "DEFENSIVE_OVERWEIGHT" in codes
    assert "SINGLE_HARD_MAX" not in codes
    assert risk.hard_stop_count == 0


def test_kr_alpha_risk_trim_executable_under_etf_only():
    gaps = [
        GapRow(
            ticker="192400",
            name="DB",
            asset_group="kr_alpha",
            current_weight=26.0,
            target_weight=4.0,
            gap=-22.0,
            min_weight=0,
            max_weight=8,
            status="Overweight",
            in_target=True,
        ),
    ]
    risk = RiskReport(
        violations=[
            RiskViolation("SINGLE_HARD_MAX", "192400", "26% > 15%", "HARD"),
            RiskViolation("KR_ALPHA_MAX", None, "40% > 35%", "HARD"),
        ],
        hard_stop_count=2,
    )
    rules = {"position_triggers": {"trim_if_target_overweight_ppt": 5}}
    exec_policy = {"kr_alpha_risk_trim_under_etf_only": True}
    raw = plan_actions(
        gaps,
        [],
        risk,
        "YELLOW",
        rules,
        execution_scope="ETF_ONLY",
        execution_policy=exec_policy,
    )
    trim = next(a for a in raw if a.ticker == "192400")
    assert trim.action == "Trim"
    assert "리스크 축소" in trim.reason

    executable, review = apply_execution_scope_to_actions(
        raw, gaps, "ETF_ONLY", execution_policy=exec_policy,
    )
    exe = next(a for a in executable if a.ticker == "192400")
    assert exe.action == "Trim"
    assert exe.allowed_size_pct < 0
