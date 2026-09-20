"""Hakedaka sequential gate — QVM scores stay untouched."""

from __future__ import annotations

from pathlib import Path

from alpha_system.scoring.engine import NameScore
from alpha_system.sizing.allocate import select_eligible
from alpha_system.sizing.cyclical_theme import is_cyclical_heavy
from alpha_system.sizing.hakedaka_screen import (
    HakedakaInputs,
    evaluate_hakedaka,
    hakedaka_fail_tickers,
    load_hakedaka_inputs,
)


def test_cyclical_heavy_catches_ship_names_outside_industrials() -> None:
    assert is_cyclical_heavy(sector="industrials", name="SNT에너지")
    assert is_cyclical_heavy(sector="auto", name="대한조선")
    assert is_cyclical_heavy(sector="auto", name="한화에어로스페이스")
    assert not is_cyclical_heavy(sector="auto", name="현대차")
    assert not is_cyclical_heavy(sector="distribution", name="F&F")


def test_unknown_metrics_fail_open() -> None:
    verdict = evaluate_hakedaka("100840", HakedakaInputs(), min_hits=2)
    assert verdict.known == 0
    assert verdict.passed is True


def test_one_known_metric_is_not_enough_to_reject() -> None:
    """A single measured miss must not eject a QVM name when min_hits=2."""
    inputs = HakedakaInputs(net_cash_to_mcap={"006040": -80.0})
    verdict = evaluate_hakedaka("006040", inputs, min_hits=2)
    assert verdict.known == 1
    assert verdict.hits == 0
    assert verdict.passed is True


def test_csv_false_circular_does_not_count_as_known() -> None:
    """Old CSV defaults related_party_risk_flag=False — not an FTC check."""
    inputs = HakedakaInputs(
        net_cash_to_mcap={"003240": 94.0},
        circular_flag={"003240": False},
    )
    verdict = evaluate_hakedaka("003240", inputs, min_hits=2)
    assert verdict.circular is None
    assert verdict.known == 1
    assert verdict.hits == 1
    assert verdict.passed is True


def test_two_known_need_two_hits() -> None:
    inputs = HakedakaInputs(
        net_cash_to_mcap={"003240": 90.0},
        treasury_ratio={"003240": 0.0},
    )
    miss = evaluate_hakedaka("003240", inputs, min_hits=2)
    assert miss.hits == 1
    assert miss.passed is False
    inputs.treasury_ratio["003240"] = 0.05
    ok = evaluate_hakedaka("003240", inputs, min_hits=2)
    assert ok.hits == 2
    assert ok.passed is True


def test_owner_proximity_band() -> None:
    inputs = HakedakaInputs(owner_pct={"005930": 17.2})
    assert evaluate_hakedaka("005930", inputs, min_hits=1).owner_band is True
    inputs.owner_pct["005930"] = 8.0
    assert evaluate_hakedaka("005930", inputs, min_hits=1).owner_band is False


def test_owner_fraction_is_treated_as_percent() -> None:
    inputs = HakedakaInputs(owner_pct={"005930": 0.172})
    assert evaluate_hakedaka("005930", inputs, min_hits=1).owner_band is True


def test_fail_tickers_and_select_eligible_fills_next() -> None:
    inputs = HakedakaInputs(
        net_cash_to_mcap={"A": -1.0},
        treasury_ratio={"A": 0.0},
    )
    skip = hakedaka_fail_tickers(["A", "B"], inputs, min_hits=2)
    assert skip == {"A"}

    def _score(ticker: str, weight: float) -> NameScore:
        return NameScore(
            ticker=ticker,
            name=ticker,
            factors={},
            total_score=weight,
            eligibility=True,
            weight_input=weight,
            eligibility_reason="test",
            sector="misc",
        )

    selected, warnings = select_eligible(
        [_score("A", 100), _score("B", 90), _score("C", 80)],
        target_names=2,
        hakedaka_skip=skip,
    )
    assert [s.ticker for s in selected] == ["B", "C"]
    assert any("hakedaka gate" in w for w in warnings)


def test_load_inputs_from_csv_and_watch(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "hakedaka_fundamentals.csv").write_text(
        "ticker,net_cash_to_market_cap,treasury_share_ratio,"
        "related_party_risk_flag,governance_event_flag\n"
        "003240,90.0,0.12,false,false\n",
        encoding="utf-8",
    )
    (data / "opendart_proposal_watch.json").write_text(
        '{"metrics":[{"ticker":"003240","largest_shareholder_pct":16.5}]}\n',
        encoding="utf-8",
    )
    inputs = load_hakedaka_inputs(tmp_path, data_dir=data)
    verdict = evaluate_hakedaka("003240", inputs, min_hits=2)
    assert verdict.net_cash is True
    assert verdict.treasury is True
    assert verdict.owner_band is True
    assert verdict.circular is None
    assert "003240" not in inputs.circular_flag
    assert verdict.passed is True


def test_load_owner_from_csv_without_watch(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "hakedaka_fundamentals.csv").write_text(
        "ticker,net_cash_to_market_cap,treasury_share_ratio,largest_shareholder_pct\n"
        "100840,5.0,0.2,16.0\n",
        encoding="utf-8",
    )
    inputs = load_hakedaka_inputs(tmp_path, data_dir=data)
    verdict = evaluate_hakedaka("100840", inputs, min_hits=2)
    assert inputs.owner_pct["100840"] == 16.0
    assert verdict.known == 3
    assert verdict.hits == 3
    assert verdict.passed is True
