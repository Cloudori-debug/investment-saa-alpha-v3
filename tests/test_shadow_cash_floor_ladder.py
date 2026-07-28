"""Shadow cash floor ladder (reference only) tests."""
from __future__ import annotations

import json
from pathlib import Path

from src.exposure.shadow_cash_floor_ladder import (
    build_shadow_cash_floor_ladder_status,
    load_shadow_cash_floor_ladder,
)


def test_load_reference_yaml() -> None:
    ref = load_shadow_cash_floor_ladder(Path("data"))
    assert ref.get("status") == "shadow_reference_only"
    assert ref.get("absolute_return_mode") is True
    assert ref.get("superseded_by") == "data/absolute_return_policy.yaml"
    assert float(ref["cash_floor_policy"]["floor_pct"]) == 28.5


def test_deployable_from_cash(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    out = tmp_path / "outputs"
    data_dir.mkdir()
    out.mkdir()
    (data_dir / "shadow_cash_floor_ladder.yaml").write_text(
        (Path("data") / "shadow_cash_floor_ladder.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (out / "exposure_lookthrough.json").write_text(json.dumps({
        "group_weights": {"current": {"cash_short_bond": 57.6}},
    }), encoding="utf-8")
    (out / "final_execution_decision.json").write_text(json.dumps({
        "data_gate": "YELLOW", "dry_run_days": 5,
    }), encoding="utf-8")
    (out / "shadow_diagnostic.json").write_text(json.dumps({
        "signals": {"buy_trigger_active": True},
    }), encoding="utf-8")

    status = build_shadow_cash_floor_ladder_status(out, data_dir=data_dir)
    assert status["current_cash_short_bond_pct"] == 57.6
    assert status["floor_pct"] == 28.5
    assert status["deployable_from_cash_pct"] == 29.1
    assert status["buy_1_max_from_cash_pct"] == 3.0
    assert status["buy_1_ready"] is False
    assert "Core benchmark ETF" in status["summary_line"]
    assert "Buy_2+ funds Core underweights" in status["summary_line"]
