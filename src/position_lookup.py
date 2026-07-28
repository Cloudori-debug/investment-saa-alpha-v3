from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data_loader import _normalize_ticker, load_latest_close_map, load_target_portfolio
from src.models import VALID_ASSET_GROUPS


def lookup_ticker_metadata(data_dir: Path, ticker: str) -> dict[str, object]:
    """종목코드 → 이름·섹터·자산군·현재가 (universe / target / prices 순)."""
    code = _normalize_ticker(str(ticker).strip())
    if not code:
        raise ValueError("종목코드를 입력하세요.")

    result: dict[str, object] = {
        "ticker": code,
        "name": code,
        "sector": "",
        "style": "",
        "asset_group": "kr_alpha",
        "current_price": None,
        "sources": [],
    }

    universe_path = data_dir / "universe.csv"
    if universe_path.exists():
        uni = pd.read_csv(universe_path, dtype=str, keep_default_na=False)
        uni["ticker"] = uni["ticker"].map(_normalize_ticker)
        hit = uni[uni["ticker"] == code]
        if not hit.empty:
            row = hit.iloc[0]
            result["name"] = str(row.get("name", code)).strip() or code
            result["sector"] = str(row.get("sector", "")).strip()
            result["sources"].append("universe.csv")

    target_path = data_dir / "target_portfolio.csv"
    if target_path.exists():
        for t in load_target_portfolio(target_path):
            if t.ticker == code:
                result["name"] = t.name or str(result["name"])
                result["asset_group"] = t.asset_group
                result["sector"] = t.sector or str(result["sector"])
                style = getattr(t, "style", None)
                if style:
                    result["style"] = style
                result["sources"].append("target_portfolio.csv")
                break

    close_map, as_of = load_latest_close_map(data_dir / "prices.csv")
    if code in close_map:
        result["current_price"] = close_map[code]
        result["price_as_of"] = as_of
        result["sources"].append("prices.csv")

    positions_path = data_dir / "positions.csv"
    if positions_path.exists():
        pos = pd.read_csv(positions_path, dtype=str, keep_default_na=False)
        pos["ticker"] = pos["ticker"].map(_normalize_ticker)
        hit = pos[pos["ticker"] == code]
        if not hit.empty:
            row = hit.iloc[0]
            result["name"] = str(row.get("name", result["name"])).strip()
            if str(row.get("asset_group", "")).strip():
                result["asset_group"] = str(row["asset_group"]).strip()
            if str(row.get("sector", "")).strip():
                result["sector"] = str(row["sector"]).strip()
            result["sources"].append("positions.csv")

    if str(result["asset_group"]) not in VALID_ASSET_GROUPS:
        result["asset_group"] = "kr_alpha"

    return result
