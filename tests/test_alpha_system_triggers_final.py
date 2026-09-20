"""§7.1 extended — T2/T3/T4 confirmed triggers + entry/exit gates + swap observe."""

from __future__ import annotations

from datetime import date

import pytest

from alpha_system.entry import (
    EntryActionType,
    TrancheState,
    TriggerSnapshot,
    attempt_execute,
    check_entry_target_valuation,
    evaluate_entry,
)
from alpha_system.exit import modify_target_valuation
from alpha_system.journal import clear_entries, list_entries
from alpha_system.loader import load_config
from alpha_system.schema import TrancheId
from alpha_system.scoring import evaluate_rescore_triggers
from alpha_system.swap import SwapObserveInput, evaluate_swap_observe


@pytest.fixture
def cfg():
    return load_config()


@pytest.fixture(autouse=True)
def _clear_journal():
    clear_entries()
    yield
    clear_entries()


GO_LIVE = date(2026, 7, 16)


def test_config_t2_event_ids_confirmed(cfg) -> None:
    t2 = cfg.t2_event_ids()
    assert "commercial_code_enforcement_decrees" in t2
    assert "msci_dm_index_inclusion_confirmed" in t2
    assert "ifrs18_domestic_adoption_schedule_confirmed" in t2
    assert cfg.thesis_background.basel3_excluded_from_t2 is True


def test_t2_fires_on_market_event(cfg) -> None:
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(
            as_of=date(2026, 8, 1),
            system_started=True,
            go_live_date=GO_LIVE,
            events_fired=frozenset({"ifrs18_domestic_adoption_schedule_confirmed"}),
        ),
    )
    assert ev.statuses == []
    assert "capital_tranches_retired" in ev.warnings


def test_t3_fires_on_kospi_pbr_band(cfg) -> None:
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(
            as_of=date(2026, 8, 1),
            system_started=True,
            go_live_date=GO_LIVE,
            kospi_pbr_in_bottom_band=True,
        ),
    )
    assert ev.statuses == []


def test_t4_initial_50pct_at_month_12(cfg) -> None:
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(
            as_of=date(2027, 7, 16),
            system_started=True,
            go_live_date=GO_LIVE,
        ),
    )
    assert ev.statuses == []


def test_t4_follow_on_50pct_when_t2_fires_after_partial(cfg) -> None:
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(
            as_of=date(2027, 8, 16),
            system_started=True,
            go_live_date=GO_LIVE,
            events_fired=frozenset({"commercial_code_enforcement_decrees"}),
        ),
        journal=False,
    )
    assert ev.statuses == []


def test_rescore_triggers_separate_from_t2(cfg) -> None:
    assert "value_up_program_disclosure" in cfg.scoring.rescore_triggers
    d = evaluate_rescore_triggers(
        cfg,
        as_of=date(2026, 7, 16),
        fired_events=["treasury_share_cancellation_resolution"],
    )
    assert d.should_rescore is True
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(
            as_of=date(2026, 7, 16),
            system_started=True,
            go_live_date=GO_LIVE,
            events_fired=frozenset({"treasury_share_cancellation_resolution"}),
        ),
        journal=False,
    )
    assert ev.statuses == []


def test_entry_blocked_without_target_valuation(cfg) -> None:
    blocked, msg = check_entry_target_valuation(
        cfg, ticker="002380", has_target_valuation=False
    )
    assert blocked is True
    assert "target valuation" in msg


def test_attempt_execute_blocked_without_exit_yaml(cfg) -> None:
    from alpha_system.entry.models import TrancheStatus
    from alpha_system.schema import TriggerType

    status = TrancheStatus(
        tranche_id=TrancheId.T1,
        state=TrancheState.READY,
        weight=0.25,
        trigger_type=TriggerType.TIME,
        trigger_met=True,
    )
    _, action = attempt_execute(
        cfg,
        tranche_id=TrancheId.T1,
        status=status,
        as_of=date(2026, 7, 18),
        journal=False,
        entry_tickers=["002380", "005830"],
        has_target_by_ticker={"002380": False, "005830": True},
    )
    assert action.blocked is True
    assert action.action_type == EntryActionType.WARN_BLOCKED
    assert "capital_tranches_retired" in action.reason


def test_attempt_execute_allows_when_all_targets_present(cfg) -> None:
    from alpha_system.entry.models import TrancheStatus
    from alpha_system.schema import TriggerType

    status = TrancheStatus(
        tranche_id=TrancheId.T1,
        state=TrancheState.READY,
        weight=0.25,
        trigger_type=TriggerType.TIME,
        trigger_met=True,
    )
    updated, action = attempt_execute(
        cfg,
        tranche_id=TrancheId.T1,
        status=status,
        as_of=date(2026, 7, 18),
        journal=False,
        entry_tickers=["005830"],
        has_target_by_ticker={"005830": True},
    )
    assert action.blocked is True
    assert "capital_tranches_retired" in action.reason
    assert updated.state == TrancheState.READY


def test_attempt_execute_fails_closed_when_entry_tickers_omitted(cfg) -> None:
    from alpha_system.entry.models import TrancheStatus
    from alpha_system.schema import TriggerType

    status = TrancheStatus(
        tranche_id=TrancheId.T1,
        state=TrancheState.READY,
        weight=0.25,
        trigger_type=TriggerType.TIME,
        trigger_met=True,
    )
    _, action = attempt_execute(
        cfg,
        tranche_id=TrancheId.T1,
        status=status,
        as_of=date(2026, 7, 18),
        journal=False,
        entry_tickers=None,
    )
    assert action.blocked is True
    assert "capital_tranches_retired" in action.reason


def test_target_valuation_price_modify_warns(cfg) -> None:
    res = modify_target_valuation(
        cfg,
        ticker="002380",
        as_of=date(2026, 7, 16),
        reason_type="price_move",
        rationale="price drift only",
    )
    assert res.warn_only is True
    assert res.allowed is False
    assert list_entries()


def test_target_valuation_fundamental_modify_allowed(cfg) -> None:
    res = modify_target_valuation(
        cfg,
        ticker="002380",
        as_of=date(2026, 7, 16),
        reason_type="fundamental_event",
        rationale="ROE revision post earnings",
    )
    assert res.allowed is True
    assert res.warn_only is False


def test_swap_observe_candidate_after_two_hits(cfg) -> None:
    rows = [
        SwapObserveInput("002380", 40.0, is_held=True),
        SwapObserveInput("021240", 70.0, is_held=False),
    ]
    e1 = evaluate_swap_observe(
        cfg, rows, as_of=date(2026, 7, 1), prior_hits={}, journal=False
    )
    assert not e1.candidates
    key = ("002380", "021240")
    e2 = evaluate_swap_observe(
        cfg,
        rows,
        as_of=date(2026, 7, 15),
        prior_hits={key: 1},
        journal=True,
    )
    assert len(e2.candidates) == 1
    assert e2.candidates[0].score_gap_pct >= 20.0
    assert any(e.action_kind == "SWAP_CANDIDATE" for e in list_entries())
