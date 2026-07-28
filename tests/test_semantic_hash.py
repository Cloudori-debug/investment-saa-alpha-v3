"""P1 — semantic dependency hash for diagnostics cache."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

from src.runtime.diagnostics_cache import (
    DiagnosticSpec,
    compute_dependency_semantic_hash,
    compute_semantic_file_hash,
    normalize_for_semantic_hash,
    run_diagnostics_with_cache,
    should_cache_hit,
    verify_no_action_cached,
)
from src.runtime.profiler import RuntimeProfiler


def test_generated_at_only_change_same_hash(tmp_path: Path) -> None:
    p = tmp_path / "doc.json"
    p.write_text(json.dumps({"execution_scope": "NO_TRADE", "generated_at": "t1"}), encoding="utf-8")
    h1 = compute_semantic_file_hash(p)
    p.write_text(json.dumps({"execution_scope": "NO_TRADE", "generated_at": "t2"}), encoding="utf-8")
    h2 = compute_semantic_file_hash(p)
    assert h1 == h2


def test_run_id_only_change_same_hash(tmp_path: Path) -> None:
    p = tmp_path / "doc.json"
    p.write_text(json.dumps({"actual_buy_allowed": 0, "run_id": "a"}), encoding="utf-8")
    h1 = compute_semantic_file_hash(p)
    p.write_text(json.dumps({"actual_buy_allowed": 0, "run_id": "b"}), encoding="utf-8")
    h2 = compute_semantic_file_hash(p)
    assert h1 == h2


def test_actual_buy_allowed_change_different_hash(tmp_path: Path) -> None:
    p = tmp_path / "doc.json"
    p.write_text(json.dumps({"actual_buy_allowed": 0}), encoding="utf-8")
    h1 = compute_semantic_file_hash(p)
    p.write_text(json.dumps({"actual_buy_allowed": 1}), encoding="utf-8")
    h2 = compute_semantic_file_hash(p)
    assert h1 != h2


def test_execution_scope_change_different_hash(tmp_path: Path) -> None:
    p = tmp_path / "doc.json"
    p.write_text(json.dumps({"execution_scope": "NO_TRADE"}), encoding="utf-8")
    h1 = compute_semantic_file_hash(p)
    p.write_text(json.dumps({"execution_scope": "ETF_ONLY"}), encoding="utf-8")
    h2 = compute_semantic_file_hash(p)
    assert h1 != h2


def test_target_hash_change_different_hash(tmp_path: Path) -> None:
    p = tmp_path / "doc.json"
    p.write_text(json.dumps({"target_hash": "aaa", "user_target_hash": "aaa"}), encoding="utf-8")
    h1 = compute_semantic_file_hash(p)
    p.write_text(json.dumps({"target_hash": "bbb", "user_target_hash": "aaa"}), encoding="utf-8")
    h2 = compute_semantic_file_hash(p)
    assert h1 != h2


def test_pmi_kr_semantic_fields_change_hash(tmp_path: Path) -> None:
    base = {"pmi_kr": {"status": "ok", "value": 50.0, "value_date": "2026-01-01", "stale_days": 0}}
    p = tmp_path / "dg.json"
    p.write_text(json.dumps(base), encoding="utf-8")
    h1 = compute_semantic_file_hash(p)
    changed = {**base, "pmi_kr": {**base["pmi_kr"], "stale_days": 3}}
    p.write_text(json.dumps(changed), encoding="utf-8")
    h2 = compute_semantic_file_hash(p)
    assert h1 != h2


def test_csv_mtime_only_same_content_same_hash(tmp_path: Path) -> None:
    p = tmp_path / "data.csv"
    p.write_text("ticker,score\nA,1\nB,2\n", encoding="utf-8")
    h1 = compute_semantic_file_hash(p)
    old = p.stat().st_mtime
    os.utime(p, (old - 3600, old - 3600))
    time.sleep(0.01)
    h2 = compute_semantic_file_hash(p)
    assert h1 == h2


def test_cache_miss_when_output_missing(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    spec = DiagnosticSpec("alpha_gate_diagnostics", ("alpha_gate_diagnostics.json",))
    dep_hash, _, per_file = compute_dependency_semantic_hash(data, out, dep_keys=spec.dep_keys)
    hit, reason, _, _ = should_cache_hit(
        spec, data_dir=data, output_dir=out, dep_hash=dep_hash, prev_entries={}, per_file_hashes=per_file,
    )
    assert hit is False
    assert reason == "output_missing"


def test_no_action_verify_mismatch_blocks_cache_hit(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    (out / "final_execution_decision.json").write_text(
        json.dumps({"execution_scope": "NO_TRADE", "allowed_actions": [], "final_trade_list": []}),
        encoding="utf-8",
    )
    (out / "no_action_diagnostics.json").write_text(
        json.dumps({
            "actual_buy_trace": {"final_actual_buy_allowed": 1},
            "status_alignment_pass": True,
            "status_alignment": {"authoritative_execution_scope": "NO_TRADE"},
        }),
        encoding="utf-8",
    )
    ok, reason = verify_no_action_cached(data, out)
    assert ok is False
    assert "actual_buy_mismatch" in reason


def test_semantic_cache_hit_second_run(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir(parents=True)
    out.mkdir(parents=True)
    (data / "target_portfolio.csv").write_text("ticker,weight\nCASH,1\n", encoding="utf-8")
    (data / "portfolio_policy.yaml").write_text("data_gate_policy: {}\n", encoding="utf-8")
    (out / "final_execution_decision.json").write_text(
        json.dumps({"execution_scope": "NO_TRADE", "run_id": "r1", "allowed_actions": [], "final_trade_list": []}),
        encoding="utf-8",
    )
    (out / "acceptance_report.json").write_text(json.dumps({"execution_scope": "NO_TRADE", "run_id": "r1"}), encoding="utf-8")
    (out / "daily_brief.json").write_text(json.dumps({"run_id": "r1"}), encoding="utf-8")

    outputs = [
        "alpha_shortlist_diagnostics.csv", "alpha_shortlist_summary.json",
        "policy_cap_counterfactual.json", "core_etf_permission_diagnostics.json",
        "core_etf_candidate_trace.csv", "data_gate_diagnostics.json",
        "data_gate_field_status.csv", "data_gate_to_permission_trace.json",
        "market_indicator_schema_diagnostics.json", "market_field_status.csv",
        "pmi_kr_source_policy.json", "data_gate_green_preflight.json",
        "alpha_gate_diagnostics.json",
    ]
    for name in outputs:
        p = out / name
        if name.endswith(".csv"):
            p.write_text("c\n1\n", encoding="utf-8")
        else:
            p.write_text("{}", encoding="utf-8")
    (out / "no_action_diagnostics.json").write_text(
        json.dumps({
            "actual_buy_trace": {"final_actual_buy_allowed": 0},
            "status_alignment_pass": True,
            "status_alignment": {"authoritative_execution_scope": "NO_TRADE"},
        }),
        encoding="utf-8",
    )

    with patch("src.validation.alpha_shortlist_diagnostics.write_alpha_shortlist_diagnostics"):
        with patch("src.validation.policy_cap_counterfactual.write_policy_cap_counterfactual"):
            with patch("src.validation.core_etf_permission_diagnostics.write_core_etf_permission_diagnostics"):
                with patch("src.validation.data_gate_diagnostics.write_data_gate_diagnostics"):
                    with patch("src.validation.alpha_gate_diagnostics.write_alpha_gate_diagnostics"):
                        with patch("src.validation.no_action_diagnostics.write_no_action_diagnostics"):
                            with patch("src.validation.kosis_tier2_refresh_diagnostics.run_kosis_tier2_refresh_with_diagnostics"):
                                prof1 = RuntimeProfiler(run_id="r1", run_mode="standard")
                                r1 = run_diagnostics_with_cache(data, out, run_id="r1", run_full_diag=False, profiler=prof1)
                                (out / "final_execution_decision.json").write_text(
                                    json.dumps({
                                        "execution_scope": "NO_TRADE",
                                        "run_id": "r2",
                                        "generated_at": "2026-07-07",
                                        "allowed_actions": [],
                                        "final_trade_list": [],
                                    }),
                                    encoding="utf-8",
                                )
                                prof2 = RuntimeProfiler(run_id="r2", run_mode="standard")
                                r2 = run_diagnostics_with_cache(data, out, run_id="r2", run_full_diag=False, profiler=prof2)

    assert r1.cache_miss_count <= 8
    assert r2.cache_hit_count >= 7
    assert prof2.diagnostics_hash_mode == "subset_semantic"
    assert prof2.diagnostics_semantic_cache_enabled is True


def test_normalize_strips_volatile_keys() -> None:
    doc = normalize_for_semantic_hash({
        "execution_scope": "NO_TRADE",
        "run_id": "x",
        "generated_at": "y",
        "target_hash": "abc",
    })
    assert "run_id" not in doc
    assert "generated_at" not in doc
    assert doc["target_hash"] == "abc"
