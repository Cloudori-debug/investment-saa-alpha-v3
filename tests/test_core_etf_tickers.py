"""Core ETF ticker registry audit."""
from __future__ import annotations

from pathlib import Path


def test_detects_deprecated_reit_ticker(tmp_path: Path) -> None:
    import shutil

    from src.data.core_etf_tickers import audit_target_portfolio_tickers

    shutil.copy(
        Path(__file__).resolve().parents[1] / "data" / "core_etf_ticker_registry.yaml",
        tmp_path / "core_etf_ticker_registry.yaml",
    )
    rows = [{
        "ticker": "357870",
        "name": "TIGER 리츠부동산인프라",
        "asset_group": "income_alt",
    }]
    result = audit_target_portfolio_tickers(rows, data_dir=tmp_path)
    assert result["pass"] is False
    assert result["issues"][0]["expected_ticker"] == "329200"


def test_passes_correct_reit_ticker(tmp_path: Path) -> None:
    import shutil

    from src.data.core_etf_tickers import audit_target_portfolio_tickers

    shutil.copy(
        Path(__file__).resolve().parents[1] / "data" / "core_etf_ticker_registry.yaml",
        tmp_path / "core_etf_ticker_registry.yaml",
    )
    rows = [{
        "ticker": "329200",
        "name": "TIGER 리츠부동산인프라",
        "asset_group": "income_alt",
    }]
    result = audit_target_portfolio_tickers(rows, data_dir=tmp_path)
    assert result["pass"] is True


def test_detects_merged_row_and_weight_sum(tmp_path: Path) -> None:
    import shutil

    from src.data.core_etf_tickers import validate_target_portfolio_structure

    shutil.copy(
        Path(__file__).resolve().parents[1] / "data" / "core_etf_ticker_registry.yaml",
        tmp_path / "core_etf_ticker_registry.yaml",
    )
    rows = [{
        "ticker": "329200",
        "name": "TIGER 리츠부동산인프라",
        "asset_group": "income_alt",
        "sector": "x",
        "role": "y",
        "target_weight": "3.6",
        "min_weight": "2.55",
        "max_weight": "4.73",
        None: ["352560", "TIGER 미국MSCI리츠(합성 H)", "income_alt", "real_asset_income", "us_reit", "3.6", "2.55", "4.73"],
    }]
    result = validate_target_portfolio_structure(rows, data_dir=tmp_path)
    assert result["pass"] is False
    assert any(i["issue"] == "merged_row" for i in result["issues"])
    assert any(i["issue"] == "weight_sum_mismatch" for i in result["issues"])
    assert any(i["issue"] == "missing_core_etf" for i in result["issues"])
