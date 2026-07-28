"""P4c — smoke acceptance checks for P0~P3d cache-first contract."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"


@pytest.mark.smoke
def test_target_guard_pass_from_system_health() -> None:
    path = OUTPUTS / "system_health.json"
    if not path.exists():
        pytest.skip("system_health.json missing — run standard pipeline first")
    doc = json.loads(path.read_text(encoding="utf-8"))
    checks = doc.get("checks") or []
    guard = next((c for c in checks if c.get("name") == "target_portfolio_guard"), None)
    assert guard is not None, "target_portfolio_guard check missing"
    assert str(guard.get("status", "")).lower() != "fail"


@pytest.mark.smoke
def test_actual_buy_allowed_zero_from_final_decision() -> None:
    path = OUTPUTS / "final_execution_decision.json"
    if not path.exists():
        pytest.skip("final_execution_decision.json missing")
    from src.report.execution_metrics import count_executable_actions

    doc = json.loads(path.read_text(encoding="utf-8"))
    actual = int(count_executable_actions(doc).get("actual_buy_allowed_count") or 0)
    assert actual == 0


@pytest.mark.smoke
def test_run_mode_contract_pass_if_present() -> None:
    path = OUTPUTS / "run_mode_contract_validation.json"
    if not path.exists():
        pytest.skip("run_mode_contract_validation.json missing")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc.get("contract_pass") is True
    assert int(doc.get("pykrx_call_count") or 0) == 0


@pytest.mark.smoke
def test_standard_cache_hit_baseline_summary() -> None:
    path = OUTPUTS / "standard_cache_hit_baseline.json"
    if not path.exists():
        path = ROOT / "outputs" / "baselines" / "runtime_profile_standard_p4_baseline_2.json"
        if not path.exists():
            pytest.skip("baseline artifacts missing")
        prof = json.loads(path.read_text(encoding="utf-8"))
        assert prof.get("pykrx_call_count") == 0
        assert prof.get("report_export_cache_hit") is True
        assert prof.get("research_outputs_cache_hit") is True
        assert prof.get("shadow_history_cache_hit") is True
        assert prof.get("post_decision_artifacts_cache_hit") is True
        return
    doc = json.loads(path.read_text(encoding="utf-8"))
    summary = doc.get("summary") or {}
    assert summary.get("all_contract_pass") is True
    assert summary.get("pykrx_call_count") == 0
    assert summary.get("actual_buy_allowed") == 0
    assert summary.get("target_write_count") == 0
    assert summary.get("all_cache_hits") is True


@pytest.mark.smoke
def test_report_clarity_validation_if_present() -> None:
    path = OUTPUTS / "report_clarity_validation.json"
    if not path.exists():
        pytest.skip("report_clarity_validation.json missing")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert "pass" in doc
    if doc.get("pass") is False:
        pytest.fail(f"report_clarity failed: {doc.get('failures')}")


@pytest.mark.smoke
def test_target_write_audit_zero_if_present() -> None:
    from src.alpha.target_write_audit import get_last_target_write_audit

    audit = get_last_target_write_audit(OUTPUTS)
    if not audit:
        pytest.skip("target write audit missing")
    assert int(audit.get("target_write_count") or 0) == 0


@pytest.mark.smoke
def test_quick_run_config_cache_only() -> None:
    from src.runtime.run_mode import RunMode, resolve_run_config

    cfg = resolve_run_config(RunMode.QUICK)
    assert cfg.refresh_network is False
    assert cfg.run_alpha_v2 is False
    assert cfg.run_research_outputs is False
    assert cfg.run_shadow_history is False
    assert cfg.pykrx_flow_refresh is False


@pytest.mark.smoke
def test_standard_run_config_cache_first() -> None:
    from src.runtime.run_mode import RunMode, resolve_run_config

    cfg = resolve_run_config(RunMode.STANDARD)
    assert cfg.refresh_network is False
    assert cfg.alpha_v2_cache_reuse is True
    assert cfg.flow_refresh_mode == "cache_first"
