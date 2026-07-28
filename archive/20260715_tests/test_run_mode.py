"""Tests for run mode separation and runtime profiling."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from src.alpha_v2.cache_decision import store_input_hash
from src.alpha_v2.input_hash import can_reuse_alpha_v2_outputs, compute_alpha_v2_input_hash
from src.runtime.pipeline_runner import run_bundle_only, run_pipeline_with_mode, run_quick_check
from src.runtime.profiler import RuntimeProfiler
from src.runtime.run_mode import RunMode, resolve_run_config

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"


def test_resolve_run_config_modes() -> None:
    quick = resolve_run_config(RunMode.QUICK)
    assert quick.refresh_network is False
    assert quick.run_alpha_v1 is False
    deep = resolve_run_config(RunMode.DEEP)
    assert deep.run_zip_bundle is True
    assert deep.kosdaq_universe_sync is True
    bundle = resolve_run_config(RunMode.BUNDLE_ONLY)
    assert bundle.run_ai_export is True
    assert bundle.run_alpha_v1 is False


def test_runtime_profile_created(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    prof = RuntimeProfiler(run_id="test-run", run_mode="quick", entrypoint="cli")
    with prof.step("target_guard"):
        pass
    prof.record_cache_hit(2)
    prof.record_cache_miss(1)
    path = prof.write(out)
    assert path.exists()
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["run_mode"] == "quick"
    assert "target_guard" in doc["step_timings"]
    assert doc["cache_hit_count"] == 2
    assert doc["slowest_steps"]


@pytest.mark.skipif(not (OUT / "final_execution_decision.json").exists(), reason="outputs missing")
def test_quick_mode_skips_full_pipeline() -> None:
    with patch("src.full_pipeline.run_full_pipeline") as mock_fp:
        result = run_quick_check(DATA, OUT)
        mock_fp.assert_not_called()
    assert result.run_mode == "quick"
    assert (OUT / "runtime_profile.json").exists()


@pytest.mark.skipif(not (OUT / "final_execution_decision.json").exists(), reason="outputs missing")
def test_quick_generates_no_action_diagnostics() -> None:
    run_quick_check(DATA, OUT)
    assert (OUT / "no_action_diagnostics.json").exists()


@pytest.mark.skipif(not (OUT / "run_manifest.json").exists(), reason="manifest missing")
def test_bundle_only_does_not_recompute_pipeline(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    for name in (
        "run_manifest.json",
        "final_execution_decision.json",
        "daily_report.md",
        "no_action_diagnostics.json",
        "system_health.json",
        "acceptance_report.json",
    ):
        src = OUT / name
        if src.exists():
            shutil.copy(src, out / name)

    with patch("src.full_pipeline.run_full_pipeline") as mock_fp:
        with patch(
            "src.validation.ai_export.build_ai_export_bundle",
            return_value={"as_of": "2026-07-03", "run_id": "test", "validation_prompt": ""},
        ):
            with patch(
                "src.validation.ai_export.validate_export_bundle_readiness",
                return_value={"pass": True, "failures": []},
            ):
                result = run_bundle_only(DATA, out, create_zip=True)
        mock_fp.assert_not_called()
    assert result.bundle_created is True
    assert (out / "runtime_profile.json").exists()


def test_all_modes_target_guard_called(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    (data / "positions.csv").write_text("ticker,qty\n", encoding="utf-8")
    (data / "target_portfolio.csv").write_text("ticker,weight\nCASH,1\n", encoding="utf-8")
    (data / "market_indicators.csv").write_text("date,kospi\n2026-07-03,1\n", encoding="utf-8")
    (data / "portfolio_policy.yaml").write_text("data_gate_policy: {}\n", encoding="utf-8")

    with patch("src.runtime.pipeline_runner._validate_target_guard", return_value={"target_guard_status": "pass"}) as mock_guard:
        with patch("src.validation.no_action_diagnostics.write_no_action_diagnostics"):
            with patch("src.report.authoritative_status.resolve_authoritative_execution", return_value={}):
                with patch("src.runtime.pipeline_runner._actual_buy_from_outputs", return_value=0):
                    run_quick_check(data, out)
        mock_guard.assert_called()


def test_profiler_records_slowest_steps() -> None:
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    with prof.step("alpha_v2"):
        with prof.step("data_refresh"):
            pass
    doc = prof.to_dict()
    assert doc["slowest_steps"]
    assert doc["recommended_speedup"]


def test_alpha_v2_cache_reuse_when_input_hash_same(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    as_of = "2026-07-03"
    (data / "universe.csv").write_text("ticker,market\n005830,KOSPI\n", encoding="utf-8")
    (data / "prices.csv").write_text("ticker,date,close\n005830,2026-07-03,1\n", encoding="utf-8")
    (out / "alpha_v2_scored.csv").write_text("ticker\n005830\n", encoding="utf-8")
    (out / "alpha_v2_summary.json").write_text("{}", encoding="utf-8")
    h = compute_alpha_v2_input_hash(data, as_of=as_of)
    store_input_hash(out, data, as_of=as_of, input_hash=h)
    ok, _ = can_reuse_alpha_v2_outputs(data, out, as_of=as_of)
    assert ok is True


def test_standard_mode_config_cache_first() -> None:
    cfg = resolve_run_config(RunMode.STANDARD)
    assert cfg.flow_refresh_mode == "cache_first"
    assert cfg.alpha_v2_cache_reuse is True
    assert cfg.kosdaq_universe_sync is False


def test_deep_mode_config_full_refresh() -> None:
    cfg = resolve_run_config(RunMode.DEEP)
    assert cfg.flow_refresh_mode == "full"
    assert cfg.kosdaq_universe_sync is True
    assert cfg.run_zip_bundle is True
