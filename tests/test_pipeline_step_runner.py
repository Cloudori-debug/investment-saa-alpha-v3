"""P2 — pipeline_core step decomposition tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.runtime.pipeline_step_contract import (
    PIPELINE_CORE_STEPS_JSON,
    STEP_STATUS_CACHE_HIT,
    STEP_STATUS_EXECUTED,
    STEP_STATUS_SKIPPED,
)
from src.runtime.pipeline_step_runner import PipelineStepRunner
from src.runtime.profiler import RuntimeProfiler


def test_step_runner_records_executed_and_skipped(tmp_path: Path) -> None:
    prof = RuntimeProfiler(run_id="test-run", run_mode="standard")
    runner = PipelineStepRunner(
        run_mode="standard",
        run_id="test-run",
        profiler=prof,
        output_dir=tmp_path,
    )

    with runner.step("portfolio_state_build"):
        pass

    runner.record_skip("tier_b_refresh", "price_hash_unchanged", cache_hit=True, cache_source="price_hash_unchanged")

    with runner.step("alpha_v2_pipeline"):
        prof.alpha_v2_reused_from_cache = True
    runner.annotate_last_step("alpha_v2_pipeline", cache_hit=True, cache_source="cache_reuse")

    summary = runner.summarize()
    assert summary["pipeline_core_step_timings"]["portfolio_state_build"] >= 0
    tier_b = [s for s in summary["steps"] if s["step_name"] == "tier_b_refresh"]
    assert tier_b and tier_b[-1]["cache_hit"] is True
    v2_steps = [s for s in summary["steps"] if s["step_name"] == "alpha_v2_pipeline"]
    assert v2_steps and v2_steps[-1]["status"] == STEP_STATUS_CACHE_HIT

    path = runner.write(tmp_path)
    assert path.name == PIPELINE_CORE_STEPS_JSON
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["run_mode"] == "standard"
    assert doc["pipeline_core_total_seconds_reconciled"] >= 0
    assert prof.pipeline_core_step_timings
    assert prof.pipeline_core_total_seconds_reconciled >= 0


def test_step_runner_failed_status(tmp_path: Path) -> None:
    runner = PipelineStepRunner(run_mode="standard", run_id="fail-run", output_dir=tmp_path)

    with pytest.raises(RuntimeError):
        with runner.step("final_execution_decision"):
            raise RuntimeError("boom")

    failed = [s for s in runner.steps if s.step_name == "final_execution_decision"]
    assert failed and failed[0].status == "failed"
    assert failed[0].errors


def test_step_contract_status_constants() -> None:
    assert STEP_STATUS_EXECUTED == "executed"
    assert STEP_STATUS_SKIPPED == "skipped"
    assert STEP_STATUS_CACHE_HIT == "cache_hit"
