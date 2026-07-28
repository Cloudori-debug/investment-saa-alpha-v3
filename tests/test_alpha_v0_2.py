"""Alpha Signal Board v0.2 — sector mapping, flow, target portfolio guard."""
from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest

from src.alpha.alpha_signal_board import build_alpha_signal_board, derive_action_state
from src.alpha.investor_flows import classify_flow_signal, write_investor_flows_template
from src.alpha.schemas import AlphaCandidate, HoldingReview
from src.alpha.sector_mapping import load_krx_sector_mapping, resolve_sector
from src.alpha.target_portfolio_guard import (
    TargetPortfolioWriteBlockedError,
    check_unapproved_target_overwrite,
    write_target_portfolio_approved,
)
from src.exposure.absolute_return_policy import write_absolute_return_target_portfolio
from src.validation.fail_soft_permissions import derive_alpha_auto_buy_permission

DATA = Path(__file__).resolve().parents[1] / "data"


def _cand(**kw) -> AlphaCandidate:
    base = {
        "rank": 1,
        "ticker": "071050",
        "name": "한국금융지주",
        "sector": "unknown",
        "quality_score": 58.0,
        "valuation_score": 61.0,
        "momentum_score": 76.0,
        "shareholder_return_score": 60.0,
        "base_score": 57.0,
        "penalty": 0.0,
        "total_score": 57.0,
        "grade": "B",
        "key_reason": "balanced QVM",
        "eligible_action": "BUY_CANDIDATE",
    }
    base.update(kw)
    return AlphaCandidate.model_validate(base)


def test_sector_unknown_blocks_buy_allowed() -> None:
    state, missing, blockers = derive_action_state(
        grade="A",
        eligible_action="BUY_CANDIDATE",
        review_action=None,
        current_weight=0,
        target_weight=0,
        axis_passes=5,
        sector_resolved=False,
        sector_unknown_rate=1.0,
        alpha_auto_buy_allowed=True,
        data_gate="GREEN",
        flow_signal="NEUTRAL",
    )
    assert state != "Buy-allowed"
    assert "sector_unknown" in blockers
    assert missing.get("sector_known") == "false"


def test_manual_sector_mapping_priority(tmp_path: Path) -> None:
    manual = tmp_path / "krx_sector_mapping_manual.csv"
    shutil.copy(DATA / "krx_sector_mapping_manual.csv", manual)
    mapping = load_krx_sector_mapping(tmp_path)
    res = resolve_sector("071050", "한국금융지주", "unknown", mapping)
    assert res["resolved"] is True
    assert res["source"] == "manual"
    assert res["sector_group"] == "financial"


def test_sector_coverage_threshold_blocks_alpha_buy() -> None:
    blocked = derive_alpha_auto_buy_permission(
        alpha_trade_permission="ALLOW_NEW",
        alpha_position_action="EXECUTABLE",
        alpha_price_action="ALPHA_OK",
        sector_coverage={
            "shortlist_unknown_rate": 0.0,
            "top10_unknown_rate": 0.0,
            "top10_sector_coverage_pct": 70.0,
        },
        alpha_data_gate="GREEN",
    )
    assert blocked == "BLOCKED"

    allowed = derive_alpha_auto_buy_permission(
        alpha_trade_permission="ALLOW_NEW",
        alpha_position_action="EXECUTABLE",
        alpha_price_action="ALPHA_OK",
        sector_coverage={
            "shortlist_unknown_rate": 0.0,
            "top10_unknown_rate": 0.0,
            "top10_sector_coverage_pct": 90.0,
        },
        alpha_data_gate="GREEN",
    )
    assert allowed == "ALLOWED"


def test_flow_stale_blocks_buy_allowed() -> None:
    state, missing, blockers = derive_action_state(
        grade="A",
        eligible_action="BUY_CANDIDATE",
        review_action=None,
        current_weight=0,
        target_weight=0,
        axis_passes=5,
        sector_resolved=True,
        sector_unknown_rate=0,
        alpha_auto_buy_allowed=True,
        data_gate="GREEN",
        flow_signal="STALE",
    )
    assert state != "Buy-allowed"
    assert "flow_stale" in blockers
    assert missing.get("flow_signal") == "STALE"


