"""P3b — research_outputs cache tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.runtime.research_outputs_cache import (
    MANIFEST_JSON,
    REQUIRED_RESEARCH_OUTPUTS,
    compute_dependency_hash,
    compute_research_dependency_hashes,
    evaluate_research_outputs_cache,
    maybe_run_research_outputs,
    write_research_outputs_manifest,
)


def _seed_deps(data_dir: Path, output_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "target_portfolio.csv").write_text(
        "ticker,asset_group,target_weight\nAAA,kr_alpha,1.0\n", encoding="utf-8",
    )
    (data_dir / "positions.csv").write_text("ticker,qty,asset_group\n", encoding="utf-8")
    (data_dir / "market_indicators.csv").write_text("date,regime\n2026-01-01,NEUTRAL\n", encoding="utf-8")
    (data_dir / "portfolio_policy.yaml").write_text("execution_policy: {}\n", encoding="utf-8")
    (output_dir / "final_execution_decision.json").write_text(
        json.dumps(
            {
                "data_gate": "YELLOW",
                "execution_scope": "ETF_ONLY",
                "execution_permissions": {"alpha_auto_buy_permission": "BLOCKED"},
                "policy_cap": {},
                "technical_status": {},
                "operating": {},
                "executable_actions": [],
            },
        ),
        encoding="utf-8",
    )
    for name in (
        "alpha_v2_summary.json",
        "alpha_v2_scored.csv",
        "alpha_v2_final_candidates.csv",
        "alpha_v2_top30.csv",
        "flow_dashboard_summary.json",
        "alpha_shortlist_summary.json",
        "alpha_gate_diagnostics.json",
        "policy_cap_counterfactual.json",
        "core_etf_permission_diagnostics.json",
    ):
        (output_dir / name).write_text("{}", encoding="utf-8")


def _seed_required_outputs(output_dir: Path) -> None:
    for name in REQUIRED_RESEARCH_OUTPUTS:
        (output_dir / name).write_text("{}", encoding="utf-8")


def test_cache_hit_when_deps_and_outputs_match(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    _seed_required_outputs(output_dir)
    hashes = compute_research_dependency_hashes(data_dir, output_dir)
    dep_hash = compute_dependency_hash(hashes)
    write_research_outputs_manifest(
        output_dir,
        {
            "dependency_hash": dep_hash,
            "dependency_file_hashes": hashes,
            "elapsed_seconds": 66.0,
        },
    )
    decision = evaluate_research_outputs_cache(data_dir, output_dir, run_mode="standard")
    assert decision["cache_hit"] is True
    assert decision["skip_reason"] == "dependency_unchanged"


def test_recompute_when_dependency_changes(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    _seed_required_outputs(output_dir)
    hashes = compute_research_dependency_hashes(data_dir, output_dir)
    write_research_outputs_manifest(
        output_dir,
        {"dependency_hash": "deadbeef00000000", "dependency_file_hashes": hashes},
    )
    decision = evaluate_research_outputs_cache(data_dir, output_dir, run_mode="standard")
    assert decision["cache_hit"] is False
    assert decision["dependency_hash_changed"] is True


def test_recompute_when_outputs_missing(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    decision = evaluate_research_outputs_cache(data_dir, output_dir, run_mode="standard")
    assert decision["cache_hit"] is False
    assert decision["missing_outputs"]


def test_run_id_only_change_keeps_hash(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    h1 = compute_dependency_hash(compute_research_dependency_hashes(data_dir, output_dir))
    doc = json.loads((output_dir / "alpha_v2_summary.json").read_text(encoding="utf-8"))
    doc["run_id"] = "run-a"
    (output_dir / "alpha_v2_summary.json").write_text(json.dumps(doc), encoding="utf-8")
    h2 = compute_dependency_hash(compute_research_dependency_hashes(data_dir, output_dir))
    doc["run_id"] = "run-b"
    doc["count"] = 1
    (output_dir / "alpha_v2_summary.json").write_text(json.dumps(doc), encoding="utf-8")
    h3 = compute_dependency_hash(compute_research_dependency_hashes(data_dir, output_dir))
    assert h1 == h2
    assert h1 != h3


def test_alpha_v2_summary_value_change_changes_hash(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    h1 = compute_dependency_hash(compute_research_dependency_hashes(data_dir, output_dir))
    (output_dir / "alpha_v2_summary.json").write_text(
        json.dumps({"candidate_count": 5}), encoding="utf-8",
    )
    h2 = compute_dependency_hash(compute_research_dependency_hashes(data_dir, output_dir))
    assert h1 != h2


def test_flow_summary_change_changes_hash(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    h1 = compute_dependency_hash(compute_research_dependency_hashes(data_dir, output_dir))
    (output_dir / "flow_dashboard_summary.json").write_text(
        json.dumps({"rows": 10}), encoding="utf-8",
    )
    h2 = compute_dependency_hash(compute_research_dependency_hashes(data_dir, output_dir))
    assert h1 != h2


def test_target_hash_change_changes_hash(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    h1 = compute_dependency_hash(compute_research_dependency_hashes(data_dir, output_dir))
    (data_dir / "target_portfolio.csv").write_text(
        "ticker,asset_group,target_weight\nBBB,kr_alpha,2.0\n", encoding="utf-8",
    )
    h2 = compute_dependency_hash(compute_research_dependency_hashes(data_dir, output_dir))
    assert h1 != h2


def test_bundle_only_no_recompute(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    _seed_required_outputs(output_dir)
    result = maybe_run_research_outputs(
        data_dir,
        output_dir,
        as_of="2026-01-01",
        run_id="test",
        run_mode="bundle_only",
    )
    assert result.cache_hit is True
    assert result.recomputed == []


def test_bundle_only_missing_outputs(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    result = maybe_run_research_outputs(
        data_dir,
        output_dir,
        as_of="2026-01-01",
        run_id="test",
        run_mode="bundle_only",
    )
    assert result.cache_hit is False


def test_manifest_written_on_cache_hit(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    _seed_required_outputs(output_dir)
    hashes = compute_research_dependency_hashes(data_dir, output_dir)
    write_research_outputs_manifest(
        output_dir,
        {
            "dependency_hash": compute_dependency_hash(hashes),
            "dependency_file_hashes": hashes,
            "elapsed_seconds": 55.0,
        },
    )
    result = maybe_run_research_outputs(
        data_dir,
        output_dir,
        as_of="2026-01-01",
        run_id="test",
        run_mode="standard",
    )
    assert result.cache_hit is True
    manifest = json.loads((output_dir / MANIFEST_JSON).read_text(encoding="utf-8"))
    assert manifest["cache_hit"] is True
    assert manifest["safety_check"]["actual_buy_allowed"] == 0
