"""Alpha Signal Board tests."""
from __future__ import annotations

import shutil
from pathlib import Path

from src.alpha.alpha_signal_board import (
    build_alpha_signal_board,
    derive_action_state,
    summarize_signal_board,
)
from src.alpha.schemas import AlphaCandidate, HoldingReview

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
        "eligible_action": "WATCH",
    }
    base.update(kw)
    return AlphaCandidate.model_validate(base)


def test_grade_separate_from_action_state() -> None:
    state, missing, blockers = derive_action_state(
        grade="B",
        eligible_action="WATCH",
        review_action=None,
        current_weight=0,
        target_weight=0,
        axis_passes=4,
        sector_resolved=True,
        sector_unknown_rate=0,
        alpha_auto_buy_allowed=False,
        data_gate="GREEN",
        flow_signal="NEUTRAL",
    )
    assert state == "Buy-ready"
    assert missing.get("execution_permission") == "blocked"


def test_sector_unknown_blocks_buy_allowed() -> None:
    state, _, blockers = derive_action_state(
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


def test_holding_trim_priority(tmp_path: Path) -> None:
    shutil.copy(DATA / "krx_sector_mapping_manual.csv", tmp_path / "krx_sector_mapping_manual.csv")
    rows = build_alpha_signal_board(
        candidates=[],
        holdings_review=[
            HoldingReview(
                ticker="005440",
                name="현대지에프홀딩스",
                current_weight=9.0,
                target_weight=1.1,
                alpha_score=50,
                grade="B",
                review_action="KEEP",
                reason="test",
            )
        ],
        graded_by_ticker={"005440": {"ticker": "005440", "name": "현대지에프홀딩스", "grade": "B", "total_score": 50, "eligible_action": "WATCH"}},
        fundamentals={},
        prices={},
        data_dir=tmp_path,
        sector_coverage={"shortlist_unknown_rate": 0},
        alpha_auto_buy_permission="BLOCKED",
        data_gate="GREEN",
    )
    assert rows[0].action_state == "Trim"


def test_signal_board_summary(tmp_path: Path) -> None:
    shutil.copy(DATA / "krx_sector_mapping_manual.csv", tmp_path / "krx_sector_mapping_manual.csv")
    rows = build_alpha_signal_board(
        candidates=[_cand()],
        holdings_review=[],
        graded_by_ticker={"071050": _cand().model_dump()},
        fundamentals={},
        prices={},
        data_dir=tmp_path,
        sector_coverage={"shortlist_unknown_rate": 1.0, "top10_sector_coverage_pct": 0},
        alpha_auto_buy_permission="BLOCKED",
        data_gate="GREEN",
        alpha_sector_data_gate="YELLOW_DATA_LIMITED",
    )
    summary = summarize_signal_board(rows)
    assert summary["total"] >= 1
    assert rows[0].sector == "증권/금융지주"


def test_buy_trigger_text_blocked_execution_permission() -> None:
    from src.alpha.alpha_signal_board import _buy_trigger_text

    text = _buy_trigger_text(
        {"execution_permission": "blocked", "eligible_action_buy_candidate": "false"},
        {"price": True, "volume": True, "flow": True},
    )
    assert "ALLOWED" not in text
    assert "BLOCKED" in text
    assert "alpha_auto_buy 승인 필요" in text


def test_truncate_display_preserves_blocked_token() -> None:
    from src.alpha.alpha_signal_board import _truncate_display

    raw = (
        "execution_permission:blocked; eligible_action_buy_candidate:false; "
        "sector_known:false"
    )
    out = _truncate_display(raw, 56)
    assert "blocked" in out
    assert "false" in out or out.endswith("…")


def test_signal_board_table_truncation_note() -> None:
    from src.alpha.alpha_signal_board import SignalBoardRow, format_signal_board_report_section, summarize_signal_board

    rows: list[SignalBoardRow] = []
    for i in range(16):
        rows.append(SignalBoardRow(
            ticker=f"{i:06d}", name=f"Buy{i}", grade="B", action_state="Buy-ready",
            thesis="", fundamental_signal="", valuation_signal="", volume_signal="",
            flow_signal="", flow_score=0.0, flow_blocker="", price_signal="",
            catalyst_signal="", risk_blocker="", missing_for_buy="", buy_trigger="",
            add_trigger="", trim_trigger="", exit_trigger="", confidence="",
            sector="", sector_source="", current_weight_pct=0.0, target_weight_pct=0.0,
            total_score=50.0 - i, eligible_action="", review_action="",
        ))
    for i in range(8):
        rows.append(SignalBoardRow(
            ticker=f"W{i:05d}", name=f"Watch{i}", grade="C", action_state="Watch",
            thesis="", fundamental_signal="", valuation_signal="", volume_signal="",
            flow_signal="", flow_score=0.0, flow_blocker="", price_signal="",
            catalyst_signal="", risk_blocker="", missing_for_buy="", buy_trigger="",
            add_trigger="", trim_trigger="", exit_trigger="", confidence="",
            sector="", sector_source="", current_weight_pct=0.0, target_weight_pct=0.0,
            total_score=10.0 - i, eligible_action="", review_action="",
        ))
    summary = summarize_signal_board(rows)
    md = "\n".join(format_signal_board_report_section(rows, summary))
    assert "**Watch**: 8" in md
    assert "Watch 4/8 표시" in md or "4/8" in md
    assert "alpha_signal_board.csv" in md
