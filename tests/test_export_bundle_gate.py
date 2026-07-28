"""Pre-export bundle gate — snapshot alignment required in zip."""
from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from src.validation.ai_export import (
    ExportBundleValidationError,
    build_export_zip,
    validate_export_bundle_readiness,
)


def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _base_health(h: str) -> dict:
    return {
        "as_of": "2026-07-03",
        "overall": "pass",
        "meta": {"target_hash": h},
        "checks": [{
            "name": "target_portfolio_guard",
            "status": "pass",
            "detail": {
                "severity": "PASS",
                "current_hash": h,
                "user_target_hash": h,
                "changed_rows": 0,
            },
        }],
    }


def test_prepare_export_fails_on_hash_mismatch(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    h_new = "newhash123456789012345678901234567890123456789012345678901234567890ab"
    h_old = "oldhash123456789012345678901234567890123456789012345678901234567890ab"
    _write_json(out / "run_manifest.json", {"run_id": "run-1", "as_of": "2026-07-03"})
    _write_json(out / "final_execution_decision.json", {"as_of": "2026-07-03", "allowed_actions": [], "final_trade_list": []})
    _write_json(out / "system_health.json", _base_health(h_new))
    _write_json(out / "acceptance_report.json", {
        "target_hash": h_old,
        "items": [{"name": "target_portfolio_guard", "detail": {"current_hash": h_old}}],
    })
    (out / "daily_report.md").write_text(
        "# Daily Portfolio Execution Report\n\n"
        "## 최종 실행 권위\n"
        "- **Actual Buy Allowed**: 0\n"
        "- **Core ETF permission**: **RESTRICTED**\n"
        "- **Alpha auto-buy permission**: **BLOCKED**\n"
        "- **Risk-reduce Trim Candidates**: 0\n"
        "### GREEN Layer Status\n\n| Layer | Status |\n\n"
        "## 운용 상태 요약\n"
        f"- **target_portfolio_guard**: curr `{h_old[:12]}`\n"
        "## 1. 실행\n",
        encoding="utf-8",
    )
    _write_json(out / "report_clarity_validation.json", {"pass": True, "failures": []})
    _write_json(out / "bundle_consistency_validation.json", {"pass": False, "snapshot_stale": True})

    gate = validate_export_bundle_readiness(data, out)
    assert gate["pass"] is False
    assert any("mismatch" in f for f in gate["failures"])


def test_export_zip_includes_consistency_validation(tmp_path: Path) -> None:
    bundle = {
        "validation_prompt": "",
        "bundle_consistency_validation": {"pass": True},
        "report_clarity_validation": {"pass": True, "failures": []},
        "export_bundle_validation": {"pass": True, "failures": []},
        "reports": {},
    }
    zbytes = build_export_zip(bundle)
    with zipfile.ZipFile(BytesIO(zbytes)) as zf:
        names = set(zf.namelist())
    assert "bundle_consistency_validation.json" in names
    assert "export_bundle_validation.json" in names
