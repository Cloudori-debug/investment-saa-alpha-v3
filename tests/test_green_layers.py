"""Tests for Technical / Operational / Market / Full GREEN layer separation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.validation.green_layers import (
    evaluate_green_layers,
    format_green_layer_table_lines,
)


def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _base_health() -> dict:
    return {
        "overall": "pass",
        "checks": [{
            "name": "target_portfolio_guard",
            "status": "pass",
            "detail": {
                "severity": "PASS",
                "current_hash": "abc123",
                "user_target_hash": "abc123",
                "changed_rows": 0,
                "system_proposal_leak_count": 0,
                "unknown_material_count": 0,
            },
        }],
    }


def _base_final(*, buy: int = 0, restore: bool = False, hard_stops: int = 0) -> dict:
    return {
        "run_id": "run-test",
        "system_status": "YELLOW",
        "data_gate": "GREEN",
        "execution_scope": "ETF_ONLY",
        "alpha_approval": "RESTRICTED",
        "target_guard_conflict_detected": False,
        "target_restore_occurred": restore,
        "policy_cap": {"active": True, "cap_regime": "YELLOW_STABLE"},
        "hard_stops_detail": {"risk_hard_stop_count": hard_stops},
        "allowed_actions": [
            {"ticker": "005440", "action": "Trim", "allowed_size_pct": -2.0},
        ] if buy == 0 else [
            {"ticker": "069500", "action": "Buy-allowed", "allowed_size_pct": 2.0},
        ],
        "final_trade_list": [] if buy == 0 else [
            {"ticker": "069500", "action": "Buy-allowed", "allowed_size_pct": 2.0},
        ],
        "execution_permissions": {},
    }


def test_technical_green_but_acceptance_yellow_not_full_green(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    data = tmp_path / "data"
    out.mkdir()
    data.mkdir()
    _write_json(out / "system_health.json", _base_health())
    _write_json(out / "acceptance_report.json", {"overall": "YELLOW", "run_id": "run-test"})
    _write_json(out / "final_execution_decision.json", _base_final(buy=0))
    _write_json(out / "run_manifest.json", {"run_id": "run-test"})
    for name in ("acceptance_report.json", "system_health.json", "ai_export_bundle.json"):
        _write_json(out / name, _base_health() if "health" in name else {"overall": "YELLOW"})

    green = evaluate_green_layers(data, out)
    assert green["technical_green"] is True
    assert green["technical_status"] == "GREEN"
    assert green["operational_green"] is False
    assert green["full_green"] is False
    assert green["full_status"] in {"YELLOW", "RED"}


def test_actual_buy_zero_blocks_operational_green(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    data = tmp_path / "data"
    out.mkdir()
    data.mkdir()
    _write_json(out / "system_health.json", _base_health())
    final = _base_final(buy=0)
    final["system_status"] = "GREEN"
    _write_json(out / "final_execution_decision.json", final)
    _write_json(out / "acceptance_report.json", {"overall": "GREEN", "run_id": "run-test"})
    _write_json(out / "run_manifest.json", {"run_id": "run-test"})

    green = evaluate_green_layers(data, out)
    assert green["operational_green"] is False
    assert green["actual_buy_allowed"] == 0
    assert "Actual Buy Allowed=0" in green["operational_blockers"]


def test_etf_only_scope_does_not_grant_buy_permission(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    data = tmp_path / "data"
    out.mkdir()
    data.mkdir()
    _write_json(out / "system_health.json", _base_health())
    _write_json(out / "final_execution_decision.json", _base_final(buy=0))
    _write_json(out / "acceptance_report.json", {"overall": "YELLOW", "execution_scope": "ETF_ONLY", "run_id": "r1"})
    _write_json(out / "run_manifest.json", {"run_id": "r1"})

    green = evaluate_green_layers(data, out)
    assert green["buy_permission_status"] == "BLOCKED"
    assert green["etf_only_is_buy_permission"] is False
    assert green["operational_green"] is False


def test_restore_occurred_caps_technical_green(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    data = tmp_path / "data"
    out.mkdir()
    data.mkdir()
    _write_json(out / "system_health.json", _base_health())
    _write_json(out / "final_execution_decision.json", _base_final(restore=True))
    _write_json(out / "acceptance_report.json", {"overall": "YELLOW", "run_id": "run-test"})
    _write_json(out / "run_manifest.json", {"run_id": "run-test"})
    log = out / "decision_log.jsonl"
    log.write_text(
        json.dumps({"event": "target_restore", "run_id": "run-test"}) + "\n",
        encoding="utf-8",
    )

    green = evaluate_green_layers(data, out)
    assert green["technical_status"] != "GREEN"
    assert green["full_green"] is False


def test_clean_run_technical_green_possible(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    data = tmp_path / "data"
    out.mkdir()
    data.mkdir()
    health = _base_health()
    _write_json(out / "system_health.json", health)
    final = _base_final(buy=0)
    final["policy_cap"] = {"active": False}
    _write_json(out / "final_execution_decision.json", final)
    _write_json(out / "acceptance_report.json", {"overall": "YELLOW", "run_id": "run-test"})
    _write_json(out / "run_manifest.json", {"run_id": "run-test"})
    _write_json(out / "acceptance_report.json", {
        "overall": "YELLOW",
        "run_id": "run-test",
        "health_snapshot_id": "snap1",
        "target_hash": "abc123",
    })
    _write_json(out / "ai_export_bundle.json", {
        "health_report": {"meta": {"health_snapshot_id": "snap1"}},
        "acceptance": {"health_snapshot_id": "snap1", "target_hash": "abc123"},
    })

    green = evaluate_green_layers(data, out)
    assert green["technical_green"] is True
    assert green["target_write_audit_status"] == "PASS"


def test_hard_stop_blocks_market_green(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    data = tmp_path / "data"
    out.mkdir()
    data.mkdir()
    (data / "portfolio_policy.yaml").write_text(
        "risk_limits:\n  kr_alpha_max: 35\n",
        encoding="utf-8",
    )
    _write_json(out / "system_health.json", _base_health())
    final = _base_final(hard_stops=2)
    final["policy_cap"] = {"active": False}
    final["group_gaps"] = [{"asset_group": "kr_alpha", "current": 42.7}]
    _write_json(out / "final_execution_decision.json", final)
    _write_json(out / "acceptance_report.json", {"overall": "YELLOW", "run_id": "r1"})
    _write_json(out / "run_manifest.json", {"run_id": "r1"})

    green = evaluate_green_layers(data, out)
    assert green["market_green"] is False
    assert any("kr_alpha_over_hard_stop" in b for b in green["market_blockers"])


def test_daily_report_table_includes_green_layers() -> None:
    green = {
        "technical_status": "GREEN",
        "operational_status": "YELLOW",
        "market_status": "YELLOW",
        "full_status": "YELLOW",
        "technical_green_reasons": ["target_guard=PASS"],
        "operational_blockers": ["acceptance_overall=YELLOW"],
        "market_blockers": ["policy_cap=YELLOW_STABLE"],
        "actual_buy_allowed": 0,
        "risk_reduce_only": True,
        "buy_permission_status": "BLOCKED",
        "green_layer_summary": {},
        "technical_green_note": "Technical GREEN means system integrity is restored. It does not mean buy permission.",
        "execution_scope_explanation": "ETF_ONLY is scope restriction, not ETF buy permission.",
    }
    lines = format_green_layer_table_lines(green)
    text = "\n".join(lines)
    assert "### GREEN Layer Status" in text
    assert "| Technical | **GREEN** |" in text
    assert "Technical GREEN means system integrity" in text
    assert "ETF_ONLY is scope restriction" in text
