"""Shadow history ledger — append-only review-only accumulation."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from src.shadow.history_ledger import (
    ALPHA_V2_SHADOW_FIELDS,
    FLOW_DASHBOARD_FIELDS,
    append_shadow_history_ledger,
    build_alpha_v2_shadow_rows,
    build_flow_dashboard_rows,
    evaluate_candidate_outcomes,
)


def _write_target_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "ticker", "name", "asset_group", "sector", "role",
        "target_weight", "min_weight", "max_weight",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def _setup_v2_outputs(out: Path) -> None:
    scored = [{
        "rank": "1", "ticker": "005830", "name": "DB손해보험", "sector": "insurance",
        "market": "KOSPI", "tier": "Core", "grade": "A",
        "quality_score": "70", "valuation_score": "65", "momentum_score": "60",
        "total_score": "68", "total_score_v1": "62", "flow_score": "6",
        "total_score_v2_shadow": "68", "pension_rank_20d": "0.92", "foreign_rank_20d": "0.85",
        "flow_signal_state": "accumulation", "flow_data_stale": "False",
        "buy_watch": "False", "trim_watch": "False",
    }, {
        "rank": "2", "ticker": "293490", "name": "카카오게임즈", "sector": "tech",
        "market": "KOSDAQ", "tier": "Mid", "grade": "B",
        "quality_score": "55", "valuation_score": "50", "momentum_score": "45",
        "total_score": "52", "total_score_v1": "50", "flow_score": "2",
        "total_score_v2_shadow": "52", "pension_rank_20d": "0.70", "foreign_rank_20d": "0.60",
        "flow_signal_state": "neutral", "flow_data_stale": "False",
        "buy_watch": "False", "trim_watch": "False",
    }]
    pd.DataFrame(scored).to_csv(out / "alpha_v2_scored.csv", index=False)
    pd.DataFrame([scored[0]]).to_csv(out / "alpha_v2_top30.csv", index=False)
    pd.DataFrame([scored[1]]).to_csv(out / "alpha_v2_final_candidates.csv", index=False)
    pd.DataFrame([{
        "ticker": "005830", "name": "DB손해보험", "market": "KOSPI", "grade": "A",
        "flow_signal_state": "accumulation", "flow_score": "6", "flow_confidence": "HIGH",
        "buy_watch": "True", "trim_watch": "False", "buy_permission": "False",
        "review_only": "True", "note": "review", "reason": "flow watch",
    }]).to_csv(out / "alpha_v2_flow_triggers.csv", index=False)
    (out / "alpha_v2_summary.json").write_text(json.dumps({
        "execution_context": {
            "actual_buy_allowed": 0,
            "no_trade": False,
            "execution_scope": "ETF_ONLY",
        },
        "coverage": {
            "buy_watch_count": 1,
            "trim_watch_count": 2,
            "trim_watch_held_count": 1,
            "trim_watch_informational_count": 1,
        },
        "trim_watch_validation": {
            "trim_watch_held_or_target": 1,
            "trim_watch_informational": 1,
        },
        "target_write_occurred": False,
    }), encoding="utf-8")
    (out / "flow_dashboard_summary.json").write_text(json.dumps({
        "fresh_ratio": 0.896,
        "ticker_count": 1,
    }), encoding="utf-8")


def _setup_flow_outputs(data: Path, out: Path) -> None:
    pd.DataFrame([{
        "date": "2026-07-01", "ticker": "005830", "name": "DB손해보험", "market": "KOSPI",
        "pension_net_buy_amount": "100", "foreign_net_buy_amount": "50",
        "pension_net_buy_volume": "", "foreign_net_buy_volume": "",
        "institution_net_buy_amount": "100", "individual_net_buy_amount": "0",
        "close": "10000", "market_cap": "1000000", "trading_value": "50000",
        "data_source": "test", "data_as_of": "2026-07-01", "stale_flag": "false",
    }, {
        "date": "2026-07-02", "ticker": "005830", "name": "DB손해보험", "market": "KOSPI",
        "pension_net_buy_amount": "200", "foreign_net_buy_amount": "80",
        "pension_net_buy_volume": "", "foreign_net_buy_volume": "",
        "institution_net_buy_amount": "200", "individual_net_buy_amount": "0",
        "close": "10100", "market_cap": "1000000", "trading_value": "50000",
        "data_source": "test", "data_as_of": "2026-07-02", "stale_flag": "false",
    }]).to_csv(out / "flow_daily_timeseries.csv", index=False)
    pd.DataFrame([{
        "ticker": "005830", "name": "DB손해보험", "market": "KOSPI",
        "pension_streak_direction": "buy", "pension_consecutive_days": "2",
        "pension_streak_amount": "300", "foreign_streak_direction": "buy",
        "foreign_consecutive_days": "2", "foreign_streak_amount": "130",
        "cobuy_consecutive_days": "1", "cosell_consecutive_days": "0",
        "latest_date": "2026-07-02", "stale_flag": "false", "actual_consecutive_days": "true",
    }]).to_csv(out / "flow_streaks.csv", index=False)
    pd.DataFrame([{
        "ticker": "005830", "name": "DB손해보험", "date": "2026-07-02",
        "flow_signal": "NEUTRAL", "source": "auto_pykrx", "staleness_days": "0",
        "foreign_5d_sum": "130", "institution_5d_sum": "300",
    }]).to_csv(data / "investor_flows.csv", index=False)


def test_build_alpha_v2_shadow_rows_flags(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    _setup_v2_outputs(out)
    rows = build_alpha_v2_shadow_rows(out, run_id="run-1", run_date="2026-07-03")
    assert len(rows) == 2
    buy_row = next(r for r in rows if r["ticker"] == "005830")
    assert buy_row["buy_watch"] == "true"
    assert buy_row["buy_permission"] == "false"
    assert buy_row["actual_buy_allowed"] == 0
    assert buy_row["is_top30"] == "true"
    kosdaq = next(r for r in rows if r["ticker"] == "293490")
    assert kosdaq["is_kosdaq"] == "true"
    assert kosdaq["is_final_candidate"] == "true"


def test_append_creates_history_files(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _setup_v2_outputs(out)
    _setup_flow_outputs(data, out)
    _write_target_csv(data / "user_target_portfolio.csv", [{
        "ticker": "005830", "name": "DB", "asset_group": "kr_alpha",
        "sector": "ins", "role": "core", "target_weight": 5,
        "min_weight": 0, "max_weight": 10,
    }])
    _write_target_csv(data / "target_portfolio.csv", [{
        "ticker": "005830", "name": "DB", "asset_group": "kr_alpha",
        "sector": "ins", "role": "core", "target_weight": 5,
        "min_weight": 0, "max_weight": 10,
    }])

    summary = append_shadow_history_ledger(
        data, out, run_id="2026-07-03T10:00:00+09:00", run_date="2026-07-03",
    )
    hist = out / "history"
    assert (hist / "alpha_v2_shadow_history.csv").exists()
    assert (hist / "flow_dashboard_history.csv").exists()
    assert (hist / "shadow_daily_summary.csv").exists()
    assert summary["alpha_v2_shadow_history_updated"] is True
    assert summary["flow_dashboard_history_updated"] is True
    assert summary["target_write_occurred"] is False
    assert summary["buy_watch_count"] == 1


def test_duplicate_run_id_not_appended(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _setup_v2_outputs(out)
    _setup_flow_outputs(data, out)
    run_id = "2026-07-03T10:00:00+09:00"
    first = append_shadow_history_ledger(data, out, run_id=run_id, run_date="2026-07-03")
    second = append_shadow_history_ledger(data, out, run_id=run_id, run_date="2026-07-03")
    assert first["alpha_v2_rows_appended"] == 2
    assert second.get("skipped_duplicate_run_id") == run_id
    df = pd.read_csv(out / "history" / "alpha_v2_shadow_history.csv")
    assert len(df) == 2


def test_stale_flow_keeps_stale_flag_in_flow_history(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _setup_v2_outputs(out)
    _setup_flow_outputs(data, out)
    pd.DataFrame([{
        "ticker": "005830", "name": "DB", "date": "2026-07-02",
        "flow_signal": "STALE", "source": "missing", "staleness_days": "999",
    }]).to_csv(data / "investor_flows.csv", index=False)
    rows = build_flow_dashboard_rows(data, out, run_id="r1", run_date="2026-07-03")
    assert rows[0]["fresh_or_stale"] == "stale"
    assert rows[0]["stale_reason"] != "fresh"


def test_outcome_eval_fail_soft_without_prices(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _setup_v2_outputs(out)
    hist = out / "history"
    hist.mkdir()
    pd.DataFrame([{
        "run_id": "r1", "run_date": "2026-01-02", "ticker": "005830", "name": "DB",
        "buy_watch": "true", "trim_watch": "false", "flow_signal_state": "accumulation",
        "is_kosdaq": "false",
    }]).to_csv(hist / "alpha_v2_shadow_history.csv", index=False)
    v2, flow = evaluate_candidate_outcomes(data, out, as_of="2026-07-03")
    assert v2 == []
    assert not (hist / "alpha_v2_candidate_outcomes.csv").exists()


def test_flow_dashboard_row_fields(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _setup_v2_outputs(out)
    _setup_flow_outputs(data, out)
    rows = build_flow_dashboard_rows(data, out, run_id="r1", run_date="2026-07-03")
    assert rows
    row = rows[0]
    for field in FLOW_DASHBOARD_FIELDS:
        assert field in row
    assert row["fresh_or_stale"] == "fresh"


def test_alpha_v2_row_fields(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    _setup_v2_outputs(out)
    rows = build_alpha_v2_shadow_rows(out, run_id="r1", run_date="2026-07-03")
    for row in rows:
        for field in ALPHA_V2_SHADOW_FIELDS:
            assert field in row
