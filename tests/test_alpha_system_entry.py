"""§7.1 — config schema + tranche state machine + hard rules."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from alpha_system.entry import (
    EntryActionType,
    TrancheState,
    TriggerSnapshot,
    attempt_execute,
    evaluate_entry,
)
from alpha_system.journal import clear_entries
from alpha_system.loader import load_config
from alpha_system.schema import (
    AlphaSystemConfig,
    ConfigTodoError,
    TrancheId,
)
from alpha_system.sizing import require_sizing
from alpha_system.universe import resolve_boundary_mode


@pytest.fixture
def cfg() -> AlphaSystemConfig:
    return load_config()


@pytest.fixture(autouse=True)
def _clear_journal() -> None:
    clear_entries()
    yield
    clear_entries()


def test_default_config_loads_with_confirmed_locks(cfg: AlphaSystemConfig) -> None:
    assert cfg.capital.max_fraction_of_total_assets == 0.30
    assert cfg.thesis_window.window_end == date(2027, 12, 31)
    assert cfg.tranches == {}
    assert "commercial_code_enforcement_decrees" in cfg.t2_event_ids()
    assert cfg.universe.boundary_mode == "shareholder_return_broad"
    assert cfg.universe.financial_only_filter is False
    assert cfg.universe.include_markets == ["KOSPI"]
    assert cfg.benchmark == "KOSPI"
    assert resolve_boundary_mode(cfg) == "shareholder_return_broad"
    todos = cfg.todo_fields()
    if cfg.scoring.score_cutoff is None:
        assert "scoring.score_cutoff" in todos
    else:
        assert "scoring.score_cutoff" not in todos
    assert "universe.boundary_mode" not in todos
    assert "benchmark" not in todos
    assert cfg.go_live_date is None


def test_capital_lock_rejects_other_fraction(tmp_path: Path, cfg: AlphaSystemConfig) -> None:
    raw = cfg.model_dump(mode="json")
    raw["capital"]["max_fraction_of_total_assets"] = 0.40
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(Exception, match="0.30"):
        load_config(path)


def _assert_tranches_retired(ev) -> None:
    assert ev.statuses == []
    assert "capital_tranches_retired" in ev.warnings


def test_t1_ready_on_system_start(cfg: AlphaSystemConfig) -> None:
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(as_of=date(2026, 7, 16), system_started=True, go_live_date=date(2026, 7, 16)),
    )
    _assert_tranches_retired(ev)


def test_hard_rule_sunset_expires_unexecuted(cfg: AlphaSystemConfig) -> None:
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(as_of=date(2028, 1, 1), system_started=True, go_live_date=date(2026, 7, 16)),
    )
    _assert_tranches_retired(ev)


def test_hard_rule_sunset_skips_executed(cfg: AlphaSystemConfig) -> None:
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(
            as_of=date(2028, 1, 1),
            system_started=True,
            go_live_date=date(2026, 7, 16),
            prior_states={TrancheId.T1: TrancheState.EXECUTED},
        ),
    )
    _assert_tranches_retired(ev)


def test_hard_rule_reverse_blocks_unmet_trigger(cfg: AlphaSystemConfig) -> None:
    from alpha_system.entry.models import TrancheStatus
    from alpha_system.schema import TriggerType

    dummy = TrancheStatus(
        tranche_id=TrancheId.T2,
        state=TrancheState.PENDING,
        weight=0.25,
        trigger_type=TriggerType.EVENT,
        trigger_met=False,
    )
    _, action = attempt_execute(
        cfg, tranche_id=TrancheId.T2, status=dummy, as_of=date(2026, 7, 16)
    )
    assert action.blocked is True
    assert "capital_tranches_retired" in action.reason


def test_hard_rule_reverse_allows_ready_execute(cfg: AlphaSystemConfig) -> None:
    from alpha_system.entry.models import TrancheStatus
    from alpha_system.schema import TriggerType

    dummy = TrancheStatus(
        tranche_id=TrancheId.T1,
        state=TrancheState.READY,
        weight=0.25,
        trigger_type=TriggerType.TIME,
        trigger_met=True,
    )
    _, action = attempt_execute(
        cfg,
        tranche_id=TrancheId.T1,
        status=dummy,
        as_of=date(2026, 7, 16),
        entry_tickers=[],
    )
    assert action.blocked is True
    assert "capital_tranches_retired" in action.reason


def test_hard_rule_thesis_damage_freezes(cfg: AlphaSystemConfig) -> None:
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(
            as_of=date(2026, 7, 16),
            system_started=True,
            go_live_date=date(2026, 7, 16),
            thesis_damage_flag=True,
        ),
    )
    _assert_tranches_retired(ev)


def test_t2_fires_when_event_configured(cfg: AlphaSystemConfig) -> None:
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(
            as_of=date(2026, 7, 16),
            system_started=True,
            go_live_date=date(2026, 7, 16),
            events_fired=frozenset({"commercial_code_enforcement"}),
        ),
    )
    _assert_tranches_retired(ev)


def test_todo_guards_refuse_silent_defaults(cfg: AlphaSystemConfig, tmp_path: Path) -> None:
    raw = cfg.model_dump(mode="json")
    raw["universe"]["boundary_mode"] = None
    path = tmp_path / "unset_universe.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    unset = load_config(path)
    with pytest.raises(ConfigTodoError, match="boundary_mode"):
        resolve_boundary_mode(unset)
    # sizing is locked (not TODO) — returns confirmed tuple
        n, init_cap, mv_cap = require_sizing(cfg)
        assert 5 <= n <= 8
        assert init_cap == 0.25
        assert mv_cap == 0.35


def test_b_mode_rejects_financial_only_filter(cfg: AlphaSystemConfig, tmp_path: Path) -> None:
    raw = cfg.model_dump(mode="json")
    raw["universe"]["financial_only_filter"] = True
    path = tmp_path / "bad_universe.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(Exception, match="financial_only_filter"):
        load_config(path)
