"""Tests for alpha export review lists in AI bundle."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from src.validation.ai_export import build_ai_export_bundle
from src.validation.alpha_export_lists import (
    CANDIDATE_ONLY_NOTE,
    build_alpha_export_sections,
    build_alpha_replace_candidates,
    build_alpha_top30_scored,
)


def _write_scored(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "rank", "ticker", "name", "sector", "quality_score", "valuation_score",
        "momentum_score", "shareholder_return_score", "base_score", "penalty",
        "total_score", "grade", "eligible_action",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _base_row(ticker: str, score: float, grade: str, sector: str = "financial") -> dict:
    return {
        "rank": 1,
        "ticker": ticker,
        "name": ticker,
        "sector": sector,
        "quality_score": 50,
        "valuation_score": 50,
        "momentum_score": 50,
        "shareholder_return_score": 50,
        "base_score": score,
        "penalty": 0,
        "total_score": score,
        "grade": grade,
        "eligible_action": "WATCH",
    }


def _setup_export_fixture(tmp_path: Path, *, block_030190: bool = False) -> tuple[Path, Path]:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()

    b_rows = [_base_row(f"{i:06d}", 56.0 - i * 0.1, "B", "financial") for i in range(1, 31)]
    c_rows = [_base_row("999999", 40.0, "C", "tech")]
    _write_scored(out / "alpha_scored_universe.csv", b_rows + c_rows)

    (out / "gpt_context.json").write_text(
        json.dumps({
            "as_of": "2026-07-03",
            "excluded_summary": {"min_market_cap": 552},
            "shortlist_meta": {
                "scored_count": 31,
                "score_distribution": {
                    "scored_count": 31,
                    "grade_counts": {"B": 30, "C": 1, "Reject": 0},
                },
            },
        }),
        encoding="utf-8",
    )
    (out / "final_execution_decision.json").write_text(
        json.dumps({
            "allowed_actions": [],
            "final_trade_list": [],
            "execution_permissions": {},
        }),
        encoding="utf-8",
    )
    (out / "alpha_signal_board.csv").write_text(
        "ticker,name,grade,action_state,review_action,sector,current_weight_pct,target_weight_pct,total_score,eligible_action\n"
        "036530,SNT, C,Replace-review,REPLACE_CANDIDATE,holding,0,0,0,WATCH\n"
        "192400,쿠쿠,C,Replace-review,REPLACE_CANDIDATE,holding,0,0,0,WATCH\n",
        encoding="utf-8",
    )
    (data / "universe.csv").write_text("ticker,name,market\n000001,A,KOSPI\n", encoding="utf-8")
    if block_030190:
        (data / "target_portfolio_write_guard.json").write_text(
            json.dumps({"blocked_reintroductions": {"030190": {"ticker": "030190", "reason": "unintended"}}}),
            encoding="utf-8",
        )
    return data, out


def test_grade_b_universe_max_30(tmp_path: Path) -> None:
    data, out = _setup_export_fixture(tmp_path)
    sections = build_alpha_export_sections(data, out)
    b_list = sections["alpha_grade_b_universe"]
    assert len(b_list) <= 30
    assert all(r["grade"] == "B" for r in b_list)


def test_top30_sorted_desc(tmp_path: Path) -> None:
    data, out = _setup_export_fixture(tmp_path)
    top = build_alpha_export_sections(data, out)["alpha_top30_scored"]
    scores = [float(r["total_score"]) for r in top]
    assert scores == sorted(scores, reverse=True)
    assert len(top) <= 30


def test_buy_permission_false_when_actual_buy_zero(tmp_path: Path) -> None:
    data, out = _setup_export_fixture(tmp_path)
    sections = build_alpha_export_sections(data, out)
    assert sections["alpha_screening_meta"]["actual_buy_allowed"] == 0
    assert sections["alpha_screening_meta"]["buy_permission_status"] == "BLOCKED"
    for row in sections["alpha_grade_b_universe"] + sections["alpha_top30_scored"]:
        assert row["buy_permission"] is False


def test_replace_candidates_count_range(tmp_path: Path) -> None:
    data, out = _setup_export_fixture(tmp_path)
    replace_rows = build_alpha_export_sections(data, out)["alpha_replace_candidates"]
    assert 0 <= len(replace_rows) <= 2 * 5
    by_from: dict[str, int] = {}
    for row in replace_rows:
        by_from[row["replace_from_ticker"]] = by_from.get(row["replace_from_ticker"], 0) + 1
    assert all(0 < count <= 5 for count in by_from.values())


def test_full_scored_table_not_in_bundle(tmp_path: Path) -> None:
    data, out = _setup_export_fixture(tmp_path)
    bundle = build_ai_export_bundle(data, out, include_health=False)
    assert "alpha_scored_universe" not in bundle
    assert "alpha_grade_b_universe" in bundle
    assert len(bundle["alpha_grade_b_universe"]) <= 30


def test_blocked_030190_excluded(tmp_path: Path) -> None:
    data, out = _setup_export_fixture(tmp_path, block_030190=True)
    scored = [
        _base_row("030190", 55.0, "B", "data_service"),
        _base_row("005830", 54.0, "B", "insurance"),
    ]
    _write_scored(out / "alpha_scored_universe.csv", scored)
    sections = build_alpha_export_sections(data, out)
    tickers = {r["ticker"] for r in sections["alpha_grade_b_universe"]}
    assert "030190" not in tickers
    replace_tickers = {r["candidate_ticker"] for r in sections["alpha_replace_candidates"]}
    assert "030190" not in replace_tickers


def test_daily_report_candidate_only_note(tmp_path: Path) -> None:
    from src.validation.alpha_export_lists import build_alpha_screening_summary_lines

    data, out = _setup_export_fixture(tmp_path)
    lines = build_alpha_screening_summary_lines(out)
    text = "\n".join(lines)
    assert CANDIDATE_ONLY_NOTE in text
    assert "B-grade universe" in text
