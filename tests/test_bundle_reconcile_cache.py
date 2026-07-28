"""Tests for bundle reconcile incremental cache v0.1."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.runtime.bundle_reconcile_cache import (
    MANIFEST_JSON,
    TRACKED_OUTPUT_FILES,
    _partition_files,
    reconcile_bundle_artifacts_with_cache,
    run_always_safety_checks,
    scan_tracked_files,
    write_manifest,
)


def _seed_tracked_outputs(out: Path, *, content: str = "{}") -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name in TRACKED_OUTPUT_FILES:
        (out / name).write_text(content, encoding="utf-8")


def _write_pass_manifest_from_scan(out: Path, run_id: str = "prev-run") -> None:
    file_states = scan_tracked_files(out)
    files_doc = {}
    for rel, state in file_states.items():
        files_doc[rel] = {
            **state,
            "reconcile_status": "pass",
            "last_check_seconds": 45,
        }
    (out / MANIFEST_JSON).write_text(
        json.dumps({
            "run_id": run_id,
            "files": files_doc,
            "cache_hit_count": len(files_doc),
            "cache_miss_count": 0,
        }),
        encoding="utf-8",
    )


def _minimal_data(data: Path) -> None:
    data.mkdir(parents=True, exist_ok=True)
    (data / "market_indicators.csv").write_text("date\n2026-01-01\n", encoding="utf-8")
    (data / "portfolio_policy.yaml").write_text("data_gate_policy: {}\n", encoding="utf-8")


_ALWAYS_PASS = {"pass": True, "actual_buy_allowed": 0, "authoritative_status": {}}


def _minimal_safety_outputs(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "final_execution_decision.json").write_text(
        json.dumps({"execution_scope": "NO_TRADE", "allowed_actions": [], "final_trade_list": []}),
        encoding="utf-8",
    )
    (out / "no_action_diagnostics.json").write_text(
        json.dumps({
            "actual_buy_trace": {"final_actual_buy_allowed": 0},
            "status_alignment_pass": True,
            "status_alignment": {"authoritative_execution_scope": "NO_TRADE"},
        }),
        encoding="utf-8",
    )
    (out / "daily_report.md").write_text("## 최종 실행 권위\n", encoding="utf-8")
    (out / "daily_brief.json").write_text("{}", encoding="utf-8")
    (out / "acceptance_report.json").write_text(json.dumps({"execution_scope": "NO_TRADE"}), encoding="utf-8")
    (out / "system_health.json").write_text(
        json.dumps({
            "checks": [{
                "name": "target_portfolio_guard",
                "status": "pass",
                "detail": {"severity": "PASS", "current_hash": "abc", "user_target_hash": "abc"},
            }],
        }),
        encoding="utf-8",
    )


def test_partition_reuses_matching_pass_files() -> None:
    current = {
        "outputs/a.json": {"exists": True, "hash": "aaa"},
        "outputs/b.json": {"exists": True, "hash": "bbb"},
    }
    prev = {
        "outputs/a.json": {"hash": "aaa", "reconcile_status": "pass", "last_check_seconds": 30},
        "outputs/b.json": {"hash": "bbb", "reconcile_status": "pass", "last_check_seconds": 40},
    }
    reused, rechecked, saved = _partition_files(current, prev)
    assert reused == ["outputs/a.json", "outputs/b.json"]
    assert rechecked == []
    assert saved == 70


def test_partition_rechecks_on_hash_change() -> None:
    current = {"outputs/a.json": {"exists": True, "hash": "new"}}
    prev = {"outputs/a.json": {"hash": "old", "reconcile_status": "pass", "last_check_seconds": 30}}
    reused, rechecked, _ = _partition_files(current, prev)
    assert reused == []
    assert rechecked == ["outputs/a.json"]


def test_partition_rechecks_missing_file() -> None:
    current = {"outputs/a.json": {"exists": False, "hash": "missing"}}
    prev = {"outputs/a.json": {"hash": "aaa", "reconcile_status": "pass", "last_check_seconds": 30}}
    reused, rechecked, _ = _partition_files(current, prev)
    assert reused == []
    assert rechecked == ["outputs/a.json"]


def test_partition_no_reuse_after_prior_fail() -> None:
    current = {"outputs/a.json": {"exists": True, "hash": "aaa"}}
    prev = {"outputs/a.json": {"hash": "aaa", "reconcile_status": "fail", "last_check_seconds": 30}}
    reused, rechecked, _ = _partition_files(current, prev)
    assert reused == []
    assert rechecked == ["outputs/a.json"]


def test_cache_hit_fast_path(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _minimal_data(data)
    _seed_tracked_outputs(out)
    _minimal_safety_outputs(out)
    _write_pass_manifest_from_scan(out)

    alignment = {"aligned": True, "issues": [], "hashes": {}, "target_hash": "abc"}
    with patch(
        "src.validation.bundle_consistency.detect_snapshot_stale_after_target_write",
        return_value={"stale": False},
    ):
        with patch(
            "src.validation.bundle_consistency.verify_bundle_snapshot_alignment",
            return_value=alignment,
        ) as mock_align:
            with patch(
                "src.validation.bundle_consistency.reconcile_bundle_artifacts",
            ) as mock_full:
                with patch(
                    "src.runtime.bundle_reconcile_cache.run_always_safety_checks",
                    return_value=_ALWAYS_PASS,
                ):
                    from src.runtime.profiler import RuntimeProfiler

                    prof = RuntimeProfiler(run_id="r2", run_mode="standard")
                    result = reconcile_bundle_artifacts_with_cache(
                        data, out, run_id="r2", as_of="2026-01-01", profiler=prof,
                    )
    mock_full.assert_not_called()
    mock_align.assert_called_once()
    assert result.get("cache_hit") is True
    assert len(result.get("reused_files") or []) == len(TRACKED_OUTPUT_FILES)
    assert prof.bundle_reconcile_cache_hit_count == len(TRACKED_OUTPUT_FILES)
    assert prof.bundle_reconcile_cache_miss_count == 0
    manifest = json.loads((out / MANIFEST_JSON).read_text(encoding="utf-8"))
    assert manifest["cache_hit_count"] == len(TRACKED_OUTPUT_FILES)


def test_hash_change_triggers_full_reconcile(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _minimal_data(data)
    _seed_tracked_outputs(out)
    _minimal_safety_outputs(out)
    _write_pass_manifest_from_scan(out)
    (out / "alpha_v2_summary.json").write_text('{"changed": true}', encoding="utf-8")

    with patch(
        "src.validation.bundle_consistency.detect_snapshot_stale_after_target_write",
        return_value={"stale": False},
    ):
        with patch(
            "src.runtime.bundle_reconcile_cache.run_always_safety_checks",
            return_value=_ALWAYS_PASS,
        ):
            with patch(
                "src.runtime.bundle_reconcile_cache._full_reconcile",
                return_value={"alignment": {"aligned": True}, "full_reconcile_ran": True},
            ) as mock_full:
                reconcile_bundle_artifacts_with_cache(
                    data, out, run_id="r2", as_of="2026-01-01",
                )
    mock_full.assert_called_once()
    call_result = mock_full.call_args.kwargs["result"]
    assert "outputs/alpha_v2_summary.json" in call_result.rechecked_files


def test_always_checks_run_on_cache_hit(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _minimal_data(data)
    _seed_tracked_outputs(out)
    _minimal_safety_outputs(out)
    _write_pass_manifest_from_scan(out)

    with patch(
        "src.validation.bundle_consistency.detect_snapshot_stale_after_target_write",
        return_value={"stale": False},
    ):
        with patch(
            "src.validation.bundle_consistency.verify_bundle_snapshot_alignment",
            return_value={"aligned": True, "issues": []},
        ):
            with patch(
                "src.runtime.bundle_reconcile_cache.run_always_safety_checks",
                return_value={"pass": True, "actual_buy_allowed": 0},
            ) as mock_always:
                result = reconcile_bundle_artifacts_with_cache(
                    data, out, run_id="r2", as_of="2026-01-01",
                )
    mock_always.assert_called_once()
    assert result["always_checks"]["actual_buy_allowed"] == 0


def test_actual_buy_allowed_always_checked(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _minimal_data(data)
    _minimal_safety_outputs(out)
    (out / "decision_log.jsonl").write_text("", encoding="utf-8")

    with patch("src.validation.system_health.run_input_health_checks") as mock_health:
        guard = MagicMock()
        guard.name = "target_portfolio_guard"
        guard.status = "pass"
        guard.detail = {"severity": "PASS", "current_hash": "x", "user_target_hash": "x"}
        mock_health.return_value = MagicMock(checks=[guard])
        with patch("src.report.authoritative_status.resolve_authoritative_execution", return_value={}):
            with patch("src.report.execution_metrics.validate_report_clarity", return_value={"pass": True}):
                with patch("src.alpha.target_write_audit.get_last_target_write_audit", return_value={}):
                    checks = run_always_safety_checks(data, out, run_id="r1")
    assert checks["actual_buy_allowed"] == 0


def test_authoritative_status_always_checked(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _minimal_data(data)
    _minimal_safety_outputs(out)

    with patch("src.validation.system_health.run_input_health_checks") as mock_health:
        guard = MagicMock()
        guard.name = "target_portfolio_guard"
        guard.status = "pass"
        guard.detail = {"severity": "PASS"}
        mock_health.return_value = MagicMock(checks=[guard])
        with patch(
            "src.report.authoritative_status.resolve_authoritative_execution",
            return_value={"execution_scope": "NO_TRADE", "unified_data_gate": "GREEN"},
        ) as mock_auth:
            with patch("src.report.execution_metrics.validate_report_clarity", return_value={"pass": True}):
                with patch("src.alpha.target_write_audit.get_last_target_write_audit", return_value={}):
                    checks = run_always_safety_checks(data, out, run_id="r1")
    mock_auth.assert_called()
    assert checks["authoritative_status"]["execution_scope"] == "NO_TRADE"


def test_fast_path_writes_consistency_from_alignment(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _minimal_data(data)
    _seed_tracked_outputs(out)
    _minimal_safety_outputs(out)
    _write_pass_manifest_from_scan(out)

    with patch(
        "src.validation.bundle_consistency.detect_snapshot_stale_after_target_write",
        return_value={"stale": False},
    ):
        with patch(
            "src.validation.bundle_consistency.verify_bundle_snapshot_alignment",
            return_value={"aligned": True, "issues": [], "hashes": {"h": 1}, "target_hash": "t1"},
        ):
            with patch("src.runtime.bundle_reconcile_cache.run_always_safety_checks", return_value=_ALWAYS_PASS):
                reconcile_bundle_artifacts_with_cache(data, out, run_id="r2", as_of="2026-01-01")

    doc = json.loads((out / "bundle_consistency_validation.json").read_text(encoding="utf-8"))
    assert doc["pass"] is True
    assert doc.get("cache_hit") is True


def test_target_write_not_allowed_in_always_checks(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _minimal_data(data)
    _minimal_safety_outputs(out)
    (out / "report_clarity_validation.json").write_text('{"pass": true}', encoding="utf-8")

    with patch("src.validation.system_health.run_input_health_checks") as mock_health:
        guard = MagicMock()
        guard.name = "target_portfolio_guard"
        guard.status = "pass"
        guard.detail = {"severity": "PASS"}
        mock_health.return_value = MagicMock(checks=[guard])
        with patch("src.report.authoritative_status.resolve_authoritative_execution", return_value={}):
            with patch("src.report.execution_metrics.validate_report_clarity", return_value={"pass": True}):
                with patch(
                    "src.alpha.target_write_audit.get_last_target_write_audit",
                    return_value={"target_write_allowed": False, "target_write_source": "blocked"},
                ):
                    checks = run_always_safety_checks(data, out, run_id="r1")
    assert checks["target_write_audit"]["allowed"] is False
    assert checks["pass"] is True, checks.get("failures")


def test_runtime_profile_records_bundle_cache(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _minimal_data(data)
    _seed_tracked_outputs(out)
    _minimal_safety_outputs(out)
    _write_pass_manifest_from_scan(out)

    with patch(
        "src.validation.bundle_consistency.detect_snapshot_stale_after_target_write",
        return_value={"stale": False},
    ):
        with patch(
            "src.validation.bundle_consistency.verify_bundle_snapshot_alignment",
            return_value={"aligned": True, "issues": []},
        ):
            with patch("src.runtime.bundle_reconcile_cache.run_always_safety_checks", return_value=_ALWAYS_PASS):
                from src.runtime.profiler import RuntimeProfiler

                prof = RuntimeProfiler(run_id="r2", run_mode="standard")
                reconcile_bundle_artifacts_with_cache(
                    data, out, run_id="r2", as_of="2026-01-01", profiler=prof,
                )
    doc = prof.to_dict()
    assert doc["bundle_reconcile_cache_hit_count"] == len(TRACKED_OUTPUT_FILES)
    assert doc["bundle_reconcile_cache_miss_count"] == 0
    assert doc["bundle_reconcile_saved_seconds_estimate"] > 0


def test_write_manifest_marks_reused_files(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir(parents=True)
    file_states = {
        "outputs/a.json": {"hash": "h1", "size": 2, "exists": True},
    }
    write_manifest(
        out,
        run_id="r1",
        file_states=file_states,
        reused=["outputs/a.json"],
        rechecked=[],
        reconcile_pass=True,
        always_checks={"pass": True},
        saved_estimate=30.0,
        reused_from_run_id="prev",
    )
    doc = json.loads((out / MANIFEST_JSON).read_text(encoding="utf-8"))
    assert doc["files"]["outputs/a.json"]["cache_hit"] is True
    assert doc["files"]["outputs/a.json"]["reused_from_run_id"] == "prev"
