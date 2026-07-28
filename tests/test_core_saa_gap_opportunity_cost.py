from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.alpha.performance_dashboard import compute_core_saa_gap_opportunity_cost
from src.models import PositionRow, TargetRow


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    import csv

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_gap_opportunity_cost_100gap_times_10pct(tmp_path: Path, monkeypatch) -> None:
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
        {"date": pd.Timestamp("2026-07-01"), "ticker": "360750", "close": 100.0},
        {"date": pd.Timestamp("2026-07-08"), "ticker": "360750", "close": 110.0},
    ])
    monkeypatch.setattr(
        "src.alpha.performance_dashboard.load_combined_prices",
        lambda _d: prices,
    )
    monkeypatch.setattr(
        "src.alpha.performance_dashboard.ticker_return_mtd",
        lambda _p, ticker, _as_of: 10.0 if str(ticker).zfill(6) == "360750" else None,
    )

    doc = compute_core_saa_gap_opportunity_cost(data, out, "2026-07-08")
    assert doc["total_gap_pct"] == 100.0
    # gap 100%p * return 10% → contrib 10.0 portfolio %p
    assert doc["opportunity_cost_mtd_pct"] == 10.0
    assert doc["by_bucket"][0]["asset_group"] == "global_beta"
    assert "Actual Buy Allowed" in doc["disclaimer"]


def test_missing_price_makes_total_null(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.setattr(
        "src.alpha.performance_dashboard.ticker_return_mtd",
        lambda *_a, **_k: None,
    )
    doc = compute_core_saa_gap_opportunity_cost(data, out, "2026-07-08")
    assert doc["opportunity_cost_mtd_pct"] is None
    assert doc["by_ticker"][0]["ticker_return_mtd"] is None
    assert doc["by_ticker"][0]["contrib_pct"] is None
    assert doc["quality"] == "partial_price_coverage"


def test_report_line_uses_na_not_zero_for_null() -> None:
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
                "weak_alpha_regime": True,
                "theoretical_buy_count": 0,
                "executable_buy_count": 0,
            },
            "gate_opportunity_cost_count": 0,
        },
    }
    joined = "\n".join(build_daily_report_v2_sections(brief))
    assert "Core SAA 갭 기회비용" in joined
    assert "n/a%p" in joined or "n/a" in joined
    assert "Core SAA 갭 기회비용(MTD, shadow)**: 0%p" not in joined
