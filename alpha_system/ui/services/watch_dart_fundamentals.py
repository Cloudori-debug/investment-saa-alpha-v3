"""OpenDART financials for the observation pool only — never the full KOSPI.

KRX ranks the liquid universe. DART fills OPM / debt / earnings for the
watch board (30 KOSPI / 10 KOSDAQ) then those names are rescored.
Names that enter the pool after that rescore get one extra DART round (still ≤ N).
HTML viewers are not used. target_portfolio.csv is not written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from alpha_system.screen_book import watch_max
from alpha_system.ui.services.cecs_opendart_pack import _hyslr_owner_pct, _repo_src_on_top

FetchOne = Callable[[str, str], Mapping[str, Any] | None]


@dataclass
class WatchDartResult:
    requested: int = 0
    filled: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    hakedaka: dict[str, dict[str, Any]] = field(default_factory=dict)


def watch_depth_tickers(
    scores: pd.DataFrame,
    *,
    market: str = "KOSPI",
    depth: int | None = None,
) -> list[str]:
    """Top N gate-pass names by composite (KRX first pass)."""
    n = int(depth) if depth is not None else int(watch_max(market))
    if scores is None or scores.empty or "ticker" not in scores.columns:
        return []
    work = scores.copy()
    work["ticker"] = work["ticker"].astype(str).map(
        lambda t: t.zfill(6) if str(t).isdigit() else str(t)
    )
    if "gate_pass" in work.columns:
        gp = work["gate_pass"].astype(str).str.lower().str.strip()
        work = work[gp.isin({"true", "1", "1.0", "yes"}) | (work["gate_pass"] == True)]  # noqa: E712
    score_col = "composite_score" if "composite_score" in work.columns else "composite_raw"
    if score_col not in work.columns:
        return list(work["ticker"].head(n))
    work[score_col] = pd.to_numeric(work[score_col], errors="coerce")
    work = work.dropna(subset=[score_col]).sort_values(
        [score_col, "ticker"], ascending=[False, True]
    )
    return [str(t) for t in work["ticker"].head(n).tolist()]


def watch_round_tickers(
    scores: pd.DataFrame,
    *,
    already: set[str] | None = None,
    market: str = "KOSPI",
    depth: int | None = None,
) -> list[str]:
    """Names now in the watch pool that have not been DART-filled this run."""
    have = {str(t).zfill(6) if str(t).isdigit() else str(t) for t in (already or set())}
    top = watch_depth_tickers(scores, market=market, depth=depth)
    return [t for t in top if t not in have]


def _as_float(val: Any) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    text = str(val).strip()
    if not text or text.lower() in {"nan", "none", ""}:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def merge_watch_dart_row(row: pd.Series, payload: Mapping[str, Any]) -> pd.Series:
    """Fill quality fields from an OpenDART metrics payload. Keep KRX PER/PBR."""
    out = row.copy()
    opm = payload.get("opm", payload.get("operating_margin"))
    debt = payload.get("debt_ratio")
    roe = payload.get("roe")
    y1 = payload.get("net_income_y1", payload.get("net_income"))
    y2 = payload.get("net_income_y2", payload.get("net_income_prior"))
    if _as_float(opm) is not None:
        out["opm"] = _as_float(opm)
    if _as_float(debt) is not None:
        out["debt_ratio"] = _as_float(debt)
    if _as_float(roe) is not None:
        out["roe"] = _as_float(roe)
    if _as_float(y1) is not None:
        out["net_income_y1"] = _as_float(y1)
    if _as_float(y2) is not None:
        out["net_income_y2"] = _as_float(y2)
    src = str(out.get("source") or "").strip().lower()
    y3 = payload.get("roe_3y_avg")
    if _as_float(y3) is not None:
        out["roe_3y_avg"] = _as_float(y3)
    elif src in {"", "liquid_stub", "liquid_template", "opendart_watch"}:
        # Single-year DART must not keep the liquid_stub dummy 3y=10.
        out["roe_3y_avg"] = pd.NA
    if src in {"", "liquid_stub", "liquid_template"}:
        out["source"] = "opendart_watch"
        out["verified"] = "dart"
    return out


def apply_watch_dart_rows(
    universe: pd.DataFrame,
    filled: Mapping[str, Mapping[str, Any]],
) -> pd.DataFrame:
    if universe.empty or not filled:
        return universe
    work = universe.copy()
    work["ticker"] = work["ticker"].astype(str).map(
        lambda t: t.zfill(6) if str(t).isdigit() else str(t)
    )
    for idx, row in work.iterrows():
        payload = filled.get(str(row["ticker"]))
        if not payload:
            continue
        work.loc[idx] = merge_watch_dart_row(row, payload)
    return work


_HK_KEYS = (
    "net_cash",
    "net_cash_to_market_cap",
    "treasury_share_ratio",
    "largest_shareholder_pct",
)


def load_market_caps(path: Path) -> dict[str, float]:
    """ticker → 시가총액 from alpha price_snapshot (or ops prices)."""
    if not path.exists():
        return {}
    try:
        df = pd.read_csv(path, dtype=str)
    except (OSError, ValueError):
        return {}
    if df.empty or "ticker" not in df.columns:
        return {}
    cap_col = next(
        (c for c in ("market_cap", "marcap", "mkt_cap", "시가총액") if c in df.columns),
        None,
    )
    if cap_col is None:
        return {}
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        ticker = str(row.get("ticker") or "").strip()
        if ticker.isdigit():
            ticker = ticker.zfill(6)
        if not ticker:
            continue
        cap = _as_float(row.get(cap_col))
        if cap is not None and cap > 0:
            out[ticker] = cap
    return out


def persist_hakedaka_watch_rows(
    path: Path,
    rows: Mapping[str, Mapping[str, Any]],
    *,
    market_caps: Mapping[str, float] | None = None,
    as_of: str = "",
) -> int:
    """Upsert DART hakedaka fields for the watch pool. Does not drop other tickers."""
    import csv
    from datetime import datetime, timezone

    if not rows:
        return 0
    caps = dict(market_caps or {})
    fieldnames = [
        "ticker",
        "as_of",
        "net_cash",
        "net_cash_to_market_cap",
        "treasury_share_ratio",
        "largest_shareholder_pct",
        "related_party_risk_flag",
        "governance_event_flag",
        "enriched_at",
    ]
    existing: dict[str, dict[str, str]] = {}
    orig_fields: list[str] = []
    if path.exists():
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                orig_fields = [str(c) for c in (reader.fieldnames or []) if c]
                for raw in reader:
                    ticker = str(raw.get("ticker") or "").strip()
                    if ticker.isdigit():
                        ticker = ticker.zfill(6)
                    if ticker:
                        existing[ticker] = dict(raw)
                        existing[ticker]["ticker"] = ticker
        except (OSError, csv.Error):
            existing = {}
            orig_fields = []
    wrote = 0
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for raw_tk, payload in rows.items():
        ticker = str(raw_tk).zfill(6) if str(raw_tk).isdigit() else str(raw_tk)
        if not ticker or not isinstance(payload, Mapping):
            continue
        net_cash = _as_float(payload.get("net_cash"))
        ncm = _as_float(payload.get("net_cash_to_market_cap"))
        if ncm is None and net_cash is not None:
            cap = caps.get(ticker)
            if cap and cap > 0:
                ncm = round(net_cash / cap * 100.0, 4)
        tre = _as_float(payload.get("treasury_share_ratio"))
        owner = _as_float(payload.get("largest_shareholder_pct"))
        if all(v is None for v in (net_cash, ncm, tre, owner)):
            continue
        row = dict(existing.get(ticker) or {"ticker": ticker})
        row["ticker"] = ticker
        if as_of:
            row["as_of"] = as_of
        if net_cash is not None:
            row["net_cash"] = str(net_cash)
        if ncm is not None:
            row["net_cash_to_market_cap"] = str(ncm)
        if tre is not None:
            row["treasury_share_ratio"] = str(tre)
        if owner is not None:
            row["largest_shareholder_pct"] = str(owner)
        row["enriched_at"] = stamp
        existing[ticker] = row
        wrote += 1
    if not wrote:
        return 0
    write_fields = list(orig_fields) if orig_fields else list(fieldnames)
    for key in fieldnames:
        if key not in write_fields:
            write_fields.append(key)
    for row in existing.values():
        for key in row:
            if key and key not in write_fields:
                write_fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=write_fields, extrasaction="ignore")
        writer.writeheader()
        for ticker in sorted(existing):
            writer.writerow({k: existing[ticker].get(k, "") for k in write_fields})
    return wrote


def persist_watch_dart_to_fundamentals(
    path: Path,
    filled: Mapping[str, Mapping[str, Any]],
) -> None:
    """Write DART quality fields onto collect fundamentals for the watch names."""
    if not filled or not path.exists():
        return
    df = pd.read_csv(path, dtype=str)
    if df.empty or "ticker" not in df.columns:
        return
    df["ticker"] = df["ticker"].astype(str).map(
        lambda t: t.zfill(6) if str(t).isdigit() else str(t)
    )
    for idx, row in df.iterrows():
        payload = filled.get(str(row["ticker"]))
        if not payload:
            continue
        df.loc[idx] = merge_watch_dart_row(row, payload)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _hakedaka_from_accounts(
    accounts: list[dict[str, Any]],
    meta: Any,
    *,
    corp: str,
    as_of: str,
    limiter: Any,
    dart_get_fn: Callable[..., Any],
    compute_hakedaka_metrics: Callable[..., Mapping[str, Any]],
) -> dict[str, Any]:
    """Same DART account list as quality metrics — extra hyslr call for owner %."""
    out: dict[str, Any] = {}
    try:
        hk_m = compute_hakedaka_metrics(accounts, meta)
    except Exception:
        hk_m = {}
    net_cash = _as_float(hk_m.get("net_cash") if isinstance(hk_m, Mapping) else None)
    tre = _as_float(hk_m.get("treasury_share_ratio") if isinstance(hk_m, Mapping) else None)
    if net_cash is not None:
        out["net_cash"] = net_cash
    if tre is not None:
        out["treasury_share_ratio"] = tre
    try:
        as_of_d = date.fromisoformat(str(as_of)[:10])
    except ValueError:
        as_of_d = date.today()

    def _limited_get(path: str, params: dict[str, Any], **kwargs: Any) -> Any:
        if limiter is not None:
            limiter.wait()
        return dart_get_fn(path, params, **kwargs)

    try:
        owner = _hyslr_owner_pct(_limited_get, corp, as_of_d)
    except Exception:
        owner = None
    if owner is not None:
        out["largest_shareholder_pct"] = owner
    return out


def collect_watch_dart_financials(
    tickers: list[str],
    *,
    as_of: date | str,
    fetch_one: FetchOne | None = None,
    root: Path | None = None,
) -> tuple[dict[str, dict[str, Any]], WatchDartResult]:
    as_of_s = as_of.isoformat() if isinstance(as_of, date) else str(as_of)[:10]
    wanted = [t.zfill(6) if str(t).isdigit() else str(t) for t in tickers if str(t).strip()]
    result = WatchDartResult(requested=len(wanted))
    filled: dict[str, dict[str, Any]] = {}
    if fetch_one is None:
        filled, result = _collect_watch_dart_live(wanted, as_of=as_of_s, root=root)
        return filled, result
    for ticker in wanted:
        try:
            payload = fetch_one(ticker, as_of_s)
        except Exception as exc:
            result.skipped += 1
            result.errors.append(f"{ticker}: {exc}")
            continue
        if not payload:
            result.skipped += 1
            continue
        has_any = any(
            _as_float(payload.get(k)) is not None
            for k in ("opm", "operating_margin", "debt_ratio", "roe", "net_income_y1", "net_income")
        )
        if not has_any:
            result.skipped += 1
            continue
        filled[ticker] = dict(payload)
        result.filled += 1
        hk = {
            key: payload[key]
            for key in _HK_KEYS
            if key in payload and payload[key] is not None
        }
        if hk:
            result.hakedaka[ticker] = hk
    return filled, result


def _collect_watch_dart_live(
    wanted: list[str],
    *,
    as_of: str,
    root: Path | None,
) -> tuple[dict[str, dict[str, Any]], WatchDartResult]:
    result = WatchDartResult(requested=len(wanted))
    filled: dict[str, dict[str, Any]] = {}
    repo = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    with _repo_src_on_top():
        from src.data_refresh.dart_account_aliases import compute_hakedaka_metrics
        from src.data_refresh.dart_client import (
            DartCredentialsError,
            RateLimiter,
            dart_get,
            get_dart_api_key,
        )
        from src.data_refresh.dart_corp_codes import build_ticker_corp_map
        from src.data_refresh.dart_financials import (
            compute_metrics,
            fetch_financial_accounts,
            find_latest_report,
        )

        try:
            get_dart_api_key(repo / "data")
        except DartCredentialsError:
            result.skipped = len(wanted)
            result.errors.append("OpenDART 키 없음 — 관찰 풀 재무 보강 생략")
            return filled, result
        try:
            corp_map = build_ticker_corp_map(repo / "data", wanted)
        except Exception as exc:
            result.skipped = len(wanted)
            result.errors.append(f"corp_code: {exc}")
            return filled, result
        limiter = RateLimiter(0.12)
        for ticker in wanted:
            corp = str(corp_map.get(ticker) or "")
            if not corp:
                result.skipped += 1
                result.errors.append(f"{ticker}: corp_code 없음")
                continue
            try:
                meta = find_latest_report(corp, as_of, limiter=limiter)
                if not meta:
                    result.skipped += 1
                    continue
                accounts = fetch_financial_accounts(meta, limiter=limiter)
                if not accounts:
                    result.skipped += 1
                    continue
                metrics = compute_metrics(accounts, meta)
                hk_row = _hakedaka_from_accounts(
                    accounts,
                    meta,
                    corp=corp,
                    as_of=as_of,
                    limiter=limiter,
                    dart_get_fn=dart_get,
                    compute_hakedaka_metrics=compute_hakedaka_metrics,
                )
                if hk_row:
                    result.hakedaka[ticker] = hk_row
                payload = {
                    "opm": metrics.get("operating_margin"),
                    "debt_ratio": metrics.get("debt_ratio"),
                    "roe": metrics.get("roe"),
                    "net_income_y1": metrics.get("net_income"),
                    "net_income_y2": metrics.get("net_income_prior"),
                }
                if not any(_as_float(v) is not None for v in payload.values()):
                    result.skipped += 1
                    continue
                filled[ticker] = payload
                result.filled += 1
            except Exception as exc:
                result.skipped += 1
                result.errors.append(f"{ticker}: {exc}")
    return filled, result
