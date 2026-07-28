from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.collect.dates import normalize_ticker
from src.loaders import load_fundamentals, load_universe
from src.sector_enrich import resolve_ticker_sector

FUNDAMENTALS_COLUMNS = [
    "ticker",
    "name",
    "as_of",
    "fiscal_year",
    "sector",
    "roe",
    "roe_3y_avg",
    "opm",
    "debt_ratio",
    "is_financial",
    "is_holding",
    "per",
    "pbr",
    "ev_ebitda",
    "fcf_yield",
    "sector_per_median",
    "sector_pbr_median",
    "net_income_y1",
    "net_income_y2",
    "audit_opinion",
    "verified",
    "source",
    "is_etf",
    "is_spac",
    "is_managed",
    "is_halted",
]


def _empty_fundamentals() -> pd.DataFrame:
    return pd.DataFrame(columns=FUNDAMENTALS_COLUMNS)


def export_fundamentals_template(
    snapshot: pd.DataFrame,
    universe: pd.DataFrame,
    *,
    existing: pd.DataFrame | None = None,
    as_of: str,
    max_rows: int = 200,
) -> pd.DataFrame:
    """Gate 통과 liquid 종목 중 fundamentals에 없는 ticker용 입력 템플릿."""
    if snapshot.empty:
        return _empty_fundamentals()

    existing = existing if existing is not None else _empty_fundamentals()
    known = set(existing["ticker"].astype(str).map(normalize_ticker)) if not existing.empty else set()

    uni = universe.copy() if not universe.empty else pd.DataFrame()
    if not uni.empty and "ticker" in uni.columns:
        uni["ticker"] = uni["ticker"].astype(str).map(normalize_ticker)
        uni = uni.set_index("ticker")

    snap = snapshot.copy()
    snap["ticker"] = snap["ticker"].astype(str).map(normalize_ticker)
    snap = snap[~snap["ticker"].isin(known)]
    if "market_cap" in snap.columns:
        snap = snap.sort_values("market_cap", ascending=False)
    snap = snap.head(max_rows)

    rows: list[dict] = []
    fiscal_year = as_of[:4]
    for _, row in snap.iterrows():
        ticker = str(row["ticker"])
        meta = uni.loc[ticker] if not uni.empty and ticker in uni.index else None
        name = str(meta["name"]) if meta is not None and "name" in meta else ticker
        uni_sector = str(meta.get("sector", "") or "") if meta is not None else ""
        resolved = resolve_ticker_sector(ticker, name, uni_sector)
        sector = str(resolved.get("sector") or "unknown")
        rows.append(
            {
                "ticker": ticker,
                "name": name,
                "as_of": as_of,
                "fiscal_year": fiscal_year,
                "sector": sector,
                "roe": "",
                "roe_3y_avg": "",
                "opm": "",
                "debt_ratio": "",
                "is_financial": "false",
                "is_holding": "false",
                "per": row.get("per", ""),
                "pbr": row.get("pbr", ""),
                "ev_ebitda": "",
                "fcf_yield": "",
                "sector_per_median": "",
                "sector_pbr_median": "",
                "net_income_y1": "",
                "net_income_y2": "",
                "audit_opinion": "unqualified",
                "verified": "false",
                "source": "liquid_template",
                "is_etf": "false",
                "is_spac": "false",
                "is_managed": "false",
                "is_halted": "false",
            }
        )
    return pd.DataFrame(rows, columns=FUNDAMENTALS_COLUMNS)


def sync_liquid_fundamentals_stubs(
    fundamentals_path: Path,
    snapshot: pd.DataFrame,
    universe: pd.DataFrame,
    *,
    as_of: str,
    gate_cfg: dict,
    max_stubs: int = 150,
    per_pbr_map: dict[str, dict[str, float]] | None = None,
) -> tuple[int, Path | None]:
    """price gate 통과 종목에 PER/PBR stub 행 추가 (Replace 후보 풀 확대)."""
    if snapshot.empty:
        return 0, None

    cap_min = float(gate_cfg.get("market_cap_min", 0))
    tv_min = float(gate_cfg.get("avg_trading_value_20d_min", 0))

    snap = snapshot.copy()
    snap["ticker"] = snap["ticker"].astype(str).map(normalize_ticker)
    snap = snap[
        (snap["market_cap"].astype(float) >= cap_min)
        & (snap["avg_trading_value_20d"].astype(float) >= tv_min)
    ]
    if snap.empty:
        return 0, None

    existing = load_fundamentals(fundamentals_path)
    known = set(existing["ticker"].astype(str).map(normalize_ticker)) if not existing.empty else set()
    missing = snap[~snap["ticker"].isin(known)].sort_values("market_cap", ascending=False).head(max_stubs)
    if missing.empty:
        return 0, None

    uni = universe.copy() if not universe.empty else pd.DataFrame()
    if not uni.empty and "ticker" in uni.columns:
        uni["ticker"] = uni["ticker"].astype(str).map(normalize_ticker)
        uni = uni.set_index("ticker")

    fiscal_year = as_of[:4]
    new_rows: list[dict] = []
    for _, row in missing.iterrows():
        ticker = str(row["ticker"])
        meta = uni.loc[ticker] if not uni.empty and ticker in uni.index else None
        name = str(meta["name"]) if meta is not None and "name" in meta else ticker
        uni_sector = str(meta.get("sector", "") or "") if meta is not None else ""
        resolved = resolve_ticker_sector(ticker, name, uni_sector)
        sector = str(resolved.get("sector") or "unknown")
        per = pbr = ""
        if per_pbr_map and ticker in per_pbr_map:
            per = per_pbr_map[ticker].get("per", "")
            pbr = per_pbr_map[ticker].get("pbr", "")
        new_rows.append(
            {
                "ticker": ticker,
                "name": name,
                "as_of": as_of,
                "fiscal_year": fiscal_year,
                "sector": sector,
                "roe": 10.0,
                "roe_3y_avg": 10.0,
                "opm": "",
                "debt_ratio": 80.0,
                "is_financial": "false",
                "is_holding": "false",
                "per": per,
                "pbr": pbr,
                "ev_ebitda": "",
                "fcf_yield": "",
                "sector_per_median": "",
                "sector_pbr_median": "",
                "net_income_y1": "",
                "net_income_y2": "",
                "audit_opinion": "unqualified",
                "verified": "stub",
                "source": "liquid_stub",
                "is_etf": "false",
                "is_spac": "false",
                "is_managed": "false",
                "is_halted": "false",
            }
        )

    out = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True) if not existing.empty else pd.DataFrame(new_rows)
    out.to_csv(fundamentals_path, index=False, encoding="utf-8-sig")

    template_path = fundamentals_path.parent / "fundamentals_liquid_template.csv"
    template = export_fundamentals_template(snapshot, universe, existing=existing, as_of=as_of)
    if not template.empty:
        template.to_csv(template_path, index=False, encoding="utf-8-sig")
    return len(new_rows), template_path if template_path.exists() else None
