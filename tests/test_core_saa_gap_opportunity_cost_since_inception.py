from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.alpha.benchmark_data import ticker_cum_return, ticker_cum_return_detail
from src.alpha.performance_dashboard import (
    compute_core_saa_gap_opportunity_cost_since_inception,
)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    import csv

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_ticker_cum_return_ok() -> None:
    prices = pd.DataFrame([
        {"date": pd.Timestamp("2026-06-17"), "ticker": "069500", "close": 100.0},
        {"date": pd.Timestamp("2026-07-08"), "ticker": "069500", "close": 110.0},
    ])
    assert ticker_cum_return(prices, "069500", "2026-06-17", "2026-07-08") == 10.0
    detail = ticker_cum_return_detail(prices, "069500", "2026-06-17", "2026-07-08")
    assert detail["quality"].startswith("ok_")


def test_ticker_cum_return_missing_inception() -> None:
    prices = pd.DataFrame([
        {"date": pd.Timestamp("2026-07-01"), "ticker": "069500", "close": 100.0},
        {"date": pd.Timestamp("2026-07-08"), "ticker": "069500", "close": 110.0},
    ])
    detail = ticker_cum_return_detail(prices, "069500", "2026-06-17", "2026-07-08")
    # first on/after inception works if data starts after inception
    assert detail["return_pct"] == 10.0


def test_ticker_cum_return_truly_missing_inception() -> None:
    prices = pd.DataFrame([
        {"date": pd.Timestamp("2026-07-08"), "ticker": "069500", "close": 110.0},
    ])
    detail = ticker_cum_return_detail(prices, "069500", "2026-06-17", "2026-07-08")
    # single point → insufficient_history (start==end after on_or_after pick)
    assert detail["return_pct"] is None
    assert detail["quality"] in {"insufficient_history", "missing_inception_price"}


def test_ticker_cum_return_stale() -> None:
    prices = pd.DataFrame([
        {"date": pd.Timestamp("2026-06-17"), "ticker": "069500", "close": 100.0},
        {"date": pd.Timestamp("2026-06-20"), "ticker": "069500", "close": 105.0},
    ])
    detail = ticker_cum_return_detail(
        prices, "069500", "2026-06-17", "2026-07-08", max_stale_days=5,
    )
    assert detail["return_pct"] is None
    assert detail["quality"] == "stale_price"


def test_ticker_cum_return_cash_zero() -> None:
    prices = pd.DataFrame()
    assert ticker_cum_return(prices, "CASH", "2026-06-17", "2026-07-08") == 0.0


def test_since_inception_gap_times_cum_return(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _write_csv(
        data / "target_portfolio.csv",
        ["ticker", "name", "asset_group", "sector", "role", "target_weight", "min_weight", "max_weight"],
        [{
            "ticker": "360750",
            "name": "US",
            "asset_group": "global_beta",
            "sector": "core",
            "role": "us",
            "target_weight": "100",
            "min_weight": "0",
            "max_weight": "100",
        }],
    )
    _write_csv(
        data / "positions.csv",
        ["ticker", "name", "asset_group", "quantity", "avg_price", "current_price", "current_value"],
        [{
            "ticker": "CASH",
            "name": "cash",
            "asset_group": "cash_short_bond",
            "quantity": "1",
            "avg_price": "100000000",
            "current_price": "100000000",
            "current_value": "100000000",
        }],
    )

    prices = pd.DataFrame([
        {"date": pd.Timestamp("2026-06-17"), "ticker": "360750", "close": 100.0},
        {"date": pd.Timestamp("2026-07-08"), "ticker": "360750", "close": 120.0},
    ])
    monkeypatch.setattr(
        "src.alpha.performance_dashboard.load_combined_prices",
        lambda _d: prices,
    )

    doc = compute_core_saa_gap_opportunity_cost_since_inception(data, out, "2026-07-08")
    assert doc["total_gap_pct"] == 100.0
    # gap 100%p * cum return 20% → contrib 20.0 portfolio %p
    assert doc["opportunity_cost_since_inception_pct"] == 20.0
    assert doc["inception_date"] == "2026-06-17"
    assert "approximation" in doc["disclaimer"].lower() or "근사" in doc["limitation"]


def test_since_inception_missing_price_makes_total_null(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    _write_csv(
        data / "target_portfolio.csv",
        ["ticker", "name", "asset_group", "sector", "role", "target_weight", "min_weight", "max_weight"],
        [{
            "ticker": "360750",
            "name": "US",
            "asset_group": "global_beta",
            "sector": "core",
            "role": "us",
            "target_weight": "50",
            "min_weight": "0",
            "max_weight": "100",
        }],
    )
    _write_csv(
        data / "positions.csv",
        ["ticker", "name", "asset_group", "quantity", "avg_price", "current_price", "current_value"],
        [{
            "ticker": "CASH",
            "name": "cash",
            "asset_group": "cash_short_bond",
            "quantity": "1",
            "avg_price": "100",
            "current_price": "100",
            "current_value": "100000000",
        }],
    )
    monkeypatch.setattr(
        "src.alpha.performance_dashboard.load_combined_prices",
        lambda _d: pd.DataFrame(),
    )
    doc = compute_core_saa_gap_opportunity_cost_since_inception(data, out, "2026-07-08")
    assert doc["opportunity_cost_since_inception_pct"] is None
    assert doc["by_ticker"][0]["ticker_cum_return_since_inception"] is None
    assert doc["quality"] in {"partial_price_coverage", "missing_inception_price"}


def test_report_line_includes_since_inception_na() -> None:
    from src.report.export_daily_brief import _fmt_optional_pct, build_daily_report_v2_sections

    assert _fmt_optional_pct(None) == "n/a"
    brief = {
        "system_status": {},
        "saa_taa": {},
        "shadow_diagnostic": {},
        "duration_sleeve": {},
        "alpha_v0_2": {},
        "core_saa_reference": {},
        "alpha_performance": {
            "mode": "shadow_diagnostic_only",
            "metrics": {
                "core_saa_return_mtd": -0.5,
                "actual_portfolio_return_mtd": 1.26,
                "actual_return_source": "holdings_price_return",
                "excess_return_vs_core_mtd": 1.76,
                "raw_nav_return_mtd": 35.0,
                "adjusted_nav_return_mtd": 3.8,
                "estimated_external_flow_mtd_krw": 1,
                "kr_alpha_return_mtd": 1.26,
                "kospi200_return_mtd": None,
                "kospi200_return_quality": "stale_price",
                "kr_alpha_excess_vs_kospi200_mtd": None,
                "core_saa_gap_opportunity_cost_mtd": None,
                "core_saa_total_gap_pct": 37.4,
                "core_saa_gap_opportunity_cost_since_inception": None,
                "core_saa_gap_inception_date": "2026-06-17",
                "weak_alpha_regime": True,
                "theoretical_buy_count": 0,
                "executable_buy_count": 0,
            },
            "gate_opportunity_cost_count": 0,
        },
    }
    joined = "\n".join(build_daily_report_v2_sections(brief))
    assert "since 2026-06-17" in joined
    assert "상한선 추정치" in joined
    assert "Core SAA 갭 기회비용 (since 2026-06-17, shadow, 근사)**: 0%p" not in joined
