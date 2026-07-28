"""Tests for investor flow auto-refresh (flow_refresh.py)."""
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from src.alpha.alpha_signal_board import build_alpha_signal_board, derive_action_state
from src.alpha.flow_refresh import (
    is_manual_verified,
    refresh_investor_flows,
    resolve_flow_target_tickers,
    run_flow_refresh,
)
from src.alpha.investor_flows import FLOW_COLUMNS, load_investor_flows, write_investor_flows_template
from src.alpha.schemas import AlphaCandidate, HoldingReview
from src.alpha.target_portfolio_guard import TargetPortfolioWriteBlockedError
from src.exposure.absolute_return_policy import write_absolute_return_target_portfolio

DATA = Path(__file__).resolve().parents[1] / "data"


def _mock_df(foreign: list[float], institution: list[float] | None = None) -> pd.DataFrame:
    institution = institution or [0.0] * len(foreign)
    return pd.DataFrame(
        {"외국인": foreign, "기관": institution},
        index=pd.date_range("2026-06-01", periods=len(foreign), freq="B"),
    )


def _fetch_ok(_ticker: str, _start: str, _end: str) -> pd.DataFrame:
    return _mock_df([1e9] * 20, [5e8] * 20)


def _fetch_fail(_ticker: str, _start: str, _end: str) -> None:
    return None


def test_flow_refresh_writes_investor_flows(tmp_path: Path) -> None:
    prices = tmp_path / "prices.csv"
    prices.write_text(
        "date,ticker,close,market_cap\n2026-07-02,071050,100,1000000000000\n",
        encoding="utf-8",
    )
    tickers = [{"ticker": "071050", "name": "한국금융지주"}]
    result = refresh_investor_flows(
        tmp_path,
        tickers,
        as_of="2026-07-02",
        sleep_sec=0,
        use_cache=False,
        fetch_fn=_fetch_ok,
    )
    path = tmp_path / "investor_flows.csv"
    assert path.exists()
    assert result.refreshed_count == 1
    rows = load_investor_flows(tmp_path)
    assert rows["071050"]["flow_signal"] in {"ACCUMULATION", "MILD_ACCUMULATION", "NEUTRAL"}
    assert rows["071050"]["source"] == "auto_pykrx"


def test_flow_refresh_failure_marks_stale(tmp_path: Path) -> None:
    tickers = [{"ticker": "071050", "name": "한국금융지주"}]
    result = refresh_investor_flows(
        tmp_path,
        tickers,
        as_of="2026-07-02",
        sleep_sec=0,
        use_cache=False,
        fetch_fn=_fetch_fail,
    )
    rows = load_investor_flows(tmp_path)
    assert rows["071050"]["flow_signal"] == "STALE"
    assert "071050" in result.failed_tickers


def test_manual_verified_flow_has_priority(tmp_path: Path) -> None:
    path = tmp_path / "investor_flows.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FLOW_COLUMNS)
        writer.writeheader()
        writer.writerow({
            "date": "2026-07-02",
            "ticker": "071050",
            "name": "한국금융지주",
            "foreign_20d_mcap_pct": "0.20",
            "flow_score": "80",
            "flow_signal": "ACCUMULATION",
            "source": "manual_verified",
            "staleness_days": "0",
        })

    result = refresh_investor_flows(
        tmp_path,
        [{"ticker": "071050", "name": "한국금융지주"}],
        as_of="2026-07-02",
        sleep_sec=0,
        use_cache=False,
        fetch_fn=_fetch_fail,
    )
    rows = load_investor_flows(tmp_path)
    assert rows["071050"]["source"] == "manual_verified"
    assert rows["071050"]["flow_signal"] == "ACCUMULATION"
    assert result.skipped_manual_count == 1
    assert is_manual_verified(rows["071050"])


def test_stale_flow_blocks_buy_allowed() -> None:
    state, _missing, blockers = derive_action_state(
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


def test_accumulation_promotes_watch_to_buy_ready_only(tmp_path: Path) -> None:
    shutil_manual = DATA / "krx_sector_mapping_manual.csv"
    if shutil_manual.exists():
        (tmp_path / "krx_sector_mapping_manual.csv").write_bytes(shutil_manual.read_bytes())

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
    rows[0]["source"] = "manual_verified"
    with flows_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    cand = AlphaCandidate.model_validate({
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
    })
    board = build_alpha_signal_board(
        candidates=[cand],
        holdings_review=[],
        graded_by_ticker={"071050": cand.model_dump()},
        fundamentals={},
        prices={},
        data_dir=tmp_path,
        sector_coverage={"shortlist_unknown_rate": 0, "top10_sector_coverage_pct": 100},
        alpha_auto_buy_permission="BLOCKED",
        data_gate="GREEN",
    )
    assert board[0].action_state == "Buy-ready"
    assert board[0].action_state != "Buy-allowed"


def test_flow_refresh_does_not_change_target_portfolio(tmp_path: Path) -> None:
    target = tmp_path / "target_portfolio.csv"
    target.write_text(
        "ticker,name,asset_group,sector,role,target_weight,min_weight,max_weight\n",
        encoding="utf-8",
    )
    before = target.read_bytes()
    run_flow_refresh(
        tmp_path,
        as_of="2026-07-02",
        tickers=[{"ticker": "071050", "name": "한국금융지주"}],
        sleep_sec=0,
        fetch_fn=_fetch_fail,
    )
    assert target.read_bytes() == before
    with pytest.raises(TargetPortfolioWriteBlockedError):
        write_absolute_return_target_portfolio(tmp_path, approve=False)


def test_resolve_flow_target_tickers_prefers_signal_board(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    board = out / "alpha_signal_board.csv"
    board.write_text(
        "ticker,name,action_state\n055550,신한지주,Watch\n",
        encoding="utf-8",
    )
    tickers = resolve_flow_target_tickers(
        holdings=[],
        candidates=[],
        signal_board_path=board,
    )
    assert len(tickers) == 1
    assert tickers[0]["ticker"] == "055550"
