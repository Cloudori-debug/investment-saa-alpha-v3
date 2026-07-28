"""P2: Alpha v0.2 shadow config off + daily_brief fail-soft."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import yaml

from src.alpha_shadow_policy import (
    V02_DISABLED_NOTE,
    alpha_shadow_flags,
    load_alpha_shadow_flags,
    resolve_alpha_v02_shadow_doc,
    run_configured_alpha_shadows,
)
from src.decision_logger import append_decision_log, get_last_decision_event
from src.report.export_daily_brief import build_daily_report_v2_sections, export_daily_brief
from src.report.publish import publish_report_exports


def _write_policy(data_dir: Path, *, v0_2_enabled: bool = False) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "portfolio": {"total_target_weight": 100},
        "risk_limits": {"kr_alpha_max": 35},
        "alpha_shadow": {
            "v0_2_enabled": v0_2_enabled,
            "v2_enabled": True,
            "flow_dashboard_enabled": True,
        },
    }
    (data_dir / "portfolio_policy.yaml").write_text(
        yaml.dump(doc, allow_unicode=True),
        encoding="utf-8",
    )


def _write_minimal_export_fixtures(
    out: Path,
    data_dir: Path,
    *,
    v0_2_enabled: bool = False,
    stale_v02: bool = False,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    _write_policy(data_dir, v0_2_enabled=v0_2_enabled)
    (out / "final_execution_decision.json").write_text(
        json.dumps({
            "as_of": "2026-07-03",
            "run_id": "test-run-p2",
            "generated_at": "2026-07-05 14:00 UTC",
            "data_gate": "GREEN",
            "execution_scope": "ETF_ONLY",
            "actual_buy_allowed": 0,
            "technical_status": {"system_status": "GREEN", "health_gate": "GREEN"},
            "policy_cap": {"active": True, "cap_regime": "YELLOW_STABLE"},
            "allowed_actions": [],
        }),
        encoding="utf-8",
    )
    (out / "acceptance_report.json").write_text(
        json.dumps({"overall": "YELLOW", "operational_overall": "YELLOW", "items": []}),
        encoding="utf-8",
    )
    (out / "shadow_diagnostic.json").write_text(
        json.dumps({
            "execution": {"primary_blocker": "dry_run"},
            "signals": {},
            "duration_bond_status": {},
            "gates": {},
        }),
        encoding="utf-8",
    )
    (out / "alpha_v2_summary.json").write_text(
        json.dumps({"mode": "shadow", "schema_version": "2.0", "coverage": {}}),
        encoding="utf-8",
    )
    if stale_v02 or v0_2_enabled:
        (out / "alpha_v0_2_shadow.json").write_text(
            json.dumps({
                "mode": "shadow",
                "run_id": "old-run" if stale_v02 else "test-run-p2",
                "alpha_budget_status": "OK",
                "current_alpha_weight_pct": 51.0,
                "new_alpha_buy_allowed": False,
                "rows": [],
            }),
            encoding="utf-8",
        )


def test_alpha_shadow_flags_default_off() -> None:
    flags = alpha_shadow_flags({})
    assert flags["v0_2_enabled"] is False
    assert flags["v2_enabled"] is True


def test_resolve_stale_v02_ignored_when_run_id_differs(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _write_minimal_export_fixtures(out, data, v0_2_enabled=True, stale_v02=True)
    doc, status, enabled = resolve_alpha_v02_shadow_doc(
        out, data_dir=data, run_id="test-run-p2",
    )
    assert enabled is True
    assert status == "stale"
    assert doc is None


def test_export_daily_brief_v02_disabled_without_file(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _write_minimal_export_fixtures(out, data, v0_2_enabled=False)
    brief = export_daily_brief(out, run_id="test-run-p2", data_dir=data)
    assert brief["alpha_v0_2"]["status"] == "disabled"
    assert brief["alpha_v0_2"]["enabled"] is False
    assert V02_DISABLED_NOTE in brief["alpha_v0_2"]["note"]


def test_export_daily_brief_v02_disabled_ignores_stale_file(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _write_minimal_export_fixtures(out, data, v0_2_enabled=False, stale_v02=True)
    brief = export_daily_brief(out, run_id="test-run-p2", data_dir=data)
    assert brief["alpha_v0_2"]["status"] == "disabled"
    assert brief["alpha_v0_2"]["current_alpha_weight_pct"] == 0


def test_export_daily_brief_v02_enabled_active(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _write_minimal_export_fixtures(out, data, v0_2_enabled=True)
    brief = export_daily_brief(out, run_id="test-run-p2", data_dir=data)
    assert brief["alpha_v0_2"]["status"] == "active"
    assert brief["alpha_v0_2"]["current_alpha_weight_pct"] == 51.0


def test_daily_report_v02_disabled_section(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _write_minimal_export_fixtures(out, data, v0_2_enabled=False)
    brief = export_daily_brief(out, run_id="test-run-p2", data_dir=data)
    lines = build_daily_report_v2_sections(brief)
    assert any("Alpha v0.2 shadow**: disabled" in line for line in lines)


def test_ai_export_bundle_v02_disabled_fields(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _write_minimal_export_fixtures(out, data, v0_2_enabled=False)
    _, bundle = publish_report_exports(
        out, data, as_of="2026-07-03", run_id="test-run-p2",
    )
    assert bundle["alpha_v0_2_enabled"] is False
    assert bundle["alpha_v0_2_status"] == "disabled"


def test_run_configured_alpha_shadows_skips_v02(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _write_policy(data, v0_2_enabled=False)
    out.mkdir(parents=True, exist_ok=True)

    with patch("src.alpha_shadow_policy._run_alpha_v0_2_shadow") as mock_v02:
        run_configured_alpha_shadows(
            data, out, run_id="rid", as_of="2026-07-03",
            positions=[], targets=[], append_log=append_decision_log,
        )
        mock_v02.assert_not_called()

    ev = get_last_decision_event(out / "decision_log.jsonl", "alpha_v0_2_shadow_skipped")
    assert ev.get("reason") == "config_disabled"


def test_run_configured_alpha_shadows_runs_v02(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _write_policy(data, v0_2_enabled=True)
    out.mkdir(parents=True, exist_ok=True)

    with patch("src.alpha_shadow_policy._run_alpha_v0_2_shadow") as mock_v02:
        run_configured_alpha_shadows(
            data, out, run_id="rid", as_of="2026-07-03",
            positions=[], targets=[], append_log=append_decision_log,
        )
        mock_v02.assert_called_once()
        assert mock_v02.call_args.kwargs.get("run_id") == "rid"

def test_load_alpha_shadow_flags_from_repo_policy() -> None:
    root = Path(__file__).resolve().parents[1]
    flags = load_alpha_shadow_flags(root / "data")
    assert flags["v0_2_enabled"] is False
    assert flags["v2_enabled"] is True
