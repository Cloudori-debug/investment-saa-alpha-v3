"""Tests for expanded market gate blockers."""
from __future__ import annotations

import json
from pathlib import Path

from src.validation.green_layers import evaluate_green_layers, format_green_layer_table_lines
from src.validation.market_gate import collect_market_gate_inputs, evaluate_market_layer


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
                "current_hash": "abc",
                "user_target_hash": "abc",
                "changed_rows": 0,
                "system_proposal_leak_count": 0,
                "unknown_material_count": 0,
            },
        }],
    }


def _setup_market_files(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    (data / "market_indicators.csv").write_text(
        "date,kospi,kospi_recent_high,kospi_200ma,sp500,sp500_recent_high,vix,usdkrw,korea_10y,oil_brent,gold,foreign_flow_3d,regime\n"
        "2026-07-03,7554,9114,7724,7483,7609,16.1,1551.8,2.2,71,4147,neutral,NEUTRAL\n",
        encoding="utf-8",
    )
    (data / "portfolio_policy.yaml").write_text(
        "risk_limits:\n  kr_alpha_max: 35\n",
        encoding="utf-8",
    )
    (data / "trigger_rules.yaml").write_text(
        "market_triggers:\n  kospi:\n    crisis_zone: -20\n    pullback_buy_1: -5\n  vix:\n    caution_above: 20\n    risk_off_above: 25\n    panic_above: 30\n  usdkrw:\n    stable_level: 1500\n    risk_level: 1550\n",
        encoding="utf-8",
    )
    (data / "compass_rules.yaml").write_text("usdkrw:\n  stress_above: 1550\n", encoding="utf-8")
    return data, out


def test_policy_cap_keeps_market_yellow(tmp_path: Path) -> None:
    data, out = _setup_market_files(tmp_path)
    final = {
        "data_gate": "GREEN",
        "execution_scope": "ETF_ONLY",
        "policy_cap": {"active": True, "cap_regime": "YELLOW_STABLE"},
        "group_gaps": [{"asset_group": "kr_alpha", "current": 30.0}],
        "execution_permissions": {"gates": {"alpha_gate": "GREEN", "data_gate": "GREEN"}},
        "allowed_actions": [],
        "final_trade_list": [],
    }
    inputs = collect_market_gate_inputs(data, out, final_doc=final)
    ev = evaluate_market_layer(inputs, actual_buy_allowed=0, conflict_detected=False)
    assert ev["market_status"] == "YELLOW"
    assert any("policy_cap" in b for b in ev["market_blockers"])


def test_data_gate_yellow_blocks_market_green(tmp_path: Path) -> None:
    data, out = _setup_market_files(tmp_path)
    final = {
        "data_gate": "YELLOW",
        "execution_scope": "ETF_ONLY",
        "policy_cap": {"active": False},
        "group_gaps": [],
        "execution_permissions": {"gates": {"alpha_gate": "GREEN", "data_gate": "YELLOW"}},
    }
    ev = evaluate_market_layer(
        collect_market_gate_inputs(data, out, final_doc=final),
        actual_buy_allowed=0,
        conflict_detected=False,
    )
    assert ev["market_status"] != "GREEN"
    assert "unified_data_gate=YELLOW" in ev["market_blockers"]


def test_kr_alpha_hard_stop_blocks_market_green(tmp_path: Path) -> None:
    data, out = _setup_market_files(tmp_path)
    final = {
        "data_gate": "GREEN",
        "execution_scope": "ETF_ONLY",
        "policy_cap": {"active": False},
        "group_gaps": [{"asset_group": "kr_alpha", "current": 42.7}],
        "execution_permissions": {"gates": {"alpha_gate": "GREEN", "data_gate": "GREEN"}},
    }
    ev = evaluate_market_layer(
        collect_market_gate_inputs(data, out, final_doc=final),
        actual_buy_allowed=0,
        conflict_detected=False,
    )
    assert ev["market_status"] != "GREEN"
    assert any("kr_alpha_over_hard_stop" in b for b in ev["market_blockers"])


def test_usdkrw_risk_in_blockers(tmp_path: Path) -> None:
    data, out = _setup_market_files(tmp_path)
    final = {
        "data_gate": "GREEN",
        "policy_cap": {"active": False},
        "group_gaps": [{"asset_group": "kr_alpha", "current": 20.0}],
        "execution_permissions": {"gates": {"alpha_gate": "GREEN"}},
    }
    ev = evaluate_market_layer(
        collect_market_gate_inputs(data, out, final_doc=final),
        actual_buy_allowed=0,
        conflict_detected=False,
    )
    assert any("usdkrw" in b for b in ev["market_blockers"] + ev["market_yellow_flags"])


def test_pullback_watch_with_buy_zero_not_market_green(tmp_path: Path) -> None:
    data, out = _setup_market_files(tmp_path)
    final = {
        "data_gate": "GREEN",
        "policy_cap": {"active": False},
        "group_gaps": [{"asset_group": "kr_alpha", "current": 20.0}],
        "execution_permissions": {"gates": {"alpha_gate": "GREEN"}},
    }
    ev = evaluate_market_layer(
        collect_market_gate_inputs(data, out, final_doc=final),
        actual_buy_allowed=0,
        conflict_detected=False,
    )
    assert ev["market_status"] != "GREEN"
    assert any("kospi" in b for b in ev["market_yellow_flags"] + ev["market_blockers"])


def test_unknown_input_not_used_as_green_reason(tmp_path: Path) -> None:
    data, out = _setup_market_files(tmp_path)
    (data / "market_indicators.csv").write_text(
        "date,kospi,kospi_recent_high,sp500,sp500_recent_high,vix,usdkrw,foreign_flow_3d\n"
        "2026-07-03,0,0,0,0,0,0,\n",
        encoding="utf-8",
    )
    final = {"data_gate": "GREEN", "policy_cap": {"active": False}, "execution_permissions": {"gates": {"alpha_gate": "GREEN"}}}
    ev = evaluate_market_layer(
        collect_market_gate_inputs(data, out, final_doc=final),
        actual_buy_allowed=0,
        conflict_detected=False,
    )
    assert ev["market_status"] != "GREEN"
    assert ev["market_unknowns"]


def test_daily_report_market_reason_shows_expanded_blockers(tmp_path: Path) -> None:
    data, out = _setup_market_files(tmp_path)
    _write_json(out / "system_health.json", _base_health())
    _write_json(out / "acceptance_report.json", {"overall": "YELLOW", "run_id": "r1"})
    _write_json(out / "run_manifest.json", {"run_id": "r1"})
    _write_json(out / "acceptance_report.json", {
        "overall": "YELLOW",
        "health_snapshot_id": "s1",
        "target_hash": "abc",
    })
    _write_json(out / "ai_export_bundle.json", {
        "health_report": {"meta": {"health_snapshot_id": "s1"}},
        "acceptance": {"health_snapshot_id": "s1", "target_hash": "abc"},
    })
    final = {
        "data_gate": "GREEN",
        "execution_scope": "ETF_ONLY",
        "system_status": "YELLOW",
        "policy_cap": {"active": True, "cap_regime": "YELLOW_STABLE"},
        "group_gaps": [{"asset_group": "kr_alpha", "current": 42.7}],
        "execution_permissions": {
            "gates": {"alpha_gate": "GREEN", "data_gate": "GREEN"},
            "alpha_sector_data_gate": "YELLOW",
        },
        "allowed_actions": [{"action": "Trim", "allowed_size_pct": -2.0, "ticker": "005440"}],
        "final_trade_list": [],
    }
    _write_json(out / "final_execution_decision.json", final)
    green = evaluate_green_layers(data, out)
    text = "\n".join(format_green_layer_table_lines(green))
    assert "policy_cap=YELLOW_STABLE" in text
    assert "kr_alpha_over_hard_stop" in text or "42.7" in text
    assert "Market YELLOW means SAA restart" in text
