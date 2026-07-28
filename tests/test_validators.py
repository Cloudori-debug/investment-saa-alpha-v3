from __future__ import annotations

from pathlib import Path

import pytest

from src.config import load_portfolio_policy
from src.data_loader import load_positions, load_target_portfolio
from src.validators import validate_inputs

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def test_target_weight_sum_100():
    targets = load_target_portfolio(DATA / "target_portfolio.csv")
    assert abs(sum(t.target_weight for t in targets) - 100.0) < 0.01


def test_positions_positive_values():
    positions = load_positions(DATA / "positions.csv")
    assert all(p.current_value > 0 for p in positions)


def test_validators_green_on_sample_data():
    positions = load_positions(DATA / "positions.csv")
    targets = load_target_portfolio(DATA / "target_portfolio.csv")
    policy = load_portfolio_policy(DATA / "portfolio_policy.yaml")
    result = validate_inputs(positions, targets, policy)
    assert result.is_valid
    assert result.data_gate in {"GREEN", "YELLOW"}
