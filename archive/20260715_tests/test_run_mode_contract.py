"""P1.6a — standard mode cache-first contract tests."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

from src.alpha_v2.cache_decision import compute_flow_hash, compute_stable_input_hash, store_input_hash, write_alpha_v2_cache_decision
from src.runtime.run_mode import RunMode, resolve_run_config
from src.runtime.run_mode_contract import (
    investor_flows_covers_as_of,
    validate_run_mode_contract,
    write_run_mode_contract_validation,
)
from src.runtime.profiler import RuntimeProfiler

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _seed_alpha_v2_outputs(data: Path, out: Path, as_of: str = "2026-07-06") -> None:
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
    (out / "alpha_v2_scored.csv").write_text("ticker,grade\n005930,A\n", encoding="utf-8")
    (out / "alpha_v2_top30.csv").write_text("ticker\n005930\n", encoding="utf-8")
    (out / "alpha_v2_final_candidates.csv").write_text("ticker\n005930\n", encoding="utf-8")
    summary = {"as_of": as_of, "mode": "shadow", "target_write_occurred": False, "kosdaq_validation_failures": []}
    (out / "alpha_v2_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    store_input_hash(out, data, as_of=as_of)
    stable = compute_stable_input_hash(data, as_of=as_of)
    write_alpha_v2_cache_decision(
        out,
        {
            "decision": "reuse_cache",
            "input_hash_current": stable,
            "flow_hash_current": compute_flow_hash(data),
            "refresh_reason": "input_hash_unchanged",
        },
    )


def test_standard_alpha_v2_skips_when_input_hash_unchanged(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_alpha_v2_outputs(data, out)
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    from src.alpha_v2.pipeline import run_alpha_v2_shadow

    with patch("src.alpha_v2.pipeline.score_alpha_v2_universe") as mock_score:
        result = run_alpha_v2_shadow(
            data, out, as_of="2026-07-06", positions=[], targets=[],
            cache_reuse=True, force_refresh=False, flow_refresh_mode="cache_first",
            run_mode="standard", run_id="r2", profiler=prof,
        )
        mock_score.assert_not_called()
    assert prof.alpha_v2_reused_from_cache is True
    assert prof.alpha_v2_full_refresh_executed is False
    assert result.get("cache_reused") is True


def test_deep_alpha_v2_force_refresh(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_alpha_v2_outputs(data, out)
    prof = RuntimeProfiler(run_id="r1", run_mode="deep")
    from src.alpha_v2.pipeline import run_alpha_v2_shadow

    with patch("src.alpha_v2.pipeline.score_alpha_v2_universe", return_value=[]):
        with patch("src.alpha_v2.pipeline.build_alpha_v2_universe", return_value=[]):
            with patch("src.alpha_v2.pipeline.load_prices", return_value=[]):
                with patch("src.alpha_v2.pipeline._execution_context", return_value={
                    "actual_buy_allowed": 0, "no_trade": True, "execution_scope": "NO_TRADE", "market_status": "—",
                }):
                    run_alpha_v2_shadow(
                        data, out, as_of="2026-07-06", positions=[], targets=[],
                        cache_reuse=False, force_refresh=True, flow_refresh_mode="full", profiler=prof,
                    )
    assert prof.alpha_v2_full_refresh_executed is True


def test_investor_flows_covers_as_of(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "investor_flows.csv").write_text(
        "date,ticker,name\n2026-07-06,005930,삼성\n",
        encoding="utf-8",
    )
    assert investor_flows_covers_as_of(data, "2026-07-06") is True
    assert investor_flows_covers_as_of(data, "2026-07-07") is False


def test_standard_contract_fails_on_mass_pykrx(tmp_path: Path) -> None:
    cfg = resolve_run_config(RunMode.STANDARD)
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    prof.pykrx_call_count = 80
    prof.alpha_v2_full_refresh_executed = True
    prof.alpha_v2_refresh_reason = "full_scoring"
    prof.flow_full_refresh_executed = False
    doc = validate_run_mode_contract(cfg, prof, hooks_meta={})
    assert doc["contract_pass"] is False
    assert any("PyKRX" in v or "alpha_v2" in v for v in doc["violations"])


def test_standard_contract_pass_on_cache_reuse(tmp_path: Path) -> None:
    cfg = resolve_run_config(RunMode.STANDARD)
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    prof.alpha_v2_reused_from_cache = True
    prof.alpha_v2_refresh_reason = "input_hash_unchanged"
    prof.flow_refresh_reason = "investor_flows_unchanged"
    prof.pykrx_call_count = 0
    prof.kosis_refresh_executed = False
    doc = validate_run_mode_contract(cfg, prof, hooks_meta={})
    assert doc["contract_pass"] is True
    out = tmp_path / "outputs"
    path = write_run_mode_contract_validation(out, doc)
    assert path.exists()


def test_standard_contract_pass_price_cache_hit_no_write(tmp_path: Path) -> None:
    cfg = resolve_run_config(RunMode.STANDARD)
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    prof.alpha_v2_reused_from_cache = True
    prof.alpha_v2_refresh_reason = "input_hash_unchanged"
    prof.shadow_flow_reused_from_cache = True
    prof.shadow_flow_refresh_executed = False
    prof.price_hash_match = True
    prof.price_hash_drift_reason = "subset_unchanged"
    prof.price_write_executed = False
    prof.price_fetch_executed = False
    prof.price_fetch_reason = "price_hash_unchanged"
    prof.pykrx_call_count = 0
    doc = validate_run_mode_contract(cfg, prof, hooks_meta={})
    assert doc["contract_pass"] is True
    assert doc["price_contract_reason"] == "standard_price_cache_hit"


def test_standard_contract_pass_coverage_check_only(tmp_path: Path) -> None:
    cfg = resolve_run_config(RunMode.STANDARD)
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    prof.alpha_v2_reused_from_cache = True
    prof.price_hash_match = True
    prof.price_hash_drift_reason = "subset_unchanged"
    prof.price_write_executed = False
    prof.price_fetch_executed = False
    prof.price_check_only = True
    prof.price_fetch_reason = "coverage_check_only"
    prof.pykrx_call_count = 0
    doc = validate_run_mode_contract(cfg, prof, hooks_meta={})
    assert doc["contract_pass"] is True


def test_standard_contract_fail_price_write(tmp_path: Path) -> None:
    cfg = resolve_run_config(RunMode.STANDARD)
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    prof.alpha_v2_reused_from_cache = False
    prof.price_write_executed = True
    prof.price_fetch_reason = "price_refresh_required"
    prof.price_hash_match = False
    prof.pykrx_call_count = 0
    doc = validate_run_mode_contract(cfg, prof, hooks_meta={})
    assert doc["contract_pass"] is False
    assert any("price write" in v for v in doc["violations"])


def test_standard_contract_fail_prices_changed(tmp_path: Path) -> None:
    cfg = resolve_run_config(RunMode.STANDARD)
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    prof.alpha_v2_reused_from_cache = False
    prof.alpha_v2_cache_blockers = ["prices_changed"]
    prof.price_hash_match = False
    prof.pykrx_call_count = 0
    doc = validate_run_mode_contract(cfg, prof, hooks_meta={})
    assert doc["contract_pass"] is False
    assert any("prices_changed" in v for v in doc["violations"])


def test_standard_contract_fail_shadow_flow_during_alpha_reuse(tmp_path: Path) -> None:
    cfg = resolve_run_config(RunMode.STANDARD)
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    prof.alpha_v2_reused_from_cache = True
    prof.shadow_flow_refresh_executed = True
    prof.shadow_flow_refresh_reason = "flow_refresh_required"
    prof.pykrx_call_count = 0
    doc = validate_run_mode_contract(cfg, prof, hooks_meta={})
    assert doc["contract_pass"] is False
    assert any("shadow flow" in v for v in doc["violations"])


def test_quick_contract_forbids_flow_refresh(tmp_path: Path) -> None:
    cfg = resolve_run_config(RunMode.QUICK)
    prof = RuntimeProfiler(run_id="r1", run_mode="quick")
    prof.flow_refresh_executed = True
    doc = validate_run_mode_contract(cfg, prof, hooks_meta={})
    assert doc["contract_pass"] is False


def test_kosis_skip_when_dep_unchanged_despite_diag_miss(tmp_path: Path) -> None:
    from src.runtime.kosis_refresh_cache import evaluate_kosis_refresh_skip, write_kosis_refresh_manifest
    from tests.test_kosis_refresh_cache import _seed_kosis_deps

    data = tmp_path / "data"
    out = tmp_path / "outputs"
    dep_hash = _seed_kosis_deps(data, out)
    skip, reason, _, _ = evaluate_kosis_refresh_skip(
        data, out, run_mode="standard", diagnostics_cache_hit_count=2, diagnostics_cache_miss_count=6,
    )
    assert skip is True
    assert reason == "dependency_unchanged"
