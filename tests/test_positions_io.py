from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.data_loader import (
    apply_prices_from_csv,
    compute_position_value,
    dataframe_to_positions,
    enrich_positions_dataframe,
    load_positions,
    positions_to_dataframe,
    write_positions,
)


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_compute_position_value():
    assert compute_position_value("005830", 100, 125000) == 12_500_000
    assert compute_position_value("CASH", 1, 18_000_000) == 18_000_000


def test_enrich_positions_dataframe():
    df = pd.DataFrame(
        [
            {"ticker": "005830", "quantity": 10, "current_price": 1000, "current_value": 0, "weight_pct": 0},
            {"ticker": "CASH", "quantity": 1, "current_price": 5000, "current_value": 0, "weight_pct": 0},
        ]
    )
    out = enrich_positions_dataframe(df)
    assert out.iloc[0]["current_value"] == 10000
    assert out.iloc[1]["current_value"] == 5000
    assert abs(out["weight_pct"].sum() - 100) < 0.01


def test_apply_prices_from_csv(tmp_path):
    prices = tmp_path / "prices.csv"
    prices.write_text(
        "date,ticker,close\n2026-06-17,005830,125000\n",
        encoding="utf-8",
    )
    df = pd.DataFrame(
        [
            {
                "ticker": "005830",
                "name": "DB손해보험",
                "asset_group": "kr_alpha",
                "quantity": 10,
                "current_price": "",
                "current_value": 0,
                "weight_pct": 0,
            }
        ]
    )
    out, stats = apply_prices_from_csv(df, prices)
    assert stats["applied"] == 1
    assert float(out.iloc[0]["current_price"]) == 125000
    assert float(out.iloc[0]["current_value"]) == 1_250_000


def test_positions_dataframe_roundtrip(tmp_path):
    src = DATA_DIR / "positions.csv"
    positions = load_positions(src)
    df = positions_to_dataframe(positions)
    assert "weight_pct" in df.columns
    assert abs(df["weight_pct"].sum() - 100) < 0.1

    out = tmp_path / "positions.csv"
    write_positions(dataframe_to_positions(df), out, backup=False)
    reloaded = load_positions(out)
    assert len(reloaded) == len(positions)


def test_write_positions_backup(tmp_path):
    src = DATA_DIR / "positions.csv"
    positions = load_positions(src)
    out = tmp_path / "positions.csv"
    write_positions(positions, out, backup=False)
    write_positions(positions, out, backup=True)
    backups = list((tmp_path / "backups").glob("positions.*.bak.csv"))
    assert len(backups) == 1
