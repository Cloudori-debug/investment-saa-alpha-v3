"""Five-rung price ladder: lookback floor → E target (or quant draft).

Display only. Does not write yaml or target_portfolio.csv.
Axis is 하한(L) → 상한(T). Fill is current on that axis.
52-week high is never the ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

LOOKBACK_TRADING_DAYS = 120
MIN_DATES_FOR_120D = 20
N_RUNGS = 5
RUNG_LABELS = ("매수1", "매수2", "줄이기", "절반", "전량")


def _norm_ticker(val: Any) -> str:
    s = str(val or "").strip()
    return s.zfill(6) if s.isdigit() else s


def _to_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        x = float(val)
    except (TypeError, ValueError):
        return None
    if x != x or x <= 0:
        return None
    return x


@dataclass(frozen=True)
class LookbackLow:
    price: float
    source: str  # 120d | low_52w | prices_min


@dataclass(frozen=True)
class PriceLadder:
    ok: bool
    low: float | None
    high: float | None
    current: float | None
    rungs: tuple[float, ...]
    labels: tuple[str, ...]
    fill_pct: float
    over_high: bool
    under_low: bool
    low_source: str
    high_source: str  # approved | quant_draft
    note: str

    def as_extra(self) -> dict[str, Any]:
        if not self.ok:
            return {"ladder_ok": False}
        return {
            "ladder_ok": True,
            "ladder_low": self.low,
            "ladder_high": self.high,
            "ladder_rungs": list(self.rungs),
            "ladder_labels": list(self.labels),
            "ladder_fill_pct": self.fill_pct,
            "ladder_over_high": self.over_high,
            "ladder_under_low": self.under_low,
            "ladder_low_source": self.low_source,
            "ladder_high_source": self.high_source,
            "ladder_note": self.note,
        }


def build_price_ladder(
    *,
    current: float | None,
    high: float | None,
    low: float | None,
    high_source: str = "approved",
    low_source: str = "",
) -> PriceLadder:
    """Equal 5 rungs on [low, high]. Fill = (current − low) / (high − low)."""
    cur = _to_float(current)
    hi = _to_float(high)
    lo = _to_float(low)
    empty = PriceLadder(
        ok=False,
        low=lo,
        high=hi,
        current=cur,
        rungs=(),
        labels=RUNG_LABELS,
        fill_pct=0.0,
        over_high=False,
        under_low=False,
        low_source=low_source or "",
        high_source=high_source or "",
        note="",
    )
    if cur is None or hi is None or lo is None:
        return empty
    if hi <= lo:
        return empty

    span = hi - lo
    rungs = tuple(round(lo + i / (N_RUNGS - 1) * span, 0) for i in range(N_RUNGS))
    raw = (cur - lo) / span * 100.0
    fill = min(100.0, max(0.0, raw))
    over = cur > hi
    under = cur < lo
    src = (high_source or "").strip() or "approved"
    note = "전량: 상한 도달 후 4주"
    if src == "quant_draft":
        note = "상한은 정량초안(E 승인 전) · " + note
    return PriceLadder(
        ok=True,
        low=round(lo, 0),
        high=round(hi, 0),
        current=round(cur, 0),
        rungs=rungs,
        labels=RUNG_LABELS,
        fill_pct=round(fill, 1),
        over_high=over,
        under_low=under,
        low_source=low_source or "",
        high_source=src,
        note=note,
    )


def attach_ladder_extra(
    extra: Mapping[str, Any] | None,
    *,
    ticker: str,
    current: float | None,
    target_price: float | None,
    lookback_lows: Mapping[str, LookbackLow] | None,
) -> dict[str, Any]:
    """Merge ladder fields onto portfolio extra. Quant mid is ceiling if no E target."""
    out = dict(extra or {})
    t = _norm_ticker(ticker)
    info = (lookback_lows or {}).get(t)
    low = info.price if info else None
    low_src = info.source if info else ""
    high = _to_float(target_price)
    high_src = "approved"
    if high is None:
        high = _to_float(out.get("quant_price_mid"))
        high_src = "quant_draft"
    ladder = build_price_ladder(
        current=current,
        high=high,
        low=low,
        high_source=high_src,
        low_source=low_src,
    )
    out.update(ladder.as_extra())
    return out


def _min_close_by_ticker(
    prices_df: pd.DataFrame | None,
) -> dict[str, tuple[float, int]]:
    if prices_df is None or prices_df.empty or "ticker" not in prices_df.columns:
        return {}
    close_col = None
    for cand in ("close", "price", "current_price"):
        if cand in prices_df.columns:
            close_col = cand
            break
    if close_col is None:
        return {}
    work = prices_df.copy()
    work["ticker"] = work["ticker"].map(_norm_ticker)
    work["_close"] = pd.to_numeric(work[close_col], errors="coerce")
    work = work.dropna(subset=["_close"])
    work = work[work["_close"] > 0]
    if work.empty:
        return {}
    if "date" in work.columns:
        work["_date"] = pd.to_datetime(work["date"], errors="coerce")
        work = work.dropna(subset=["_date"])
        work = work.sort_values("_date")
        grouped = work.groupby("ticker", sort=False)
    else:
        grouped = work.groupby("ticker", sort=False)
    out: dict[str, tuple[float, int]] = {}
    for t, g in grouped:
        if "_date" in g.columns:
            g = g.drop_duplicates("_date", keep="last")
        g = g.tail(LOOKBACK_TRADING_DAYS)
        if g.empty:
            continue
        out[str(t)] = (float(g["_close"].min()), int(len(g)))
    return out


def _low_52w_from_snapshot(root: Path) -> dict[str, float]:
    path = root / "alpha_portfolio" / "data" / "raw" / "price_snapshot.csv"
    if not path.exists():
        return {}
    try:
        df = pd.read_csv(path)
    except Exception:
        return {}
    if df.empty or "ticker" not in df.columns or "low_52w" not in df.columns:
        return {}
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        t = _norm_ticker(row.get("ticker"))
        low = _to_float(row.get("low_52w"))
        if t and low is not None:
            out[t] = low
    return out


def load_lookback_lows(
    root: Path,
    prices_df: pd.DataFrame | None = None,
) -> dict[str, LookbackLow]:
    """120-session min close when history is thick enough; else 52-week low.

    Never uses high_52w.
    """
    hist = _min_close_by_ticker(prices_df)
    if not hist:
        prices_path = Path(root) / "data" / "prices.csv"
        if prices_path.exists():
            try:
                hist = _min_close_by_ticker(pd.read_csv(prices_path))
            except Exception:
                hist = {}
    snap = _low_52w_from_snapshot(Path(root))
    tickers = set(hist) | set(snap)
    out: dict[str, LookbackLow] = {}
    for t in tickers:
        h = hist.get(t)
        s = snap.get(t)
        if h is not None and h[1] >= MIN_DATES_FOR_120D:
            out[t] = LookbackLow(price=h[0], source="120d")
        elif s is not None:
            out[t] = LookbackLow(price=s, source="low_52w")
        elif h is not None:
            out[t] = LookbackLow(price=h[0], source="prices_min")
    return out
