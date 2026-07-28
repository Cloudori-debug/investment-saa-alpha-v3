from __future__ import annotations

from pathlib import Path

from src.action_planner import plan_actions
from src.config import load_portfolio_policy, load_trigger_rules
from src.data_loader import load_market_indicators, load_positions, load_target_portfolio
from src.portfolio_gap import compute_gaps
from src.risk_limits import check_risk_limits
from src.trigger_engine import evaluate_triggers
from src.validators import validate_inputs

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def test_underweight_without_trigger_returns_wait():
    from src.models import GapRow

    gaps = [
        GapRow(
            ticker="069500",
            name="KODEX 200",
            asset_group="domestic_beta",
            current_weight=0.0,
            target_weight=11.0,
            gap=11.0,
            min_weight=6.0,
            max_weight=18.0,
            status="No position",
            in_target=True,
        )
    ]
    rules = load_trigger_rules(DATA / "trigger_rules.yaml")
    risk = check_risk_limits([], gaps, {"risk_limits": {}})
    actions = plan_actions(gaps, [], risk, "GREEN", rules)
    kodex = next(a for a in actions if a.ticker == "069500")
    assert kodex.action == "Wait"


def test_not_in_target_returns_replace():
    positions = load_positions(DATA / "positions.csv")
    targets = load_target_portfolio(DATA / "target_portfolio.csv")
    policy = load_portfolio_policy(DATA / "portfolio_policy.yaml")
    rules = load_trigger_rules(DATA / "trigger_rules.yaml")
    market = load_market_indicators(DATA / "market_indicators.csv")
    gaps = compute_gaps(positions, targets)
    risk = check_risk_limits(positions, gaps, policy)
    alerts = evaluate_triggers(market, rules)
    actions = plan_actions(gaps, alerts, risk, "GREEN", rules, execution_scope="FULL_WITH_ALPHA")
    holding = next(a for a in actions if a.ticker == "192400")
    assert holding.action == "Replace"


def test_data_red_blocks_trade():
    from src.models import GapRow

    gaps = [
        GapRow(
            ticker="X", name="X", asset_group="kr_alpha",
            current_weight=5, target_weight=4, gap=-1,
            min_weight=2, max_weight=6, status="Within band", in_target=True,
        )
    ]
    actions = plan_actions(gaps, [], check_risk_limits([], gaps, {"risk_limits": {}}), "RED", {})
    assert actions[0].action == "No trade"


def test_cash_overweight_parks_without_buy_trigger():
    positions = load_positions(DATA / "positions.csv")
    targets = load_target_portfolio(DATA / "target_portfolio.csv")
    policy = load_portfolio_policy(DATA / "portfolio_policy.yaml")
    rules = load_trigger_rules(DATA / "trigger_rules.yaml")
    market = load_market_indicators(DATA / "market_indicators.csv")
    gaps = compute_gaps(positions, targets)
    risk = check_risk_limits(positions, gaps, policy)
    alerts = evaluate_triggers(market, rules)
    actions = plan_actions(
        gaps,
        alerts,
        risk,
        "YELLOW",
        rules,
        group_actions={"cash_short_bond": "Park"},
        buy_triggers_active=False,
    )
    cash = next(a for a in actions if a.ticker == "CASH")
    assert cash.action == "Park"
    bond = next(a for a in actions if a.ticker == "157450")
    assert bond.action == "Park"


def test_kr_alpha_replace_theoretical_low_priority():
    positions = load_positions(DATA / "positions.csv")
    targets = load_target_portfolio(DATA / "target_portfolio.csv")
    policy = load_portfolio_policy(DATA / "portfolio_policy.yaml")
    rules = load_trigger_rules(DATA / "trigger_rules.yaml")
    market = load_market_indicators(DATA / "market_indicators.csv")
    gaps = compute_gaps(positions, targets)
    risk = check_risk_limits(positions, gaps, policy)
    alerts = evaluate_triggers(market, rules)
    actions = plan_actions(
        gaps,
        alerts,
        risk,
        "YELLOW",
        rules,
        execution_scope="ETF_ONLY",
    )
    replace = next((a for a in actions if a.action == "Replace"), None)
    if replace:
        assert replace.priority == "Low"
        assert "이론값" in replace.reason


def test_trim_includes_partial_sizing():
    from src.models import GapRow

    gaps = [
        GapRow(
            ticker="157450",
            name="TIGER 단기통안채",
            asset_group="cash_short_bond",
            current_weight=23.67,
            target_weight=16.66,
            gap=-7.01,
            min_weight=5,
            max_weight=30,
            status="Overweight",
            in_target=True,
        ),
    ]
    rules = load_trigger_rules(DATA / "trigger_rules.yaml")
    actions = plan_actions(
        gaps,
        [],
        check_risk_limits([], gaps, {"risk_limits": {}}),
        "YELLOW",
        rules,
        buy_triggers_active=True,
    )
    trim = next(a for a in actions if a.ticker == "157450")
    assert trim.action == "Trim"
    assert trim.allowed_size_pct == -2.0
    assert "1회 권장 Trim 2.0%p" in trim.reason
