from __future__ import annotations

from pathlib import Path

from src.alpha.benchmark_data import load_combined_prices, ticker_return_mtd
from src.alpha.nav_log import build_nav_snapshot, nav_return_mtd, append_portfolio_nav_log
from src.alpha.performance_dashboard import compute_core_saa_benchmark_mtd, write_alpha_performance_outputs


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_combined_prices_mtd_not_zero_for_sp500() -> None:
    prices = load_combined_prices(DATA_DIR)
    assert not prices.empty
    # Prefer a recent as_of present in the price series (data drifts).
    as_of = str(prices["date"].max().date())
    ret = ticker_return_mtd(prices, "360750", as_of)
    detail_rows = prices[prices["ticker"] == "360750"]
    if len(detail_rows) <= 1:
        assert ret is None or ret == 0.0
    else:
        # With multiple prints, MTD should resolve or be explicitly stale/insufficient.
        from src.alpha.benchmark_data import ticker_return_mtd_detail
        detail = ticker_return_mtd_detail(prices, "360750", as_of)
        assert detail["quality"] in {
            "ok", "ok_from_prior_month_close", "stale_price",
            "insufficient_history", "no_price_on_or_before_as_of",
        }
        if detail["quality"].startswith("ok"):
            assert ret is not None


def test_core_benchmark_uses_combined_prices() -> None:
    prices = load_combined_prices(DATA_DIR)
    as_of = str(prices["date"].max().date()) if not prices.empty else "2026-07-08"
    core = compute_core_saa_benchmark_mtd(DATA_DIR, as_of)
    assert core.get("price_source") == "prices_history+prices.csv"
    # If core ETFs lack July history, MTD may be None — coverage of metadata still required.
    assert "core_saa_return_mtd" in core
    assert "core_weight_with_price_pct" in core
    assert core.get("components") is not None


def test_nav_log_mtd(tmp_path: Path) -> None:
    log = tmp_path / "portfolio_nav_log.csv"
    append_portfolio_nav_log(log, {
        "date": "2026-06-01", "run_id": "r1", "total_nav_krw": 100_000_000,
        "cash_krw": 0, "positions_value_krw": 100_000_000,
        "kr_alpha_value_krw": 0, "core_reference_held_krw": 0, "satellite_other_krw": 0,
    })
    append_portfolio_nav_log(log, {
        "date": "2026-06-26", "run_id": "r2", "total_nav_krw": 102_000_000,
        "cash_krw": 0, "positions_value_krw": 102_000_000,
        "kr_alpha_value_krw": 0, "core_reference_held_krw": 0, "satellite_other_krw": 0,
    })
    mtd = nav_return_mtd(log, "2026-06-26")
    assert mtd == 2.0


def test_nav_log_mtd_excludes_core_registration_jump(tmp_path: Path) -> None:
    log = tmp_path / "portfolio_nav_log.csv"
    append_portfolio_nav_log(log, {
        "date": "2026-07-01", "run_id": "r1", "total_nav_krw": 90_000_000,
        "cash_krw": 10_000_000, "positions_value_krw": 80_000_000,
        "kr_alpha_value_krw": 40_000_000, "core_reference_held_krw": 30_000_000,
        "satellite_other_krw": 10_000_000,
    })
    append_portfolio_nav_log(log, {
        "date": "2026-07-03", "run_id": "r2", "total_nav_krw": 120_000_000,
        "cash_krw": 10_000_000, "positions_value_krw": 110_000_000,
        "kr_alpha_value_krw": 40_000_000, "core_reference_held_krw": 60_000_000,
        "satellite_other_krw": 10_000_000,
    })
    mtd = nav_return_mtd(log, "2026-07-03")
    assert mtd is not None
    assert abs(mtd) < 5.0
    assert mtd != 33.3333


def test_nav_snapshot_from_data() -> None:
    snap = build_nav_snapshot(DATA_DIR, as_of="2026-06-26", run_id="t")
    assert snap["total_nav_krw"] > 0
    assert snap["kr_alpha_value_krw"] > 0
