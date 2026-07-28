"""P1.5 — dependency subset hash tests."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

from src.runtime.diagnostics_cache import DiagnosticSpec, run_diagnostics_with_cache, should_cache_hit
from src.runtime.diagnostics_subset_hash import (
    compute_subset_dependency_hash,
    explain_subset_hash_changes,
    load_dependency_inputs,
)


def _base_final(**extra: object) -> dict:
    return {"execution_scope": "NO_TRADE", "allowed_actions": [], "final_trade_list": [], **extra}


def _seed(data: Path, out: Path) -> None:
    data.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    (data / "target_portfolio.csv").write_text("ticker,weight\nCASH,1\n", encoding="utf-8")
    (data / "portfolio_policy.yaml").write_text("data_gate_policy: {}\n", encoding="utf-8")
    (data / "tier2_kosis_manual.yaml").write_text("pmi_kr: {}\n", encoding="utf-8")
    (data / "tier2_provenance.json").write_text(json.dumps({
        "fields": {"pmi_kr": {"status": "stale", "value": 50, "value_date": "2026-01-01", "stale_business_days": 5}},
    }), encoding="utf-8")
    (out / "final_execution_decision.json").write_text(json.dumps(_base_final()), encoding="utf-8")
    (out / "acceptance_report.json").write_text(json.dumps({
        "execution_scope": "NO_TRADE",
        "items": [{
            "name": "target_portfolio_guard",
            "detail": {"severity": "PASS", "current_hash": "h1", "user_target_hash": "h1", "changed_rows": 0},
        }],
    }), encoding="utf-8")
    (out / "daily_brief.json").write_text(json.dumps({
        "system_status": {
            "execution_scope": "NO_TRADE",
            "unified_data_gate": "GREEN",
            "actual_buy_allowed": 0,
            "policy_cap_active": True,
        },
    }), encoding="utf-8")
    (out / "flow_dashboard_summary.json").write_text(json.dumps({
        "fresh_flow_count": 10, "stale_flow_count": 0, "run_id": "x",
    }), encoding="utf-8")


def test_generated_at_only_same_subset_hash(tmp_path: Path) -> None:
    data, out = tmp_path / "data", tmp_path / "outputs"
    _seed(data, out)
    loaded1 = load_dependency_inputs(data, out)
    h1, _, _ = compute_subset_dependency_hash("no_action_diagnostics", loaded1)
    (out / "daily_brief.json").write_text(json.dumps({
        "generated_at": "t2",
        "system_status": loaded1.daily_brief["system_status"],
    }), encoding="utf-8")
    loaded2 = load_dependency_inputs(data, out)
    h2, _, _ = compute_subset_dependency_hash("no_action_diagnostics", loaded2)
    assert h1 == h2


def test_actual_buy_allowed_changes_subset_hash(tmp_path: Path) -> None:
    data, out = tmp_path / "data", tmp_path / "outputs"
    _seed(data, out)
    loaded1 = load_dependency_inputs(data, out)
    h1, _, _ = compute_subset_dependency_hash("no_action_diagnostics", loaded1)
    (out / "final_execution_decision.json").write_text(json.dumps({
        **_base_final(),
        "allowed_actions": [{"action": "Buy", "allowed_size_pct": 1}],
        "final_trade_list": [{"action": "Buy", "allowed_size_pct": 1}],
    }), encoding="utf-8")
    loaded2 = load_dependency_inputs(data, out)
    h2, _, _ = compute_subset_dependency_hash("no_action_diagnostics", loaded2)
    assert h1 != h2


def test_execution_scope_change_affects_policy_cap_subset(tmp_path: Path) -> None:
    data, out = tmp_path / "data", tmp_path / "outputs"
    _seed(data, out)
    loaded1 = load_dependency_inputs(data, out)
    h1, _, _ = compute_subset_dependency_hash("policy_cap_counterfactual", loaded1)
    (out / "final_execution_decision.json").write_text(json.dumps(_base_final(execution_scope="ETF_ONLY")), encoding="utf-8")
    (out / "daily_brief.json").write_text(json.dumps({
        "system_status": {**_system_status_from(loaded1), "execution_scope": "ETF_ONLY"},
    }), encoding="utf-8")
    loaded2 = load_dependency_inputs(data, out)
    h2, _, _ = compute_subset_dependency_hash("policy_cap_counterfactual", loaded2)
    assert h1 != h2


def _system_status_from(loaded) -> dict:
    return loaded.daily_brief.get("system_status") or {}


def test_pmi_kr_change_affects_data_gate_subset(tmp_path: Path) -> None:
    data, out = tmp_path / "data", tmp_path / "outputs"
    _seed(data, out)
    loaded1 = load_dependency_inputs(data, out)
    h1, _, _ = compute_subset_dependency_hash("data_gate_diagnostics", loaded1)
    (data / "tier2_provenance.json").write_text(json.dumps({
        "fields": {"pmi_kr": {"status": "fresh", "value": 51, "value_date": "2026-02-01", "stale_business_days": 0}},
    }), encoding="utf-8")
    loaded2 = load_dependency_inputs(data, out)
    h2, _, _ = compute_subset_dependency_hash("data_gate_diagnostics", loaded2)
    assert h1 != h2


def test_csv_content_same_despite_mtime(tmp_path: Path) -> None:
    data, out = tmp_path / "data", tmp_path / "outputs"
    _seed(data, out)
    (out / "alpha_candidates.csv").write_text("ticker\nA\n", encoding="utf-8")
    loaded1 = load_dependency_inputs(data, out)
    h1, _, _ = compute_subset_dependency_hash("alpha_shortlist_diagnostics", loaded1)
    p = out / "alpha_candidates.csv"
    os.utime(p, (time.time() - 9999, time.time() - 9999))
    loaded2 = load_dependency_inputs(data, out)
    h2, _, _ = compute_subset_dependency_hash("alpha_shortlist_diagnostics", loaded2)
    assert h1 == h2


def test_explain_subset_changes(tmp_path: Path) -> None:
    prev = {"execution_scope": "NO_TRADE", "actual_buy_allowed": 0}
    curr = {"execution_scope": "ETF_ONLY", "actual_buy_allowed": 0}
    paths = explain_subset_hash_changes(prev, curr)
    assert "execution_scope" in paths


def test_subset_cache_hit_second_run(tmp_path: Path) -> None:
    data, out = tmp_path / "data", tmp_path / "outputs"
    _seed(data, out)
    outputs = [
        "alpha_shortlist_diagnostics.csv", "alpha_shortlist_summary.json",
        "policy_cap_counterfactual.json", "core_etf_permission_diagnostics.json",
        "core_etf_candidate_trace.csv", "data_gate_diagnostics.json",
        "data_gate_field_status.csv", "data_gate_to_permission_trace.json",
        "market_indicator_schema_diagnostics.json", "market_field_status.csv",
        "pmi_kr_source_policy.json", "data_gate_green_preflight.json",
        "alpha_gate_diagnostics.json", "no_action_diagnostics.json",
    ]
    for name in outputs:
        p = out / name
        p.write_text("{}" if name.endswith(".json") else "c\n1\n", encoding="utf-8")
    (out / "no_action_diagnostics.json").write_text(json.dumps({
        "actual_buy_trace": {"final_actual_buy_allowed": 0},
        "status_alignment_pass": True,
        "status_alignment": {"authoritative_execution_scope": "NO_TRADE"},
    }), encoding="utf-8")

    with patch("src.validation.alpha_shortlist_diagnostics.write_alpha_shortlist_diagnostics"):
        with patch("src.validation.policy_cap_counterfactual.write_policy_cap_counterfactual"):
            with patch("src.validation.core_etf_permission_diagnostics.write_core_etf_permission_diagnostics"):
                with patch("src.validation.data_gate_diagnostics.write_data_gate_diagnostics"):
                    with patch("src.validation.alpha_gate_diagnostics.write_alpha_gate_diagnostics"):
                        with patch("src.validation.no_action_diagnostics.write_no_action_diagnostics"):
                            r1 = run_diagnostics_with_cache(data, out, run_id="r1", run_full_diag=False)
                            (out / "final_execution_decision.json").write_text(json.dumps(_base_final(run_id="r2", generated_at="now")), encoding="utf-8")
                            r2 = run_diagnostics_with_cache(data, out, run_id="r2", run_full_diag=False)
    assert r1.cache_miss_count <= 8
    assert r2.cache_hit_count >= 5


def test_cache_miss_when_output_missing(tmp_path: Path) -> None:
    data, out = tmp_path / "data", tmp_path / "outputs"
    _seed(data, out)
    spec = DiagnosticSpec("alpha_gate_diagnostics", ("alpha_gate_diagnostics.json",))
    loaded = load_dependency_inputs(data, out)
    dep_hash, subset, _ = compute_subset_dependency_hash(spec.name, loaded)
    hit, reason, _, _ = should_cache_hit(
        spec, data_dir=data, output_dir=out, dep_hash=dep_hash,
        prev_entries={}, subset_snapshot=subset,
    )
    assert hit is False
    assert reason == "output_missing"
