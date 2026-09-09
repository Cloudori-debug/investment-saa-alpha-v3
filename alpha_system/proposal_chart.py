"""Review-only daily chart readout for proposal names.

Does not change QVM ranks, write target_portfolio.csv, or place orders.
OHLCV is PyKRX per ticker (same source as the snapshot). FASTJUSIK 금지.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from alpha_system.screen_book import is_kosdaq

CACHE_DIR_REL = Path("data") / "local"
LOOKBACK_DAYS = 400
SMA_WINDOWS = (20, 60, 120)
RSI_LEN = 14
BB_LEN = 20
BB_K = 2.0
VOL_LEN = 20
MIN_BARS = 30

GetOhlcv = Callable[[str, str, str], Any]


def norm_ticker(raw: object) -> str:
    """6-digit code. KOSDAQ names often arrive as 247540.0 from CSV."""
    text = str(raw or "").strip()
    if text.endswith(".0") and text[:-2].replace(".", "", 1).isdigit():
        text = text[:-2]
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return ""
    if len(digits) > 6:
        digits = digits[-6:]
    return digits.zfill(6)



@dataclass
class ChartRead:
    ticker: str
    name: str
    as_of: str = ""
    close: float | None = None
    sma20: float | None = None
    sma60: float | None = None
    sma120: float | None = None
    rsi: float | None = None
    vol_ratio: float | None = None
    bb_pct: float | None = None
    ma_label: str = ""
    rsi_label: str = ""
    vol_label: str = ""
    bb_label: str = ""
    advice: str = ""
    note: str = ""

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ChartBoard:
    market: str
    fetched_at: str = ""
    as_of: str = ""
    items: list[ChartRead] = field(default_factory=list)
    detail: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "fetched_at": self.fetched_at,
            "as_of": self.as_of,
            "items": [item.to_payload() for item in self.items],
            "detail": self.detail,
        }


def cache_path(root: Path, market: str) -> Path:
    tag = "KOSDAQ" if is_kosdaq(market) else "KOSPI"
    return Path(root) / CACHE_DIR_REL / f"proposal_chart_{tag}.json"


def _f(series: pd.Series | None) -> float | None:
    if series is None or series.empty:
        return None
    val = series.iloc[-1]
    if val is None or (isinstance(val, float) and val != val):
        return None
    return float(val)


def _col(df: pd.DataFrame, *names: str) -> pd.Series | None:
    lower = {str(c).lower(): c for c in df.columns}
    for name in names:
        if name in df.columns:
            return pd.to_numeric(df[name], errors="coerce")
        hit = lower.get(name.lower())
        if hit is not None:
            return pd.to_numeric(df[hit], errors="coerce")
    return None


def _sma_label(*, above20: bool | None, above60: bool | None, above120: bool | None) -> str:
    if above60 is True and above120 is True:
        return "120일선 위"
    if above60 is True:
        return "60일선 위"
    if above20 is True and above60 is False:
        return "20일선만 위"
    if above60 is False:
        return "60일선 아래"
    if above20 is True:
        return "20일선 위"
    return "이평 부족"


def _rsi_label(rsi: float | None) -> str:
    if rsi is None:
        return "없음"
    if rsi >= 70:
        return "과열"
    if rsi <= 30:
        return "식음"
    return "보통"


def _vol_label(ratio: float | None) -> str:
    if ratio is None:
        return "없음"
    if ratio >= 1.5:
        return "많음"
    if ratio <= 0.7:
        return "적음"
    return "보통"


def _bb_label(pct: float | None) -> str:
    if pct is None:
        return "없음"
    if pct >= 1.0:
        return "상단 밖"
    if pct <= 0.0:
        return "하단 밖"
    return "밴드 안"


def _advice(
    *,
    ma_label: str,
    rsi_label: str,
    bb_label: str,
    rung: str = "",
) -> str:
    if rsi_label == "과열" or bb_label == "상단 밖":
        return "단기 과열. 지금 더 사지 않음."
    if ma_label == "60일선 아래" and rsi_label == "식음":
        return "이평 아래·식음. 싸 보여도 자동 매수 아님."
    if rung in {"줄이기", "절반", "전량"}:
        return "목표가 쪽. 추가는 보류."
    if ma_label in {"120일선 위", "60일선 위"} and rsi_label == "보통":
        if rung == "매수1":
            return "이평은 위쪽. 제일 싼 칸 — 첫 매수만 검토."
        if rung == "매수2":
            return "이평은 위쪽. 둘째 칸 — 남은 분만 천천히."
        return "이평은 위쪽. RSI 보통."
    if ma_label == "60일선 아래":
        return "이평 아래. 나눠 사는 속도는 천천히."
    return "참고만. 순위와 목표 파일은 그대로입니다."


def summary_tone(item: ChartRead) -> str:
    if item.rsi_label == "과열" or item.bb_label == "상단 밖":
        return "hot"
    if item.ma_label == "60일선 아래" or item.rsi_label == "식음":
        return "weak"
    return "ok"


def summary_line(item: ChartRead, *, ladder: str = "") -> str:
    rung = (ladder or "").replace("지금 ", "").replace("사다리 ", "").strip()
    if (item.note or "").strip():
        body = item.note.strip()
    elif item.ma_label or item.rsi_label or item.bb_label:
        body = _advice(
            ma_label=item.ma_label,
            rsi_label=item.rsi_label,
            bb_label=item.bb_label,
            rung=rung,
        )
    else:
        body = (item.advice or "").strip()
    if ladder and body:
        return f"{ladder} · {body}"
    return ladder or body


def wilder_rsi(close: pd.Series, length: int = RSI_LEN) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.mask(avg_loss.fillna(0.0) == 0.0, 100.0)
    return rsi


def analyze_ohlcv(df: pd.DataFrame, *, ticker: str, name: str) -> ChartRead:
    if df is None or df.empty:
        return ChartRead(ticker=ticker, name=name, note="일봉 없음")
    work = df.copy()
    if not isinstance(work.index, pd.DatetimeIndex):
        if "date" in work.columns:
            work.index = pd.to_datetime(work["date"], errors="coerce")
        else:
            work.index = pd.to_datetime(work.index, errors="coerce")
    work = work.sort_index()
    close = _col(work, "종가", "close", "Close")
    volume = _col(work, "거래량", "volume", "Volume")
    if close is None:
        return ChartRead(ticker=ticker, name=name, note="종가 없음")
    close = close.dropna()
    if len(close) < MIN_BARS:
        return ChartRead(
            ticker=ticker,
            name=name,
            as_of=str(close.index[-1].date()) if len(close) else "",
            close=_f(close),
            note=f"봉 {len(close)}개 · {MIN_BARS}개 이상 필요",
        )
    sma = {n: close.rolling(n, min_periods=n).mean() for n in SMA_WINDOWS}
    last = float(close.iloc[-1])
    s20, s60, s120 = _f(sma[20]), _f(sma[60]), _f(sma[120])
    above20 = None if s20 is None else last >= s20
    above60 = None if s60 is None else last >= s60
    above120 = None if s120 is None else last >= s120
    rsi = _f(wilder_rsi(close))
    vol_ratio = None
    if volume is not None:
        vol = volume.reindex(close.index)
        avg = vol.rolling(VOL_LEN, min_periods=VOL_LEN).mean()
        last_vol, avg_vol = _f(vol), _f(avg)
        if last_vol is not None and avg_vol and avg_vol > 0:
            vol_ratio = round(last_vol / avg_vol, 2)
    mid = close.rolling(BB_LEN, min_periods=BB_LEN).mean()
    std = close.rolling(BB_LEN, min_periods=BB_LEN).std()
    upper = mid + BB_K * std
    lower = mid - BB_K * std
    bb_pct = None
    u, lo, m = _f(upper), _f(lower), _f(mid)
    if u is not None and lo is not None and u != lo:
        bb_pct = round((last - lo) / (u - lo), 3)
    elif m is not None:
        bb_pct = 0.5
    ma_label = _sma_label(above20=above20, above60=above60, above120=above120)
    rsi_label = _rsi_label(rsi)
    vol_label = _vol_label(vol_ratio)
    bb_label = _bb_label(bb_pct)
    as_of = str(close.index[-1].date())
    return ChartRead(
        ticker=ticker,
        name=name,
        as_of=as_of,
        close=round(last, 0),
        sma20=None if s20 is None else round(s20, 0),
        sma60=None if s60 is None else round(s60, 0),
        sma120=None if s120 is None else round(s120, 0),
        rsi=None if rsi is None else round(float(rsi), 1),
        vol_ratio=vol_ratio,
        bb_pct=bb_pct,
        ma_label=ma_label,
        rsi_label=rsi_label,
        vol_label=vol_label,
        bb_label=bb_label,
        advice=_advice(ma_label=ma_label, rsi_label=rsi_label, bb_label=bb_label),
    )


def _default_ohlcv(ticker: str, start: str, end: str) -> pd.DataFrame:
    from pykrx import stock  # type: ignore[import-untyped]

    return stock.get_market_ohlcv(start, end, ticker)


def refresh_proposal_charts(
    root: Path,
    names: Sequence[Mapping[str, str]],
    *,
    market: str = "KOSPI",
    get_ohlcv: GetOhlcv | None = None,
    today: date | None = None,
) -> ChartBoard:
    """Fetch daily bars for proposal tickers only. Never writes target."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    day = today or date.today()
    start = (day - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
    end = day.strftime("%Y%m%d")
    fetch = get_ohlcv or _default_ohlcv
    items: list[ChartRead] = []
    last_as_of = ""
    for row in names:
        ticker = norm_ticker(row.get("ticker"))
        name = str(row.get("name") or ticker)
        if not ticker:
            continue
        try:
            raw = fetch(ticker, start, end)
            read = analyze_ohlcv(raw if isinstance(raw, pd.DataFrame) else pd.DataFrame(), ticker=ticker, name=name)
        except Exception as exc:
            read = ChartRead(ticker=ticker, name=name, note=str(exc)[:160])
        items.append(read)
        if read.as_of:
            last_as_of = read.as_of
        if get_ohlcv is None:
            time.sleep(0.2)
    board = ChartBoard(
        market="KOSDAQ" if is_kosdaq(market) else "KOSPI",
        fetched_at=now,
        as_of=last_as_of,
        items=items,
        detail="제안 종목 일봉 읽기 · 순위·target 미변경",
    )
    path = cache_path(root, board.market)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(board.to_payload(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return board


def load_cached_charts(root: Path, market: str) -> ChartBoard | None:
    path = cache_path(root, market)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    allowed = {item.name for item in fields(ChartRead)}
    items = [
        ChartRead(**{k: v for k, v in item.items() if k in allowed})
        for item in raw.get("items") or []
        if isinstance(item, dict)
    ]
    return ChartBoard(
        market=str(raw.get("market") or market),
        fetched_at=str(raw.get("fetched_at") or ""),
        as_of=str(raw.get("as_of") or ""),
        items=items,
        detail=str(raw.get("detail") or ""),
    )
