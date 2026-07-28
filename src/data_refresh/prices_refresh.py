from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.csv_utils import read_csv_optional
from src.data_refresh.price_store import PRICE_COLUMNS, merge_prices_dataframes


@dataclass
class PricesRefreshResult:
    as_of: str
    row_count: int
    source: str
    warnings: list[str] = field(default_factory=list)
    path: Path | None = None


def _normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip()
    return t.zfill(6) if t.isdigit() else t


def validate_prices(path: Path) -> list[str]:
    if not path.exists():
        return [f"파일 없음: {path}"]
    df = read_csv_optional(path, dtype=str, keep_default_na=False)
    if df is None:
        return ["prices.csv 비어 있음"]
    issues: list[str] = []
    missing = [c for c in PRICE_COLUMNS if c not in df.columns]
    if missing:
        issues.append(f"컬럼 누락: {', '.join(missing)}")
    if df.empty:
        issues.append("prices.csv 비어 있음")
    return issues


@dataclass
class TierAPricesResult:
    as_of: str
    required_count: int
    missing_before: int
    added: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def merge_prices_dataframes(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Re-export — see price_store."""
    from src.data_refresh.price_store import merge_prices_dataframes as _merge

    return _merge(existing, new)


def _load_alpha_top_tickers(output_dir: Path | None, *, top_n: int) -> list[str]:
    if output_dir is None or top_n <= 0:
        return []
    for name in ("alpha_shortlist.csv", "alpha_candidates.csv"):
        path = output_dir / name
        df = read_csv_optional(path, dtype=str, keep_default_na=False)
        if df is None or df.empty or "ticker" not in df.columns:
            continue
        out: list[str] = []
        for raw in df["ticker"].head(top_n):
            t = _normalize_ticker(str(raw))
            if t and t != "CASH":
                out.append(t)
        if out:
            return out
    return []


def _load_trade_action_tickers(output_dir: Path | None) -> set[str]:
    if output_dir is None:
        return set()
    path = output_dir / "trade_actions.csv"
    df = read_csv_optional(path, dtype=str, keep_default_na=False)
    if df is None:
        return set()
    tickers: set[str] = set()
    for raw in df.get("ticker", []):
        t = _normalize_ticker(str(raw))
        if t and t not in {"CASH", "PORTFOLIO"}:
            tickers.add(t)
    return tickers


def collect_tier_a_tickers(
    data_dir: Path,
    output_dir: Path | None = None,
    *,
    top_n: int = 50,
    extra: set[str] | None = None,
) -> set[str]:
    """Tier A — 보유·target·trade_actions·Alpha 상위 후보."""
    from src.data_loader import load_positions, load_target_portfolio

    tickers: set[str] = set()
    tickers |= _load_trade_action_tickers(output_dir)
    tickers.update(_load_alpha_top_tickers(output_dir, top_n=top_n))
    if extra:
        tickers |= {_normalize_ticker(t) for t in extra}

    for path, loader, weight_attr in (
        (data_dir / "positions.csv", load_positions, None),
        (data_dir / "target_portfolio.csv", load_target_portfolio, "target_weight"),
    ):
        if not path.exists():
            continue
        for row in loader(path):
            t = _normalize_ticker(row.ticker)
            if not t or t == "CASH":
                continue
            if weight_attr == "target_weight" and float(getattr(row, weight_attr, 0) or 0) <= 0:
                continue
            tickers.add(t)
    return tickers


def tickers_for_fundamental_prefetch(
    usable_fund: dict[str, Any],
    prices_by_ticker: dict[str, Any],
    *,
    limit: int = 50,
    data_dir: Path | None = None,
    output_dir: Path | None = None,
) -> list[str]:
    """재무 통과·시세 없음 — ROE/Value/earnings_momentum proxy 다각 prefetch."""
    missing = [t for t in usable_fund if t not in prices_by_ticker]
    if not missing:
        return []

    per_bucket = max(10, limit // 3)

    def _fund(t: str) -> Any:
        return usable_fund[t]

    roe_rank = sorted(missing, key=lambda t: (-float(getattr(_fund(t), "roe", 0) or 0), t))
    value_rank = sorted(
        missing,
        key=lambda t: (
            float(getattr(_fund(t), "per", 999) or 999),
            float(getattr(_fund(t), "pbr", 999) or 999),
            t,
        ),
    )
    earnings_momentum_rank = sorted(
        missing,
        key=lambda t: (-float(getattr(_fund(t), "earnings_yoy", 0) or 0), t),
    )

    ordered: list[str] = []
    for bucket in (
        roe_rank[:per_bucket],
        value_rank[:per_bucket],
        earnings_momentum_rank[:per_bucket],
    ):
        ordered.extend(bucket)

    if data_dir is not None:
        ordered.extend(
            t for t in sorted(collect_tier_a_tickers(data_dir, output_dir, top_n=0))
            if t in missing
        )
    if output_dir is not None:
        prev = _load_alpha_top_tickers(output_dir, top_n=50)
        ordered.extend(t for t in prev if t in missing)

    seen: set[str] = set()
    out: list[str] = []
    for t in ordered:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= limit:
            break
    return out


def fetch_and_merge_prices(
    data_dir: Path,
    tickers: list[str] | set[str],
    as_of: str,
    *,
    output_dir: Path | None = None,
    only_missing: bool = True,
) -> tuple[list[str], list[str]]:
    """PyKRX on-demand fetch → prices.csv merge.

    only_missing=True: prices.csv에 없는 ticker만 (legacy).
    only_missing=False: Tier A 등 운용 필수 ticker **기존 row도 최신 as_of로 재수집**.
    """
    import time

    from src.data_refresh.price_fetch_log import PriceFetchLogEntry, write_price_fetch_outputs

    prices_path = data_dir / "prices.csv"
    normalized = sorted({_normalize_ticker(t) for t in tickers if str(t).strip()})
    if not normalized:
        return [], []

    if prices_path.exists():
        existing = set(
            _normalize_ticker(t)
            for t in pd.read_csv(prices_path, dtype=str, keep_default_na=False)["ticker"]
        )
    else:
        existing = set()

    if only_missing:
        to_fetch = [t for t in normalized if t not in existing]
        skipped = sorted(t for t in normalized if t in existing)
    else:
        to_fetch = list(normalized)
        skipped = []

    if not to_fetch:
        return [], []

    started = time.perf_counter()
    warnings: list[str] = []
    reason = ""
    try:
        from src.data_refresh.pykrx_client import import_pykrx_stock, resolve_trading_date
        from src.data_refresh.pykrx_bulk import fetch_prices_for_tickers

        stock = import_pykrx_stock(data_dir)
        as_of_date = resolve_trading_date(stock, as_of)
        fetched = fetch_prices_for_tickers(stock, to_fetch, as_of_date)
        if fetched.empty:
            reason = "empty_response"
            log = PriceFetchLogEntry(
                as_of=as_of,
                requested_tickers=to_fetch,
                failed_tickers=to_fetch,
                skipped_tickers=skipped,
                elapsed_seconds=round(time.perf_counter() - started, 3),
                source="pykrx",
                reason=reason,
            )
            write_price_fetch_outputs(output_dir, log)
            return [], [f"시세 fetch 실패: {', '.join(to_fetch[:10])}"]
    except Exception as exc:
        reason = str(exc)
        log = PriceFetchLogEntry(
            as_of=as_of,
            requested_tickers=to_fetch,
            failed_tickers=to_fetch,
            skipped_tickers=skipped,
            elapsed_seconds=round(time.perf_counter() - started, 3),
            source="pykrx",
            reason=reason,
        )
        write_price_fetch_outputs(output_dir, log)
        return [], [f"시세 fetch 불가: {exc}"]

    fetched["ticker"] = fetched["ticker"].map(_normalize_ticker)
    got = set(fetched["ticker"].astype(str))
    failed = [t for t in to_fetch if t not in got]

    if prices_path.exists():
        old = pd.read_csv(prices_path, dtype=str, keep_default_na=False)
        merged = merge_prices_dataframes(old, fetched.astype(str))
    else:
        merged = fetched.astype(str)
    merged.to_csv(prices_path, index=False, encoding="utf-8-sig")

    log = PriceFetchLogEntry(
        as_of=as_of,
        requested_tickers=to_fetch,
        success_tickers=sorted(got),
        failed_tickers=failed,
        skipped_tickers=skipped,
        elapsed_seconds=round(time.perf_counter() - started, 3),
        source="pykrx",
        reason="partial_failure" if failed else ("refresh" if not only_missing else ""),
    )
    write_price_fetch_outputs(output_dir, log)
    return sorted(got), warnings + ([f"시세 fetch 실패: {', '.join(failed)}"] if failed else [])


def fetch_and_merge_missing_prices(
    data_dir: Path,
    tickers: list[str] | set[str],
    as_of: str,
    *,
    output_dir: Path | None = None,
) -> tuple[list[str], list[str]]:
    """PyKRX on-demand fetch → prices.csv merge (missing ticker only)."""
    return fetch_and_merge_prices(
        data_dir, tickers, as_of, output_dir=output_dir, only_missing=True,
    )


def ensure_tier_a_prices(
    data_dir: Path,
    as_of: str,
    *,
    output_dir: Path | None = None,
    top_n: int = 50,
    extra_tickers: set[str] | None = None,
    prefetch_fundamental: bool = False,
    usable_fund: dict[str, Any] | None = None,
    prices_by_ticker: dict[str, Any] | None = None,
    fetch_missing: bool = True,
    refresh_existing: bool = False,
) -> TierAPricesResult:
    """Tier A — 운용 필수 ticker 시세 100% + freshness 목표.

    refresh_existing=True: 보유·target 등 Tier A 전 종목 PyKRX 재수집 (stale 해소).
    """
    required = collect_tier_a_tickers(data_dir, output_dir, top_n=top_n, extra=extra_tickers)
    if prefetch_fundamental and usable_fund is not None and prices_by_ticker is not None:
        required |= set(
            tickers_for_fundamental_prefetch(
                usable_fund,
                prices_by_ticker,
                limit=top_n,
                data_dir=data_dir,
                output_dir=output_dir,
            )
        )

    prices_path = data_dir / "prices.csv"
    if prices_path.exists():
        have = {
            _normalize_ticker(t)
            for t in pd.read_csv(prices_path, dtype=str, keep_default_na=False)["ticker"]
        }
    else:
        have = set()

    missing_before = len(required - have)
    if not fetch_missing and not refresh_existing:
        return TierAPricesResult(
            as_of=as_of,
            required_count=len(required),
            missing_before=missing_before,
            failed=sorted(required - have),
        )

    added, warnings = fetch_and_merge_prices(
        data_dir,
        sorted(required),
        as_of,
        output_dir=output_dir,
        only_missing=not refresh_existing,
    )
    failed = sorted(required - have - set(added)) if not refresh_existing else sorted(required - set(added))
    return TierAPricesResult(
        as_of=as_of,
        required_count=len(required),
        missing_before=missing_before,
        added=added,
        failed=failed,
        warnings=warnings,
    )


def _required_kr_tickers(data_dir: Path) -> set[str]:
    """운용 필수 kr_alpha 시세 — 목표·보유 종목."""
    from src.data_loader import load_positions, load_target_portfolio

    tickers: set[str] = set()
    for path, loader in (
        (data_dir / "positions.csv", load_positions),
        (data_dir / "target_portfolio.csv", load_target_portfolio),
    ):
        if not path.exists():
            continue
        for row in loader(path):
            if getattr(row, "asset_group", "") != "kr_alpha":
                continue
            t = _normalize_ticker(row.ticker)
            if t and t != "CASH":
                tickers.add(t)
    return tickers


def ensure_required_price_tickers(data_dir: Path, as_of: str) -> tuple[list[str], list[str]]:
    """positions·target kr_alpha 중 prices.csv에 없는 종목 PyKRX로 추가 (merge)."""
    result = ensure_tier_a_prices(data_dir, as_of, top_n=0)
    return result.added, result.warnings


def refresh_prices_snapshot(data_dir: Path, as_of: str | None = None) -> PricesRefreshResult:
    """Tier A 운용 필수 시세 PyKRX 재수집 + prices.csv merge."""
    prices_path = data_dir / "prices.csv"
    warnings = validate_prices(prices_path)
    as_of_date = as_of or date.today().isoformat()

    tier = ensure_tier_a_prices(
        data_dir,
        as_of_date,
        top_n=50,
        refresh_existing=True,
    )
    from src.data_refresh.tier_h import ensure_tier_h_prices

    tier_h = ensure_tier_h_prices(data_dir, as_of_date, fetch_missing=True)
    warnings.extend(tier_h.warnings)
    if tier_h.failed:
        warnings.append(f"Tier H 시세 실패: {', '.join(tier_h.failed[:10])}")
    warnings.extend(tier.warnings)
    if tier.failed:
        warnings.append(f"Tier A 시세 실패: {', '.join(tier.failed[:10])}")
    source = "pykrx_tier_a" if tier.added else "unchanged"
    row_count = 0
    if prices_path.exists():
        row_count = len(pd.read_csv(prices_path, dtype=str, keep_default_na=False))
    return PricesRefreshResult(
        as_of=as_of_date,
        row_count=row_count,
        source=source,
        warnings=warnings,
        path=prices_path if prices_path.exists() else None,
    )


def _try_pykrx_fetch(df: pd.DataFrame, as_of: str) -> pd.DataFrame | None:
    try:
        from pykrx import stock  # type: ignore[import-untyped]
    except ImportError:
        return None

    as_of_compact = as_of.replace("-", "")
    rows: list[dict] = []
    for _, row in df.iterrows():
        ticker = _normalize_ticker(row["ticker"])
        if not ticker.isdigit():
            continue
        try:
            end = as_of_compact
            ohlcv = stock.get_market_ohlcv_by_date(end, end, ticker)
            if ohlcv.empty:
                updated = dict(row)
                updated["date"] = as_of
                rows.append(updated)
                continue
            close = float(ohlcv.iloc[-1]["종가"])
            cap_df = stock.get_market_cap_by_date(end, end, ticker)
            mcap = float(cap_df.iloc[-1]["시가총액"]) if not cap_df.empty else float(row.get("market_cap", 0) or 0)
            updated = dict(row)
            updated["date"] = as_of
            updated["close"] = str(int(close))
            updated["market_cap"] = str(int(mcap))
            rows.append(updated)
        except Exception:
            updated = dict(row)
            updated["date"] = as_of
            rows.append(updated)

    if not rows:
        return None
    return pd.DataFrame(rows)


def append_prices_history(data_dir: Path, history_file: str = "prices_history.csv") -> Path | None:
    """현재 prices.csv 스냅샷을 history에 append (동일 date 중복 제거)."""
    from src.data_refresh.price_store import atomic_write_csv

    prices_path = data_dir / "prices.csv"
    if not prices_path.exists():
        return None
    current = pd.read_csv(prices_path, dtype=str, keep_default_na=False)
    history_path = data_dir / history_file
    baseline_rows = 0
    if history_path.exists():
        history = pd.read_csv(history_path, dtype=str, keep_default_na=False)
        baseline_rows = len(history)
        history = history[history["date"] != current["date"].iloc[0]]
        merged = pd.concat([history, current], ignore_index=True)
    else:
        merged = current
    merged = merged.sort_values(["date", "ticker"])
    # Never shrink history below prior count when replacing same-date rows would
    # only drop the prior as_of slice — still require non-empty write.
    atomic_write_csv(
        history_path,
        merged,
        encoding="utf-8-sig",
        min_rows=max(1, min(baseline_rows, len(merged))),
    )
    return history_path
