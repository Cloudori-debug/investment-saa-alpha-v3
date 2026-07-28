from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

TREASURY_EVENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "treasury_acquire": ("자기주식취득결정", "자기주식 취득결정", "자사주 매입", "자기주식 매입"),
    "treasury_dispose": ("자기주식처분결정", "자기주식 처분결정", "자사주 처분"),
    "treasury_cancel": ("자기주식소각결정", "자기주식 소각결정", "주식소각결정", "자기주식 소각"),
    "dividend_policy": ("배당정책", "현금배당", "배당 확대"),
    "shareholder_return": ("주주환원", "중기 주주환원", "자본환원"),
}

TREASURY_CSV_FIELDS = [
    "as_of", "ticker", "name", "event_date", "event_type",
    "announced_amount", "announced_share_count",
    "cancellation_amount", "cancellation_share_count",
    "buyback_period_start", "buyback_period_end",
    "source_report_name", "source_url_or_receipt_no",
    "text_evidence", "extraction_confidence",
]

# Phase 4f — ticker-level precision columns (also on event rows for join convenience)
TREASURY_PRECISION_EXTRA_FIELDS = [
    "treasury_share_count", "treasury_share_ratio", "treasury_share_value",
    "buyback_announced_amount", "buyback_announced_shares",
    "cancellation_announced_amount", "cancellation_announced_shares",
    "cancellation_completed_amount", "cancellation_completed_shares",
    "cancellation_progress_pct",
    "missing_reason",
]

TREASURY_CSV_FIELDS_EXTENDED = TREASURY_CSV_FIELDS + [
    f for f in TREASURY_PRECISION_EXTRA_FIELDS if f not in TREASURY_CSV_FIELDS
]


def _parse_rcept_dt(s: str) -> str:
    s = re.sub(r"\D", "", str(s))
    if len(s) >= 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return ""


def _classify_treasury_event(title: str) -> str:
    for event_type, kws in TREASURY_EVENT_KEYWORDS.items():
        if any(k in title for k in kws):
            return event_type
    return ""


from src.value_list.hakedaka_treasury_extraction import extract_treasury_event_details


@dataclass
class TreasuryEventRow:
    ticker: str
    name: str
    event_date: str
    event_type: str
    announced_amount: float | None
    announced_share_count: float | None
    cancellation_amount: float | None
    cancellation_share_count: float | None
    buyback_period_start: str
    buyback_period_end: str
    source_report_name: str
    source_url_or_receipt_no: str
    text_evidence: str
    extraction_confidence: str


def fetch_ticker_treasury_events(
    ticker: str,
    name: str,
    corp_code: str,
    *,
    lookback_days: int = 365,
    as_of: str | None = None,
    limiter: Any = None,
) -> list[TreasuryEventRow]:
    from src.data_refresh.dart_client import dart_get

    end = as_of or date.today().isoformat()
    start = (datetime.strptime(end, "%Y-%m-%d") - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    bgn = start.replace("-", "")
    end_d = end.replace("-", "")
    rows: list[TreasuryEventRow] = []

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
            event_type = _classify_treasury_event(title)
            if not event_type:
                continue
            rcept = _parse_rcept_dt(str(item.get("rcept_dt", "")))
            rcept_no = str(item.get("rcept_no", ""))
            details = extract_treasury_event_details(title, event_type)
            amt = details["amount"]
            shares = details["shares"]
            p_start, p_end = details["period_start"], details["period_end"]
            cancel_amt = amt if "cancel" in event_type else None
            cancel_sh = shares if "cancel" in event_type else None
            conf = details["treasury_event_confidence"]
            if conf == "low" and (amt is not None or shares is not None):
                conf = "medium"
            rows.append(
                TreasuryEventRow(
                    ticker=ticker.zfill(6),
                    name=name,
                    event_date=rcept,
                    event_type=event_type,
                    announced_amount=amt if "acquire" in event_type else None,
                    announced_share_count=shares if "acquire" in event_type else None,
                    cancellation_amount=cancel_amt,
                    cancellation_share_count=cancel_sh,
                    buyback_period_start=p_start,
                    buyback_period_end=p_end,
                    source_report_name=title,
                    source_url_or_receipt_no=rcept_no,
                    text_evidence=title,
                    extraction_confidence=conf,
                )
            )
        if len(items) < 100:
            break
    return rows


def scan_hakedaka_treasury_events(
    data_dir: Path,
    output_dir: Path,
    registry: list[dict[str, Any]],
    *,
    as_of: str | None = None,
    lookback_days: int = 365,
) -> dict[str, Any]:
    from src.data_refresh.dart_client import RateLimiter
    from src.data_refresh.dart_corp_codes import build_ticker_corp_map
    from src.settings.user_secrets import credential_status

    today = as_of or date.today().isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "hakedaka_treasury_events.csv"

    if not credential_status(data_dir).get("dart"):
        return {"as_of": today, "events": 0, "skipped": "no_credentials"}

    tickers = [str(r["ticker"]).zfill(6) for r in registry if r.get("ticker")]
    name_by = {str(r["ticker"]).zfill(6): str(r.get("name", "")) for r in registry if r.get("ticker")}
    corp_map = build_ticker_corp_map(data_dir, tickers)
    limiter = RateLimiter(min_interval_sec=0.12)
    all_rows: list[TreasuryEventRow] = []
    scan_status: dict[str, dict[str, Any]] = {}
    event_found_tickers: set[str] = set()

    for t in tickers:
        corp = corp_map.get(t)
        if not corp:
            scan_status[t] = {
                "scan_ok": False,
                "event_found": False,
                "error": "no_corp_code",
            }
            continue
        try:
            ticker_rows = fetch_ticker_treasury_events(
                t, name_by.get(t, t), corp,
                lookback_days=lookback_days, as_of=today, limiter=limiter,
            )
            all_rows.extend(ticker_rows)
            found = len(ticker_rows) > 0
            if found:
                event_found_tickers.add(t)
            scan_status[t] = {
                "scan_ok": True,
                "event_found": found,
                "error": "",
                "events": len(ticker_rows),
            }
        except Exception as exc:
            scan_status[t] = {
                "scan_ok": False,
                "event_found": False,
                "error": str(exc),
            }

    scan_ok_count = sum(1 for s in scan_status.values() if s.get("scan_ok"))
    total = len(tickers) or 1
    scan_summary = {
        "scan_attempted": len(tickers),
        "scan_ok": scan_ok_count,
        "event_found": len(event_found_tickers),
        "treasury_scan_coverage_pct": round(scan_ok_count / total * 100, 1),
        "treasury_event_found_rate_pct": round(len(event_found_tickers) / total * 100, 1),
    }
    status_path = output_dir / "hakedaka_treasury_scan_status.json"
    status_path.write_text(
        json.dumps(
            {
                "as_of": today,
                "lookback_days": lookback_days,
                "tickers": scan_status,
                "summary": scan_summary,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TREASURY_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in all_rows:
            writer.writerow({
                "as_of": today,
                **row.__dict__,
            })

    with_qty = sum(
        1 for r in all_rows
        if r.announced_share_count or r.cancellation_share_count or r.announced_amount
    )
    return {
        "as_of": today,
        "events": len(all_rows),
        "with_quantity_or_amount": with_qty,
        "lookback_days": lookback_days,
        **scan_summary,
    }
