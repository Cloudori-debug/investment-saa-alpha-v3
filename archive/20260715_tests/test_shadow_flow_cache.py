"""P1.6c — shadow flow refresh cache tests."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

from src.alpha_flow.shadow_flow_cache import (
    ALLOWED_STANDARD_SHADOW_FLOW_REFRESH_REASONS,
    evaluate_shadow_flow_cache_decision,
    maybe_run_shadow_flow_dashboard,
    write_shadow_flow_cache_decision,
)
from src.runtime.profiler import RuntimeProfiler
from src.runtime.run_mode import RunMode, resolve_run_config
from src.runtime.run_mode_contract import validate_run_mode_contract

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _seed_flow(data: Path, out: Path, as_of: str = "2026-07-07") -> None:
    data.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("universe.csv", "investor_flows.csv", "market_indicators.csv"):
        src = DATA_DIR / name
        if src.exists():
            shutil.copy(src, data / name)
    (out / "flow_daily_timeseries.csv").write_text(
        "date,ticker,name,market,foreign_net,institution_net,retail_net,program_net,mcap,stale_flag\n"
        f"{as_of},005930,삼성,KOSPI,1,2,3,4,100,false\n",
        encoding="utf-8",
    )
    (out / "flow_dashboard_summary.json").write_text(json.dumps({"as_of": as_of}), encoding="utf-8")
    (out / "alpha_v2_cache_decision.json").write_text(
        json.dumps({"decision": "reuse_cache", "alpha_v2_reused_from_cache": True}),
        encoding="utf-8",
    )
    from src.alpha_flow.shadow_flow_cache import compute_flow_dependency_hash

    dep = compute_flow_dependency_hash(data, out)
    write_shadow_flow_cache_decision(
        out,
        {
            "flow_dependency_hash_current": dep,
            "shadow_flow_reused_from_cache": True,
            "refresh_reason": "alpha_v2_cache_reuse",
        },
    )


def test_standard_shadow_flow_skip_when_alpha_v2_reused(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_flow(data, out)
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    prof.alpha_v2_reused_from_cache = True
    doc = evaluate_shadow_flow_cache_decision(
        data, out, as_of="2026-07-07", run_mode="standard", profiler=prof,
    )
    assert doc["shadow_flow_reused_from_cache"] is True
    assert doc["shadow_flow_refresh_executed"] is False
    assert doc["refresh_reason"] == "alpha_v2_cache_reuse"


def test_standard_shadow_flow_skip_no_pykrx(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_flow(data, out)
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    prof.alpha_v2_reused_from_cache = True
    with patch("src.alpha_flow.flow_analytics.run_flow_dashboard_outputs") as mock_run:
        with patch("src.alpha_flow.flow_analytics.reuse_flow_dashboard_outputs") as mock_reuse:
            mock_reuse.return_value = None
            maybe_run_shadow_flow_dashboard(
                data, out, as_of="2026-07-07", run_mode="standard", run_id="r2",
                force_refresh=False, refresh_mode="cache_first", profiler=prof,
            )
            mock_run.assert_not_called()
            mock_reuse.assert_called_once()
    assert prof.shadow_flow_reused_from_cache is True
    assert prof.pykrx_call_count == 0


def test_standard_missing_flow_output_allows_refresh(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_flow(data, out)
    (out / "flow_daily_timeseries.csv").unlink()
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    prof.alpha_v2_reused_from_cache = True
    doc = evaluate_shadow_flow_cache_decision(
        data, out, as_of="2026-07-07", run_mode="standard", profiler=prof,
    )
    assert doc["shadow_flow_refresh_executed"] is True
    assert doc["refresh_reason"] == "flow_required_outputs_missing"


def test_deep_allows_shadow_flow_refresh(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_flow(data, out)
    doc = evaluate_shadow_flow_cache_decision(
        data, out, as_of="2026-07-07", run_mode="deep", force_refresh=True,
    )
    assert doc["shadow_flow_refresh_executed"] is True
    assert doc["refresh_reason"] == "deep_force_refresh"


def test_quick_blocks_shadow_flow_refresh(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    doc = evaluate_shadow_flow_cache_decision(
        data, out, as_of="2026-07-07", run_mode="quick",
    )
    assert doc["shadow_flow_reused_from_cache"] is False
    assert "flow_required_outputs_missing" in doc["cache_blockers"]


def test_contract_fail_pykrx_during_alpha_v2_reuse(tmp_path: Path) -> None:
    cfg = resolve_run_config(RunMode.STANDARD)
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    prof.alpha_v2_reused_from_cache = True
    prof.alpha_v2_refresh_reason = "input_hash_unchanged"
    prof.pykrx_call_count = 80
    doc = validate_run_mode_contract(cfg, prof, hooks_meta={})
    assert doc["contract_pass"] is False
    assert any("alpha_v2 cache reuse" in v for v in doc["violations"])


def test_allowed_shadow_flow_reasons(tmp_path: Path) -> None:
    assert "flow_hash_changed" in ALLOWED_STANDARD_SHADOW_FLOW_REFRESH_REASONS
