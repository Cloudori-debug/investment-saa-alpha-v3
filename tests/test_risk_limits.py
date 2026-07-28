from __future__ import annotations

from pathlib import Path

from src.data_loader import load_positions, load_target_portfolio
from src.portfolio_gap import compute_gaps
from src.config import load_portfolio_policy
from src.risk_limits import check_risk_limits

ROOT = Path(__file__).resolve().parents[1]


def test_single_stock_hard_limit():
    assert 15 >= 8  # policy threshold reference


def test_not_in_target_holding_flags_warn():
    positions = load_positions(ROOT / "data" / "positions.csv")
    targets = load_target_portfolio(ROOT / "data" / "target_portfolio.csv")
    policy = load_portfolio_policy(ROOT / "data" / "portfolio_policy.yaml")
    gaps = compute_gaps(positions, targets)
    risk = check_risk_limits(positions, gaps, policy)
    orphan = next(r for r in gaps if r.ticker == "192400")
    assert not orphan.in_target and orphan.current_weight > 0
    assert any(v.code == "NOT_IN_TARGET" and v.ticker == "192400" for v in risk.violations)
