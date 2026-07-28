from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import pandas as pd

from src.value_list.dart_disclosure import load_hakedaka_dart_signals, refresh_hakedaka_dart_signals
from src.value_list.ticker_registry import load_integration_config, resolve_hakedaka_registry


@dataclass
class HakedakaDartVerificationRow:
    no: int
    name: str
    ticker: str
    grade: str
    group_id: int
    corp_code: str
    dart_signal: str
    dart_latest_date: str
    cancel_disclosure: bool
    has_fundamentals: bool
    fundamentals_usable_from: str
    verification_status: str  # verified | partial | failed | skipped
    issues: str


def _fundamentals_index(data_dir: Path) -> dict[str, dict[str, str]]:
    path = data_dir / "fundamentals.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    out: dict[str, dict[str, str]] = {}
    for _, row in df.iterrows():
        t = str(row.get("ticker", "")).zfill(6)
        if t:
            out[t] = dict(row)
    return out


def _corp_map(data_dir: Path, tickers: list[str]) -> dict[str, str]:
    try:
        from src.data_refresh.dart_corp_codes import build_ticker_corp_map

        return build_ticker_corp_map(data_dir, tickers)
    except Exception:
        return {}


def _classify_verification(
    *,
    ticker: str,
    corp_code: str,
    dart: dict[str, Any],
    fund: dict[str, str] | None,
) -> tuple[str, list[str]]:
    issues: list[str] = []
    if not ticker or ticker == "000000":
        return "failed", ["ticker_unresolved"]
    if not corp_code:
        issues.append("no_corp_code")
    if dart.get("error"):
        issues.append(f"dart:{dart.get('error')}")
    if not fund:
        issues.append("no_fundamentals")
    elif not str(fund.get("usable_from_date", "")).strip():
        issues.append("fundamentals_no_pit_date")

    if issues:
        if corp_code and fund and not dart.get("error"):
            return "partial", issues
        return "failed", issues

    if dart.get("signal") in ("unknown", "") and not dart.get("latest_date"):
        return "partial", ["dart_no_disclosure_match"]

    return "verified", []


def build_verification_rows(
    data_dir: Path,
    *,
    dart_payload: dict[str, Any] | None = None,
) -> list[HakedakaDartVerificationRow]:
    registry = resolve_hakedaka_registry(data_dir)
    dart = dart_payload or load_hakedaka_dart_signals(data_dir)
    dart_tickers = dart.get("tickers") or {}
    tickers = [str(r["ticker"]).zfill(6) for r in registry if r.get("ticker")]
    corp_map = _corp_map(data_dir, tickers)
    fund_idx = _fundamentals_index(data_dir)

    rows: list[HakedakaDartVerificationRow] = []
    for stock in registry:
        ticker = str(stock.get("ticker", "")).zfill(6)
        dart_row = dart_tickers.get(ticker, {})
        fund = fund_idx.get(ticker)
        corp = corp_map.get(ticker, "")
        status, issues = _classify_verification(
            ticker=ticker,
            corp_code=corp,
            dart=dart_row,
            fund=fund,
        )
        rows.append(
            HakedakaDartVerificationRow(
                no=int(stock.get("no", 0)),
                name=str(stock.get("name", "")),
                ticker=ticker,
                grade=str(stock.get("grade", "")),
                group_id=int(stock.get("group_id", 0)),
                corp_code=corp,
                dart_signal=str(dart_row.get("signal", "unknown")),
                dart_latest_date=str(dart_row.get("latest_date", "")),
                cancel_disclosure=bool(dart_row.get("cancel_disclosure")),
                has_fundamentals=fund is not None,
                fundamentals_usable_from=str(fund.get("usable_from_date", "")) if fund else "",
                verification_status=status,
                issues=";".join(issues),
            )
        )
    return rows


def write_hakedaka_dart_verification(
    data_dir: Path,
    output_dir: Path,
    rows: list[HakedakaDartVerificationRow],
    *,
    dart_payload: dict[str, Any] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([asdict(r) for r in rows])
    csv_path = output_dir / "hakedaka_dart_verification.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    summary = {
        "verified": sum(1 for r in rows if r.verification_status == "verified"),
        "partial": sum(1 for r in rows if r.verification_status == "partial"),
        "failed": sum(1 for r in rows if r.verification_status == "failed"),
        "dart_strong": sum(1 for r in rows if r.dart_signal == "strong"),
        "with_fundamentals": sum(1 for r in rows if r.has_fundamentals),
    }
    cache = data_dir / "cache" / "hakedaka_dart_verification.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of": (dart_payload or {}).get("as_of", ""),
        "total": len(rows),
        "summary": summary,
        "rows": [asdict(r) for r in rows],
    }
    cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return csv_path


def run_hakedaka_dart_verification(
    data_dir: Path,
    output_dir: Path,
    tickers: list[str],
    *,
    force: bool = False,
) -> dict[str, Any]:
    cfg = load_integration_config(data_dir)
    dart_cfg = cfg.get("dart") or {}
    from src.settings.user_secrets import credential_status

    dart_payload: dict[str, Any] = {"as_of": "", "tickers": {}}
    if credential_status(data_dir).get("dart"):
        dart_payload = refresh_hakedaka_dart_signals(
            data_dir,
            tickers,
            force=force or bool(dart_cfg.get("force_refresh")),
        )
    else:
        dart_payload = load_hakedaka_dart_signals(data_dir)

    rows = build_verification_rows(data_dir, dart_payload=dart_payload)
    write_hakedaka_dart_verification(data_dir, output_dir, rows, dart_payload=dart_payload)
    return {"dart": dart_payload, "summary": {k: sum(1 for r in rows if getattr(r, "verification_status", "") == k) for k in ("verified", "partial", "failed")}}
