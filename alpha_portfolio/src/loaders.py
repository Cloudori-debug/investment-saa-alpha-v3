from __future__ import annotations

from pathlib import Path

import pandas as pd


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, dtype={"ticker": str})
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    return df


def load_positions(path: Path, *, kr_alpha_only: bool = True) -> pd.DataFrame:
    df = _read_csv(path)
    if df.empty:
        return df
    if kr_alpha_only and "asset_group" in df.columns:
        df = df[df["asset_group"] == "kr_alpha"].copy()
    return df


def load_all_positions(path: Path) -> pd.DataFrame:
    return load_positions(path, kr_alpha_only=False)


def load_fundamentals(path: Path) -> pd.DataFrame:
    return _read_csv(path)


def load_price_snapshot(path: Path) -> pd.DataFrame:
    return _read_csv(path)


def load_shareholder(path: Path) -> pd.DataFrame:
    return _read_csv(path)


def load_target_portfolio(path: Path) -> pd.DataFrame:
    df = _read_csv(path)
    if df.empty:
        return df
    if "asset_group" in df.columns:
        df = df[df["asset_group"] == "kr_alpha"].copy()
    return df


def load_universe(path: Path) -> pd.DataFrame:
    return _read_csv(path)


def load_park_state(path: Path) -> pd.DataFrame:
    return _read_csv(path)


def load_stock_flags(path: Path) -> pd.DataFrame:
    return _read_csv(path)
