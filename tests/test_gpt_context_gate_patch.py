from __future__ import annotations

import json
from pathlib import Path

from src.full_pipeline import _patch_gpt_context_gate


def test_patch_gpt_context_keeps_portfolio_gate_separate_from_policy(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "gpt_context.json").write_text(
        json.dumps({"schema_version": "1.0", "data_gate": "RED"}),
        encoding="utf-8",
    )
    _patch_gpt_context_gate(
        out,
        executable_gate="RED",
        policy_gate="YELLOW",
        health_gate="RED",
        portfolio_gate="GREEN",
        alpha_data_gate="GREEN",
        execution_scope="NO_TRADE",
        alpha_trade_permission="BLOCK_ALL",
        alpha_position_action="REVIEW_ONLY",
    )
    ctx = json.loads((out / "gpt_context.json").read_text(encoding="utf-8"))
    assert ctx["portfolio_gate"] == "GREEN"
    assert ctx["policy_gate"] == "YELLOW"
    assert ctx["compass_base_gate"] == "GREEN"
    assert ctx["execution_data_gate"] == "RED"
