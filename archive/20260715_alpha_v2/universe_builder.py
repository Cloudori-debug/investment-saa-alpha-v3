from __future__ import annotations

from pathlib import Path

from src.alpha.loaders import load_universe
from src.alpha.schemas import UniverseRecord


def build_alpha_v2_universe(data_dir: Path) -> list[UniverseRecord]:
    """KOSPI + KOSDAQ common stocks from universe.csv (excludes ETF/REIT/SPAC/preferred)."""
    path = data_dir / "universe.csv"
    if not path.exists():
        return []
    rows = load_universe(path)
    out: list[UniverseRecord] = []
    for rec in rows:
        market = (rec.market or "KOSPI").upper()
        if market not in {"KOSPI", "KOSDAQ"}:
            continue
        if rec.is_etf_etn or rec.is_reit or rec.is_spac or rec.is_preferred:
            continue
        if rec.security_type not in {"", "common_stock"}:
            continue
        if rec.is_trading_halt or rec.is_administrative_issue:
            continue
        out.append(rec)
    return out
