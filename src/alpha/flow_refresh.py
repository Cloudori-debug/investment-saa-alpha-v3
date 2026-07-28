"""Best-effort investor flow refresh for Alpha Signal Board targets only."""
from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

KST = timezone(timedelta(hours=9))


def format_flow_refresh_timestamp(dt: datetime | None = None) -> str:
    """ISO-8601 timestamp in KST for last_successful_flow_refresh."""
    when = dt or datetime.now(KST)
    if when.tzinfo is None:
        when = when.replace(tzinfo=KST)
    else:
        when = when.astimezone(KST)
    return when.isoformat(timespec="seconds")

from src.alpha.investor_flows import (
    FLOW_COLUMNS,
    classify_flow_signal,
    flow_score_from_signal,
    load_investor_flows,
)
from src.alpha_v2_gate import is_flow_record_stale

MANUAL_VERIFIED_SOURCES = frozenset({"manual_verified"})
AUTO_SOURCES = frozenset({"auto_pykrx", "auto_krx", "pykrx"})
DEFAULT_SLEEP_SEC = 0.25
DEFAULT_LOOKBACK_DAYS = 25
FLOW_COVERAGE_WARN_PCT = 80.0


@dataclass
class FlowRefreshResult:
    as_of: str
    target_count: int
    refreshed_count: int
    stale_count: int
    skipped_manual_count: int
    failed_tickers: list[str] = field(default_factory=list)
    flow_coverage_pct: float = 0.0
    stale_signal_count: int = 0
    path: str = ""
    warnings: list[str] = field(default_factory=list)
    cache_hit_count: int = 0
    cache_miss_count: int = 0
    pykrx_call_count: int = 0
    stale_reason_summary: dict[str, int] = field(default_factory=dict)
    last_successful_flow_refresh: str = ""
    coverage_scope: str = "watched_universe"

    def to_meta(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "target_count": self.target_count,
            "refreshed_count": self.refreshed_count,
            "stale_count": self.stale_count,
            "skipped_manual_count": self.skipped_manual_count,
            "failed_tickers": self.failed_tickers,
            "flow_coverage_pct": self.flow_coverage_pct,
            "stale_signal_count": self.stale_signal_count,
            "path": self.path,
            "warnings": self.warnings,
            "flow_unit": "KRW_net_trading_value",
            "flow_source": "auto_pykrx",
            "cache_hit_count": self.cache_hit_count,
            "cache_miss_count": self.cache_miss_count,
            "pykrx_call_count": self.pykrx_call_count,
            "stale_reason_summary": self.stale_reason_summary,
            "last_successful_flow_refresh": self.last_successful_flow_refresh,
            "coverage_scope": self.coverage_scope,
        }


