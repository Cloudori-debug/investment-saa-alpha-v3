"""KOSPI market PBR history — monthly T3 feed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd


@dataclass(frozen=True)
class T3PbrStatus:
    available: bool
    current_pbr: Optional[float]
    percentile_10y: Optional[float]
    in_bottom_band: Optional[bool]
    bottom_pct: float
    as_of: Optional[date]
    source_note: str


def _percentile_rank(series: pd.Series, value: float) -> float:
    s = series.dropna().astype(float)
    if s.empty:
        return float("nan")
    return 100.0 * (s < value).sum() / len(s)


def load_t3_pbr_status(
    root: Path,
    *,
    bottom_percentile: float = 20.0,
    lookback_years: int = 10,
    today: date | None = None,
) -> T3PbrStatus:
    """
  Priority:
  1. data/kospi_market_pbr_history.csv (month_end, market_pbr)
  2. PyKRX index fundamental probe (best-effort, may fail)
    """
    today = today or date.today()
    hist_path = root / "data" / "kospi_market_pbr_history.csv"
    if hist_path.exists():
        df = pd.read_csv(hist_path)
        if "market_pbr" in df.columns:
            col_date = "month_end" if "month_end" in df.columns else df.columns[0]
            df[col_date] = pd.to_datetime(df[col_date], errors="coerce")
            cutoff = pd.Timestamp(today) - pd.DateOffset(years=lookback_years)
            window = df[df[col_date] >= cutoff].copy()
            if not window.empty:
                latest = window.sort_values(col_date).iloc[-1]
                cur = float(latest["market_pbr"])
                pct = _percentile_rank(window["market_pbr"], cur)
                in_band = pct <= bottom_percentile if pd.notna(pct) else None
                as_of = _parse_date(latest[col_date])
                return T3PbrStatus(
                    available=True,
                    current_pbr=cur,
                    percentile_10y=round(pct, 1) if pd.notna(pct) else None,
                    in_bottom_band=in_band,
                    bottom_pct=bottom_percentile,
                    as_of=as_of,
                    source_note="kospi_market_pbr_history.csv",
                )

    probe = _probe_pykrx_market_pbr(today)
    if probe is not None:
        return probe

    return T3PbrStatus(
        available=False,
        current_pbr=None,
        percentile_10y=None,
        in_bottom_band=None,
        bottom_pct=bottom_percentile,
        as_of=None,
        source_note=(
            "10년 월간 PBR 이력 없음. PyKRX/KRX 공개 지수 펀더멘털로 "
            "data/kospi_market_pbr_history.csv 생성 후 월 1회 판정 연결."
        ),
    )


def _parse_date(val) -> Optional[date]:
    try:
        return pd.Timestamp(val).date()
    except Exception:
        return None


# Avoid live PyKRX probe noise on every dashboard load when history CSV missing.
# Operator can still generate data/kospi_market_pbr_history.csv for T3.
def _probe_pykrx_market_pbr(today: date) -> Optional[T3PbrStatus]:
    return None


def write_monthly_snapshot(root: Path, market_pbr: float, month_end: date) -> Path:
    """Append one monthly row to history CSV (operator / batch)."""
    path = root / "data" / "kospi_market_pbr_history.csv"
    row = pd.DataFrame([{"month_end": month_end.isoformat(), "market_pbr": market_pbr}])
    if path.exists():
        existing = pd.read_csv(path)
        combined = pd.concat([existing, row], ignore_index=True)
        combined = combined.drop_duplicates(subset=["month_end"], keep="last")
    else:
        combined = row
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(path, index=False)
    return path
