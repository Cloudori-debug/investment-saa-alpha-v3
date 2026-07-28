"""P0 — diagnostics must run once per pipeline; bundle_reconcile verifies only."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.runtime.diagnostics_cache import (
    DIAGNOSTIC_SPECS,
    verify_diagnostics_outputs,
)
from src.runtime.profiler import RuntimeProfiler


def _seed_diag_outputs(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "alpha_shortlist_diagnostics.csv": "t\n1\n",
        "alpha_shortlist_summary.json": "{}",
        "policy_cap_counterfactual.json": '{"policy_cap": "YELLOW_STABLE"}',
        "core_etf_permission_diagnostics.json": '{"core_etf_permission": "RESTRICTED"}',
        "core_etf_candidate_trace.csv": "t\n1\n",
        "data_gate_diagnostics.json": '{"data_gate_status": "GREEN"}',
        "data_gate_field_status.csv": "f\n1\n",
        "data_gate_to_permission_trace.json": "{}",
        "market_indicator_schema_diagnostics.json": "{}",
        "market_field_status.csv": "f\n1\n",
        "pmi_kr_source_policy.json": "{}",
        "data_gate_green_preflight.json": "{}",
        "alpha_gate_diagnostics.json": '{"alpha_gate_status": "GREEN"}',
        "no_action_diagnostics.json": json.dumps({
            "status_alignment_pass": True,
            "actual_buy_trace": {"final_actual_buy_allowed": 0},
            "status_alignment": {"authoritative_execution_scope": "NO_TRADE"},
        }),
    }
    for name, content in files.items():
        (out / name).write_text(content, encoding="utf-8")


def _seed_deps(data: Path, out: Path) -> None:
    data.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    (data / "market_indicators.csv").write_text("date\n2026-01-01\n", encoding="utf-8")
    (data / "portfolio_policy.yaml").write_text("data_gate_policy: {}\n", encoding="utf-8")
    (out / "final_execution_decision.json").write_text(
        json.dumps({"execution_scope": "NO_TRADE", "allowed_actions": [], "final_trade_list": []}),
        encoding="utf-8",
    )
    (out / "acceptance_report.json").write_text(json.dumps({"execution_scope": "NO_TRADE"}), encoding="utf-8")
    (out / "daily_brief.json").write_text("{}", encoding="utf-8")


def test_reconcile_does_not_call_run_diagnostics_with_cache(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_deps(data, out)
    _seed_diag_outputs(out)

    with patch("src.validation.bundle_consistency.finalize_health_snapshot") as mock_health:
        mock_health.return_value = MagicMock(
            to_dict=lambda: {"checks": [], "overall": "ok", "as_of": "2026-01-01", "meta": {}},
            as_of="2026-01-01",
            overall="ok",
            checks=[],
            summary={},
        )
        with patch("src.validation.bundle_consistency.run_acceptance_check") as mock_acc:
            mock_acc.return_value = MagicMock(
                to_dict=lambda: {"execution_scope": "NO_TRADE"},
                execution_scope="NO_TRADE",
                overall="ok",
            )
            with patch("src.validation.bundle_consistency.verify_bundle_snapshot_alignment", return_value={"aligned": True, "issues": []}):
                with patch("src.validation.bundle_consistency.detect_snapshot_stale_after_target_write", return_value={"stale": False}):
                    with patch("src.validation.bundle_consistency.refresh_daily_report_authoritative"):
                        with patch("src.report.authoritative_status.refresh_daily_brief_authoritative"):
                            with patch("src.report.authoritative_status.patch_alpha_v2_execution_context"):
                                with patch("src.validation.green_layers.evaluate_green_layers", return_value={}):
                                    with patch("src.validation.saa_restart_readiness.write_saa_restart_readiness_report", return_value={}):
                                        with patch("src.validation.ai_export.build_ai_export_bundle", return_value={}):
                                            with patch("src.validation.ai_export.write_ai_export_json"):
                                                with patch("src.report.execution_metrics.validate_report_clarity", return_value={"pass": True}):
                                                    with patch(
                                                        "src.runtime.diagnostics_cache.run_diagnostics_with_cache",
                                                    ) as mock_run:
                                                        from src.validation.bundle_consistency import reconcile_bundle_artifacts

                                                        reconcile_bundle_artifacts(
                                                            data, out, run_id="r1", as_of="2026-01-01",
                                                        )
    mock_run.assert_not_called()
    doc = json.loads((out / "bundle_consistency_validation.json").read_text(encoding="utf-8"))
    assert "diagnostics_verify" in doc
    assert doc["diagnostics_verify"]["diagnostics_ready"] is True


def test_verify_diagnostics_outputs_missing_records_fail(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_deps(data, out)
    result = verify_diagnostics_outputs(data, out, run_id="r1")
    assert result["diagnostics_ready"] is False
    assert result["pass"] is False
    assert len(result["missing_outputs"]) > 0


def test_run_diagnostics_increments_invocation_count(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_deps(data, out)
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    with patch("src.validation.alpha_shortlist_diagnostics.write_alpha_shortlist_diagnostics"):
        with patch("src.validation.policy_cap_counterfactual.write_policy_cap_counterfactual"):
            with patch("src.validation.core_etf_permission_diagnostics.write_core_etf_permission_diagnostics"):
                with patch("src.validation.data_gate_diagnostics.write_data_gate_diagnostics"):
                    with patch("src.validation.alpha_gate_diagnostics.write_alpha_gate_diagnostics"):
                        with patch("src.validation.no_action_diagnostics.write_no_action_diagnostics"):
                            with patch(
                                "src.validation.kosis_tier2_refresh_diagnostics.run_kosis_tier2_refresh_with_diagnostics",
                                return_value=(None, {"manual_required_fields": ["pmi_kr"], "refreshed_fields": [], "failed_fields": []}),
                            ):
                                from src.runtime.diagnostics_cache import run_diagnostics_with_cache

                                run_diagnostics_with_cache(data, out, run_id="r1", run_full_diag=True, profiler=prof)
    assert prof.diagnostics_invocation_count == 1
    assert prof.diagnostics_cache_miss_count <= 8


def test_all_diagnostic_specs_have_unique_output_files() -> None:
    seen: set[str] = set()
    for spec in DIAGNOSTIC_SPECS:
        for fname in spec.output_files:
            assert fname not in seen or fname in {
                "pmi_kr_source_policy.json",
                "data_gate_green_preflight.json",
            }
            seen.add(fname)
