from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass
class SeriesSnapshot:
    symbol: str
    close: float
    recent_high: float
    ma200: float
    source: str = "yahoo_chart"
    last_updated: str = ""
    confidence: str = "medium"
    fallback_used: bool = False


@dataclass
class ExternalMarketFetchResult:
    as_of: str
    series: dict[str, SeriesSnapshot] = field(default_factory=dict)
    fx_usdkrw: float | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


_YAHOO_SYMBOLS = {
    "sp500": "^GSPC",
    "vix": "^VIX",
    "gold": "GC=F",
    "oil_brent": "BZ=F",
    "usdkrw": "KRW=X",
}


def _fetch_yahoo_chart(symbol: str, *, range_days: int = 400) -> list[tuple[int, float]]:
    encoded = urllib.request.quote(symbol, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}"
        f"?interval=1d&range={range_days}d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "multi-asset-trigger-portfolio/2.1"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        raise ValueError(f"empty chart for {symbol}")
    block = result[0]
    timestamps = block.get("timestamp") or []
    quotes = ((block.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quotes.get("close") or []
    out: list[tuple[int, float]] = []
    for ts, c in zip(timestamps, closes):
        if c is not None:
            out.append((int(ts), float(c)))
    if not out:
        raise ValueError(f"no closes for {symbol}")
    return out


def _snapshot_from_closes(symbol: str, points: list[tuple[int, float]]) -> SeriesSnapshot:
    closes = [c for _, c in points]
    close = closes[-1]
    recent_high = max(closes)
    window = min(200, len(closes))
    ma200 = sum(closes[-window:]) / window
    last_ts = points[-1][0]
    last_updated = datetime.fromtimestamp(last_ts, tz=timezone.utc).strftime("%Y-%m-%d")
    return SeriesSnapshot(
        symbol=symbol,
        close=round(close, 4),
        recent_high=round(recent_high, 4),
        ma200=round(ma200, 4),
        last_updated=last_updated,
    )


def fetch_external_market(*, as_of: str | None = None) -> ExternalMarketFetchResult:
    """VIX·SP500·금·유가·USD/KRW — Yahoo Chart API (키 불필요)."""
    resolved = as_of or datetime.now().strftime("%Y-%m-%d")
    result = ExternalMarketFetchResult(as_of=resolved)

    for key, yahoo_sym in _YAHOO_SYMBOLS.items():
        try:
            points = _fetch_yahoo_chart(yahoo_sym)
            snap = _snapshot_from_closes(yahoo_sym, points)
            if key == "usdkrw":
                result.fx_usdkrw = snap.close
            else:
                result.series[key] = snap
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            result.errors.append(f"{key}({yahoo_sym}): {exc}")

    if result.fx_usdkrw is None:
        fx = _fetch_frankfurter_usdkrw()
        if fx:
            result.fx_usdkrw = fx[0]
            result.warnings.append("USD/KRW: Frankfurter fallback")
            result.series["usdkrw"] = SeriesSnapshot(
                symbol="USD/KRW",
                close=fx[0],
                recent_high=fx[0],
                ma200=fx[0],
                source="frankfurter",
                last_updated=fx[1],
                confidence="low",
                fallback_used=True,
            )

    return result


def _fetch_frankfurter_usdkrw() -> tuple[float, str] | None:
    try:
        url = "https://api.frankfurter.app/latest?from=USD&to=KRW"
        req = urllib.request.Request(url, headers={"User-Agent": "multi-asset-trigger-portfolio/2.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        rate = (data.get("rates") or {}).get("KRW")
        as_of = str(data.get("date", ""))
        return (float(rate), as_of) if rate else None
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None


def business_days_between(start: str, end: str) -> int:
    """ISO date 간 영업일 근사 (주말 제외)."""
    try:
        d0 = datetime.strptime(start[:10], "%Y-%m-%d")
        d1 = datetime.strptime(end[:10], "%Y-%m-%d")
    except ValueError:
        return 99
    if d1 < d0:
        return 0
    days = 0
    cur = d0
    while cur < d1:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            days += 1
    return days


def build_provenance(ext: ExternalMarketFetchResult, as_of: str) -> dict[str, Any]:
    from src.validation.market_indicator_schema import (
        build_normalized_field_from_snapshot,
        normalize_provenance_doc,
    )

    now = datetime.now().isoformat(timespec="seconds")
    fields: dict[str, Any] = {}
    for key, snap in ext.series.items():
        fields[key] = build_normalized_field_from_snapshot(
            key,
            value=snap.close,
            value_date=snap.last_updated or as_of,
            source=snap.source,
            fetch_method=snap.source,
            as_of=as_of,
            symbol=snap.symbol,
            confidence=snap.confidence,
            fallback_used=snap.fallback_used,
            fetched_at=now,
        )
    if ext.fx_usdkrw and "usdkrw" not in fields:
        usdkrw_snap = ext.series.get("usdkrw")
        if usdkrw_snap:
            fields["usdkrw"] = build_normalized_field_from_snapshot(
                "usdkrw",
                value=ext.fx_usdkrw,
                value_date=usdkrw_snap.last_updated or as_of,
                source=usdkrw_snap.source,
                fetch_method=usdkrw_snap.source,
                as_of=as_of,
                symbol=usdkrw_snap.symbol,
                confidence=usdkrw_snap.confidence,
                fallback_used=usdkrw_snap.fallback_used,
                fetched_at=now,
            )
        else:
            fields["usdkrw"] = build_normalized_field_from_snapshot(
                "usdkrw",
                value=ext.fx_usdkrw,
                value_date=as_of,
                source="unknown",
                fetch_method="fallback",
                as_of=as_of,
                confidence="low",
                fallback_used=True,
                fetched_at=now,
            )
    raw = {"as_of": as_of, "updated_at": now, "fields": fields}
    return normalize_provenance_doc(raw, as_of=as_of)


def write_provenance(data_dir: Path, provenance: dict[str, Any]) -> Path:
    path = data_dir / "market_data_provenance.json"
    path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def fetch_korea_10y_pykrx(data_dir, as_of: str) -> float | None:
    """PyKRX OTC 국채 수익률 — 10년물 근사."""
    try:
        from src.data_refresh.pykrx_client import import_pykrx_stock, to_compact_date, lookback_start

        import_pykrx_stock(data_dir)
        from pykrx import bond  # type: ignore[import-untyped]

        start = lookback_start(as_of, 14)
        df = bond.get_otc_treasury_yields(to_compact_date(start), to_compact_date(as_of))
        if df is None or df.empty:
            return None
        # 컬럼명: 잔존만기별 — 10년 근사
        for col in df.columns:
            label = str(col)
            if "10" in label and "년" in label:
                val = df[col].dropna()
                if not val.empty:
                    parsed = round(float(val.iloc[-1]), 3)
                    return parsed if is_valid_korea_10y_nominal(parsed) else None
        numeric_cols = [c for c in df.columns if str(c) != "날짜"]
        if numeric_cols:
            last = df[numeric_cols].iloc[-1].dropna()
            if not last.empty:
                parsed = round(float(last.iloc[-1]), 3)
                return parsed if is_valid_korea_10y_nominal(parsed) else None
    except Exception:
        return None
    return None


KOREA_10Y_NOMINAL_MIN = 0.5
KOREA_10Y_NOMINAL_MAX = 15.0


def is_valid_korea_10y_nominal(value: float | None) -> bool:
    """명목 10년 국채 수익률(%). 실질금리·변화율 등 오매핑 배제."""
    if value is None:
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return KOREA_10Y_NOMINAL_MIN <= v <= KOREA_10Y_NOMINAL_MAX


def korea_10y_from_history(data_dir: Path, *, exclude_invalid: bool = True) -> float | None:
    """market_indicators / history에서 마지막 유효 명목 10Y."""
    for name in ("market_indicators.csv", "market_indicators_history.csv"):
        path = data_dir / name
        if not path.exists():
            continue
        import pandas as pd

        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        for rec in reversed(df.to_dict(orient="records")):
            raw = str(rec.get("korea_10y", "")).strip()
            if not raw:
                continue
            try:
                v = float(raw)
            except ValueError:
                continue
            if exclude_invalid and not is_valid_korea_10y_nominal(v):
                continue
            return round(v, 3)
    return None


def fetch_foreign_flow_pykrx(data_dir, as_of: str, *, lookback_days: int = 5) -> str | None:
    """PyKRX KOSPI 외국인 순매수 3영업일 근사 → inflow/outflow/neutral."""
    try:
        from src.data_refresh.pykrx_client import import_pykrx_stock, to_compact_date, lookback_start

        stock = import_pykrx_stock(data_dir)
        start = lookback_start(as_of, lookback_days + 10)
        df = stock.get_market_net_purchases_of_equities(
            to_compact_date(start), to_compact_date(as_of), "KOSPI", "외국인"
        )
        if df is None or df.empty:
            return None
        tail = df.tail(3)
        net = float(tail.sum().sum()) if hasattr(tail.sum(), "sum") else float(tail.values.sum())
        if net > 0:
            return "inflow"
        if net < 0:
            return "outflow"
        return "neutral"
    except Exception:
        return None


def korea_10y_from_macro_tier2(macro_row: dict[str, Any]) -> float | None:
    """macro Tier2에는 명목 10Y가 없음 — real_rate+spread는 명목 proxy로 부적합."""
    return None
