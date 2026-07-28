"""P3d — report_export cache tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.runtime.report_export_cache import (
    MANIFEST_JSON,
    REQUIRED_REPORT_OUTPUTS,
    ReportExportWriteContext,
    compute_dependency_hash,
    compute_report_export_dependency_hashes,
    evaluate_report_export_cache,
    maybe_run_report_exports,
    write_report_export_manifest,
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
        "flow_dashboard_summary.json",
        "alpha_gate_diagnostics.json",
        "policy_cap_counterfactual.json",
        "acceptance_report.json",
        "system_health.json",
        "no_action_diagnostics.json",
    ):
        (output_dir / name).write_text("{}", encoding="utf-8")
    (output_dir / "research_outputs_manifest.json").write_text(
        json.dumps({"dependency_hash": "abc123"}), encoding="utf-8",
    )
    (output_dir / "shadow_history_manifest.json").write_text(
        json.dumps({"semantic_snapshot_key": "snap001"}), encoding="utf-8",
    )


def _seed_required_outputs(output_dir: Path) -> None:
    for name in REQUIRED_REPORT_OUTPUTS:
        (output_dir / name).write_text("{}", encoding="utf-8")


def _minimal_ctx(data_dir: Path, output_dir: Path) -> ReportExportWriteContext:
    return ReportExportWriteContext(
        data_dir=data_dir,
        output_dir=output_dir,
        run_id="test-run",
        as_of="2026-01-01",
        acceptance=type("A", (), {"items": []})(),
        data_gate="YELLOW",
        market=type("M", (), {"date": "2026-01-01"})(),
        gap_rows=[],
        alerts=[],
        actions=[],
        execution_level=1,
    )


def test_cache_hit_when_deps_and_outputs_match(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    _seed_required_outputs(output_dir)
    hashes = compute_report_export_dependency_hashes(data_dir, output_dir)
    dep_hash = compute_dependency_hash(hashes)
    write_report_export_manifest(
        output_dir,
        {
            "dependency_hash": dep_hash,
            "dependency_file_hashes": hashes,
            "elapsed_seconds": 2.0,
        },
    )
    decision = evaluate_report_export_cache(data_dir, output_dir, run_mode="standard")
    assert decision["cache_hit"] is True
    assert decision["skip_reason"] == "dependency_unchanged"


def test_recompute_when_dependency_changes(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    _seed_required_outputs(output_dir)
    hashes = compute_report_export_dependency_hashes(data_dir, output_dir)
    write_report_export_manifest(
        output_dir,
        {"dependency_hash": "deadbeef00000000", "dependency_file_hashes": hashes},
    )
    decision = evaluate_report_export_cache(data_dir, output_dir, run_mode="standard")
    assert decision["cache_hit"] is False
    assert decision["dependency_hash_changed"] is True


def test_recompute_when_outputs_missing(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    decision = evaluate_report_export_cache(data_dir, output_dir, run_mode="standard")
    assert decision["cache_hit"] is False
    assert decision["missing_outputs"]


def test_run_id_only_change_keeps_hash(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    h1 = compute_dependency_hash(compute_report_export_dependency_hashes(data_dir, output_dir))
    doc = json.loads((output_dir / "alpha_v2_summary.json").read_text(encoding="utf-8"))
    doc["run_id"] = "run-a"
    doc["generated_at"] = "t1"
    (output_dir / "alpha_v2_summary.json").write_text(json.dumps(doc), encoding="utf-8")
    h2 = compute_dependency_hash(compute_report_export_dependency_hashes(data_dir, output_dir))
    doc["run_id"] = "run-b"
    doc["count"] = 1
    (output_dir / "alpha_v2_summary.json").write_text(json.dumps(doc), encoding="utf-8")
    h3 = compute_dependency_hash(compute_report_export_dependency_hashes(data_dir, output_dir))
    assert h1 == h2
    assert h1 != h3


def test_actual_buy_allowed_change_changes_hash(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    h1 = compute_dependency_hash(compute_report_export_dependency_hashes(data_dir, output_dir))
    (output_dir / "final_execution_decision.json").write_text(
        json.dumps(
            {
                "data_gate": "YELLOW",
                "execution_scope": "ETF_ONLY",
                "executable_actions": [{"action": "BUY", "allowed": True}],
            },
        ),
        encoding="utf-8",
    )
    h2 = compute_dependency_hash(compute_report_export_dependency_hashes(data_dir, output_dir))
    assert h1 != h2


def test_execution_scope_change_changes_hash(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    h1 = compute_dependency_hash(compute_report_export_dependency_hashes(data_dir, output_dir))
    (output_dir / "final_execution_decision.json").write_text(
        json.dumps({"data_gate": "YELLOW", "execution_scope": "NO_TRADE", "executable_actions": []}),
        encoding="utf-8",
    )
    h2 = compute_dependency_hash(compute_report_export_dependency_hashes(data_dir, output_dir))
    assert h1 != h2


def test_target_hash_change_changes_hash(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    h1 = compute_dependency_hash(compute_report_export_dependency_hashes(data_dir, output_dir))
    (data_dir / "target_portfolio.csv").write_text(
        "ticker,asset_group,target_weight\nBBB,kr_alpha,2.0\n", encoding="utf-8",
    )
    h2 = compute_dependency_hash(compute_report_export_dependency_hashes(data_dir, output_dir))
    assert h1 != h2


def test_bundle_only_no_recompute(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    _seed_required_outputs(output_dir)
    result = maybe_run_report_exports(
        _minimal_ctx(data_dir, output_dir),
        run_mode="bundle_only",
    )
    assert result.cache_hit is True
    assert result.recomputed == []


def test_bundle_only_missing_outputs(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    result = maybe_run_report_exports(
        _minimal_ctx(data_dir, output_dir),
        run_mode="bundle_only",
    )
    assert result.cache_hit is False


def test_manifest_written_on_cache_hit(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    _seed_required_outputs(output_dir)
    hashes = compute_report_export_dependency_hashes(data_dir, output_dir)
    write_report_export_manifest(
        output_dir,
        {
            "dependency_hash": compute_dependency_hash(hashes),
            "dependency_file_hashes": hashes,
            "elapsed_seconds": 1.5,
        },
    )
    result = maybe_run_report_exports(
        _minimal_ctx(data_dir, output_dir),
        run_mode="standard",
    )
    assert result.cache_hit is True
    manifest = json.loads((output_dir / MANIFEST_JSON).read_text(encoding="utf-8"))
    assert manifest["cache_hit"] is True
    assert manifest["reused_outputs"] == list(REQUIRED_REPORT_OUTPUTS)


def test_safety_check_actual_buy_zero(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    _seed_required_outputs(output_dir)
    result = maybe_run_report_exports(
        _minimal_ctx(data_dir, output_dir),
        run_mode="bundle_only",
    )
    assert result.safety.get("actual_buy_allowed") == 0


def test_report_clarity_validation_runs_outside_cache_wrapper(tmp_path: Path) -> None:
    """full_pipeline always calls validate_report_clarity after report_exports."""
    from src.full_pipeline import run_full_pipeline  # noqa: F401

    source = Path(__file__).resolve().parents[1] / "src" / "full_pipeline.py"
    text = source.read_text(encoding="utf-8")
    clarity_idx = text.index("validate_report_clarity")
    report_exports_idx = text.rindex('with _core_step("report_exports")')
    assert clarity_idx > report_exports_idx


def test_maybe_run_skips_heavy_exports_on_cache_hit(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    _seed_deps(data_dir, output_dir)
    _seed_required_outputs(output_dir)
    (output_dir / "daily_brief.json").write_text('{"cached": true}', encoding="utf-8")
    hashes = compute_report_export_dependency_hashes(data_dir, output_dir)
    write_report_export_manifest(
        output_dir,
        {
            "dependency_hash": compute_dependency_hash(hashes),
            "dependency_file_hashes": hashes,
            "elapsed_seconds": 2.0,
        },
    )
    with patch("src.runtime.report_export_cache._run_report_exports") as mock_run:
        result = maybe_run_report_exports(
            _minimal_ctx(data_dir, output_dir),
            run_mode="standard",
        )
    mock_run.assert_not_called()
    assert result.cache_hit is True
    assert result.daily_brief.get("cached") is True
