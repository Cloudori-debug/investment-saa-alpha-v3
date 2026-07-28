"""Tests for UI 7-step run progress mapping."""
from __future__ import annotations

from src.runtime.run_mode import RunMode
from src.ui.run_progress import (
    MODE_ACTIVE_STEPS,
    PROFILER_STEP_TO_UI,
    RunProgressState,
    format_duration,
)


def test_quick_mode_skips_heavy_steps() -> None:
    state = RunProgressState(run_mode=RunMode.QUICK.value)
    skipped = [s.key for s in state.steps if s.status == "skipped"]
    assert "bundle_export" in skipped
    assert "alpha_scoring" in skipped
    assert "target_guard" not in skipped


def test_deep_mode_all_steps_active() -> None:
    state = RunProgressState(run_mode=RunMode.DEEP.value)
    assert all(s.status == "pending" for s in state.steps)


def test_profiler_step_maps_to_ui() -> None:
    state = RunProgressState(run_mode=RunMode.STANDARD.value)
    state.apply_profiler_step("start", "target_guard")
    assert state.current_step == "target_guard"
    state.apply_profiler_step("end", "target_guard", 0.5)
    tg = next(s for s in state.steps if s.key == "target_guard")
    assert tg.status == "done"


def test_apply_runtime_profile_aggregates_timings() -> None:
    state = RunProgressState(run_mode=RunMode.STANDARD.value)
    state.apply_runtime_profile({
        "step_timings": {
            "target_guard": 1.0,
            "alpha_v2": 10.0,
            "pipeline_core": 100.0,
            "diagnostics": 5.0,
        },
    })
    alpha = next(s for s in state.steps if s.key == "alpha_scoring")
    assert alpha.seconds == 110.0
    assert alpha.status == "done"


def test_format_duration() -> None:
    assert format_duration(45) == "45.0s"
    assert format_duration(125) == "2m 05s"


def test_bundle_only_active_steps() -> None:
    active = MODE_ACTIVE_STEPS[RunMode.BUNDLE_ONLY.value]
    assert active == frozenset({"target_guard", "bundle_export"})


def test_pipeline_core_maps_alpha() -> None:
    assert PROFILER_STEP_TO_UI["pipeline_core"] == "alpha_scoring"
