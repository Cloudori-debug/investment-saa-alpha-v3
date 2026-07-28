from __future__ import annotations

import json
from pathlib import Path

from src.alpha.gate_stamp import build_alpha_execution_status
from src.compass.group_gap import compute_group_gaps, group_gap_rows_to_trigger_map
from src.final_execution_decision import GROUP_GAP_SOURCE_COMPASS, build_final_execution_decision
from src.models import TradeAction
from src.validation.acceptance_check import run_acceptance_check


def test_group_gap_trigger_map_matches_compass():
    from src.compass.models import GroupGapRow

    rows = [
        GroupGapRow(
            asset_group="cash_short_bond",
            current=52.0,
            target=37.0,
            gap=-15.0,
            action="Hold",
            reason="",
        )
    ]
    m = group_gap_rows_to_trigger_map(rows)
    assert m["cash_short_bond"]["gap"] == -15.0


def test_alpha_gate_stamp_research_only_on_etf_only():
    status = build_alpha_execution_status(
        data_gate="YELLOW",
        alpha_data_gate="GREEN",
        execution_scope="ETF_ONLY",
        alpha_trade_permission="BLOCK_NEW_BUY",
        alpha_position_action="REVIEW_ONLY",
    )
    assert status["alpha_execution_status"] == "RESEARCH_ONLY"
    assert status["usage"] == "research_only"


def test_final_execution_decision_schema():
    decision = build_final_execution_decision(
        run_id="test-run",
        as_of="2026-06-17",
        system_status="YELLOW",
        data_gate="YELLOW",
        execution_scope="ETF_ONLY",
        alpha_approval="RESTRICTED",
        alpha_execution_status="RESEARCH_ONLY",
        group_gap_source=GROUP_GAP_SOURCE_COMPASS,
        operational_verdict="test",
        dry_run_days=1,
        executable_actions=[
            TradeAction(
                ticker="CASH",
                name="예수금",
                action="Park",
                reason="funding",
                allowed_size_pct=0,
                priority="Low",
            )
        ],
        review_actions=[
            TradeAction(
                ticker="005830",
                name="DB",
                action="Replace",
                reason="theoretical",
                allowed_size_pct=0,
                priority="Low",
            )
        ],
    )
    d = decision.to_dict()
    assert d["authoritative"] is True
    assert d["group_gap_source"] == GROUP_GAP_SOURCE_COMPASS
    assert any(b["ticker"] == "005830" for b in d["blocked_actions"])


def test_acceptance_scope_matches_decision_log(tmp_path):
    root = Path(__file__).resolve().parents[1]
    data = root / "data"
    out = root / "outputs"
    if not (out / "decision_log.jsonl").exists():
        return
    report = run_acceptance_check(data, out)
    log_line = (out / "decision_log.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1]
    log = json.loads(log_line)
    assert report.execution_scope == log.get("execution_scope")