def test_distribution_flow_blocks_buy_allowed() -> None:
    state, missing, blockers = derive_action_state(
        grade="A",
        eligible_action="BUY_CANDIDATE",
        review_action=None,
        current_weight=0,
        target_weight=0,
        axis_passes=5,
        sector_resolved=True,
        sector_unknown_rate=0,
        alpha_auto_buy_allowed=True,
        data_gate="GREEN",
        flow_signal="DISTRIBUTION",
    )
    assert state != "Buy-allowed"
    assert "flow_distribution" in blockers
    assert missing.get("flow_signal") == "DISTRIBUTION"


def test_accumulation_flow_can_promote_to_buy_ready(tmp_path: Path) -> None:
    shutil.copy(DATA / "krx_sector_mapping_manual.csv", tmp_path / "krx_sector_mapping_manual.csv")
    write_investor_flows_template(
        tmp_path,
        [{"ticker": "071050", "name": "한국금융지주"}],
        as_of="2026-07-02",
    )
    flows_path = tmp_path / "investor_flows.csv"
    rows = list(csv.DictReader(flows_path.open(encoding="utf-8")))
    rows[0]["flow_signal"] = "ACCUMULATION"
    rows[0]["flow_score"] = "80"
    rows[0]["foreign_20d_mcap_pct"] = "0.15"
    rows[0]["staleness_days"] = "0"
    with flows_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    board = build_alpha_signal_board(
        candidates=[_cand(eligible_action="WATCH", grade="B")],
        holdings_review=[],
        graded_by_ticker={"071050": _cand(eligible_action="WATCH", grade="B").model_dump()},
        fundamentals={},
        prices={},
        data_dir=tmp_path,
        sector_coverage={"shortlist_unknown_rate": 0, "top10_sector_coverage_pct": 100},
        alpha_auto_buy_permission="BLOCKED",
        data_gate="GREEN",
    )
    assert board[0].action_state == "Buy-ready"
    assert "ACCUMULATION" in board[0].flow_signal


def test_target_portfolio_not_overwritten_without_approval(tmp_path: Path) -> None:
    target = tmp_path / "target_portfolio.csv"
    target.write_text("ticker,name,asset_group,sector,role,target_weight,min_weight,max_weight\n", encoding="utf-8")
    with pytest.raises(TargetPortfolioWriteBlockedError):
        write_absolute_return_target_portfolio(tmp_path, approve=False)

    write_target_portfolio_approved(
        tmp_path,
        [{
            "ticker": "069500",
            "name": "KODEX 200",
            "asset_group": "domestic_beta",
            "sector": "index",
            "role": "beta",
            "target_weight": 10.0,
            "min_weight": 5.0,
            "max_weight": 15.0,
        }],
        approved_by="test",
    )
    assert "069500" in target.read_text(encoding="utf-8")


def test_classify_flow_signal_rules() -> None:
    assert classify_flow_signal(
        foreign_5d_mcap_pct=-0.15,
        foreign_20d_mcap_pct=0.0,
        institution_5d_mcap_pct=0.0,
        staleness_days=0,
    ) == "DISTRIBUTION"
    assert classify_flow_signal(
        foreign_5d_mcap_pct=0.0,
        foreign_20d_mcap_pct=0.12,
        institution_5d_mcap_pct=0.0,
        staleness_days=0,
    ) == "ACCUMULATION"
    assert classify_flow_signal(
        foreign_5d_mcap_pct=0.0,
        foreign_20d_mcap_pct=0.0,
        institution_5d_mcap_pct=0.0,
        staleness_days=5,
    ) == "STALE"


def test_unapproved_target_overwrite_warns(tmp_path: Path) -> None:
    path = tmp_path / "target_portfolio.csv"
    path.write_text("original\n", encoding="utf-8")
    guard = tmp_path / "target_portfolio_write_guard.json"
    guard.write_text('{"operational_target_hash": "deadbeef"}', encoding="utf-8")
    warnings = check_unapproved_target_overwrite(tmp_path)
    assert warnings
