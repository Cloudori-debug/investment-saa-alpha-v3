"""v1.0.3 Fail-Soft Validation Patch tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.alpha.data_gate import evaluate_candidate_sector_data_gate
from src.report.execution_metrics import build_execution_authority_lines, count_executable_actions
from src.validation.fail_soft_permissions import (
    build_fail_soft_permissions,
    derive_alpha_auto_buy_permission,
    derive_core_etf_permission,
)
from src.validation.sector_coverage import compute_candidate_sector_coverage, merge_coverage_metrics
from src.validation.validation_findings import FINDING_TYPES, build_validation_findings


def test_sector_coverage_all_unknown() -> None:
    cands = [{"sector": "unknown"} for _ in range(14)]
    cov = compute_candidate_sector_coverage(cands)
    assert cov["unknown_rate"] == 1.0
    assert cov["candidate_sector_coverage_pct"] == 0.0


def test_candidate_sector_gate_data_limited_at_100pct() -> None:
    gate, notes = evaluate_candidate_sector_data_gate(1.0, 1.0)
    assert gate == "YELLOW_DATA_LIMITED"
    assert notes


def test_core_etf_not_blocked_by_alpha_sector_unknown() -> None:
    core = derive_core_etf_permission(
        execution_scope="ETF_ONLY",
        core_price_gate_status="pass",
        health_gate="GREEN",
        data_gate="GREEN",
        portfolio_gate="GREEN",
        allowed_capabilities=["ETF_REBALANCE", "RISK_REDUCE_TRIM"],
        policy_permissions={"etf_new_buy": "REVIEW_ONLY"},
        dry_run_days=6,
        dry_run_required=10,
    )
    assert core in {"ALLOWED", "RESTRICTED"}
    assert core != "BLOCKED"

    alpha_auto = derive_alpha_auto_buy_permission(
        alpha_trade_permission="BLOCK_NEW_BUY",
        alpha_position_action="RISK_REDUCE_ONLY",
        alpha_price_action="ALPHA_OK",
        sector_coverage={"shortlist_unknown_rate": 1.0, "top10_unknown_rate": 1.0},
        alpha_data_gate="GREEN",
    )
    assert alpha_auto == "BLOCKED"


def test_alpha_auto_buy_blocked_on_sector_unknown_even_if_allow_new() -> None:
    alpha_auto = derive_alpha_auto_buy_permission(
        alpha_trade_permission="ALLOW_NEW",
        alpha_position_action="EXECUTABLE",
        alpha_price_action="ALPHA_OK",
        sector_coverage={"shortlist_unknown_rate": 1.0, "top10_unknown_rate": 1.0},
        alpha_data_gate="GREEN",
    )
    assert alpha_auto == "BLOCKED"


def test_fail_soft_permissions_structure() -> None:
    doc = build_fail_soft_permissions(
        execution_scope="ETF_ONLY",
        alpha_trade_permission="BLOCK_NEW_BUY",
        alpha_position_action="RISK_REDUCE_ONLY",
        alpha_price_action="ALPHA_OK",
        core_price_gate_status="pass",
        alpha_price_gate_status="pass",
        health_gate="GREEN",
        data_gate="GREEN",
        portfolio_gate="GREEN",
        alpha_data_gate="GREEN",
        allowed_capabilities=["ETF_REBALANCE", "RISK_REDUCE_TRIM"],
        blocked_capabilities=["KR_ALPHA_NEW_BUY"],
        policy_permissions={"etf_new_buy": "REVIEW_ONLY", "kr_alpha_new_buy": "BLOCKED"},
        sector_coverage={"shortlist_unknown_rate": 1.0, "top10_unknown_rate": 1.0},
        candidate_count=14,
        actual_buy_allowed=0,
        dry_run_days=6,
        dry_run_required=10,
        policy_cap_active=True,
        alpha_sector_data_gate="YELLOW_DATA_LIMITED",
    )
    assert doc["patch_version"] == "v1.0.3"
    assert doc["core_etf_permission"] in {"RESTRICTED", "ALLOWED"}
    assert doc["alpha_auto_buy_permission"] == "BLOCKED"
    assert doc["alpha_research_permission"] == "ALLOWED"
    assert doc["alpha_sector_data_gate"] == "YELLOW_DATA_LIMITED"


def test_validation_findings_data_defect_not_buy_permission() -> None:
    findings = build_validation_findings(
        run_id="test",
        as_of="2026-07-01",
        fail_soft={
            "sector_coverage": {"shortlist_unknown_rate": 1.0},
            "manual_review_required": True,
        },
        clarity=None,
        cross_val=None,
        actual_buy_allowed=0,
        execution_scope="ETF_ONLY",
        dry_run_days=6,
        dry_run_required=10,
        core_etf_permission="RESTRICTED",
        alpha_auto_buy_permission="BLOCKED",
    )
    assert findings["manual_review_required"] is True
    assert any(f["type"] == "DATA_DEFECT_BLOCK" for f in findings["findings"])
    for f in findings["findings"]:
        assert f["grants_buy_permission"] is False
        assert f["type"] in FINDING_TYPES


def test_authority_lines_separate_core_and_alpha() -> None:
    final = {
        "system_status": "YELLOW",
        "execution_scope": "ETF_ONLY",
        "dry_run_days": 6,
        "operating": {"dry_run_required": 10},
        "allowed_actions": [],
        "final_trade_list": [],
        "execution_permissions": {
            "core_etf_permission": "RESTRICTED",
            "alpha_auto_buy_permission": "BLOCKED",
            "alpha_research_permission": "ALLOWED",
            "main_block_reason": "dry_run 6/10",
            "alpha_sector_data_gate": "YELLOW_DATA_LIMITED",
            "sector_coverage": {"candidate_sector_coverage_pct": 0.0, "shortlist_unknown_rate": 1.0},
            "manual_review_required": True,
            "kr_alpha_replace": "BLOCKED",
        },
    }
    text = "\n".join(build_execution_authority_lines(final))
    assert "**Core ETF permission**: **RESTRICTED**" in text
    assert "**Alpha auto-buy permission**: **BLOCKED**" in text
    assert "**Alpha research permission**: **ALLOWED**" in text
    assert "**Manual review required**: **yes**" in text


def test_merge_coverage_metrics() -> None:
    sl = compute_candidate_sector_coverage([{"sector": ""}] * 14)
    t10 = compute_candidate_sector_coverage([{"sector": ""}] * 10)
    merged = merge_coverage_metrics(sl, t10)
    assert merged["shortlist_count"] == 14
    assert merged["top10_unknown_rate"] == 1.0
