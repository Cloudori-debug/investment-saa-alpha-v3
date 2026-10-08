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
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
MACD_DIV_LOOKBACK = 40
MIN_BARS = 35

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
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    ma_label: str = ""
    rsi_label: str = ""
    vol_label: str = ""
    bb_label: str = ""
    macd_label: str = ""
    macd_hist_label: str = ""
    macd_div_label: str = ""
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


def _trade_verdict(
    *,
    ma_label: str,
    rsi_label: str,
    bb_label: str,
    macd_label: str = "",
    macd_hist_label: str = "",
    macd_div_label: str = "",
    rung: str = "",
) -> tuple[str, str]:
    """Return (결론, 한줄 이유) for Review-only display — not an order."""
    if rsi_label == "과열" or bb_label == "상단 밖":
        return (
            "추가 매수 금지",
            "이미 과열(단기 과매수). 지금 사면 고점 추격에 가깝습니다.",
        )
    if macd_div_label == "고점 다이버전스":
        return (
            "추가 매수 금지 · 비중 축소 검토",
            "주가는 버티거나 올라도 상승 힘이 약해진 구간입니다.",
        )
    if macd_label == "데드크로스":
        return (
            "신규·추가 매수 보류 · 보유는 축소 검토",
            "단기 추세가 장기 추세 아래로 꺾였습니다.",
        )
    if macd_hist_label == "히스토그램 축소" and macd_label == "시그널 위":
        return (
            "추가 매수 보류",
            "아직 상승 쪽이나 힘이 줄고 있습니다. 추격하지 마세요.",
        )
    if macd_label == "시그널 아래" or "음수" in (macd_hist_label or ""):
        if macd_div_label == "저점 다이버전스":
            return (
                "소량 분할 매수만 검토",
                "하락 힘이 약해질 조짐입니다. 전량·추격 매수는 아닙니다.",
            )
        return (
            "매수 보류 · 보유는 축소·관망",
            "하락(또는 약세) 추세입니다. 싸 보여도 바로 담지 마세요.",
        )
    if macd_div_label == "저점 다이버전스":
        return (
            "소량 분할 매수만 검토",
            "바닥 근처 반등 후보일 수 있습니다. 한 번에 사지 마세요.",
        )
    if ma_label == "60일선 아래" and rsi_label == "식음":
        return (
            "매수 보류",
            "이평 아래·과매도입니다. 반등 확인 전엔 관망이 낫습니다.",
        )
    if rung in {"줄이기", "절반", "전량"}:
        return (
            "추가 매수 금지 · 익절·축소 쪽 검토",
            "가격이 목표가 구간에 들어와 있습니다.",
        )
    if macd_label == "골든크로스" or (
        macd_label == "시그널 위" and macd_hist_label == "히스토그램 확대"
    ):
        if rung == "매수1":
            return (
                "첫 매수(가장 싼 칸)만 검토",
                "상승 힘이 붙은 편입니다. 전량이 아니라 사다리 1칸만.",
            )
        if rung == "매수2":
            return (
                "남은 매수 분은 천천히만",
                "상승 흐름이나 추격 비중은 키우지 마세요.",
            )
        if ma_label in {"120일선 위", "60일선 위"}:
            return (
                "보유 유지 · 추격 매수 금지",
                "추세는 우호적입니다. 더 사지 말고 비중만 점검하세요.",
            )
        return (
            "분할 매수 검토 · 추격 금지",
            "단기 상승 힘이 있습니다. 한 번에 담지 마세요.",
        )
    if ma_label in {"120일선 위", "60일선 위"} and rsi_label == "보통":
        if rung == "매수1":
            return (
                "첫 매수만 검토",
                "이평은 위쪽입니다. 제일 싼 칸만 보세요.",
            )
        if rung == "매수2":
            return (
                "둘째 칸만 천천히",
                "이평은 위쪽입니다. 남은 분만 나눠 보세요.",
            )
        return (
            "보유 유지 · 추격 금지",
            "큰 이상은 없습니다. 새로 크게 사지 마세요.",
        )
    if ma_label == "60일선 아래":
        return (
            "매수 속도 낮춤 · 관망 우선",
            "이평 아래입니다. 반등·사다리 확인 후에만 검토하세요.",
        )
    return (
        "관망 · 기존 규칙만 따르기",
        "차트만으로 매매하지 마세요. 순위·게이트·목표가와 같이 보세요.",
    )


def _advice(
    *,
    ma_label: str,
    rsi_label: str,
    bb_label: str,
    macd_label: str = "",
    macd_hist_label: str = "",
    macd_div_label: str = "",
    rung: str = "",
) -> str:
    verdict, why = _trade_verdict(
        ma_label=ma_label,
        rsi_label=rsi_label,
        bb_label=bb_label,
        macd_label=macd_label,
        macd_hist_label=macd_hist_label,
        macd_div_label=macd_div_label,
        rung=rung,
    )
    return f"결론: {verdict} — {why}"


def summary_tone(item: ChartRead) -> str:
    if (
        item.rsi_label == "과열"
        or item.bb_label == "상단 밖"
        or item.macd_label == "데드크로스"
        or item.macd_div_label == "고점 다이버전스"
    ):
        return "hot"
    if (
        item.ma_label == "60일선 아래"
        or item.rsi_label == "식음"
        or item.macd_label == "시그널 아래"
        or "음수" in (item.macd_hist_label or "")
    ):
        return "weak"
    return "ok"


