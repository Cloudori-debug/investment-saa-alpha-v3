"""Tests for no_action_diagnostics and gate detail enrichment."""
from __future__ import annotations

import json
from pathlib import Path

from src.validation.acceptance_check import run_acceptance_check
from src.validation.gate_detail_builders import (
    build_portfolio_gate_detail,
    build_unified_data_gate_detail,
)
from src.validation.no_action_diagnostics import build_no_action_diagnostics, write_no_action_diagnostics


def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    (data / "portfolio_policy.yaml").write_text("risk_limits:\n  kr_alpha_max: 35\n", encoding="utf-8")
    (data / "positions.csv").write_text(
        "ticker,name,asset_group,current_value\n005930,삼성전자,kr_alpha,1000000\n",
        encoding="utf-8",
    )
    (data / "target_portfolio.csv").write_text(
        "ticker,name,asset_group,target_weight,min_weight,max_weight\n"
        "005930,삼성전자,kr_alpha,10,5,15\n"
        "069500,KODEX 200,domestic_beta,90,85,95\n",
        encoding="utf-8",
    )
    (data / "market_indicators.csv").write_text(
        "date,kospi,kospi_recent_high,vix,usdkrw,foreign_flow_3d,regime\n"
        "2026-07-03,8000,9000,16,1528,neutral,YELLOW_STABLE\n",
        encoding="utf-8",
    )
    (data / "trigger_rules.yaml").write_text(
        "market_triggers:\n  kospi:\n    crisis_zone: -20\n"
        "  vix:\n    caution_above: 20\n  usdkrw:\n    stable_level: 1500\n",
        encoding="utf-8",
    )
    (data / "compass_rules.yaml").write_text("usdkrw:\n  stress_above: 1550\n", encoding="utf-8")
    (out / "decision_log.jsonl").write_text(
        json.dumps({
            "data_gate": "RED",
            "portfolio_gate": "RED",
            "alpha_gate": "GREEN",
            "health_gate": "GREEN",
            "execution_scope": "NO_TRADE",
        }) + "\n",
        encoding="utf-8",
    )
    health = {
        "as_of": "2026-07-03",
        "overall": "pass",
        "summary": {"fail": 0, "warn": 2},
        "checks": [
            {"name": "core_price_gate", "status": "pass", "message": "ok", "detail": {"coverage_pct": 100}},
            {"name": "target_portfolio_guard", "status": "pass", "detail": {"severity": "PASS"}},
        ],
    }
    final = {
        "as_of": "2026-07-03",
        "run_id": "run-test",
        "data_gate": "RED",
        "execution_scope": "NO_TRADE",
        "policy_cap": {"active": True, "cap_regime": "YELLOW_STABLE"},
        "execution_permissions": {
            "execution_scope": "NO_TRADE",
            "core_etf_permission": "BLOCKED",
            "alpha_auto_buy_permission": "BLOCKED",
            "main_block_reason": "execution_scope=NO_TRADE · policy_cap_active",
            "gates": {"data_gate": "RED", "portfolio_gate": "RED", "health_gate": "GREEN"},
            "sector_coverage": {"top10_sector_coverage_pct": 60, "top10_unknown_rate": 0.4},
        },
        "allowed_actions": [],
        "final_trade_list": [],
    }
    acceptance = {
        "as_of": "2026-07-03",
        "overall": "RED",
        "execution_scope": "NO_TRADE",
        "items": [],
    }
    brief = {
        "system_status": {"execution_scope": "NO_TRADE", "full_status": "RED"},
        "execution": {
            "execution_scope": "NO_TRADE",
            "operational_verdict": "Overall RED · Scope NO_TRADE",
            "actual_buy_allowed_count": 0,
            "executable_action_count": 0,
        },
    }
    _write_json(out / "system_health.json", health)
    _write_json(out / "final_execution_decision.json", final)
    _write_json(out / "acceptance_report.json", acceptance)
    _write_json(out / "daily_brief.json", brief)
    _write_json(out / "shadow_diagnostic.json", {"gates": {"dry_run_required": 10}})
    _write_json(out / "gpt_context.json", {
        "shortlist_meta": {"top10_sector_coverage_pct": 60, "top10_unknown_rate": 0.4},
    })
    return data, out


def test_gate_detail_not_empty_when_red(tmp_path: Path) -> None:
    data, out = _fixture(tmp_path)
    from src.validation.system_health import run_system_health

    health = run_system_health(data, out)
    log = json.loads((out / "decision_log.jsonl").read_text(encoding="utf-8").strip())
    unified = build_unified_data_gate_detail(
        gate="RED", log=log, health=health, output_dir=out, data_dir=data,
    )
    portfolio = build_portfolio_gate_detail(
        gate="RED", log=log, health=health, output_dir=out, data_dir=data,
    )
    assert unified["gate"] == "RED"
    assert unified["fail_reasons"]
    assert unified["blocking"] is True
    assert portfolio["gate"] == "RED"
    assert portfolio["fail_reasons"]
    assert portfolio["executable_action_block_reasons"]


def test_acceptance_ac02_ac03_have_detail(tmp_path: Path) -> None:
    data, out = _fixture(tmp_path)
    report = run_acceptance_check(data, out)
    by_id = {i.id: i for i in report.items}
    assert by_id["AC-02"].detail.get("fail_reasons")
    assert by_id["AC-03"].detail.get("fail_reasons")
    assert by_id["AC-02"].detail.get("gate") == "RED"


def test_no_action_diagnostics_output(tmp_path: Path) -> None:
    data, out = _fixture(tmp_path)
    report = run_acceptance_check(data, out)
    from src.validation.acceptance_check import write_acceptance_report

    write_acceptance_report(report, out / "acceptance_report.json")
    doc = write_no_action_diagnostics(data, out)
    assert (out / "no_action_diagnostics.json").exists()
    assert "primary_blockers" in doc
    assert doc["actual_buy_trace"]["final_actual_buy_allowed"] == 0
    assert doc["actual_buy_trace"]["authoritative_execution_scope"] == "NO_TRADE"
    assert "counterfactual_results" in doc
    assert "policy_cap_removed" in doc["counterfactual_results"]
    assert doc["gate_detail_complete"] is True
    assert isinstance(doc["no_action_is_expected"], bool)


def test_counterfactual_sector_80_may_open_path(tmp_path: Path) -> None:
    data, out = _fixture(tmp_path)
    report = run_acceptance_check(data, out)
    from src.validation.acceptance_check import write_acceptance_report

    write_acceptance_report(report, out / "acceptance_report.json")
    doc = build_no_action_diagnostics(data, out)
    sector_cf = doc["counterfactual_results"]["sector_coverage_80_assumed"]
    assert "would_open_buy_path" in sector_cf
