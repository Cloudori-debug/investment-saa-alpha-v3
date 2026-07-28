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
    for tid in ("T1", "T2", "T3", "T4"):
        assert cfg.tranches[tid].weight == 0.25
    assert cfg.universe.boundary_mode == "shareholder_return_broad"
    assert cfg.universe.financial_only_filter is False
    assert cfg.universe.include_markets == ["KOSPI"]
    assert cfg.benchmark == "KOSPI"
    assert resolve_boundary_mode(cfg) == "shareholder_return_broad"
    todos = cfg.todo_fields()
    # score_cutoff may already be confirmed in operating config — then omit from todos
    if cfg.scoring.score_cutoff is None:
        assert "scoring.score_cutoff" in todos
    else:
        assert "scoring.score_cutoff" not in todos
    assert "universe.boundary_mode" not in todos
    assert "benchmark" not in todos
    assert "tranches.T2.event_ids" not in todos
    assert "tranches.T3.valuation_band" not in todos
    assert "tranches.T4.hybrid_rules" not in todos
    assert cfg.go_live_date is None


def test_capital_lock_rejects_other_fraction(tmp_path: Path, cfg: AlphaSystemConfig) -> None:
    raw = cfg.model_dump(mode="json")
    raw["capital"]["max_fraction_of_total_assets"] = 0.40
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(Exception, match="0.30"):
        load_config(path)


def test_t1_ready_on_system_start(cfg: AlphaSystemConfig) -> None:
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(as_of=date(2026, 7, 16), system_started=True, go_live_date=date(2026, 7, 16)),
    )
    t1 = next(s for s in ev.statuses if s.tranche_id == TrancheId.T1)
    assert t1.state == TrancheState.READY
    assert t1.trigger_met is True
    assert any(
        a.action_type == EntryActionType.MARK_READY and a.tranche_id == TrancheId.T1
        for a in ev.actions
    )
    # T2/T3/T4 stay PENDING while TODO configs empty
    for tid in (TrancheId.T2, TrancheId.T3, TrancheId.T4):
        st = next(s for s in ev.statuses if s.tranche_id == tid)
        assert st.state == TrancheState.PENDING
        assert st.trigger_met is False


def test_hard_rule_sunset_expires_unexecuted(cfg: AlphaSystemConfig) -> None:
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(as_of=date(2028, 1, 1), system_started=True, go_live_date=date(2026, 7, 16)),
    )
    assert all(s.state == TrancheState.EXPIRED for s in ev.statuses)
    reflux = [a for a in ev.actions if a.action_type == EntryActionType.REFLUX_TO_SAA]
    assert len(reflux) == 4


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
    t1 = next(s for s in ev.statuses if s.tranche_id == TrancheId.T1)
    assert t1.state == TrancheState.EXECUTED
    others = [s for s in ev.statuses if s.tranche_id != TrancheId.T1]
    assert all(s.state == TrancheState.EXPIRED for s in others)


def test_hard_rule_reverse_blocks_unmet_trigger(cfg: AlphaSystemConfig) -> None:
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(as_of=date(2026, 7, 16), system_started=True, go_live_date=date(2026, 7, 16)),
    )
    t2 = next(s for s in ev.statuses if s.tranche_id == TrancheId.T2)
    _, action = attempt_execute(
        cfg, tranche_id=TrancheId.T2, status=t2, as_of=date(2026, 7, 16)
    )
    assert action.blocked is True
    assert action.action_type == EntryActionType.WARN_BLOCKED


def test_hard_rule_reverse_allows_ready_execute(cfg: AlphaSystemConfig) -> None:
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(as_of=date(2026, 7, 16), system_started=True, go_live_date=date(2026, 7, 16)),
    )
    t1 = next(s for s in ev.statuses if s.tranche_id == TrancheId.T1)
    updated, action = attempt_execute(
        cfg,
        tranche_id=TrancheId.T1,
        status=t1,
        as_of=date(2026, 7, 16),
        entry_tickers=[],  # no names → target gate N/A; omit (=None) would fail closed
    )
    assert action.blocked is False
    assert action.action_type == EntryActionType.EXECUTE
    assert updated.state == TrancheState.EXECUTED


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
    assert all(s.state == TrancheState.FROZEN for s in ev.statuses)
    assert any(a.action_type == EntryActionType.FREEZE for a in ev.actions)
    assert any(a.action_type == EntryActionType.REFLUX_TO_SAA for a in ev.actions)


def test_t2_fires_when_event_configured(tmp_path: Path, cfg: AlphaSystemConfig) -> None:
    raw = cfg.model_dump(mode="json")
    raw["tranches"]["T2"]["event_ids"] = ["commercial_code_enforcement"]
    path = tmp_path / "with_t2.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    loaded = load_config(path)
    ev = evaluate_entry(
        loaded,
        TriggerSnapshot(
            as_of=date(2026, 7, 16),
            system_started=True,
            go_live_date=date(2026, 7, 16),
            events_fired=frozenset({"commercial_code_enforcement"}),
        ),
    )
    t2 = next(s for s in ev.statuses if s.tranche_id == TrancheId.T2)
    assert t2.state == TrancheState.READY
    assert t2.trigger_met is True


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
