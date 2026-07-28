"""Sector enrichment from data/krx_sector_mapping.csv."""

from __future__ import annotations

import pandas as pd
import pytest

from src.sector_enrich import enrich_sectors, gate_pass_coverage, resolve_ticker_sector


@pytest.fixture
def sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ticker": "005930", "name": "삼성전자", "sector": "", "gate_pass": True},
            {"ticker": "021240", "name": "코웨이", "sector": "unknown", "gate_pass": True},
            {"ticker": "999999", "name": "없는종목", "sector": "", "gate_pass": True},
        ]
    )


def test_resolve_from_krx_official_mapping() -> None:
    res = resolve_ticker_sector("034020", "두산에너빌리티", "")
    assert res["resolved"] is True
    assert res["sector"] == "기계·장비"
    assert res["source"] == "krx_official"


def test_manual_override_wins() -> None:
    res = resolve_ticker_sector("005930", "삼성전자", "")
    assert res["resolved"] is True
    assert res["source"] == "manual"


def test_enrich_sectors_fills_blank(sample_df: pd.DataFrame) -> None:
    df = sample_df[sample_df["ticker"] != "005930"]  # manual override row
    df = pd.concat(
        [df, pd.DataFrame([{"ticker": "034020", "name": "두산에너빌리티", "sector": "", "gate_pass": True}])],
        ignore_index=True,
    )
    out = enrich_sectors(df)
    kia = out[out["ticker"] == "034020"].iloc[0]
    assert kia["sector"] == "기계·장비"
    assert kia["sector_source"] == "krx_official"
    missing = out[out["ticker"] == "999999"].iloc[0]
    assert missing["sector"] == "unknown"


def test_enrich_preserves_manual_sector(sample_df: pd.DataFrame) -> None:
    df = sample_df.copy()
    df.loc[df["ticker"] == "005930", "sector"] = "custom_manual"
    out = enrich_sectors(df)
    assert out[out["ticker"] == "005930"].iloc[0]["sector"] == "custom_manual"


def test_gate_pass_coverage_meets_target(sample_df: pd.DataFrame) -> None:
    # Use real mapping for known tickers only
    df = sample_df[sample_df["ticker"] != "999999"]
    stats = gate_pass_coverage(df)
    assert stats["gate_pass"] == 2
    assert stats["unknown_count"] == 0
    assert stats["target_met"] is True
