"""Tests for SAA Restart Readiness Report."""
from __future__ import annotations

import json
from pathlib import Path

from src.validation.saa_restart_readiness import (
    build_saa_restart_readiness_report,
    format_saa_restart_readiness_md,
    write_saa_restart_readiness_report,
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
                "current_hash": "abc",
                "user_target_hash": "abc",
                "changed_rows": 0,
                "system_proposal_leak_count": 0,
                "unknown_material_count": 0,
            },
        }],
    }


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    (data / "asset_group_labels.yaml").write_text(
        "groups:\n  global_beta:\n    label: 미국 주식\n",
        encoding="utf-8",
    )
    (data / "portfolio_policy.yaml").write_text("risk_limits:\n  kr_alpha_max: 35\n", encoding="utf-8")
    (data / "duration_sleeve_tags.yaml").write_text(
        "shadow_targets_pct:\n  kr_duration_bond:\n    target: 12.5\n  global_duration_bond:\n    target: 7.5\n",
        encoding="utf-8",
    )
    (data / "market_indicators.csv").write_text(
        "date,kospi,kospi_recent_high,vix,usdkrw,foreign_flow_3d\n"
        "2026-07-03,7554,9114,16.1,1546,neutral\n",
        encoding="utf-8",
    )
    return data, out


def test_not_ready_when_actual_buy_zero(tmp_path: Path) -> None:
    data, out = _setup(tmp_path)
    _write_json(out / "system_health.json", _base_health())
    _write_json(out / "acceptance_report.json", {"overall": "YELLOW", "run_id": "r1"})
    _write_json(out / "run_manifest.json", {"run_id": "r1"})
    _write_json(out / "daily_brief.json", {
        "duration_sleeve": {"kr_duration_pct": 0, "global_duration_pct": 0},
    })
    final = {
        "data_gate": "GREEN",
        "execution_scope": "ETF_ONLY",
        "system_status": "YELLOW",
        "policy_cap": {"active": True, "cap_regime": "YELLOW_STABLE"},
        "group_gaps": [
            {"asset_group": "global_beta", "current": 0, "target": 25, "gap": 25, "action": "Buy"},
            {"asset_group": "kr_alpha", "current": 42.7, "target": 21.8, "gap": -20.9, "action": "Trim"},
            {"asset_group": "cash_short_bond", "current": 55, "target": 31, "gap": -24, "action": "Park"},
        ],
        "allowed_actions": [{"ticker": "005440", "action": "Trim", "allowed_size_pct": -2.0}],
        "final_trade_list": [],
        "execution_permissions": {"gates": {"alpha_gate": "GREEN", "data_gate": "GREEN"}},
    }
    _write_json(out / "final_execution_decision.json", final)

    report = build_saa_restart_readiness_report(data, out)
    assert report["verdict"] == "NOT_READY"
    assert report["restart_level"] == 0
    assert "Actual Buy Allowed=0" in report["restart_blockers"]
    assert report["next_allowed_action"] == "risk-reduce only — no new SAA buys"
    assert report["human_approval_required"] is True


def test_gap_summary_includes_duration_bond(tmp_path: Path) -> None:
    data, out = _setup(tmp_path)
    _write_json(out / "system_health.json", _base_health())
    _write_json(out / "acceptance_report.json", {"overall": "YELLOW"})
    _write_json(out / "daily_brief.json", {
        "duration_sleeve": {
            "kr_duration_pct": 0,
            "global_duration_pct": 0,
            "diagnosis": "duration absent",
        },
    })
    _write_json(out / "core_saa_reference_diagnostic.json", {
        "sleeve_target_pct": {"duration_bond": 18.75},
    })
    _write_json(out / "final_execution_decision.json", {
        "data_gate": "GREEN",
        "policy_cap": {"active": True},
        "group_gaps": [],
        "allowed_actions": [],
        "final_trade_list": [],
    })

    report = build_saa_restart_readiness_report(data, out)
    groups = {r["asset_group"] for r in report["saa_gap_summary"]}
    assert "duration_bond" in groups
    dur = next(r for r in report["saa_gap_summary"] if r["asset_group"] == "duration_bond")
    assert dur["target_weight_pct"] == 18.75
    assert dur["gap_pct"] == 18.75


def test_mandatory_blockers_include_policy_and_kr_alpha(tmp_path: Path) -> None:
    data, out = _setup(tmp_path)
    _write_json(out / "system_health.json", _base_health())
    _write_json(out / "acceptance_report.json", {"overall": "YELLOW"})
    _write_json(out / "daily_brief.json", {"duration_sleeve": {}})
    _write_json(out / "final_execution_decision.json", {
        "data_gate": "GREEN",
        "execution_scope": "ETF_ONLY",
        "system_status": "YELLOW",
        "policy_cap": {"active": True, "cap_regime": "YELLOW_STABLE"},
        "group_gaps": [{"asset_group": "kr_alpha", "current": 42.7, "target": 21.8, "gap": -20.9}],
        "allowed_actions": [],
        "final_trade_list": [],
        "execution_permissions": {"gates": {"alpha_gate": "GREEN"}},
    })

    report = build_saa_restart_readiness_report(data, out)
    blockers = " ".join(report["restart_blockers"])
    assert "policy_cap" in blockers
    assert "kr_alpha" in blockers
    assert "Operational YELLOW" in blockers
    assert "Market YELLOW" in blockers


def test_daily_report_md_section(tmp_path: Path) -> None:
    data, out = _setup(tmp_path)
    _write_json(out / "system_health.json", _base_health())
    _write_json(out / "acceptance_report.json", {"overall": "YELLOW"})
    _write_json(out / "daily_brief.json", {"duration_sleeve": {}})
    _write_json(out / "final_execution_decision.json", {
        "policy_cap": {"active": True},
        "group_gaps": [],
        "allowed_actions": [],
        "final_trade_list": [],
    })

    report = write_saa_restart_readiness_report(data, out)
    md = format_saa_restart_readiness_md(report)
    assert "## SAA Restart Readiness Report" in md
    assert "SAA gap summary" in md
    assert "Prohibitions" in md
    assert (out / "saa_restart_readiness_report.json").exists()
