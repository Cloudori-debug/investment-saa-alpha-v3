"""OpenDART financials for the observation pool only — never the full KOSPI.

KRX ranks the liquid universe. DART fills OPM / debt / earnings for the
watch board (30 KOSPI / 10 KOSDAQ) then those names are rescored.
HTML viewers are not used. target_portfolio.csv is not written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from alpha_system.screen_book import watch_max
from alpha_system.ui.services.cecs_opendart_pack import _repo_src_on_top

FetchOne = Callable[[str, str], Mapping[str, Any] | None]


@dataclass
class WatchDartResult:
    requested: int = 0
    filled: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


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
        from src.data_refresh.dart_client import (
            DartCredentialsError,
            RateLimiter,
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
