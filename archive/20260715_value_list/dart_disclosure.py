from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

_CANCEL_KW = ("소각", "소멸", "자기주식 소각", "소각 실시")
_ACQUIRE_KW = ("자기주식 취득", "취득 결정", "자사주 매입", "자기주식 매입")
_DISPOSE_KW = ("자기주식 처분", "처분 결정", "자사주 처분")
_RETURN_KW = ("주주환원", "배당", "자본환원", "현금배당", "중기 주주환원")
_GOVERNANCE_KW = ("지배구조", "이사회", "최대주주", "주요주주", "특수관계인", "공개매수", "합병", "분할")
_CANCEL_KW_EXT = _CANCEL_KW + ("자기주식소각결정", "자기주식 소각결정", "자기주식소각")
_ACQUIRE_KW_EXT = _ACQUIRE_KW + ("자기주식취득결정", "자기주식 취득결정")

EVENT_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "treasury_cancel": _CANCEL_KW_EXT,
    "treasury_acquire": _ACQUIRE_KW_EXT,
    "treasury_dispose": _DISPOSE_KW,
    "dividend_policy": ("배당", "현금배당", "배당정책", "배당 확대"),
    "shareholder_return": ("주주환원", "자본환원", "중기 주주환원"),
    "merger_split": ("합병", "분할", "분할합병"),
    "tender_offer": ("공개매수",),
    "major_shareholder": ("최대주주", "주요주주", "최대주주변경", "주요주주변경"),
    "governance": _GOVERNANCE_KW,
}


@dataclass
class TreasurySignal:
    ticker: str
    corp_code: str
    cancel_disclosure: bool
    acquire_disclosure: bool
    dispose_disclosure: bool
    return_disclosure: bool
    latest_date: str
    latest_title: str
    signal: str  # strong | neutral | weak | unknown
    alignment_pts: float


def _cache_path(data_dir: Path) -> Path:
    return data_dir / "cache" / "hakedaka_dart_signals.json"


def _classify_report(name: str) -> dict[str, bool]:
    n = name or ""
    return {
        "cancel": any(k in n for k in _CANCEL_KW_EXT),
        "acquire": any(k in n for k in _ACQUIRE_KW_EXT),
        "dispose": any(k in n for k in _DISPOSE_KW),
        "return": any(k in n for k in _RETURN_KW),
    }


def _signal_from_flags(flags: dict[str, bool]) -> tuple[str, float]:
    if flags.get("cancel"):
        return "strong", 25.0
    if flags.get("return") and not flags.get("dispose"):
        return "neutral", 12.0
    if flags.get("acquire") and not flags.get("cancel"):
        return "weak", -8.0
    if flags.get("dispose"):
        return "weak", -12.0
    if flags.get("return"):
        return "neutral", 8.0
    return "unknown", 0.0


def _parse_rcept_dt(s: str) -> str:
    s = re.sub(r"\D", "", str(s))
    if len(s) >= 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return ""


def _classify_event_types(title: str) -> list[str]:
    n = title or ""
    hits: list[str] = []
    for event_type, keywords in EVENT_TYPE_KEYWORDS.items():
        if any(k in n for k in keywords):
            hits.append(event_type)
    return hits


