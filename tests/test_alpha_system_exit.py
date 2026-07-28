"""§7.3 exit module — four rules + discretionary warn-not-block asymmetry."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from alpha_system.exit import (
    ExitActionType,
    ExitReason,
    ExitSnapshot,
    PositionView,
    attempt_exit,
    evaluate_exits,
)
from alpha_system.journal import clear_entries, list_entries
from alpha_system.loader import load_config


@pytest.fixture(autouse=True)
def _clear_journal():
    clear_entries()
    yield
    clear_entries()


@pytest.fixture
def cfg():
    return load_config()


def test_thesis_damage_exits_held_not_entry_freeze(cfg) -> None:
    ev = evaluate_exits(
        cfg,
        ExitSnapshot(
            as_of=date(2026, 7, 16),
            positions=[PositionView(ticker="005930", weight=0.1)],
            thesis_damage_flag=True,
            thesis_damage_events=("commercial_code_rollback",),
        ),
    )
    acts = [a for a in ev.actions if a.reason == ExitReason.THESIS_DAMAGE]
    assert len(acts) == 1
    assert acts[0].action_type == ExitActionType.LIQUIDATE
    assert acts[0].ticker == "005930"
    assert "FROZEN" in acts[0].detail
    assert acts[0].journal_id is not None
    assert list_entries()


def test_score_below_cutoff_requires_cutoff(tmp_path: Path, cfg) -> None:
    # Without cutoff: warn, no score-exit action
    ev = evaluate_exits(
        cfg,
        ExitSnapshot(
            as_of=date(2026, 7, 16),
            positions=[PositionView(ticker="A", total_score=10.0)],
        ),
    )
    assert not any(a.reason == ExitReason.SCORE_BELOW_CUTOFF for a in ev.actions)
    assert any("score_cutoff" in w for w in ev.warnings)

    raw = cfg.model_dump(mode="json")
    raw["scoring"]["score_cutoff"] = 60.0
    path = tmp_path / "cut.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    loaded = load_config(path)
    ev2 = evaluate_exits(
        loaded,
        ExitSnapshot(
            as_of=date(2026, 7, 16),
            positions=[PositionView(ticker="A", total_score=10.0)],
        ),
    )
    score_acts = [a for a in ev2.actions if a.reason == ExitReason.SCORE_BELOW_CUTOFF]
    assert len(score_acts) == 1
    assert score_acts[0].action_type == ExitActionType.REDUCE


def test_target_valuation_exit(cfg) -> None:
    ev = evaluate_exits(
        cfg,
        ExitSnapshot(
            as_of=date(2026, 7, 16),
            positions=[
                PositionView(ticker="B", target_valuation_reached=True),
            ],
        ),
    )
    acts = [a for a in ev.actions if a.reason == ExitReason.TARGET_VALUATION]
    assert len(acts) == 1
    assert acts[0].action_type == ExitActionType.LIQUIDATE


def test_window_end_portfolio_report(cfg) -> None:
    ev = evaluate_exits(
        cfg,
        ExitSnapshot(
            as_of=date(2027, 12, 31),
            positions=[PositionView(ticker="C"), PositionView(ticker="D")],
        ),
    )
    assert ev.window_end_report is not None
    wind = [
        a for a in ev.actions if a.reason == ExitReason.WINDOW_END
    ]
    assert len(wind) == 1
    assert wind[0].action_type == ExitActionType.PORTFOLIO_WIND_DOWN_REPORT
    assert wind[0].ticker == "*"


def test_discretionary_exit_warns_but_does_not_block(cfg) -> None:
    action = attempt_exit(
        cfg,
        ticker="E",
        as_of=date(2026, 7, 16),
        rule_met=False,
        fraction=1.0,
        discretionary_reason="macro shock — cut risk before window rule fires",
        rationale="ops override",
    )
    assert action.blocked is False
    assert action.action_type == ExitActionType.WARN_DISCRETIONARY
    assert action.meta.get("allowed") is True
    assert action.meta.get("follow_through_journal_id")
    assert len(list_entries()) >= 2


def test_discretionary_reason_required(cfg) -> None:
    from alpha_system.journal import JournalValidationError

    with pytest.raises(JournalValidationError, match="discretionary_reason"):
        attempt_exit(
            cfg,
            ticker="E",
            as_of=date(2026, 7, 16),
            rule_met=False,
            discretionary_reason="",
        )
