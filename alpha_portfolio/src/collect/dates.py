from __future__ import annotations

from datetime import datetime, timedelta


def to_compact(iso_date: str) -> str:
    return iso_date.replace("-", "")[:8]


def to_iso(compact: str) -> str:
    c = compact.replace("-", "")[:8]
    return f"{c[:4]}-{c[4:6]}-{c[6:8]}"


def lookback_start(iso_date: str, calendar_days: int) -> str:
    dt = datetime.strptime(iso_date[:10], "%Y-%m-%d") - timedelta(days=calendar_days)
    return dt.strftime("%Y-%m-%d")


def normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip()
    return t.zfill(6) if t.isdigit() else t