def fetch_ticker_dart_events(
    ticker: str,
    corp_code: str,
    *,
    lookback_days: int = 90,
    as_of: str | None = None,
    limiter: Any = None,
) -> list[dict[str, Any]]:
    """최근 lookback 구간 DART 공시 이벤트 목록."""
    from src.data_refresh.dart_client import dart_get

    end = as_of or date.today().isoformat()
    start = (datetime.strptime(end, "%Y-%m-%d") - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    bgn = start.replace("-", "")
    end_d = end.replace("-", "")
    events: list[dict[str, Any]] = []

    for page in range(1, 6):
        if limiter:
            limiter.wait()
        data = dart_get(
            "list.json",
            {
                "corp_code": corp_code,
                "bgn_de": bgn,
                "end_de": end_d,
                "page_no": page,
                "page_count": 100,
            },
        )
        items = data.get("list") or []
        if not items:
            break
        for item in items:
            title = str(item.get("report_nm", ""))
            rcept = _parse_rcept_dt(str(item.get("rcept_dt", "")))
            types = _classify_event_types(title)
            if not types:
                continue
            events.append({
                "ticker": ticker.zfill(6),
                "corp_code": corp_code,
                "event_date": rcept,
                "report_title": title,
                "event_types": "|".join(types),
                "rcept_no": str(item.get("rcept_no", "")),
            })
        if len(items) < 100:
            break
    return events


def scan_hakedaka_dart_events(
    data_dir: Path,
    output_dir: Path,
    tickers: list[str],
    *,
    as_of: str | None = None,
    lookback_days: int = 90,
    force_rescan: bool = True,
) -> dict[str, Any]:
    """하케다카 50 DART 이벤트 재스캔 → hakedaka_dart_events.csv."""
    import csv

    from src.data_refresh.dart_client import RateLimiter
    from src.data_refresh.dart_corp_codes import build_ticker_corp_map
    from src.settings.user_secrets import credential_status

    today = as_of or date.today().isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "hakedaka_dart_events.csv"

    if not credential_status(data_dir).get("dart"):
        return {"as_of": today, "events": 0, "skipped": "no_credentials"}

    norm = [str(t).zfill(6) for t in tickers if str(t).strip()]
    corp_map = build_ticker_corp_map(data_dir, norm)
    limiter = RateLimiter(min_interval_sec=0.12)
    all_events: list[dict[str, Any]] = []

    for t in norm:
        corp = corp_map.get(t)
        if not corp:
            continue
        try:
            evs = fetch_ticker_dart_events(
                t, corp, lookback_days=lookback_days, as_of=today, limiter=limiter,
            )
            all_events.extend(evs)
        except Exception:
            continue

    fieldnames = ["as_of", "ticker", "corp_code", "event_date", "event_types", "report_title", "rcept_no"]
    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for ev in all_events:
            writer.writerow({"as_of": today, **ev})

    signals = refresh_hakedaka_dart_signals(
        data_dir, norm, as_of=today, force=force_rescan, lookback_days=lookback_days,
    )
    return {"as_of": today, "events": len(all_events), "lookback_days": lookback_days, "signals": signals.get("scanned", 0)}


def fetch_ticker_disclosures(
    ticker: str,
    corp_code: str,
    *,
    lookback_days: int = 365,
    as_of: str | None = None,
    limiter: Any = None,
) -> TreasurySignal:
    from src.data_refresh.dart_client import dart_get

    end = as_of or date.today().isoformat()
    start = (datetime.strptime(end, "%Y-%m-%d") - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    bgn = start.replace("-", "")
    end_d = end.replace("-", "")

    flags = {"cancel": False, "acquire": False, "dispose": False, "return": False}
    latest_date = ""
    latest_title = ""

    for page in range(1, 4):
        if limiter:
            limiter.wait()
        data = dart_get(
            "list.json",
            {
                "corp_code": corp_code,
                "bgn_de": bgn,
                "end_de": end_d,
                "page_no": page,
                "page_count": 100,
            },
        )
        items = data.get("list") or []
        if not items:
            break
        for item in items:
            title = str(item.get("report_nm", ""))
            rcept = _parse_rcept_dt(str(item.get("rcept_dt", "")))
            cls = _classify_report(title)
            for k, v in cls.items():
                flags[k] = flags[k] or v
            if rcept and (not latest_date or rcept > latest_date):
                latest_date = rcept
                latest_title = title
        if len(items) < 100:
            break

    sig, pts = _signal_from_flags(flags)
    return TreasurySignal(
        ticker=ticker.zfill(6),
        corp_code=corp_code,
        cancel_disclosure=flags["cancel"],
        acquire_disclosure=flags["acquire"],
        dispose_disclosure=flags["dispose"],
        return_disclosure=flags["return"],
        latest_date=latest_date,
        latest_title=latest_title,
        signal=sig,
        alignment_pts=pts,
    )


def refresh_hakedaka_dart_signals(
    data_dir: Path,
    tickers: list[str],
    *,
    as_of: str | None = None,
    force: bool = False,
    lookback_days: int = 365,
) -> dict[str, Any]:
    """50종 DART 공시 스캔 — force=True면 매 run 재스캔."""
    cache = _cache_path(data_dir)
    cache.parent.mkdir(parents=True, exist_ok=True)
    today = as_of or date.today().isoformat()
    norm_tickers = [str(t).zfill(6) for t in tickers if str(t).strip() and str(t).zfill(6) != "000000"]
    norm_set = set(norm_tickers)

    if not force and cache.exists():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        cached_keys = set((cached.get("tickers") or {}).keys())
        if cached.get("as_of") == today and norm_set and norm_set.issubset(cached_keys):
            return cached

    from src.data_refresh.dart_client import RateLimiter
    from src.data_refresh.dart_corp_codes import build_ticker_corp_map

    try:
        corp_map = build_ticker_corp_map(data_dir, tickers)
    except Exception as exc:
        return {"as_of": today, "tickers": {}, "error": f"corp_code_map_failed:{exc}"}

    limiter = RateLimiter(min_interval_sec=0.15)
    out_tickers: dict[str, Any] = {}
    if not force and cache.exists():
        try:
            prev = json.loads(cache.read_text(encoding="utf-8"))
            out_tickers = dict(prev.get("tickers") or {})
        except Exception:
            out_tickers = {}
    errors: list[str] = []

    for raw in norm_tickers:
        t = raw
        if (
            not force
            and t in out_tickers
            and out_tickers[t].get("signal") not in (None, "")
            and not out_tickers[t].get("error")
        ):
            continue
        corp = corp_map.get(t)
        if not corp:
            out_tickers[t] = {"signal": "unknown", "alignment_pts": 0, "error": "no_corp_code"}
            continue
        try:
            sig = fetch_ticker_disclosures(t, corp, as_of=today, lookback_days=lookback_days, limiter=limiter)
            out_tickers[t] = {
                "cancel_disclosure": sig.cancel_disclosure,
                "acquire_disclosure": sig.acquire_disclosure,
                "dispose_disclosure": sig.dispose_disclosure,
                "return_disclosure": sig.return_disclosure,
                "latest_date": sig.latest_date,
                "latest_title": sig.latest_title,
                "signal": sig.signal,
                "alignment_pts": sig.alignment_pts,
            }
        except Exception as exc:
            errors.append(f"{t}:{exc}")
            out_tickers[t] = {"signal": "unknown", "alignment_pts": 0, "error": str(exc)}

    payload = {
        "as_of": today,
        "lookback_days": lookback_days,
        "tickers": out_tickers,
        "scanned": len(out_tickers),
        "force_rescan": force,
        "errors_sample": errors[:5],
    }
    cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def load_hakedaka_dart_signals(data_dir: Path) -> dict[str, Any]:
    path = _cache_path(data_dir)
    if not path.exists():
        return {"as_of": "", "tickers": {}}
    return json.loads(path.read_text(encoding="utf-8"))
