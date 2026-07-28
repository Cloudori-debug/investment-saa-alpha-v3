"""PRE_LAUNCH lock, checklist gate, judgment copy."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from alpha_system.entry import TrancheState, TriggerSnapshot, evaluate_entry
from alpha_system.journal import clear_entries
from alpha_system.loader import load_config
from alpha_system.ui.services.go_live_gate import assess_checklist, block_go_live_reasons
from alpha_system.ui.services.judgment_copy import explain_tranche
from alpha_system.ui.services.ui_copy import format_tranche_label, load_ui_copy


@pytest.fixture(autouse=True)
def _clear():
    clear_entries()
    load_ui_copy.cache_clear()
    yield
    clear_entries()
    load_ui_copy.cache_clear()


def test_config_go_live_default_null() -> None:
    cfg = load_config()
    assert cfg.go_live_date is None


def test_pre_launch_locks_all_tranches_no_t1_ready() -> None:
    cfg = load_config()
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(as_of=date(2026, 7, 16), system_started=True),  # app up ≠ live
        journal=False,
    )
    assert any("PRE_LAUNCH" in w for w in ev.warnings)
    assert all(s.state == TrancheState.PENDING for s in ev.statuses)
    assert all(not s.trigger_met for s in ev.statuses)
    assert all(s.meta.get("pre_launch") for s in ev.statuses)
    t1 = next(s for s in ev.statuses if s.tranche_id.value == "T1")
    assert t1.state != TrancheState.READY


def test_go_live_in_snapshot_unlocks_t1() -> None:
    cfg = load_config()
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(
            as_of=date(2026, 7, 16),
            system_started=True,
            go_live_date=date(2026, 7, 16),
        ),
        journal=False,
    )
    assert not any("PRE_LAUNCH" in w for w in ev.warnings)
    t1 = next(s for s in ev.statuses if s.tranche_id.value == "T1")
    assert t1.trigger_met is True


def test_checklist_blocks_incomplete(tmp_path: Path) -> None:
    cfg = load_config()
    cfg = cfg.model_copy(
        update={"scoring": cfg.scoring.model_copy(update={"score_cutoff": None})}
    )
    # empty root → T3 missing; cutoff forced null. Ops A: CECS is non-blocking.
    status = assess_checklist(cfg, root=tmp_path, go_live_date=None)
    assert status.ready_for_go_live is False
    keys = {i.key for i in status.blocking}
    assert "score_cutoff" in keys
    assert "t3_history" in keys
    assert "cecs_final" not in keys
    reasons = block_go_live_reasons(status)
    assert len(reasons) >= 2


def test_tranche_display_from_ui_copy() -> None:
    assert "즉시 집행분" in format_tranche_label("T1")
    assert "(T1)" in format_tranche_label("T1")


def test_judgment_maps_pre_launch_korean() -> None:
    cfg = load_config()
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(as_of=date(2026, 7, 16), system_started=True),
        journal=False,
    )
    sentence = explain_tranche(ev.statuses[0], pre_launch=True)
    assert "가동 전" in sentence.headline
    assert "system_started" not in sentence.headline
