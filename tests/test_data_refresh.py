from __future__ import annotations

from pathlib import Path

import pytest

from src.backtest.alpha_backtest import run_alpha_lite_backtest, write_alpha_backtest_outputs
from src.data_refresh.fundamentals_validate import validate_fundamentals
from src.data_refresh.prices_refresh import append_prices_history, refresh_prices_snapshot, validate_prices
from src.data_refresh.refresh_main import run_refresh
from src.data_refresh.universe_sync import sync_universe_from_holdings


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_validate_prices_ok():
    issues = validate_prices(DATA_DIR / "prices.csv")
    assert issues == []


def test_validate_fundamentals_ok():
    result = validate_fundamentals(DATA_DIR)
    assert result.row_count > 0
    assert not result.errors


def test_sync_universe_idempotent():
    first = sync_universe_from_holdings(DATA_DIR)
    second = sync_universe_from_holdings(DATA_DIR)
    assert second.added == []
    assert second.total == first.total


@pytest.mark.pykrx
@pytest.mark.network
def test_refresh_prices_snapshot(tmp_path, monkeypatch):
    import shutil
    from src.data_refresh.prices_refresh import TierAPricesResult

    monkeypatch.setattr(
        "src.data_refresh.prices_refresh.ensure_tier_a_prices",
        lambda data_dir, as_of, **kw: TierAPricesResult(
            as_of=as_of, required_count=1, missing_before=0, added=["005830"],
        ),
    )
    shutil.copy(DATA_DIR / "prices.csv", tmp_path / "prices.csv")
    result = refresh_prices_snapshot(tmp_path, as_of="2026-06-20")
    assert result.row_count > 0
    assert result.as_of == "2026-06-20"


def test_append_prices_history(tmp_path):
    import shutil

    shutil.copy(DATA_DIR / "prices.csv", tmp_path / "prices.csv")
    path = append_prices_history(tmp_path)
    assert path is not None
    assert path.exists()


def test_run_refresh_report(tmp_path):
    import shutil

    for name in ("universe.csv", "prices.csv", "fundamentals.csv", "positions.csv", "target_portfolio.csv"):
        shutil.copy(DATA_DIR / name, tmp_path / name)
    report = run_refresh(tmp_path, as_of="2026-06-17", append_history=True)
    assert "steps" in report
    assert len(report["steps"]) >= 3


def test_alpha_lite_backtest():
    result = run_alpha_lite_backtest(DATA_DIR)
    assert len(result.dates) >= 2
    assert result.quintiles or result.warnings


def test_alpha_backtest_outputs(tmp_path):
    result = run_alpha_lite_backtest(DATA_DIR)
    write_alpha_backtest_outputs(result, tmp_path)
    assert (tmp_path / "alpha_backtest_summary.csv").exists()
    assert (tmp_path / "alpha_backtest_report.md").exists()
