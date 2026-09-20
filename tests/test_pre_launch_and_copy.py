"""PRE_LAUNCH lock, checklist gate, judgment copy."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from alpha_system.entry import TriggerSnapshot, evaluate_entry
from alpha_system.journal import clear_entries
from alpha_system.loader import load_config
from alpha_system.ui.services.go_live_gate import assess_checklist, block_go_live_reasons
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


def test_pre_launch_does_not_run_capital_tranches() -> None:
    cfg = load_config()
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(as_of=date(2026, 7, 16), system_started=True),
        journal=False,
    )
    assert ev.statuses == []
    assert "capital_tranches_retired" in ev.warnings


def test_go_live_does_not_unlock_capital_tranches() -> None:
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
    assert ev.statuses == []
    assert "capital_tranches_retired" in ev.warnings


def test_checklist_blocks_incomplete(tmp_path: Path) -> None:
    cfg = load_config()
    cfg = cfg.model_copy(
        update={"scoring": cfg.scoring.model_copy(update={"score_cutoff": None})}
    )
    status = assess_checklist(cfg, root=tmp_path, go_live_date=None)
    assert status.ready_for_go_live is False
    keys = {i.key for i in status.blocking}
    assert "score_cutoff" in keys
    assert "t3_history" not in keys
    assert "cecs_final" not in keys
    reasons = block_go_live_reasons(status)
    assert len(reasons) >= 1


def test_tranche_display_from_ui_copy() -> None:
    assert "즉시 집행분" in format_tranche_label("T1")
    assert "(T1)" in format_tranche_label("T1")


def test_retired_entry_has_no_tranche_judgment() -> None:
    cfg = load_config()
    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(as_of=date(2026, 7, 16), system_started=True),
        journal=False,
    )
    assert ev.statuses == []