def is_manual_verified(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    return str(row.get("source") or "").strip().lower() in MANUAL_VERIFIED_SOURCES


def extract_tickers_from_signal_board(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    out: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            tk = str(row.get("ticker", "")).zfill(6)
            if tk:
                out.append({"ticker": tk, "name": str(row.get("name") or "")})
    return out


def resolve_flow_target_tickers(
    *,
    holdings: list[Any] | None = None,
    candidates: list[Any] | None = None,
    signal_board_path: Path | None = None,
    data_dir: Path | None = None,
    output_dir: Path | None = None,
    max_tickers: int = 80,
) -> list[dict[str, str]]:
    """Watched universe when output_dir given; else legacy holdings+candidates+board."""
    if data_dir is not None and output_dir is not None:
        from src.alpha_v2_gate import resolve_watched_universe_tickers

        watched = resolve_watched_universe_tickers(data_dir, output_dir, max_tickers=max_tickers)
        if watched:
            return watched

    if signal_board_path and signal_board_path.exists():
        board = extract_tickers_from_signal_board(signal_board_path)
        if board:
            return board[:max_tickers]

    merged: dict[str, dict[str, str]] = {}
    for c in candidates or []:
        tk = str(getattr(c, "ticker", c.get("ticker") if isinstance(c, dict) else "")).zfill(6)
        if not tk:
            continue
        name = getattr(c, "name", None) or (c.get("name") if isinstance(c, dict) else "")
        merged[tk] = {"ticker": tk, "name": str(name or "")}
    for h in holdings or []:
        tk = str(getattr(h, "ticker", h.get("ticker") if isinstance(h, dict) else "")).zfill(6)
        if not tk:
            continue
        name = getattr(h, "name", None) or (h.get("name") if isinstance(h, dict) else "")
        merged[tk] = {"ticker": tk, "name": str(name or merged.get(tk, {}).get("name", ""))}
    return list(merged.values())


def compute_flow_quality_metrics(
    rows: dict[str, dict[str, Any]],
    target_tickers: set[str],
) -> dict[str, Any]:
    if not target_tickers:
        return {
            "flow_coverage_pct": 0.0,
            "stale_count": 0,
            "stale_signal_count": 0,
            "fresh_count": 0,
            "target_count": 0,
            "failed_tickers": [],
        }
    stale_signals = 0
    fresh = 0
    failed: list[str] = []
    for tk in sorted(target_tickers):
        row = rows.get(tk) or {}
        sig = str(row.get("flow_signal") or "STALE")
        src = str(row.get("source") or "")
        if sig == "STALE" or src in {"template", "missing", ""}:
            stale_signals += 1
            if src in {"template", "missing", ""} or int(row.get("staleness_days") or 0) >= 3:
                failed.append(tk)
        else:
            fresh += 1
    n = len(target_tickers)
    return {
        "flow_coverage_pct": round(100.0 * fresh / n, 1),
        "stale_count": stale_signals,
        "stale_signal_count": stale_signals,
        "fresh_count": fresh,
        "target_count": n,
        "failed_tickers": failed,
    }


def format_flow_coverage_report_lines(meta: dict[str, Any]) -> list[str]:
    lines = [
        "## Investor Flow Refresh",
        "",
        f"- **target_count**: {meta.get('target_count', 0)}",
        f"- **refreshed_count**: {meta.get('refreshed_count', 0)}",
        f"- **flow_coverage_pct**: {meta.get('flow_coverage_pct', '—')}%",
        f"- **stale_signal_count**: {meta.get('stale_signal_count', 0)}",
        f"- **skipped_manual_verified**: {meta.get('skipped_manual_count', 0)}",
        f"- **flow_unit**: {meta.get('flow_unit', 'KRW_net_trading_value')}",
        f"- **flow_source**: {meta.get('flow_source', 'auto_pykrx')}",
    ]
    failed = meta.get("failed_tickers") or []
    if failed:
        lines.append(f"- **failed_tickers**: {', '.join(failed)}")
    warns = meta.get("warnings") or []
    for w in warns:
        lines.append(f"- **WARN**: {w}")
    lines.append("")
    lines.append(
        "> Flow는 Buy-ready 보조 신호입니다. `flow_signal`만으로 Buy-allowed가 되지 않습니다."
    )
    lines.append("")
    return lines


def _cache_path(data_dir: Path, ticker: str) -> Path:
    return data_dir / "cache" / "flow_refresh" / f"{ticker}.json"


def _read_cache(
    data_dir: Path,
    ticker: str,
    as_of: str,
    *,
    max_age_days: int = 3,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return (row, status) where status is cache_hit | cache_too_old | None."""
    path = _cache_path(data_dir, ticker)
    if not path.exists():
        return None, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, None
    cached_as_of = str(payload.get("as_of") or "")[:10]
    if not cached_as_of:
        return None, None
    age = _business_days_between(cached_as_of, as_of[:10])
    if age > max_age_days:
        return None, "cache_too_old"
    row = payload.get("row")
    if not isinstance(row, dict):
        return None, None
    out = dict(row)
    out["staleness_days"] = age
    if age > 0:
        out["source"] = "cache_stale"
        sig = classify_flow_signal(
            foreign_5d_mcap_pct=_float_or_none(out.get("foreign_5d_mcap_pct")),
            foreign_20d_mcap_pct=_float_or_none(out.get("foreign_20d_mcap_pct")),
            institution_5d_mcap_pct=_float_or_none(out.get("institution_5d_mcap_pct")),
            institution_20d_mcap_pct=_float_or_none(out.get("institution_20d_mcap_pct")),
            staleness_days=age,
        )
        out["flow_signal"] = sig
        out["flow_score"] = flow_score_from_signal(sig)
    return out, "cache_hit"


def _float_or_none(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _write_cache(data_dir: Path, ticker: str, as_of: str, row: dict[str, Any]) -> None:
    path = _cache_path(data_dir, ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"as_of": as_of[:10], "row": row}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_mcap_by_ticker(data_dir: Path) -> dict[str, float]:
    path = data_dir / "prices.csv"
    if not path.exists():
        return {}
    try:
        import pandas as pd

        px = pd.read_csv(path, dtype=str)
    except Exception:
        return {}
    if px.empty or "market_cap" not in px.columns:
        return {}
    out: dict[str, float] = {}
    latest = px.sort_values("date").groupby("ticker").tail(1)
    for _, r in latest.iterrows():
        try:
            out[str(r["ticker"]).zfill(6)] = float(r["market_cap"])
        except (TypeError, ValueError):
            pass
    return out


def _business_days_between(start_iso: str, end_iso: str) -> int:
    try:
        start = datetime.strptime(start_iso[:10], "%Y-%m-%d")
        end = datetime.strptime(end_iso[:10], "%Y-%m-%d")
    except ValueError:
        return 999
    if end < start:
        return 0
    days = 0
    cur = start
    while cur < end:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            days += 1
    return days


def _last_row_date(df: Any, as_of: str) -> str:
    try:
        if hasattr(df.index, "max"):
            idx = df.index.max()
            text = str(idx)
            if len(text) >= 8 and text[:8].isdigit():
                c = text.replace("-", "")[:8]
                return f"{c[:4]}-{c[4:6]}-{c[6:8]}"
    except Exception:
        pass
    return as_of[:10]


def _find_flow_columns(df: Any) -> tuple[Any | None, Any | None, Any | None, Any | None]:
    foreign_col = institution_col = retail_col = program_col = None
    for col in df.columns:
        c = str(col)
        if "외국인" in c:
            foreign_col = col
        elif "기관" in c:
            institution_col = col
        elif "개인" in c:
            retail_col = col
        elif "프로그램" in c:
            program_col = col
    return foreign_col, institution_col, retail_col, program_col


def _extract_investor_nets(df: Any) -> tuple[float, float, float, float]:
    """Extract period net trading values (KRW) for foreign/institution/retail/program."""
    foreign = institution = retail = program = 0.0
    if df is None or getattr(df, "empty", True):
        return foreign, institution, retail, program
    for idx, row in df.iterrows():
        label = str(idx)
        try:
            if "순매수" in row.index:
                net = float(row["순매수"])
            else:
                net = float(row.iloc[-1])
        except (TypeError, ValueError, IndexError):
            continue
        if "외국인" in label:
            if "기타" in label:
                program = net
            else:
                foreign = net
        elif "기관" in label:
            institution = net
        elif "개인" in label:
            retail = net
    return foreign, institution, retail, program


def _build_flow_row_from_period_nets(
    *,
    ticker: str,
    name: str,
    as_of: str,
    mcap: float,
    foreign_5d: float,
    institution_5d: float,
    foreign_20d: float,
    institution_20d: float,
    foreign_daily: float,
    institution_daily: float,
    retail_daily: float,
    program_daily: float,
    staleness_days: int = 0,
    source: str = "auto_pykrx",
) -> dict[str, Any]:
    f5_pct = (foreign_5d / mcap * 100) if mcap > 0 else None
    f20_pct = (foreign_20d / mcap * 100) if mcap > 0 else None
    i5_pct = (institution_5d / mcap * 100) if mcap > 0 else None
    i20_pct = (institution_20d / mcap * 100) if mcap > 0 else None
    signal = classify_flow_signal(
        foreign_5d_mcap_pct=f5_pct,
        foreign_20d_mcap_pct=f20_pct,
        institution_5d_mcap_pct=i5_pct,
        institution_20d_mcap_pct=i20_pct,
        staleness_days=staleness_days,
    )
    return {
        "date": as_of[:10],
        "ticker": ticker,
        "name": name,
        "foreign_net_value": foreign_daily,
        "institution_net_value": institution_daily,
        "retail_net_value": retail_daily,
        "program_net_value": program_daily,
        "foreign_5d_sum": foreign_5d,
        "institution_5d_sum": institution_5d,
        "foreign_20d_sum": foreign_20d,
        "institution_20d_sum": institution_20d,
        "foreign_5d_mcap_pct": f5_pct if f5_pct is not None else "",
        "institution_5d_mcap_pct": i5_pct if i5_pct is not None else "",
        "foreign_20d_mcap_pct": f20_pct if f20_pct is not None else "",
        "institution_20d_mcap_pct": i20_pct if i20_pct is not None else "",
        "flow_score": flow_score_from_signal(signal),
        "flow_signal": signal,
        "source": source,
        "staleness_days": staleness_days,
    }


def _fetch_flow_row_pykrx(
    stock: Any,
    ticker: str,
    name: str,
    as_of: str,
    mcap: float,
) -> dict[str, Any] | None:
    """Use get_market_trading_value_by_investor — net trading value in KRW (원)."""
    from src.data_refresh.pykrx_client import lookback_start, to_compact_date

    end_c = to_compact_date(as_of)
    start_5 = to_compact_date(lookback_start(as_of, 12))
    start_20 = to_compact_date(lookback_start(as_of, 40))

    df20 = stock.get_market_trading_value_by_investor(start_20, end_c, ticker)
    df5 = stock.get_market_trading_value_by_investor(start_5, end_c, ticker)
    df1 = stock.get_market_trading_value_by_investor(end_c, end_c, ticker)
    if df20 is None or getattr(df20, "empty", True):
        return None

    f20, i20, _, _ = _extract_investor_nets(df20)
    f5, i5, _, _ = _extract_investor_nets(df5)
    fd, id_, rd, pd_ = _extract_investor_nets(df1)

    return _build_flow_row_from_period_nets(
        ticker=ticker,
        name=name,
        as_of=as_of,
        mcap=mcap,
        foreign_5d=f5,
        institution_5d=i5,
        foreign_20d=f20,
        institution_20d=i20,
        foreign_daily=fd,
        institution_daily=id_,
        retail_daily=rd,
        program_daily=pd_,
        staleness_days=0,
        source="auto_pykrx",
    )


def _build_flow_row_from_df(
    *,
    df: Any,
    ticker: str,
    name: str,
    as_of: str,
    mcap: float,
    source: str = "auto_pykrx",
) -> dict[str, Any]:
    foreign_col, institution_col, retail_col, program_col = _find_flow_columns(df)
    if foreign_col is None:
        raise ValueError("foreign column missing")

    foreign_vals = [float(x) for x in df[foreign_col].astype(float).tolist()]
    inst_vals = (
        [float(x) for x in df[institution_col].astype(float).tolist()]
        if institution_col is not None
        else [0.0] * len(foreign_vals)
    )
    retail_vals = (
        [float(x) for x in df[retail_col].astype(float).tolist()]
        if retail_col is not None
        else []
    )
    program_vals = (
        [float(x) for x in df[program_col].astype(float).tolist()]
        if program_col is not None
        else []
    )

    f5 = sum(foreign_vals[-5:]) if foreign_vals else 0.0
    i5 = sum(inst_vals[-5:]) if inst_vals else 0.0
    f20 = sum(foreign_vals[-20:]) if foreign_vals else 0.0
    i20 = sum(inst_vals[-20:]) if inst_vals else 0.0

    f5_pct = (f5 / mcap * 100) if mcap > 0 else None
    f20_pct = (f20 / mcap * 100) if mcap > 0 else None
    i5_pct = (i5 / mcap * 100) if mcap > 0 else None
    i20_pct = (i20 / mcap * 100) if mcap > 0 else None

    last_date = _last_row_date(df, as_of)
    staleness = _business_days_between(last_date, as_of[:10])
    signal = classify_flow_signal(
        foreign_5d_mcap_pct=f5_pct,
        foreign_20d_mcap_pct=f20_pct,
        institution_5d_mcap_pct=i5_pct,
        institution_20d_mcap_pct=i20_pct,
        staleness_days=staleness,
    )

    return {
        "date": as_of[:10],
        "ticker": ticker,
        "name": name,
        "foreign_net_value": foreign_vals[-1] if foreign_vals else "",
        "institution_net_value": inst_vals[-1] if inst_vals else "",
        "retail_net_value": retail_vals[-1] if retail_vals else "",
        "program_net_value": program_vals[-1] if program_vals else "",
        "foreign_5d_sum": f5,
        "institution_5d_sum": i5,
        "foreign_20d_sum": f20,
        "institution_20d_sum": i20,
        "foreign_5d_mcap_pct": f5_pct if f5_pct is not None else "",
        "institution_5d_mcap_pct": i5_pct if i5_pct is not None else "",
        "foreign_20d_mcap_pct": f20_pct if f20_pct is not None else "",
        "institution_20d_mcap_pct": i20_pct if i20_pct is not None else "",
        "flow_score": flow_score_from_signal(signal),
        "flow_signal": signal,
        "source": source,
        "staleness_days": staleness,
    }


def _stale_row(
    ticker: str,
    name: str,
    as_of: str,
    *,
    existing: dict[str, Any] | None = None,
    preserve_existing: bool = False,
) -> dict[str, Any]:
    if preserve_existing and existing:
        return dict(existing)
    base = dict(existing or {})
    return {
        "date": as_of[:10],
        "ticker": ticker,
        "name": name or base.get("name", ""),
        "foreign_net_value": base.get("foreign_net_value", ""),
        "institution_net_value": base.get("institution_net_value", ""),
        "retail_net_value": base.get("retail_net_value", ""),
        "program_net_value": base.get("program_net_value", ""),
        "foreign_5d_sum": base.get("foreign_5d_sum", ""),
        "institution_5d_sum": base.get("institution_5d_sum", ""),
        "foreign_20d_sum": base.get("foreign_20d_sum", ""),
        "institution_20d_sum": base.get("institution_20d_sum", ""),
        "foreign_5d_mcap_pct": base.get("foreign_5d_mcap_pct", ""),
        "institution_5d_mcap_pct": base.get("institution_5d_mcap_pct", ""),
        "foreign_20d_mcap_pct": base.get("foreign_20d_mcap_pct", ""),
        "institution_20d_mcap_pct": base.get("institution_20d_mcap_pct", ""),
        "flow_score": 0.0,
        "flow_signal": "STALE",
        "source": str(base.get("source") or "auto_pykrx"),
        "staleness_days": max(int(base.get("staleness_days") or 0), 3),
    }


def _write_investor_flows(path: Path, rows: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FLOW_COLUMNS)
        writer.writeheader()
        for tk in sorted(rows):
            writer.writerow({k: rows[tk].get(k, "") for k in FLOW_COLUMNS})


def refresh_investor_flows(
    data_dir: Path,
    tickers: list[dict[str, str]],
    *,
    as_of: str,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    sleep_sec: float = DEFAULT_SLEEP_SEC,
    use_cache: bool = True,
    fetch_fn: Callable[[str, str, str], Any] | None = None,
) -> FlowRefreshResult:
    """Refresh flow rows for target tickers only; preserve manual_verified and non-target rows."""
    as_of = as_of[:10]
    existing = load_investor_flows(data_dir)
    out_rows: dict[str, dict[str, Any]] = dict(existing)
    target_set = {str(t["ticker"]).zfill(6) for t in tickers if t.get("ticker")}
    mcap_by_ticker = _load_mcap_by_ticker(data_dir)

    stock = None
    start_c = end_c = ""
    if fetch_fn is None:
        try:
            from src.data_refresh.pykrx_client import import_pykrx_stock, lookback_start, to_compact_date

            stock = import_pykrx_stock(data_dir)
            start_c = to_compact_date(lookback_start(as_of, lookback_days + 10))
            end_c = to_compact_date(as_of)
        except Exception:
            stock = None

    refreshed = 0
    stale = 0
    skipped_manual = 0
    failed: list[str] = []
    cache_hits = 0
    cache_misses = 0
    pykrx_calls = 0
    reason_list: list[str] = []
    last_success_ts = ""

    from src.alpha_v2_gate import classify_stale_reason, summarize_stale_reasons

    for item in tickers:
        tk = str(item.get("ticker", "")).zfill(6)
        name = str(item.get("name") or "")
        if not tk:
            continue

        prev = out_rows.get(tk)
        if is_manual_verified(prev):
            skipped_manual += 1
            reason_list.append("fresh")
            continue

        row: dict[str, Any] | None = None
        parse_error = False
        pykrx_failed = False

        if use_cache:
            cached, cache_status = _read_cache(data_dir, tk, as_of, max_age_days=3)
            if cached and not is_flow_record_stale(cached):
                out_rows[tk] = cached
                refreshed += 1
                cache_hits += 1
                reason_list.append(classify_stale_reason(cached))
                last_success_ts = format_flow_refresh_timestamp()
                continue
            if cache_status == "cache_too_old":
                reason_list.append("cache_too_old")
            cache_misses += 1
        else:
            cache_misses += 1

        try:
            if fetch_fn is not None:
                df = fetch_fn(tk, start_c or "20260101", end_c or as_of.replace("-", ""))
                if df is not None and not getattr(df, "empty", True):
                    mcap = mcap_by_ticker.get(tk) or 0.0
                    row = _build_flow_row_from_df(
                        df=df,
                        ticker=tk,
                        name=name,
                        as_of=as_of,
                        mcap=mcap,
                    )
            elif stock is not None:
                pykrx_calls += 1
                mcap = mcap_by_ticker.get(tk) or 0.0
                row = _fetch_flow_row_pykrx(stock, tk, name, as_of, mcap)
                if row is None:
                    pykrx_calls += 1
                    df = stock.get_market_net_purchases_of_equities_by_ticker(start_c, end_c, tk)
                    if df is not None and not getattr(df, "empty", True):
                        row = _build_flow_row_from_df(
                            df=df,
                            ticker=tk,
                            name=name,
                            as_of=as_of,
                            mcap=mcap,
                        )
        except Exception:
            row = None
            parse_error = True

        if row is None:
            pykrx_failed = True
            cached_fallback, _ = _read_cache(data_dir, tk, as_of, max_age_days=999)
            preserve = bool(
                prev
                and str(prev.get("source") or "") not in {"template", "missing", ""}
                and not is_manual_verified(prev)
                and str(prev.get("flow_signal") or "") != "STALE"
            )
            if cached_fallback and not is_flow_record_stale(cached_fallback):
                out_rows[tk] = cached_fallback
                refreshed += 1
                reason_list.append(classify_stale_reason(cached_fallback, pykrx_failed=True))
            else:
                out_rows[tk] = _stale_row(tk, name, as_of, existing=prev, preserve_existing=preserve)
                stale += 1
                failed.append(tk)
                reason_list.append(
                    classify_stale_reason(
                        out_rows[tk],
                        ticker=tk,
                        pykrx_failed=True,
                        parse_error=parse_error,
                    )
                )
        else:
            out_rows[tk] = row
            refreshed += 1
            last_success_ts = format_flow_refresh_timestamp()
            reason_list.append(classify_stale_reason(row))
            if use_cache:
                _write_cache(data_dir, tk, as_of, row)

        if sleep_sec > 0 and fetch_fn is None and stock is not None:
            time.sleep(sleep_sec)

    path = data_dir / "investor_flows.csv"
    _write_investor_flows(path, out_rows)

    quality = compute_flow_quality_metrics(out_rows, target_set)
    stale_summary = summarize_stale_reasons(reason_list)
    warnings: list[str] = []
    if quality["flow_coverage_pct"] < FLOW_COVERAGE_WARN_PCT:
        warnings.append(
            f"flow_coverage_pct {quality['flow_coverage_pct']}% < {FLOW_COVERAGE_WARN_PCT}%"
        )
    if failed:
        warnings.append(f"pykrx_failed_tickers: {len(failed)}")

    return FlowRefreshResult(
        as_of=as_of,
        target_count=len(target_set),
        refreshed_count=refreshed,
        stale_count=stale,
        skipped_manual_count=skipped_manual,
        failed_tickers=failed,
        flow_coverage_pct=float(quality["flow_coverage_pct"]),
        stale_signal_count=int(quality["stale_signal_count"]),
        path=str(path),
        warnings=warnings,
        cache_hit_count=cache_hits,
        cache_miss_count=cache_misses,
        pykrx_call_count=pykrx_calls,
        stale_reason_summary=stale_summary,
        last_successful_flow_refresh=last_success_ts or format_flow_refresh_timestamp(),
        coverage_scope="watched_universe",
    )


def run_flow_refresh(
    data_dir: Path,
    output_dir: Path | None = None,
    *,
    as_of: str,
    holdings: list[Any] | None = None,
    candidates: list[Any] | None = None,
    tickers: list[dict[str, str]] | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    sleep_sec: float = DEFAULT_SLEEP_SEC,
    fetch_fn: Callable[[str, str, str], Any] | None = None,
    use_cache: bool = True,
) -> FlowRefreshResult:
    """Entry point: resolve board-equivalent tickers and refresh flows."""
    output_dir = output_dir or data_dir.parent / "outputs"
    signal_board_path = output_dir / "alpha_signal_board.csv"
    targets = tickers or resolve_flow_target_tickers(
        holdings=holdings,
        candidates=candidates,
        signal_board_path=signal_board_path,
        data_dir=data_dir,
        output_dir=output_dir,
    )
    return refresh_investor_flows(
        data_dir,
        targets,
        as_of=as_of,
        lookback_days=lookback_days,
        sleep_sec=sleep_sec,
        fetch_fn=fetch_fn,
        use_cache=use_cache,
    )
