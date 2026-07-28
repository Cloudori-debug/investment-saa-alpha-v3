"""Snapshot alignment after target write and bundle refresh."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from src.alpha.target_write_audit import write_operational_target
from src.models import TargetRow
from src.validation.bundle_consistency import (
    detect_snapshot_stale_after_target_write,
    refresh_daily_report_authoritative,
    verify_bundle_snapshot_alignment,
)
from src.validation.green_layers import evaluate_green_layers


def _write_target(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "ticker", "name", "asset_group", "sector", "role",
        "target_weight", "min_weight", "max_weight",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _row(ticker: str, weight: float) -> dict:
    return {
        "ticker": ticker,
        "name": ticker,
        "asset_group": "kr_alpha",
        "sector": "tech",
        "role": "core",
        "target_weight": weight,
        "min_weight": 0,
        "max_weight": 20,
    }


def _base_health(hash_val: str) -> dict:
    return {
        "overall": "pass",
        "checks": [{
            "name": "target_portfolio_guard",
            "status": "pass",
            "detail": {
                "severity": "PASS",
                "current_hash": hash_val,
                "user_target_hash": hash_val,
                "changed_rows": 0,
                "system_proposal_leak_count": 0,
                "unknown_material_count": 0,
            },
        }],
    }


def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def test_verify_bundle_detects_hash_mismatch(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    _write_json(out / "system_health.json", _base_health("newhash1234567890"))
    _write_json(out / "acceptance_report.json", {
        "target_hash": "oldhash1234567890",
        "items": [{
            "name": "target_portfolio_guard",
            "detail": {"current_hash": "oldhash1234567890"},
        }],
    })
    _write_json(out / "daily_report.md", {
        "x": 1,
    })
    (out / "daily_report.md").write_text(
        "## 최종 실행 권위\n- **Actual Buy Allowed**: 0\n"
        "### GREEN Layer Status\n| Layer | Status |\n"
        "## 운용 상태 요약\n- target_portfolio_guard: curr `oldhash1234567890`\n"
        "## 1. 실행\n",
        encoding="utf-8",
    )
    _write_json(out / "ai_export_bundle.json", {
        "target_hash": "newhash1234567890",
        "health_report": _base_health("newhash1234567890"),
    })
    _write_json(out / "final_execution_decision.json", {"allowed_actions": [], "final_trade_list": []})

    alignment = verify_bundle_snapshot_alignment(out)
    assert alignment["aligned"] is False
    assert any("acceptance" in i for i in alignment["issues"])


def test_snapshot_stale_blocks_technical_green(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    data = tmp_path / "data"
    out.mkdir()
    data.mkdir()
    h = "samehash123456789"
    _write_json(out / "system_health.json", _base_health(h))
    _write_json(out / "acceptance_report.json", {"overall": "YELLOW", "target_hash": h, "run_id": "r1"})
    _write_json(out / "run_manifest.json", {"run_id": "r1"})
    _write_json(out / "final_execution_decision.json", {
        "snapshot_stale": True,
        "policy_cap": {"active": True},
        "allowed_actions": [],
        "final_trade_list": [],
    })

    green = evaluate_green_layers(data, out)
    assert green["technical_status"] != "GREEN"
    assert green["actual_buy_allowed"] == 0


def test_write_audit_includes_run_id(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _write_json(out / "run_manifest.json", {"run_id": "pipeline-run-1"})
    _write_target(data / "user_target_portfolio.csv", [_row("005830", 10.0)])
    _write_target(data / "target_portfolio.csv", [_row("005830", 10.0)])
    _write_json(out / "final_execution_decision.json", {
        "allowed_actions": [],
        "final_trade_list": [],
        "group_gaps": [],
    })

    result = write_operational_target(
        data,
        [
            TargetRow.model_validate(_row("005830", 9.0)),
            TargetRow.model_validate(_row("030190", 1.0)),
        ],
        source="approval_bridge",
        reason="test",
        approved_by_user=True,
        output_dir=out,
    )
    assert result.audit.get("run_id") == "pipeline-run-1"


def test_refresh_daily_report_updates_target_hash_line(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    data = tmp_path / "data"
    out.mkdir()
    data.mkdir()
    h = "freshhash12345678"
    _write_json(out / "system_health.json", _base_health(h))
    _write_json(out / "acceptance_report.json", {"overall": "YELLOW", "target_hash": h})
    _write_json(out / "final_execution_decision.json", {
        "execution_scope": "ETF_ONLY",
        "system_status": "YELLOW",
        "policy_cap": {"active": True},
        "allowed_actions": [],
        "final_trade_list": [],
    })
    (out / "daily_report.md").write_text(
        "# Daily Portfolio Execution Report\n\n"
        "## 최종 실행 권위\nold\n"
        "## 1. 실행\nbody\n",
        encoding="utf-8",
    )
    refresh_daily_report_authoritative(out, data)
    text = (out / "daily_report.md").read_text(encoding="utf-8")
    assert "### GREEN Layer Status" in text
    assert "## 1. 실행" in text
