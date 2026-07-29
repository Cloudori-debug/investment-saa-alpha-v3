"""§7.5 sizing — selectable names / 25% / 35% caps + iterative allocation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from alpha_system.exit import ExitReason, ExitSnapshot, PositionView, evaluate_exits
from alpha_system.journal import clear_entries
from alpha_system.loader import load_config
from alpha_system.schema import TrancheId
from alpha_system.scoring.engine import NameScore
from alpha_system.sizing import allocate_tranche, require_sizing


@pytest.fixture(autouse=True)
def _clear():
    clear_entries()
    yield
    clear_entries()


@pytest.fixture
def cfg():
    return load_config()


def _score(
    ticker: str,
    weight_input: float,
    *,
    eligible: bool = True,
) -> NameScore:
    return NameScore(
        ticker=ticker,
        name=ticker,
        factors={},
        total_score=weight_input,
        eligibility=eligible,
        weight_input=weight_input if eligible else 0.0,
        eligibility_reason="test",
    )


def test_sizing_locks(cfg) -> None:
    n, init_cap, mv_cap = require_sizing(cfg)
    assert 5 <= n <= 9
    assert init_cap == 0.25
    assert mv_cap == 0.35
    assert int(getattr(cfg.sizing, "max_names_per_sector", 2)) == 2
    assert float(getattr(cfg.sizing, "sector_weight_cap", 0.35)) == 0.35


def test_sizing_accepts_design_band_count(tmp_path: Path, cfg) -> None:
    raw = cfg.model_dump(mode="json")
    raw["sizing"]["target_names"] = 8
    path = tmp_path / "selected.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    assert load_config(path).sizing.target_names == 8


def test_sizing_rejects_count_outside_design_band(tmp_path: Path, cfg) -> None:
    raw = cfg.model_dump(mode="json")
    raw["sizing"]["target_names"] = 30
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(Exception):
        load_config(path)


def test_selected_count_controls_actual_allocation(tmp_path: Path, cfg) -> None:
    raw = cfg.model_dump(mode="json")
    raw["sizing"]["target_names"] = 7
    path = tmp_path / "seven.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    selected_cfg = load_config(path)
    scores = [_score(chr(ord("A") + i), 100 - i) for i in range(10)]

    result = allocate_tranche(
        selected_cfg,
        tranche_id=TrancheId.T1,
        scores=scores,
        existing_weights={},
        tranche_budget=0.25,
    )

    assert result.target_names == 7
    assert len(result.allocated) == 7


def test_iterative_cap_redistribution(cfg) -> None:
    # One name dominates weight_input; cap must clip and redistribute
    scores = [
        _score("A", 100),
        _score("B", 10),
        _score("C", 10),
        _score("D", 10),
        _score("E", 10),
        _score("F", 10),
    ]
    result = allocate_tranche(
        cfg,
        tranche_id=TrancheId.T1,
        scores=scores,
        existing_weights={},
        tranche_budget=0.25,
    )
    by = {a.ticker: a for a in result.allocated}
    assert by["A"].total_weight_after <= 0.25 + 1e-9
    assert by["A"].incremental_weight <= 0.25 + 1e-9
    # Surplus went to others
    assert by["B"].incremental_weight > 0
    assert abs(sum(a.incremental_weight for a in result.allocated) + result.unallocated_weight - 0.25) < 1e-6
    assert all(a.total_weight_after <= 0.25 + 1e-9 for a in result.allocated)


def test_three_eligible_leaves_unallocated_and_shortfall(cfg) -> None:
    scores = [
        _score("A", 50),
        _score("B", 40),
        _score("C", 30),
        _score("D", 20, eligible=False),
        _score("E", 10, eligible=False),
    ]
    result = allocate_tranche(
        cfg,
        tranche_id=TrancheId.T1,
        scores=scores,
        tranche_budget=0.25,
    )
    assert result.eligible_count == 3
    assert result.shortfall_names == max(0, result.target_names - 3)
    assert any("shortfall" in w for w in result.warnings)
    # With room enough, 3 names can take full 0.25 under 25% cap each
    assert result.unallocated_weight < 1e-9
    assert all(a.total_weight_after <= 0.25 + 1e-9 for a in result.allocated)
    # Ineligible never appear
    assert {a.ticker for a in result.allocated} == {"A", "B", "C"}


def test_all_capped_leaves_unallocated_warn(cfg) -> None:
    scores = [_score(t, 50) for t in ("A", "B", "C")]
    # Existing already at cap
    existing = {"A": 0.25, "B": 0.25, "C": 0.25}
    result = allocate_tranche(
        cfg,
        tranche_id=TrancheId.T2,
        scores=scores,
        existing_weights=existing,
        tranche_budget=0.25,
    )
    assert result.unallocated_weight == pytest.approx(0.25)
    assert any("WARN" in w and "unallocated" in w.lower() or "already at" in w for w in result.warnings)


def test_multi_tranche_cumulative_cap(cfg) -> None:
    scores = [_score(t, 50) for t in ("A", "B", "C", "D", "E", "F")]
    t1 = allocate_tranche(
        cfg,
        tranche_id=TrancheId.T1,
        scores=scores,
        existing_weights={},
        tranche_budget=0.25,
    )
    after_t1 = {a.ticker: a.total_weight_after for a in t1.allocated}
    # Force A already near cap from T1
    after_t1["A"] = 0.25
    t2 = allocate_tranche(
        cfg,
        tranche_id=TrancheId.T2,
        scores=scores,
        existing_weights=after_t1,
        tranche_budget=0.25,
    )
    a2 = next(a for a in t2.allocated if a.ticker == "A")
    assert a2.incremental_weight == pytest.approx(0.0)
    assert a2.total_weight_after == pytest.approx(0.25)
    # Others can still receive T2 budget
    assert sum(a.incremental_weight for a in t2.allocated) > 0
    assert all(a.total_weight_after <= 0.25 + 1e-9 for a in t2.allocated)


def test_market_value_cap_is_exit_not_sizing(cfg) -> None:
    # Sizing never emits reduce for mark-to-market
    scores = [_score("A", 50), _score("B", 50)]
    sized = allocate_tranche(
        cfg, tranche_id=TrancheId.T1, scores=scores, tranche_budget=0.10
    )
    assert sized.unallocated_weight >= 0
    # Exit detects breach above 35%
    ev = evaluate_exits(
        cfg,
        ExitSnapshot(
            as_of=__import__("datetime").date(2026, 7, 16),
            positions=[PositionView(ticker="A", weight=0.40)],
        ),
    )
    mv = [a for a in ev.actions if a.reason == ExitReason.MARKET_VALUE_CAP]
    assert len(mv) == 1
    assert mv[0].action_type.value == "REDUCE"
    assert mv[0].meta.get("owned_by") == "exit"