def summary_line(item: ChartRead, *, ladder: str = "") -> str:
    rung = (ladder or "").replace("지금 ", "").replace("사다리 ", "").strip()
    if (item.note or "").strip():
        body = item.note.strip()
    elif item.ma_label or item.rsi_label or item.bb_label or item.macd_label:
        body = _advice(
            ma_label=item.ma_label,
            rsi_label=item.rsi_label,
            bb_label=item.bb_label,
            macd_label=item.macd_label,
            macd_hist_label=item.macd_hist_label,
            macd_div_label=item.macd_div_label,
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


def macd_series(
    close: pd.Series,
    *,
    fast: int = MACD_FAST,
    slow: int = MACD_SLOW,
    signal: int = MACD_SIGNAL,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
    line = ema_fast - ema_slow
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = line - sig
    return line, sig, hist


def _macd_cross_label(line: pd.Series, sig: pd.Series) -> str:
    if len(line) < 2 or len(sig) < 2:
        return "없음"
    a0, a1 = float(line.iloc[-2]), float(line.iloc[-1])
    b0, b1 = float(sig.iloc[-2]), float(sig.iloc[-1])
    if any(x != x for x in (a0, a1, b0, b1)):  # NaN
        return "없음"
    d0, d1 = a0 - b0, a1 - b1
    if d0 <= 0 < d1:
        return "골든크로스"
    if d0 >= 0 > d1:
        return "데드크로스"
    if d1 > 0:
        return "시그널 위"
    if d1 < 0:
        return "시그널 아래"
    return "시그널 접촉"


def _macd_hist_label(hist: pd.Series) -> str:
    if len(hist) < 2:
        return "없음"
    h0, h1 = float(hist.iloc[-2]), float(hist.iloc[-1])
    if h0 != h0 or h1 != h1:
        return "없음"
    if h1 > 0 and h1 > h0:
        return "히스토그램 확대"
    if h1 > 0 and h1 < h0:
        return "히스토그램 축소"
    if h1 < 0 and h1 < h0:
        return "히스토그램 음수 확대"
    if h1 < 0 and h1 > h0:
        return "히스토그램 음수 축소"
    if h1 > 0:
        return "히스토그램 양수"
    if h1 < 0:
        return "히스토그램 음수"
    return "히스토그램 0"


def _macd_div_label(close: pd.Series, hist: pd.Series, *, lookback: int = MACD_DIV_LOOKBACK) -> str:
    """Simple peak/trough divergence — display only, not a trade trigger."""
    n = min(len(close), len(hist), lookback)
    if n < 20:
        return ""
    c = close.iloc[-n:]
    h = hist.iloc[-n:]
    if h.isna().all() or c.isna().all():
        return ""
    # Bearish: price near window high, hist peak earlier was higher
    mid = n // 2
    c_last = float(c.iloc[-1])
    h_last = float(h.iloc[-1])
    if c_last != c_last or h_last != h_last:
        return ""
    c_hi_early = float(c.iloc[:mid].max())
    c_hi_late = float(c.iloc[mid:].max())
    h_hi_early = float(h.iloc[:mid].max())
    h_hi_late = float(h.iloc[mid:].max())
    if (
        c_hi_late >= c_hi_early * 0.995
        and h_hi_late < h_hi_early * 0.92
        and h_hi_early > 0
        and abs(c_last - c_hi_late) / max(c_hi_late, 1e-9) < 0.02
    ):
        return "고점 다이버전스"
    c_lo_early = float(c.iloc[:mid].min())
    c_lo_late = float(c.iloc[mid:].min())
    h_lo_early = float(h.iloc[:mid].min())
    h_lo_late = float(h.iloc[mid:].min())
    if (
        c_lo_late <= c_lo_early * 1.005
        and h_lo_late > h_lo_early * 0.92
        and h_lo_early < 0
        and abs(c_last - c_lo_late) / max(abs(c_lo_late), 1e-9) < 0.02
    ):
        return "저점 다이버전스"
    return ""


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
    macd_line, macd_sig, macd_hist = macd_series(close)
    macd_v, sig_v, hist_v = _f(macd_line), _f(macd_sig), _f(macd_hist)
    macd_label = _macd_cross_label(macd_line, macd_sig)
    macd_hist_label = _macd_hist_label(macd_hist)
    macd_div_label = _macd_div_label(close, macd_hist)
    as_of = str(close.index[-1].date())
    advice = _advice(
        ma_label=ma_label,
        rsi_label=rsi_label,
        bb_label=bb_label,
        macd_label=macd_label,
        macd_hist_label=macd_hist_label,
        macd_div_label=macd_div_label,
    )
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
        macd=None if macd_v is None else round(macd_v, 2),
        macd_signal=None if sig_v is None else round(sig_v, 2),
        macd_hist=None if hist_v is None else round(hist_v, 2),
        ma_label=ma_label,
        rsi_label=rsi_label,
        vol_label=vol_label,
        bb_label=bb_label,
        macd_label=macd_label,
        macd_hist_label=macd_hist_label,
        macd_div_label=macd_div_label,
        advice=advice,
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
