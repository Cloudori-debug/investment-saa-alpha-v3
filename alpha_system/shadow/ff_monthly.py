"""Ken French 월간 팩터 로더 · 장기 GEM 검증용 (Review-only)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

FF_US_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_Factors_CSV.zip"
)
FF_DEV_EXUS_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "Developed_ex_US_5_Factors_CSV.zip"
)
CACHE_US = Path("data") / "local" / "ff_us_factors_monthly.csv"
CACHE_DEV = Path("data") / "local" / "ff_dev_exus_monthly.csv"


def _parse_ff_monthly_csv(text: str) -> pd.DataFrame:
    """월 블록만 (연간 섹션 전). 값은 %."""
    rows: list[dict[str, float]] = []
    header: list[str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if rows:
                break  # annual section
            continue
        if line.startswith(",") or line.lower().startswith("mkt"):
            # ",Mkt-RF,SMB,..." or "Mkt-RF,..."
            parts = [p.strip() for p in line.split(",") if p.strip()]
            if parts and parts[0].upper().startswith("MKT"):
                header = parts
            elif len(parts) >= 2 and "Mkt" in parts[0] or any(
                "Mkt" in p for p in parts
            ):
                header = [p for p in line.split(",")]
                header = [h.strip() for h in header if h.strip()]
            continue
        if header is None and "Mkt-RF" in line:
            header = [p.strip() for p in line.split(",") if p.strip()]
            continue
        if not line[:6].isdigit():
            continue
        if header is None:
            continue
        # stop at annual YYYY only (4 digits)
        key = line.split(",")[0].strip()
        if len(key) == 4 and key.isdigit():
            break
        if len(key) < 6:
            continue
        parts = [p.strip() for p in line.split(",")]
        yyyymm = parts[0]
        try:
            dt = pd.Timestamp(year=int(yyyymm[:4]), month=int(yyyymm[4:6]), day=1)
            dt = dt + pd.offsets.MonthEnd(0)
        except (TypeError, ValueError):
            continue
        vals = {}
        # header may not include date col
        cols = header
        if cols and cols[0].upper().startswith("MKT"):
            data_cols = cols
            data_vals = parts[1:]
        else:
            data_cols = cols[1:] if cols and not cols[0][:1].isdigit() else cols
            data_vals = parts[1:]
        for c, v in zip(data_cols, data_vals):
            try:
                vals[c] = float(v)
            except (TypeError, ValueError):
                vals[c] = float("nan")
        vals["date"] = dt
        rows.append(vals)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("date").sort_index()
    return df


def _download_zip_csv(url: str) -> str:
    resp = requests.get(url, timeout=90)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        name = zf.namelist()[0]
        return zf.read(name).decode("latin-1")


def load_ff_us_monthly(
    root: Path, *, ensure_fetch: bool = True
) -> pd.DataFrame:
    path = Path(root) / CACHE_US
    if path.is_file() and not ensure_fetch:
        df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
        return df
    if ensure_fetch or not path.is_file():
        try:
            text = _download_zip_csv(FF_US_URL)
            df = _parse_ff_monthly_csv(text)
        except (OSError, ValueError, requests.RequestException):
            df = pd.DataFrame()
        if not df.empty:
            path.parent.mkdir(parents=True, exist_ok=True)
            out = df.reset_index()
            out.to_csv(path, index=False, encoding="utf-8")
            return df
    if path.is_file():
        return pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    return pd.DataFrame()


def load_ff_dev_exus_monthly(
    root: Path, *, ensure_fetch: bool = True
) -> pd.DataFrame:
    path = Path(root) / CACHE_DEV
    if path.is_file() and not ensure_fetch:
        return pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    if ensure_fetch or not path.is_file():
        try:
            text = _download_zip_csv(FF_DEV_EXUS_URL)
            df = _parse_ff_monthly_csv(text)
        except (OSError, ValueError, requests.RequestException):
            df = pd.DataFrame()
        if not df.empty:
            path.parent.mkdir(parents=True, exist_ok=True)
            df.reset_index().to_csv(path, index=False, encoding="utf-8")
            return df
    if path.is_file():
        return pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    return pd.DataFrame()


def equity_total_return_index(ff: pd.DataFrame) -> pd.Series:
    """Mkt-RF + RF (%) → 총수익 지수."""
    if ff.empty or "Mkt-RF" not in ff.columns or "RF" not in ff.columns:
        return pd.Series(dtype=float)
    mkt = (ff["Mkt-RF"] + ff["RF"]) / 100.0
    return (1.0 + mkt.fillna(0.0)).cumprod()


def bill_total_return_index(ff: pd.DataFrame) -> pd.Series:
    if ff.empty or "RF" not in ff.columns:
        return pd.Series(dtype=float)
    rf = ff["RF"] / 100.0
    return (1.0 + rf.fillna(0.0)).cumprod()


__all__ = [
    "equity_total_return_index",
    "bill_total_return_index",
    "load_ff_dev_exus_monthly",
    "load_ff_us_monthly",
]
