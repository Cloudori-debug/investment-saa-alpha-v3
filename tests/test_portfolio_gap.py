from __future__ import annotations

from pathlib import Path

import pytest

from src.data_loader import load_positions, load_target_portfolio
from src.portfolio_gap import classify_gap, compute_gaps

ROOT = Path(__file__).resolve().parents[1]


def test_gap_calculation():
    current = 6.0
    target = 4.0
    gap = target - current
    assert gap == -2.0
    assert classify_gap(gap, True, current) == "Slightly overweight"


def test_gap_underweight():
    assert classify_gap(10.0, True, 0.0) == "No position"


def test_compute_gaps_sample():
    positions = load_positions(ROOT / "data" / "positions.csv")
    targets = load_target_portfolio(ROOT / "data" / "target_portfolio.csv")
    rows = compute_gaps(positions, targets)
    holding = next(r for r in rows if r.ticker == "005440")
    assert holding.status in ("Overweight", "Slightly overweight")
    assert holding.gap < 0

    kodex = next(r for r in rows if r.ticker == "069500")
    assert kodex.current_weight == 0
    assert kodex.target_weight == pytest.approx(10.12, abs=0.05)
    assert kodex.gap == pytest.approx(10.12, abs=0.05)
