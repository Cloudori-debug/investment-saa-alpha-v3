from __future__ import annotations

import json
from pathlib import Path

from src.validation.output_cross_validation import validate_outputs_cross_check


def test_cross_validation_passes_on_consistent_outputs(tmp_path):
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "system_health.json").write_text(json.dumps({
        "as_of": "2026-06-24",
        "overall": "warn",
        "meta": {"restricted_modes": ["RESEARCH_QUALITY_WARN"]},
        "checks": [
            {
                "module": "alpha",
                "name": "core_price_gate",
                "status": "pass",
                "message": "ok",
                "detail": {"status": "pass"},
            },
            {
                "module": "alpha",
                "name": "alpha_price_gate",
                "status": "pass",
                "message": "ok",
                "detail": {"status": "pass", "action": "ALPHA_OK"},
            },
        ],
    }, ensure_ascii=False), encoding="utf-8")
    (out / "price_coverage_report.json").write_text(json.dumps({
        "as_of": "2026-06-24",
        "restricted_modes": [],
        "core_price_gate": {"status": "pass"},
        "alpha_price_gate": {"status": "pass", "action": "ALPHA_OK"},
    }, ensure_ascii=False), encoding="utf-8")
    (out / "final_execution_decision.json").write_text(json.dumps({
        "as_of": "2026-06-24",
        "data_gate": "GREEN",
        "execution_scope": "FULL_WITH_ALPHA",
        "data_gate_detail": {"health_gate": "GREEN"},
        "execution_permissions": {
            "alpha_price_action": "ALPHA_OK",
            "blocked_capabilities": [],
        },
    }, ensure_ascii=False), encoding="utf-8")
    (out / "trade_actions.csv").write_text(
        "ticker,name,action,reason,allowed_size_pct,priority\n"
        "069500,KODEX,Wait,ok,0,Medium\n",
        encoding="utf-8",
    )

    report = validate_outputs_cross_check(out)
    assert report.overall in ("pass", "warn")
    assert not any(i.check_id == "CV-01" and i.status == "fail" for i in report.items)
