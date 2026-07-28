"""Authoritative status snapshot aligns daily_brief and report summary with acceptance."""
from __future__ import annotations

import json
from pathlib import Path

from src.report.authoritative_status import build_authoritative_status_snapshot
from src.report.export_daily_brief import export_daily_brief
from src.report_writer import build_daily_report_status_summary
from src.validation.market_gate import collect_market_gate_inputs, evaluate_market_layer


def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _minimal_green_fixture(tmp_path: Path) -> tuple[Path, Path]:
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
        "market_triggers:\n  kospi:\n    crisis_zone: -20\n    pullback_buy_1: -5\n"
        "  vix:\n    caution_above: 20\n    risk_off_above: 25\n    panic_above: 30\n"
        "  usdkrw:\n    stable_level: 1500\n    risk_level: 1550\n",
        encoding="utf-8",
    )
    (data / "compass_rules.yaml").write_text("usdkrw:\n  stress_above: 1550\n", encoding="utf-8")
    health = {
        "overall": "pass",
        "checks": [{
            "name": "target_portfolio_guard",
            "status": "pass",
            "detail": {
                "severity": "PASS",
                "current_hash": "abc",
                "user_target_hash": "abc",
                "changed_rows": 0,
                "system_proposal_leak_count": 0,
                "unknown_material_count": 0,
            },
        }],
    }
    acceptance = {
        "overall": "RED",
        "operational_overall": "RED",
        "technical_overall": "GREEN",
        "execution_scope": "NO_TRADE",
        "items": [
            {"id": "AC-02", "name": "unified_data_gate", "status": "fail", "message": "gate=RED"},
            {"id": "AC-03", "name": "portfolio_gate", "status": "fail", "message": "gate=RED"},
        ],
    }
    final = {
        "as_of": "2026-07-03",
        "run_id": "run-1",
        "data_gate": "GREEN",
        "execution_scope": "ETF_ONLY",
        "system_status": "YELLOW",
        "technical_status": {"system_status": "YELLOW", "data_gate": "YELLOW"},
        "policy_cap": {"active": True, "cap_regime": "YELLOW_STABLE"},
        "group_gaps": [{"asset_group": "kr_alpha", "current": 42.7}],
        "execution_permissions": {
            "alpha_sector_data_gate": "YELLOW",
            "gates": {"data_gate": "GREEN", "alpha_gate": "GREEN"},
        },
        "allowed_actions": [],
        "final_trade_list": [],
    }
    _write_json(out / "system_health.json", health)
    _write_json(out / "acceptance_report.json", acceptance)
    _write_json(out / "final_execution_decision.json", final)
    _write_json(out / "shadow_diagnostic.json", {"execution": {}, "signals": {}, "gates": {"dry_run_required": 10}})
    return data, out


def test_daily_brief_matches_acceptance_not_stale_final(tmp_path: Path) -> None:
    data, out = _minimal_green_fixture(tmp_path)
    brief = export_daily_brief(out, data_dir=data)
    assert brief["system_status"]["acceptance_overall"] == "RED"
    assert brief["system_status"]["execution_scope"] == "NO_TRADE"
    assert brief["system_status"]["technical_status"] == "GREEN"
    assert brief["system_status"]["operational_status"] == "RED"
    assert brief["system_status"]["unified_data_gate"] == "RED"
    assert brief["system_status"]["portfolio_gate"] == "RED"


def test_daily_report_summary_matches_green_layers(tmp_path: Path) -> None:
    data, out = _minimal_green_fixture(tmp_path)
    lines = build_daily_report_status_summary(out)
    text = "\n".join(lines)
    assert "technical_status**: `GREEN`" in text
    assert "operational_status**: `RED`" in text
    assert "scope `NO_TRADE`" in text


def test_market_blockers_use_acceptance_red_gates(tmp_path: Path) -> None:
    data, out = _minimal_green_fixture(tmp_path)
    final = json.loads((out / "final_execution_decision.json").read_text(encoding="utf-8"))
    acceptance = json.loads((out / "acceptance_report.json").read_text(encoding="utf-8"))
    inputs = collect_market_gate_inputs(data, out, final_doc=final, acceptance_doc=acceptance)
    ev = evaluate_market_layer(inputs, actual_buy_allowed=0, conflict_detected=False)
    assert "unified_data_gate=RED" in ev["market_blockers"]
    assert "portfolio_gate=RED" in ev["market_blockers"]
    assert "data_gate=YELLOW" not in ev["market_blockers"]


def test_alpha_v2_execution_context_uses_authoritative_status(tmp_path: Path) -> None:
    data, out = _minimal_green_fixture(tmp_path)
    from src.report.authoritative_status import patch_alpha_v2_execution_context

    (out / "alpha_v2_summary.json").write_text(
        json.dumps({
            "execution_context": {
                "actual_buy_allowed": 0,
                "no_trade": False,
                "execution_scope": "ETF_ONLY",
                "market_status": "YELLOW",
            },
        }),
        encoding="utf-8",
    )
    patch_alpha_v2_execution_context(data, out)
    v2 = json.loads((out / "alpha_v2_summary.json").read_text(encoding="utf-8"))
    ctx = v2["execution_context"]
    assert ctx["execution_scope"] == "NO_TRADE"
    assert ctx["no_trade"] is True
    assert ctx.get("authoritative_source") == "acceptance+green_layers"


def test_daily_report_scope_matches_acceptance(tmp_path: Path) -> None:
    data, out = _minimal_green_fixture(tmp_path)
    from src.report_writer import build_daily_report_status_summary

    lines = build_daily_report_status_summary(out)
    text = "\n".join(lines)
    assert "Scope**: `NO_TRADE`" in text
    assert "scope `ETF_ONLY`" not in text


def test_authoritative_scope_alignment(tmp_path: Path) -> None:
    data, out = _minimal_green_fixture(tmp_path)
    from src.report.execution_metrics import validate_report_clarity

    brief = export_daily_brief(out, data_dir=data)
    (out / "daily_brief.json").write_text(json.dumps(brief, ensure_ascii=False), encoding="utf-8")
    (out / "daily_report.md").write_text(
        "- **system_health_overall**: pass\n\n"
        + "\n".join(build_daily_report_status_summary(out))
        + "\n## 1. Test\n",
        encoding="utf-8",
    )
    from src.report.authoritative_status import patch_alpha_v2_execution_context

    (out / "alpha_v2_summary.json").write_text(
        json.dumps({"execution_context": {"execution_scope": "ETF_ONLY"}}),
        encoding="utf-8",
    )
    patch_alpha_v2_execution_context(data, out)
    result = validate_report_clarity(out)
    assert result["pass"] is True


def test_daily_brief_execution_operational_verdict_aligned(tmp_path: Path) -> None:
    data, out = _minimal_green_fixture(tmp_path)
    brief = export_daily_brief(out, data_dir=data)
    assert brief["execution"]["execution_scope"] == "NO_TRADE"
    assert brief["execution"]["no_trade"] is True
    assert "RED" in str(brief["execution"].get("acceptance_overall") or brief["system_status"]["acceptance_overall"])


def test_authoritative_snapshot_fields(tmp_path: Path) -> None:
    data, out = _minimal_green_fixture(tmp_path)
    snap = build_authoritative_status_snapshot(data, out)
    assert snap["acceptance_overall"] == "RED"
    assert snap["execution_scope"] == "NO_TRADE"
    assert snap["unified_data_gate"] == "RED"
