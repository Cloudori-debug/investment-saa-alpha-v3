"""Sector weight rollup exposure for proposal book."""

from __future__ import annotations

from pathlib import Path

from alpha_system.ui.services.context import PortfolioRow
from alpha_system.ui.services.sector_exposure import assess_sector_weight_caps


def _row(ticker: str, weight: float, sector: str) -> PortfolioRow:
    return PortfolioRow(
        ticker=ticker,
        name=ticker,
        weight_pct=weight,
        initial_weight_pct=weight,
        avg_price=None,
        current_price=100.0,
        target_price=None,
        target_progress=None,
        remaining_upside_pct=None,
        has_target=True,
        target_detail="",
        cap_pct=35.0,
        cap_headroom_pct=10.0,
        cap_near=False,
        sector=sector,
    )


def test_financial_theme_weight_cap_flags_over(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    rows = [
        _row("316140", 12.0, "financial"),
        _row("105560", 13.0, "financial"),
        _row("005830", 12.2, "insurance"),  # rolls into financial → 37.2%
        _row("000660", 20.0, "semiconductor"),
    ]
    exp = assess_sector_weight_caps(rows, data_dir=data, sector_max=35.0)
    fin = next(e for e in exp if e.bucket == "financial")
    assert fin.weight_pct == 37.2
    assert fin.limit_pct == 35.0
    assert fin.over is True
    assert fin.name_count == 3
    assert set(fin.tickers) == {"316140", "105560", "005830"}


def test_two_names_under_35_not_over(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    rows = [
        _row("316140", 17.0, "financial"),
        _row("105560", 17.0, "financial"),
        _row("000660", 20.0, "semiconductor"),
    ]
    exp = assess_sector_weight_caps(rows, data_dir=data, sector_max=35.0)
    fin = next(e for e in exp if e.bucket == "financial")
    assert fin.weight_pct == 34.0
    assert fin.over is False
    assert fin.name_count == 2
