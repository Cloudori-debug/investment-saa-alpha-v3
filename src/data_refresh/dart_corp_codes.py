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


def _read_cache(cache: Path) -> pd.DataFrame:
    return pd.read_csv(cache, dtype=str, keep_default_na=False)


def _is_zip_bytes(raw: bytes) -> bool:
    return len(raw) >= 4 and raw[:2] == b"PK"


def download_corp_code_table(data_dir: Path, *, max_age_days: int = 30) -> pd.DataFrame:
    """Load corp_code↔ticker table. Prefer fresh download; fall back to stale cache.

    OpenDART corpCode.xml is a zip. When the response is HTML/JSON (bad key,
    throttle, proxy), ZipFile raises — we must not wipe a working local cache.
    """
    cache = corp_code_cache_path(data_dir)
    if cache.exists():
        age = datetime.now() - datetime.fromtimestamp(cache.stat().st_mtime)
        if age < timedelta(days=max_age_days):
            return _read_cache(cache)

    try:
        raw = dart_get_bytes("corpCode.xml", {})
        if not _is_zip_bytes(raw):
            raise zipfile.BadZipFile(
                f"corpCode response is not a zip ({len(raw)} bytes)"
            )
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
        if df.empty:
            raise ValueError("corpCode.xml parsed empty")
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache, index=False, encoding="utf-8-sig")
        return df
    except Exception:
        if cache.exists():
            # Stale-but-usable beats empty corp_map (which zeros owner %).
            return _read_cache(cache)
        raise


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
