"""Tests for Alpha flow dashboard (UI data + analytics)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.alpha_flow.dashboard_data import (
    build_holdings_target_flow_table,
    build_v2_candidate_flow_table,
    compute_dashboard_cards,
    load_trim_watch_tables,
)
from src.alpha_flow.flow_analytics import (
    consecutive_cobuy,
    consecutive_days,
    compute_streak_row,
    parse_daily_timeseries_from_df,
)
from src.alpha_flow.policy import FLOW_UI_POLICY_LINES


def test_consecutive_days_breaks_on_zero() -> None:
    assert consecutive_days([1.0, 2.0, 0.0, 3.0], "buy") == 1
    assert consecutive_days([1.0, 2.0, 3.0], "buy") == 3
    assert consecutive_days([-1.0, -2.0, -3.0], "sell") == 3


def test_consecutive_cobuy() -> None:
    p = [1.0, 2.0, 3.0, 4.0]
    f = [1.0, 1.0, 1.0, 1.0]
    assert consecutive_cobuy(p, f) == 4


def test_compute_streak_row_from_daily() -> None:
    daily = pd.DataFrame([
        {"date": "2026-07-01", "pension_net_buy_amount": 1e9, "foreign_net_buy_amount": 1e9},
        {"date": "2026-07-02", "pension_net_buy_amount": 2e9, "foreign_net_buy_amount": 1e9},
        {"date": "2026-07-03", "pension_net_buy_amount": 3e9, "foreign_net_buy_amount": -1e9},
    ])
    row = compute_streak_row("005830", "DB", "KOSPI", daily)
    assert row["pension_consecutive_days"] == 3
    assert row["pension_streak_direction"] == "buy"
    assert row["actual_consecutive_days"] == "true"
    assert row["cobuy_consecutive_days"] == 0


def test_parse_daily_timeseries_from_df() -> None:
    df = pd.DataFrame(
        {"외국인": [100.0, 200.0], "기관": [50.0, -10.0]},
        index=["20260701", "20260702"],
    )
    rows = parse_daily_timeseries_from_df(
        df, ticker="005830", name="DB", market="KOSPI", as_of="2026-07-03", mcap=1e12,
    )
    assert len(rows) == 2
    assert rows[-1]["foreign_net_buy_amount"] == 200.0


def test_holdings_flow_fail_soft(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    pd.DataFrame(columns=["ticker"]).to_csv(data / "positions.csv", index=False)
    pd.DataFrame(columns=["ticker"]).to_csv(data / "target_portfolio.csv", index=False)
    assert build_holdings_target_flow_table(data, out).empty
    assert build_v2_candidate_flow_table(out).empty


def test_trim_watch_held_informational_split(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    pd.DataFrame([
        {"ticker": "005830", "trim_category": "held_or_target", "trim_reason": "grade"},
        {"ticker": "035720", "trim_category": "informational", "trim_reason": "watch"},
    ]).to_csv(out / "alpha_v2_trim_watch_detail.csv", index=False)
    held, info = load_trim_watch_tables(out)
    assert len(held) == 1
    assert len(info) == 1


def test_dashboard_cards_no_trade(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "final_execution_decision.json").write_text(
        '{"execution_scope": "NO_TRADE"}', encoding="utf-8",
    )
    (out / "alpha_v2_summary.json").write_text(
        '{"coverage": {"stale_flow_count": 5, "fresh_flow_count": 3}}', encoding="utf-8",
    )
    cards = compute_dashboard_cards(out)
    assert cards["no_trade"] is True
    assert cards["actual_buy_allowed"] == 0


def test_policy_lines_present() -> None:
    text = "\n".join(FLOW_UI_POLICY_LINES)
    assert "매수 허가" in text
    assert "review-only" in text


def test_flow_status_panel_import() -> None:
    from src.ui.flow_status_panel import render_flow_status_tab

    assert callable(render_flow_status_tab)
