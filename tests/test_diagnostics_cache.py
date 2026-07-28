"""Tests for diagnostics hash cache v0.1."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.runtime.diagnostics_cache import (
    MANIFEST_JSON,
    DiagnosticSpec,
    compute_dependency_hash,
    load_manifest,
    run_diagnostics_with_cache,
    should_cache_hit,
    verify_no_action_cached,
)
from src.runtime.diagnostics_subset_hash import compute_subset_dependency_hash, load_dependency_inputs
from src.runtime.profiler import RuntimeProfiler


def _seed_deps(data: Path, out: Path) -> None:
    data.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    (data / "target_portfolio.csv").write_text("ticker,weight\nCASH,1\n", encoding="utf-8")
    (data / "portfolio_policy.yaml").write_text("data_gate_policy: {}\n", encoding="utf-8")
    (out / "final_execution_decision.json").write_text(
        json.dumps({"execution_scope": "NO_TRADE", "actions": []}),
        encoding="utf-8",
    )
    (out / "acceptance_report.json").write_text(json.dumps({"execution_scope": "NO_TRADE"}), encoding="utf-8")
    (out / "daily_brief.json").write_text("{}", encoding="utf-8")


def _write_outputs(out: Path, names: list[str]) -> None:
    for name in names:
        p = out / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith(".csv"):
            p.write_text("a\n1\n", encoding="utf-8")
        else:
            p.write_text("{}", encoding="utf-8")


def test_dependency_hash_stable(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_deps(data, out)
    h1, _ = compute_dependency_hash(data, out)
    h2, _ = compute_dependency_hash(data, out)
    assert h1 == h2


def test_dependency_hash_changes_when_input_changes(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_deps(data, out)
    h1, _ = compute_dependency_hash(data, out)
    (out / "final_execution_decision.json").write_text('{"execution_scope":"ETF_ONLY"}', encoding="utf-8")
    h2, _ = compute_dependency_hash(data, out)
    assert h1 != h2


def test_cache_hit_when_hash_and_outputs_match(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_deps(data, out)
    spec = DiagnosticSpec("policy_cap_counterfactual", ("policy_cap_counterfactual.json",))
    _write_outputs(out, ["policy_cap_counterfactual.json"])
    dep_hash, subset, fields = compute_subset_dependency_hash("policy_cap_counterfactual", load_dependency_inputs(data, out))
    (out / MANIFEST_JSON).write_text(
        json.dumps({
            "entries": {
                "policy_cap_counterfactual": {
                    "subset_dependency_hash": dep_hash,
                    "dependency_hash": dep_hash,
                    "subset_snapshot": subset,
                    "run_id": "prev-run",
                    "last_compute_seconds": 120,
                },
            },
        }),
        encoding="utf-8",
    )
    hit, reason, _, _ = should_cache_hit(
        spec,
        data_dir=data,
        output_dir=out,
        dep_hash=dep_hash,
        prev_entries=_manifest_entries(out),
        subset_snapshot=subset,
    )
    assert hit is True
    assert reason == "hash_match"


def _manifest_entries(out: Path) -> dict:
    return load_manifest(out).get("entries") or {}


def test_cache_miss_when_output_missing(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_deps(data, out)
    spec = DiagnosticSpec("alpha_gate_diagnostics", ("alpha_gate_diagnostics.json",))
    dep_hash, _ = compute_dependency_hash(data, out, dep_keys=spec.dep_keys)
    hit, reason, _, _ = should_cache_hit(
        spec, data_dir=data, output_dir=out, dep_hash=dep_hash, prev_entries={},
    )
    assert hit is False
    assert reason == "output_missing"


def test_no_action_verify_fails_on_actual_buy_mismatch(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_deps(data, out)
    (out / "no_action_diagnostics.json").write_text(
        json.dumps({
            "actual_buy_trace": {"final_actual_buy_allowed": 1},
            "status_alignment_pass": True,
            "status_alignment": {},
        }),
        encoding="utf-8",
    )
    ok, reason = verify_no_action_cached(data, out)
    assert ok is False
    assert "actual_buy_mismatch" in reason


def test_run_diagnostics_cache_hit_skips_writer(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_deps(data, out)
    dep_hash, _ = compute_dependency_hash(data, out)
    _write_outputs(out, [
        "alpha_shortlist_diagnostics.csv",
        "alpha_shortlist_summary.json",
        "policy_cap_counterfactual.json",
        "core_etf_permission_diagnostics.json",
        "core_etf_candidate_trace.csv",
        "data_gate_diagnostics.json",
        "data_gate_field_status.csv",
        "data_gate_to_permission_trace.json",
        "market_indicator_schema_diagnostics.json",
        "market_field_status.csv",
        "pmi_kr_source_policy.json",
        "data_gate_green_preflight.json",
        "alpha_gate_diagnostics.json",
        "no_action_diagnostics.json",
    ])
    entries = {}
    loaded = load_dependency_inputs(data, out)
    for name in (
            "alpha_shortlist_diagnostics",
            "policy_cap_counterfactual",
            "core_etf_permission_diagnostics",
            "data_gate_diagnostics",
            "pmi_kr_source_policy",
            "data_gate_green_preflight",
            "alpha_gate_diagnostics",
            "no_action_diagnostics",
        ):
        dh, subset, _ = compute_subset_dependency_hash(name, loaded)
        entries[name] = {
            "subset_dependency_hash": dh,
            "dependency_hash": dh,
            "subset_snapshot": subset,
            "run_id": "prev",
            "last_compute_seconds": 90,
        }
    (out / MANIFEST_JSON).write_text(json.dumps({"entries": entries}), encoding="utf-8")
    (out / "no_action_diagnostics.json").write_text(
        json.dumps({
            "actual_buy_trace": {"final_actual_buy_allowed": 0},
            "status_alignment_pass": True,
            "status_alignment": {"authoritative_execution_scope": "NO_TRADE"},
        }),
        encoding="utf-8",
    )

    with patch("src.validation.alpha_shortlist_diagnostics.write_alpha_shortlist_diagnostics") as mock_short:
        with patch("src.validation.data_gate_diagnostics.write_data_gate_diagnostics") as mock_dg:
            prof = RuntimeProfiler(run_id="r1", run_mode="standard")
            result = run_diagnostics_with_cache(
                data, out, run_id="r2", run_full_diag=False, profiler=prof,
            )
    assert result.cache_hit_count >= 5
    mock_short.assert_not_called()
    mock_dg.assert_not_called()
    assert prof.diagnostics_cache_hit_count >= 5


def test_runtime_profile_records_diagnostics_cache() -> None:
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    prof.record_diagnostics_cache_hit("policy_cap_counterfactual", 120)
    prof.record_diagnostics_cache_miss("data_gate_diagnostics")
    doc = prof.to_dict()
    assert doc["diagnostics_cache_hit_count"] == 1
    assert doc["diagnostics_cache_miss_count"] == 1
    assert "policy_cap_counterfactual" in doc["diagnostics_reused"]
    assert doc["diagnostics_cache_saved_seconds_estimate"] == 120


def test_refresh_no_action_diagnostics_if_stale_on_scope_mismatch(tmp_path: Path) -> None:
    from src.runtime.diagnostics_cache import refresh_no_action_diagnostics_if_stale

    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_deps(data, out)
    (out / "acceptance_report.json").write_text(
        json.dumps({
            "execution_scope": "ETF_ONLY",
            "authoritative_execution_scope": "ETF_ONLY",
            "overall": "YELLOW",
            "items": [],
        }),
        encoding="utf-8",
    )
    (out / "final_execution_decision.json").write_text(
        json.dumps({
            "execution_scope": "ETF_ONLY",
            "target_guard_conflict_detected": True,
            "execution_permissions": {"gates": {}},
            "allowed_actions": [],
            "final_trade_list": [],
        }),
        encoding="utf-8",
    )
    (out / "no_action_diagnostics.json").write_text(
        json.dumps({
            "actual_buy_trace": {"final_actual_buy_allowed": 0},
            "status_alignment_pass": False,
            "status_alignment": {"authoritative_execution_scope": "ETF_ONLY"},
        }),
        encoding="utf-8",
    )
    (out / MANIFEST_JSON).write_text(
        json.dumps({"entries": {"no_action_diagnostics": {"cache_hit": True}}}),
        encoding="utf-8",
    )

    refreshed_payload = {
        "actual_buy_trace": {"final_actual_buy_allowed": 0},
        "status_alignment_pass": True,
        "status_alignment": {"authoritative_execution_scope": "NO_TRADE"},
    }

    def _write(_data: Path, output_dir: Path, **kwargs: object) -> Path:
        (output_dir / "no_action_diagnostics.json").write_text(
            json.dumps(refreshed_payload),
            encoding="utf-8",
        )
        return output_dir / "no_action_diagnostics.json"

    with patch("src.validation.no_action_diagnostics.write_no_action_diagnostics", side_effect=_write):
        did_refresh, reason = refresh_no_action_diagnostics_if_stale(data, out)

    assert did_refresh is True
    assert "scope_mismatch" in reason
    manifest = json.loads((out / MANIFEST_JSON).read_text(encoding="utf-8"))
    entry = manifest["entries"]["no_action_diagnostics"]
    assert entry["cache_hit"] is False
    assert entry["recompute_required"] is True
