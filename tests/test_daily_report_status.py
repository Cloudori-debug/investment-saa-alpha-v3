from __future__ import annotations

import json
from pathlib import Path

from src.report_writer import build_daily_report_status_summary


def test_daily_report_status_summary_four_lines(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "final_execution_decision.json").write_text(
        json.dumps({
            "system_status": "RED",
            "execution_scope": "NO_TRADE",
            "technical_status": {
                "system_status": "RED",
                "execution_scope": "NO_TRADE",
            },
            "policy_cap": {
                "active": True,
                "cap_regime": "YELLOW_STABLE",
                "capped_execution_scope": "NO_TRADE",
            },
        }),
        encoding="utf-8",
    )
    exposure = {
        "by_dimension": {
            "region": {
                "current_pct": {"KR": 98.2, "US": 1.8},
                "target_pct": {"KR": 81.0, "US": 15.0},
            },
        },
    }
    cov = out / "price_coverage_report.json"
    cov.write_text(
        json.dumps({
            "core_price_gate": {
                "stale_core": [
                    {"ticker": "036530", "last_price_date": "2026-06-24", "price_age_business_days": 2},
                ],
            },
        }),
        encoding="utf-8",
    )
    lines = build_daily_report_status_summary(out, exposure)
    text = "\n".join(lines)
    assert "technical_status" in text
    assert "policy_cap" in text
    assert "operational_status" in text
    assert "look-through 편중" in text
    assert "core_price stale" in text
    assert "036530" in text
