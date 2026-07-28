from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.data_refresh.dart_client import dart_get_bytes


def _normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip()
    return t.zfill(6) if t.isdigit() else t


def corp_code_cache_path(data_dir: Path) -> Path:
    return data_dir / "cache" / "dart_corp_codes.csv"


def download_corp_code_table(data_dir: Path, *, max_age_days: int = 7) -> pd.DataFrame:
    cache = corp_code_cache_path(data_dir)
    if cache.exists():
        age = datetime.now() - datetime.fromtimestamp(cache.stat().st_mtime)
        if age < timedelta(days=max_age_days):
            return pd.read_csv(cache, dtype=str, keep_default_na=False)

    raw = dart_get_bytes("corpCode.xml", {})
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        xml_name = next(n for n in zf.namelist() if n.lower().endswith(".xml"))
        xml_bytes = zf.read(xml_name)

    root = ET.fromstring(xml_bytes)
    rows: list[dict[str, str]] = []
    for item in root.findall("list"):
        stock = (item.findtext("stock_code") or "").strip()
        if not stock or stock == " ":
            continue
        rows.append(
            {
                "corp_code": (item.findtext("corp_code") or "").strip(),
                "corp_name": (item.findtext("corp_name") or "").strip(),
                "stock_code": _normalize_ticker(stock),
                "modify_date": (item.findtext("modify_date") or "").strip(),
            }
        )
    df = pd.DataFrame(rows)
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False, encoding="utf-8-sig")
    return df


def ticker_to_corp_code(data_dir: Path, ticker: str) -> str | None:
    ticker = _normalize_ticker(ticker)
    table = download_corp_code_table(data_dir)
    matched = table[table["stock_code"] == ticker]
    if matched.empty:
        return None
    return str(matched.iloc[0]["corp_code"])


def build_ticker_corp_map(data_dir: Path, tickers: list[str]) -> dict[str, str]:
    table = download_corp_code_table(data_dir)
    lookup = {row["stock_code"]: row["corp_code"] for _, row in table.iterrows()}
    out: dict[str, str] = {}
    for t in tickers:
        nt = _normalize_ticker(t)
        if nt in lookup:
            out[nt] = lookup[nt]
    return out
