from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class FredObservation:
    date: str
    value: float


@dataclass
class FredFetchResult:
    series_id: str
    observations: list[FredObservation] = field(default_factory=list)
    last_date: str = ""
    error: str | None = None


def _fred_get(
    base_url: str,
    *,
    series_id: str,
    api_key: str,
    limit: int = 24,
) -> FredFetchResult:
    result = FredFetchResult(series_id=series_id)
    if not api_key.strip():
        result.error = "FRED_API_KEY 미설정"
        return result

    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=800)).strftime("%Y-%m-%d")
    params = urllib.parse.urlencode({
        "series_id": series_id,
        "api_key": api_key.strip(),
        "file_type": "json",
        "observation_start": start,
        "observation_end": end,
        "sort_order": "desc",
        "limit": limit,
    })
    url = f"{base_url}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "multi-asset-trigger-portfolio/2.2"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        result.error = str(exc)
        return result

    obs_block = payload.get("observations") or []
    for row in obs_block:
        raw = str(row.get("value", "")).strip()
        if raw in ("", "."):
            continue
        try:
            val = float(raw)
        except ValueError:
            continue
        date = str(row.get("date", ""))[:10]
        if not date:
            continue
        result.observations.append(FredObservation(date=date, value=val))
        if not result.last_date:
            result.last_date = date

    if not result.observations:
        result.error = f"no valid observations for {series_id}"
    return result


def compute_yoy_pct(observations: list[FredObservation]) -> tuple[float | None, str]:
    """월간 시계열 — 최신값 대비 12개월 전 YoY(%)."""
    if len(observations) < 13:
        return None, "insufficient history for YoY"
    latest = observations[0]
    # desc sort — find ~12 months earlier
    lag = observations[12] if len(observations) > 12 else None
    if lag is None or lag.value <= 0:
        return None, "lag value missing"
    yoy = (latest.value / lag.value - 1.0) * 100.0
    return round(yoy, 2), latest.date


def extract_last(observations: list[FredObservation]) -> tuple[float | None, str]:
    if not observations:
        return None, ""
    obs = observations[0]
    return round(obs.value, 4), obs.date


def fetch_fred_field(
    base_url: str,
    *,
    series_id: str,
    api_key: str,
    transform: str,
) -> tuple[float | None, str, str | None]:
    """Returns (value, last_date, error)."""
    fetched = _fred_get(base_url, series_id=series_id, api_key=api_key)
    if fetched.error:
        return None, "", fetched.error
    if transform == "yoy_pct":
        val, dt = compute_yoy_pct(fetched.observations)
        if val is None:
            return None, fetched.last_date, "YoY 계산 실패"
        return val, dt, None
    val, dt = extract_last(fetched.observations)
    if val is None:
        return None, "", "empty series"
    # HY OAS는 bp 단위로 저장 (FRED는 %)
    if series_id == "BAMLH0A0HYM2":
        val = round(val * 100, 1)
    return val, dt, None
