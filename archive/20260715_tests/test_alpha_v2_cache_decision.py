"""P1.6b — Alpha v2 cache decision tests."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

from src.alpha_v2.cache_decision import (
    ALLOWED_STANDARD_REFRESH_REASONS,
    commit_pipeline_input_snapshot,
    evaluate_alpha_v2_cache_decision,
    store_input_hash,
    write_alpha_v2_cache_decision,
    write_pipeline_input_snapshot,
)
from src.runtime.profiler import RuntimeProfiler
from src.runtime.run_mode import RunMode, resolve_run_config
from src.runtime.run_mode_contract import validate_run_mode_contract

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _seed(data: Path, out: Path, as_of: str = "2026-07-07") -> None:
    data.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    for name in (
        "universe.csv",
        "prices.csv",
        "prices_history.csv",
        "investor_flows.csv",
        "fundamentals_pit.csv",
        "fundamentals.csv",
        "market_indicators.csv",
    ):
        src = DATA_DIR / name
        if src.exists():
            shutil.copy(src, data / name)
    for name in (
        "alpha_v2_scored.csv",
        "alpha_v2_summary.json",
        "alpha_v2_top30.csv",
        "alpha_v2_final_candidates.csv",
    ):
        (out / name).write_text("{}\n" if name.endswith(".json") else "ticker\n005930\n", encoding="utf-8")
    if (out / "alpha_v2_summary.json").exists():
        (out / "alpha_v2_summary.json").write_text(
            json.dumps({"as_of": as_of, "kosdaq_validation_failures": [], "mode": "shadow"}),
            encoding="utf-8",
        )
    store_input_hash(out, data, as_of=as_of)
    from src.alpha_v2.cache_decision import compute_stable_input_hash, compute_flow_hash

    stable = compute_stable_input_hash(data, as_of=as_of)
    commit_pipeline_input_snapshot(out, data, as_of=as_of, run_id="seed")
    write_alpha_v2_cache_decision(
        out,
        {
            "schema_version": "1.0",
            "run_id": "seed",
            "run_mode": "standard",
            "decision": "reuse_cache",
            "input_hash_current": stable,
            "flow_hash_current": compute_flow_hash(data),
            "refresh_reason": "input_hash_unchanged",
            "alpha_v2_reused_from_cache": True,
            "alpha_v2_full_refresh_executed": False,
        },
    )


def test_standard_reuse_when_stable_hash_matches(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    doc = evaluate_alpha_v2_cache_decision(
        data, out, as_of="2026-07-07", run_mode="standard", cache_reuse=True,
    )
    assert doc["decision"] == "reuse_cache"
    assert doc["input_hash_match"] is True
    assert doc["refresh_reason"] == "input_hash_unchanged"


def test_standard_full_refresh_when_output_missing(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    (out / "alpha_v2_scored.csv").unlink()
    doc = evaluate_alpha_v2_cache_decision(
        data, out, as_of="2026-07-07", run_mode="standard", cache_reuse=True,
    )
    assert doc["decision"] == "full_refresh"
    assert doc["refresh_reason"] == "required_outputs_missing"


def test_standard_full_refresh_when_stable_hash_changes(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    uni = data / "universe.csv"
    text = uni.read_text(encoding="utf-8")
    uni.write_text(text.replace("005930", "005931", 1), encoding="utf-8")
    write_pipeline_input_snapshot(out, data, as_of="2026-07-07", run_id="changed")
    doc = evaluate_alpha_v2_cache_decision(
        data, out, as_of="2026-07-07", run_mode="standard", cache_reuse=True,
    )
    assert doc["decision"] == "full_refresh"
    assert doc["refresh_reason"] == "input_hash_changed"


def test_deep_force_refresh(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    doc = evaluate_alpha_v2_cache_decision(
        data, out, as_of="2026-07-07", run_mode="deep", force_refresh=True, cache_reuse=False,
    )
    assert doc["decision"] == "full_refresh"
    assert doc["refresh_reason"] == "deep_force_refresh"


def test_quick_blocks_without_cache(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    doc = evaluate_alpha_v2_cache_decision(
        data, out, as_of="2026-07-07", run_mode="quick", cache_reuse=True,
    )
    assert doc["decision"] == "blocked_no_cache"


def test_second_run_reuses_after_committed_snapshot(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    write_pipeline_input_snapshot(out, data, as_of="2026-07-07", run_id="run-2")
    doc = evaluate_alpha_v2_cache_decision(
        data, out, as_of="2026-07-07", run_mode="standard", cache_reuse=True, run_id="run-2",
    )
    assert doc["decision"] == "reuse_cache"
    assert doc["input_hash_match"] is True
    assert doc["alpha_v2_reused_from_cache"] is True


def test_pipeline_reuse_skips_scoring(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    from src.alpha_v2.pipeline import run_alpha_v2_shadow

    write_pipeline_input_snapshot(out, data, as_of="2026-07-07", run_id="r2")
    with patch("src.alpha_v2.pipeline.score_alpha_v2_universe") as mock_score:
        result = run_alpha_v2_shadow(
            data, out, as_of="2026-07-07", positions=[], targets=[],
            cache_reuse=True, force_refresh=False, run_mode="standard", run_id="r2", profiler=prof,
        )
        mock_score.assert_not_called()
    assert prof.alpha_v2_reused_from_cache is True
    assert prof.pykrx_call_count == 0
    assert result.get("cache_reused") is True


def test_contract_violation_on_standard_mass_pykrx(tmp_path: Path) -> None:
    cfg = resolve_run_config(RunMode.STANDARD)
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    prof.pykrx_call_count = 80
    prof.alpha_v2_full_refresh_executed = True
    prof.alpha_v2_refresh_reason = "input_hash_unchanged"
    doc = validate_run_mode_contract(cfg, prof, hooks_meta={})
    assert doc["contract_pass"] is False
    assert any("PyKRX" in v or "contradicts" in v for v in doc["violations"])


def test_allowed_reasons_include_standard_refresh(tmp_path: Path) -> None:
    assert "input_hash_changed" in ALLOWED_STANDARD_REFRESH_REASONS
    assert "no_previous_alpha_v2_cache" in ALLOWED_STANDARD_REFRESH_REASONS
