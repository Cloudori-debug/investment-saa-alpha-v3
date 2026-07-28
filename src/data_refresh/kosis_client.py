from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class KosisPoint:
    period: str
    value: float


@dataclass
class KosisFetchResult:
    query_key: str
    points: list[KosisPoint] = field(default_factory=list)
    last_period: str = ""
    error: str | None = None


def _parse_kosis_value(raw: Any) -> float | None:
    text = str(raw).strip().replace(",", "")
    if not text or text in ("-", "X", "..."):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _period_sort_key(period: str) -> str:
    """YYYYMM or YYYYQQ → 정렬용."""
    p = period.strip()
    return p.zfill(6)


def fetch_kosis_series(
    base_url: str,
    *,
    api_key: str,
    org_id: str,
    tbl_id: str,
    itm_id: str,
    obj_l1: str = "ALL",
    prd_se: str = "M",
    months_back: int = 24,
) -> KosisFetchResult:
    result = KosisFetchResult(query_key=tbl_id)
    if not api_key.strip():
        result.error = "KOSIS_API_KEY 미설정"
        return result

    end = datetime.now()
    start = end - timedelta(days=months_back * 31)
    start_prd = start.strftime("%Y%m")
    end_prd = end.strftime("%Y%m")

    params = {
        "method": "getList",
        "apiKey": api_key.strip(),
        "format": "json",
        "jsonVD": "Y",
        "orgId": org_id,
        "tblId": tbl_id,
        "itmId": itm_id,
        "objL1": obj_l1,
        "objL2": "",
        "objL3": "",
        "objL4": "",
        "objL5": "",
        "objL6": "",
        "objL7": "",
        "objL8": "",
        "prdSe": prd_se,
        "startPrdDe": start_prd,
        "endPrdDe": end_prd,
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "multi-asset-trigger-portfolio/2.2"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        result.error = str(exc)
        return result

    if isinstance(payload, dict) and payload.get("err"):
        err_code = str(payload.get("err") or "")
        err_msg = str(payload.get("errMsg") or "KOSIS API error")
        result.error = f"KOSIS err={err_code}: {err_msg} (tbl={tbl_id})"
        return result

    rows: list[dict[str, Any]] = []
    if isinstance(payload, list):
        rows = [r for r in payload if isinstance(r, dict)]
    elif isinstance(payload, dict):
        inner = payload.get("StatisticSearch") or payload.get("result") or payload
        if isinstance(inner, list):
            rows = [r for r in inner if isinstance(r, dict)]
        elif isinstance(inner, dict) and "row" in inner:
            row_data = inner["row"]
            rows = row_data if isinstance(row_data, list) else [row_data]

    for row in rows:
        period = str(row.get("PRD_DE") or row.get("prdDe") or row.get("TIME") or "").strip()
        val = _parse_kosis_value(row.get("DT") or row.get("dt") or row.get("DATA_VALUE"))
        if period and val is not None:
            result.points.append(KosisPoint(period=period, value=val))

    result.points.sort(key=lambda p: _period_sort_key(p.period), reverse=True)
    if result.points:
        result.last_period = result.points[0].period
    else:
        result.error = f"empty KOSIS response for {tbl_id}"
    return result


def kosis_yoy_pct(points: list[KosisPoint]) -> tuple[float | None, str]:
    if len(points) < 13:
        return None, ""
    latest = points[0]
    lag = points[12]
    if lag.value <= 0:
        return None, latest.period
    yoy = (latest.value / lag.value - 1.0) * 100.0
    return round(yoy, 2), latest.period


def fetch_kosis_field(
    base_url: str,
    query: dict[str, Any],
    *,
    api_key: str,
) -> tuple[float | None, str, str | None]:
    fetched = fetch_kosis_series(
        base_url,
        api_key=api_key,
        org_id=str(query.get("orgId", "")),
        tbl_id=str(query.get("tblId", "")),
        itm_id=str(query.get("itmId", "T10")),
        obj_l1=str(query.get("objL1", "ALL")),
        prd_se=str(query.get("prdSe", "M")),
    )
    if fetched.error:
        return None, "", fetched.error
    transform = str(query.get("transform", "last"))
    if transform == "yoy_pct":
        val, period = kosis_yoy_pct(fetched.points)
        if val is None:
            return None, fetched.last_period, "YoY 계산 실패"
        return val, period, None
    if not fetched.points:
        return None, "", "empty"
    return round(fetched.points[0].value, 2), fetched.points[0].period, None
