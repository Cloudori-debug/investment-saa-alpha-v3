from __future__ import annotations

import json
from pathlib import Path

from src.report.export_daily_brief import export_daily_brief, write_daily_brief


def test_export_daily_brief_minimal(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    data = tmp_path / "data"
    out.mkdir()
    data.mkdir()
    (data / "portfolio_policy.yaml").write_text(
        "alpha_shadow:\n  v0_2_enabled: true\n  v2_enabled: true\n",
        encoding="utf-8",
    )
    (out / "final_execution_decision.json").write_text(
        json.dumps({
            "as_of": "2026-06-26",
            "run_id": "test-run",
            "generated_at": "2026-06-27 06:19 UTC",
            "system_status": "YELLOW",
            "data_gate": "YELLOW",
            "execution_scope": "ETF_ONLY",
            "alpha_approval": "RESTRICTED",
            "alpha_execution_status": "RISK_REDUCE_ONLY",
            "dry_run_days": 5,
            "operational_verdict": "test verdict",
            "technical_status": {"system_status": "YELLOW", "health_gate": "YELLOW"},
            "policy_cap": {"active": True, "cap_regime": "YELLOW_STABLE"},
            "allowed_actions": [
                {"ticker": "005440", "name": "현대지에프", "action": "Trim", "allowed_size_pct": -1.5, "reason": "risk"},
            ],
            "operating": {
                "group_gaps": [
                    {"asset_group": "kr_alpha", "current": 40.61, "target": 33, "gap": -7.61, "action": "Trim"},
                ],
            },
        }),
        encoding="utf-8",
    )
    (out / "acceptance_report.json").write_text(
        json.dumps({"overall": "YELLOW", "operational_overall": "YELLOW", "items": []}),
        encoding="utf-8",
    )
    (out / "shadow_diagnostic.json").write_text(
        json.dumps({
            "mode": "shadow",
            "execution_authority": "v1.0.2",
            "execution": {"status": "REVIEW_ONLY", "primary_blocker": "dry_run", "blocked_by": ["dry_run"]},
            "signals": {"buy_trigger_active": True, "dip_buy_stage": "L1", "kospi_drawdown_pct": -7.7},
            "amounts": {"theoretical_gap_krw": 1000, "actual_allowed_krw": 0},
            "observations": {"signal_execution_mismatch": True},
            "performance": {"vs_saa_mtd": -1.2},
            "gates": {"dry_run_required": 10},
            "duration_bond_status": {
                "cash_short_current_pct": 57.6,
                "kr_duration_bond_current_pct": 0,
                "duration_gap": "absent",
                "diagnosis": "중장기 국채 부재",
            },
        }),
        encoding="utf-8",
    )

    (out / "alpha_v0_2_shadow.json").write_text(
        json.dumps({
            "mode": "shadow",
            "run_id": "test-run",
            "alpha_budget_status": "OVERWEIGHT",
            "current_alpha_weight_pct": 51.04,
            "new_alpha_buy_allowed": False,
            "rows": [],
        }),
        encoding="utf-8",
    )

    brief = export_daily_brief(out, as_of="2026-06-26", run_id="test-run", data_dir=data)
    assert brief["report_version"] == "v2.0"
    assert brief["date"] == "2026-06-26"
    assert brief["system_status"]["execution_scope"] == "ETF_ONLY"
    assert brief["shadow_diagnostic"]["signal_execution_mismatch"] is True
    assert brief["duration_sleeve"]["kr_duration_pct"] == 0
    assert brief["execution"]["top_actions"][0]["action"] == "Trim"
    assert brief["alpha_v0_2"]["weight_basis"] == "investable_assets_ex_cash"
    assert brief["alpha_v0_2"]["kr_alpha_v1_portfolio_pct"] == 40.61

    path = write_daily_brief(out / "daily_brief.json", brief)
    assert path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["references"]["authoritative_execution"] == "final_execution_decision.json"


def test_build_daily_report_v2_sections() -> None:
    from src.report.export_daily_brief import build_daily_report_v2_sections

    brief = {
        "execution_authority": "v1.0.2",
        "system_status": {"operational_status": "YELLOW", "execution_scope": "ETF_ONLY", "data_gate": "YELLOW", "dry_run_days": 5, "dry_run_required": 10},
        "saa_taa": {"profile": "balanced", "applied_regime": "YELLOW_STABLE", "market_phase": "correction"},
        "shadow_diagnostic": {"primary_blocker": "dry_run", "signal_execution_mismatch": True, "vs_saa_mtd": -1.2},
        "duration_sleeve": {"cash_short_pct": 57.6, "kr_duration_pct": 0, "duration_gap": "absent", "diagnosis": "중장기 국채 부재"},
        "alpha_v0_2": {"alpha_budget_status": "within", "current_alpha_weight_pct": 51, "new_alpha_buy_allowed": False},
    }
    lines = build_daily_report_v2_sections(brief)
    assert any("Report v2.0" in line for line in lines)
    assert any("dry_run" in line for line in lines)
