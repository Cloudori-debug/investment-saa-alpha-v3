"""Phase 4i / 4i-1 — forward return tracker tests."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from src.value_list.hakedaka_forward_return_tracker import (
    build_forward_return_tracker_rows,
    collect_tracking_universe,
    resolve_effective_signal_date,
    run_hakedaka_forward_return_tracking,
)


def _write_prices(data_dir: Path, rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    df.to_csv(data_dir / "prices.csv", index=False)


def _write_top15(output_dir: Path) -> None:
    rows = [
        {"as_of": "2026-01-02", "ticker": "005930", "name": "삼성전자"},
        {"as_of": "2026-01-02", "ticker": "000660", "name": "SK하이닉스"},
    ]
    with (output_dir / "hakedaka_top_candidate_verification.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["as_of", "ticker", "name"], extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _write_watchlist(output_dir: Path) -> None:
    rows = [{
        "ticker": "002700", "name": "신일전자", "event_type": "treasury_acquire",
        "confidence": "high", "shareholder_return_yield": "7.43",
        "hakedaka_score": "69.6", "hakedaka_rank": "16",
    }]
    with (output_dir / "hakedaka_catalyst_watchlist.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _write_scores(output_dir: Path) -> None:
    df = pd.DataFrame([
        {"ticker": "005930", "name": "삼성전자", "hakedaka_total_score": 80.0},
        {"ticker": "000660", "name": "SK하이닉스", "hakedaka_total_score": 75.0},
        {"ticker": "002700", "name": "신일전자", "hakedaka_total_score": 69.6},
    ])
    df.to_csv(output_dir / "hakedaka_catalyst_scores.csv", index=False)


@pytest.fixture
def fixture_dirs(tmp_path: Path) -> tuple[Path, Path]:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    data_dir.mkdir()
    output_dir.mkdir()
    dates = pd.bdate_range("2026-01-02", periods=130)
    price_rows: list[dict] = []
    for i, d in enumerate(dates):
        px = 100.0 + i * 0.5
        for t in ("005930", "000660", "002700", "069500"):
            price_rows.append({"date": d.strftime("%Y-%m-%d"), "ticker": t, "close": px})
    _write_prices(data_dir, price_rows)
    _write_top15(output_dir)
    _write_watchlist(output_dir)
    _write_scores(output_dir)
    return data_dir, output_dir


def test_collect_tracking_universe_tags(fixture_dirs: tuple[Path, Path]) -> None:
    _, output_dir = fixture_dirs
    uni = collect_tracking_universe(output_dir)
    assert "005930" in uni
    assert "top15" in uni["005930"]["sources"]
    assert "002700" in uni
    assert "catalyst_watchlist" in uni["002700"]["sources"]


def test_forward_return_available_when_data_exists(fixture_dirs: tuple[Path, Path]) -> None:
    data_dir, output_dir = fixture_dirs
    rows = build_forward_return_tracker_rows(data_dir, output_dir, as_of="2026-01-02")
    sam = next(r for r in rows if r["ticker"] == "005930")
    assert sam["effective_signal_date"] == "2026-01-02"
    assert sam["signal_date_adjustment_reason"] == "none"
    assert sam["price_at_signal"] == 100.0
    assert sam["forward_return_5d"] is not None
    assert sam["forward_target_date_5d"] is not None
    assert sam["available_price_date_5d"] is not None
    assert sam["result_status"] == "available"


def test_signal_date_alignment_weekend_and_price_lag(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    data_dir.mkdir()
    output_dir.mkdir()
    _write_prices(data_dir, [
        {"date": "2026-06-24", "ticker": "005930", "close": 100.0},
        {"date": "2026-06-25", "ticker": "005930", "close": 101.0},
        {"date": "2026-06-26", "ticker": "005930", "close": 102.0},
        {"date": "2026-06-24", "ticker": "069500", "close": 50.0},
        {"date": "2026-06-25", "ticker": "069500", "close": 50.5},
        {"date": "2026-06-26", "ticker": "069500", "close": 51.0},
    ])
    _write_top15(output_dir)
    _write_scores(output_dir)

    prices = pd.read_csv(data_dir / "prices.csv", dtype={"ticker": str})
    prices["date"] = pd.to_datetime(prices["date"])
    prices["ticker"] = prices["ticker"].str.zfill(6)
    effective, reason, last = resolve_effective_signal_date(prices, "2026-06-28")
    assert effective == "2026-06-26"
    assert last == "2026-06-26"
    assert reason == "non_trading_day_or_price_lag"

    rows = build_forward_return_tracker_rows(data_dir, output_dir, as_of="2026-06-28")
    sam = next(r for r in rows if r["ticker"] == "005930")
    assert sam["signal_calendar_date"] == "2026-06-28"
    assert sam["effective_signal_date"] == "2026-06-26"
    assert sam["price_at_signal"] == 102.0
    assert sam["benchmark_price_at_signal"] == 51.0
    assert sam["result_status"] == "pending"


def test_forward_return_pending_when_horizon_beyond_data(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    data_dir.mkdir()
    output_dir.mkdir()
    _write_prices(data_dir, [
        {"date": "2026-06-26", "ticker": "005930", "close": 100.0},
        {"date": "2026-06-26", "ticker": "069500", "close": 50.0},
    ])
    _write_top15(output_dir)
    _write_scores(output_dir)
    rows = build_forward_return_tracker_rows(data_dir, output_dir, as_of="2026-06-26")
    sam = next(r for r in rows if r["ticker"] == "005930")
    assert sam["forward_return_120d"] is None
    assert sam["forward_target_date_120d"] is not None
    assert sam["available_price_date_120d"] is None
    assert sam["result_status"] == "pending"


def test_signal_price_missing_graceful(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "outputs"
    data_dir.mkdir()
    output_dir.mkdir()
    _write_prices(data_dir, [{"date": "2026-01-02", "ticker": "069500", "close": 50.0}])
    _write_top15(output_dir)
    _write_scores(output_dir)
    rows = build_forward_return_tracker_rows(data_dir, output_dir, as_of="2026-01-02")
    sam = next(r for r in rows if r["ticker"] == "005930")
    assert sam["price_at_signal"] is None
    assert sam["result_status"] == "signal_price_missing"


def test_run_writes_all_outputs(fixture_dirs: tuple[Path, Path]) -> None:
    data_dir, output_dir = fixture_dirs
    report = run_hakedaka_forward_return_tracking(data_dir, output_dir, as_of="2026-01-02")
    assert report["phase"] == "4i"
    assert (output_dir / "hakedaka_forward_return_tracker.csv").exists()
    assert (output_dir / "hakedaka_forward_return_tracker.json").exists()
    assert (output_dir / "hakedaka_catalyst_watchlist_performance.csv").exists()
    assert (output_dir / "hakedaka_phase4i_report.json").exists()
    assert (output_dir / "hakedaka_phase4i1_report.json").exists()
    qa = json.loads((output_dir / "hakedaka_phase4i1_report.json").read_text(encoding="utf-8"))
    assert qa["phase"] == "4i-1"
    assert qa["summary"]["effective_signal_date"] == "2026-01-02"
