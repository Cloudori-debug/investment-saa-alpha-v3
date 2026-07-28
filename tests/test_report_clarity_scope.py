"""P4e — dual scope (authoritative NO_TRADE vs display ETF_ONLY) clarity tests."""
from __future__ import annotations

import json
from pathlib import Path

from src.report.authoritative_status import sync_acceptance_authoritative_scope_fields
from src.report.execution_metrics import validate_report_clarity
from src.report.export_daily_brief import export_daily_brief
from src.report_writer import build_daily_report_status_summary


def _dual_scope_fixture(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    (data / "portfolio_policy.yaml").write_text("risk_limits:\n  kr_alpha_max: 35\n", encoding="utf-8")
    (data / "market_indicators.csv").write_text(
        "date,kospi,kospi_recent_high,vix,usdkrw,foreign_flow_3d\n"
        "2026-07-03,8000,9000,16,1480,neutral\n",
        encoding="utf-8",
    )
    (data / "trigger_rules.yaml").write_text(
        "market_triggers:\n  kospi:\n    crisis_zone: -20\n"
        "  vix:\n    caution_above: 20\n  usdkrw:\n    stable_level: 1500\n",
        encoding="utf-8",
    )
    (data / "compass_rules.yaml").write_text("usdkrw:\n  stress_above: 1550\n", encoding="utf-8")
    final = {
        "as_of": "2026-07-03",
        "run_id": "run-dual",
        "data_gate": "YELLOW",
        "execution_scope": "ETF_ONLY",
        "system_status": "YELLOW",
        "target_guard_conflict_detected": True,
        "dry_run_days": 12,
        "operating": {"dry_run_required": 10},
        "allowed_actions": [],
        "final_trade_list": [],
        "execution_permissions": {
            "alpha_auto_buy_permission": "BLOCKED",
            "core_etf_permission": "RESTRICTED",
        },
        "policy_cap": {"active": True, "cap_regime": "YELLOW_STABLE", "technical_execution_scope": "ETF_ONLY"},
    }
    acceptance = {
        "overall": "YELLOW",
        "execution_scope": "ETF_ONLY",
        "operational_verdict": "Overall YELLOW · Scope ETF_ONLY",
        "items": [
            {"id": "AC-02", "name": "unified_data_gate", "status": "warn", "message": "gate=YELLOW"},
            {"id": "AC-03", "name": "portfolio_gate", "status": "pass", "message": "gate=GREEN"},
        ],
    }
    health = {
        "overall": "warn",
        "checks": [{
            "name": "target_portfolio_guard",
            "status": "pass",
            "detail": {"severity": "PASS", "changed_rows": 0},
        }],
    }
    (out / "final_execution_decision.json").write_text(json.dumps(final), encoding="utf-8")
    (out / "acceptance_report.json").write_text(json.dumps(acceptance), encoding="utf-8")
    (out / "system_health.json").write_text(json.dumps(health), encoding="utf-8")
    (out / "shadow_diagnostic.json").write_text(
        json.dumps({"execution": {}, "signals": {}, "gates": {"dry_run_required": 10}}),
        encoding="utf-8",
    )
    return data, out


def test_dual_scope_clarity_passes_with_explanation(tmp_path: Path) -> None:
    data, out = _dual_scope_fixture(tmp_path)
    sync_acceptance_authoritative_scope_fields(data, out)
    brief = export_daily_brief(out, data_dir=data)
    (out / "daily_brief.json").write_text(json.dumps(brief, ensure_ascii=False), encoding="utf-8")
    summary = build_daily_report_status_summary(out)
    (out / "daily_report.md").write_text(
        "- **system_health_overall**: WARN\n\n" + "\n".join(summary) + "\n## 1. Test\n",
        encoding="utf-8",
    )
    from src.report.authoritative_status import patch_alpha_v2_execution_context

    (out / "alpha_v2_summary.json").write_text(
        json.dumps({"execution_context": {"execution_scope": "ETF_ONLY"}}),
        encoding="utf-8",
    )
    patch_alpha_v2_execution_context(data, out)
    result = validate_report_clarity(out)
    assert result["pass"] is True, result.get("failures")


def test_sync_daily_report_system_health_overall(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "system_health.json").write_text(json.dumps({"overall": "warn"}), encoding="utf-8")
    (out / "daily_report.md").write_text(
        "## 1. Test\n- **system_health_overall**: **PASS**\n",
        encoding="utf-8",
    )
    from src.report.execution_metrics import sync_daily_report_system_health_overall, validate_report_clarity

    assert sync_daily_report_system_health_overall(out) is True
    text = (out / "daily_report.md").read_text(encoding="utf-8")
    assert "**WARN**" in text
    assert "PASS" not in text.split("**system_health_overall**")[1][:20]
