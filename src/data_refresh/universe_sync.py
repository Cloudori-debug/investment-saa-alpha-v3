from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.data_loader import load_positions, load_target_portfolio

UNIVERSE_COLUMNS = [
    "ticker", "name", "market", "security_type", "sector", "industry", "listed_date",
    "is_preferred", "is_etf_etn", "is_reit", "is_spac", "is_trading_halt",
    "is_administrative_issue", "audit_opinion", "capital_impairment",
]


@dataclass
class SyncResult:
    added: list[str]
    total: int
    path: Path


def _normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip()
    return t.zfill(6) if t.isdigit() else t


def _default_universe_row(ticker: str, name: str, sector: str = "") -> dict[str, str]:
    return {
        "ticker": ticker,
        "name": name,
        "market": "KOSPI",
        "security_type": "common_stock",
        "sector": sector,
        "industry": sector,
        "listed_date": "2010-01-01",
        "is_preferred": "false",
        "is_etf_etn": "false",
        "is_reit": "false",
        "is_spac": "false",
        "is_trading_halt": "false",
        "is_administrative_issue": "false",
        "audit_opinion": "clean",
        "capital_impairment": "false",
    }


def sync_universe_from_holdings(data_dir: Path) -> SyncResult:
    """positions + target_portfolio의 kr_alpha/common 종목을 universe.csv에 병합."""
    universe_path = data_dir / "universe.csv"
    if universe_path.exists():
        universe_df = pd.read_csv(universe_path, dtype=str, keep_default_na=False)
    else:
        universe_df = pd.DataFrame(columns=UNIVERSE_COLUMNS)

    universe_df["ticker"] = universe_df["ticker"].map(_normalize_ticker)
    existing = set(universe_df["ticker"].tolist())

    positions = load_positions(data_dir / "positions.csv")
    targets = load_target_portfolio(data_dir / "target_portfolio.csv")

    added: list[str] = []
    new_rows: list[dict[str, str]] = []

    for src in list(positions) + list(targets):
        ticker = _normalize_ticker(src.ticker)
        if ticker in {"", "CASH"} or ticker in existing:
            continue
        if src.asset_group != "kr_alpha":
            continue
        sector = getattr(src, "sector", "") or ""
        new_rows.append(_default_universe_row(ticker, src.name, sector))
        existing.add(ticker)
        added.append(ticker)

    if new_rows:
        universe_df = pd.concat([universe_df, pd.DataFrame(new_rows)], ignore_index=True)

    universe_df = universe_df[UNIVERSE_COLUMNS] if not universe_df.empty else pd.DataFrame(columns=UNIVERSE_COLUMNS)
    universe_path.parent.mkdir(parents=True, exist_ok=True)
    universe_df.to_csv(universe_path, index=False, encoding="utf-8-sig")

    return SyncResult(added=added, total=len(universe_df), path=universe_path)
