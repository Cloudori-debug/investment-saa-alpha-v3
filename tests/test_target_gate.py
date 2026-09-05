"""Proposal target gate — drop names already at/above justified take-profit."""

from __future__ import annotations

import pandas as pd

from alpha_system.scoring.engine import NameScore
from alpha_system.sizing.allocate import select_eligible
from alpha_system.sizing.target_gate import (
    collect_above_justified_target_tickers,
    is_at_or_above_justified_target,
    ops_proposal_membership,
)


def _score(ticker: str, weight: float, *, sector: str = "misc") -> NameScore:
    return NameScore(
        ticker=ticker,
        name=ticker,
        factors={},
        total_score=weight,
        eligibility=True,
        weight_input=weight,
        eligibility_reason="test",
        sector=sector,
    )


def test_yaml_price_above_target_is_hit() -> None:
    assert is_at_or_above_justified_target(
        current_price=1_674_000,
        current_pbr=9.62,
        yaml_targets={"target_price": 626_445, "valuation": {"pbr_max": 3.60}},
    )


def test_yaml_below_target_is_not_hit() -> None:
    assert not is_at_or_above_justified_target(
        current_price=100_000,
        current_pbr=0.48,
        yaml_targets={"target_price": 112_146, "valuation": {"pbr_max": 1.40}},
    )


def test_live_justified_without_yaml_hits_stretched_pbr() -> None:
    assert is_at_or_above_justified_target(
        current_price=1_674_000,
        current_pbr=9.62,
        roe=22.0,
    )


def test_live_justified_cheap_pbr_is_not_hit() -> None:
    assert not is_at_or_above_justified_target(
        current_price=100_000,
        current_pbr=0.48,
        roe=11.0,
    )


def test_yaml_not_hit_wins_over_live_formula() -> None:
    """Approved yaml line is the take-profit; do not fall through to live P/B."""
    assert not is_at_or_above_justified_target(
        current_price=1_674_000,
        current_pbr=9.62,
        yaml_targets={"target_price": 2_000_000, "valuation": {"pbr_max": 12.0}},
        roe=22.0,
    )


def test_missing_data_fail_open() -> None:
    assert not is_at_or_above_justified_target()


def test_collect_uses_yaml_and_live() -> None:
    prices = pd.DataFrame(
        [
            {"ticker": "000660", "close": 1_674_000},
            {"ticker": "006040", "close": 100_000},
            {"ticker": "000003", "close": 50_000},
        ]
    )
    funds = pd.DataFrame(
        [
            {"ticker": "000660", "pbr": 9.62, "roe": 22.0},
            {"ticker": "006040", "pbr": 0.48, "roe": 11.0},
            {"ticker": "000003", "pbr": 1.0, "roe": 12.0},
        ]
    )
    yaml_doc = {
        "tickers": {
            "000660": {"target_price": 626_445, "valuation": {"pbr_max": 3.6}},
        }
    }
    hit = collect_above_justified_target_tickers(
        ["000660", "006040", "000003"],
        prices_df=prices,
        fundamentals_df=funds,
        exit_yaml=yaml_doc,
    )
    assert hit == {"000660"}


def test_select_eligible_drops_above_target_and_fills_next() -> None:
    scores = [_score(str(i).zfill(6), 100 - i, sector=f"s{i}") for i in range(1, 8)]
    selected, warnings = select_eligible(
        scores,
        target_names=3,
        max_names_per_sector=2,
        exclude_tickers={"000001"},
    )
    assert [s.ticker for s in selected] == ["000002", "000003", "000004"]
    assert any("000001" in w and "target gate" in w for w in warnings)
    assert scores[0].total_score == 99


def test_held_above_target_stays_in_s2a_membership() -> None:
    members = ops_proposal_membership(
        ["006040", "271560"],
        held_tickers=["000660", "006040"],
        above_target=["000660"],
    )
    assert members == {"006040", "271560", "000660"}
