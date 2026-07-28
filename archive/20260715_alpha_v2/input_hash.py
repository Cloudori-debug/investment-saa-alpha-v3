"""P1.6e — Alpha v2 stable price subset hashing and drift diagnostics."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.runtime.diagnostics_subset_hash import compute_semantic_file_hash, normalize_for_semantic_hash

PRICE_HASH_MODE = "subset_semantic"
DRIFT_DEBUG_JSON = "price_hash_drift_debug.json"

# Fields used by alpha_v2 scoring via load_prices / factor_scoring
PRICE_HASH_FIELDS: tuple[str, ...] = (
    "close",
    "market_cap",
    "trading_value_20d",
    "trading_value_60d",
    "return_1m",
    "return_3m",
    "return_6m",
    "return_12m",
    "return_12m_ex_1m",
    "high_52w",
    "distance_from_52w_high",
    "volatility_60d",
)


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip()
    return t.zfill(6) if t.isdigit() else t


def alpha_v2_universe_tickers(data_dir: Path) -> list[str]:
    from src.alpha_v2.universe_builder import build_alpha_v2_universe

    return sorted({_normalize_ticker(u.ticker) for u in build_alpha_v2_universe(data_dir)})


def extract_alpha_v2_price_subset(data_dir: Path, as_of: str) -> dict[str, Any]:
    """Extract alpha_v2-universe price rows for the required market date."""
    as_of_s = as_of[:10]
    tickers = alpha_v2_universe_tickers(data_dir)
    path = data_dir / "prices.csv"
    rows_by_ticker: dict[str, dict[str, str]] = {}
    dates_used: dict[str, str] = {}
    missing_tickers: list[str] = []
    extra_tickers_ignored: list[str] = []
    unrelated_rows_ignored = 0

    if not path.exists() or not tickers:
        return {
            "market_date": as_of_s,
            "alpha_v2_universe_count": len(tickers),
            "tickers": tickers,
            "rows": rows_by_ticker,
            "dates_used": dates_used,
            "missing_tickers": list(tickers),
            "extra_tickers_ignored": [],
            "unrelated_rows_ignored": 0,
        }

    import pandas as pd

    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if df.empty or "ticker" not in df.columns:
        return {
            "market_date": as_of_s,
            "alpha_v2_universe_count": len(tickers),
            "tickers": tickers,
            "rows": rows_by_ticker,
            "dates_used": dates_used,
            "missing_tickers": list(tickers),
            "extra_tickers_ignored": [],
            "unrelated_rows_ignored": 0,
        }

    df["ticker"] = df["ticker"].map(_normalize_ticker)
    if "date" in df.columns:
        df["_date"] = df["date"].astype(str).str[:10]
    else:
        df["_date"] = as_of_s

    universe_set = set(tickers)
    file_tickers = set(df["ticker"].astype(str))
    extra_tickers_ignored = sorted(file_tickers - universe_set)
    unrelated_rows_ignored = int(len(df[~df["ticker"].isin(universe_set)]))

    for ticker in tickers:
        sub = df[df["ticker"] == ticker]
        if sub.empty:
            missing_tickers.append(ticker)
            continue
        exact = sub[sub["_date"] == as_of_s]
        if not exact.empty:
            row = exact.sort_values("_date").iloc[-1]
        else:
            prior = sub[sub["_date"] <= as_of_s]
            if prior.empty:
                missing_tickers.append(ticker)
                continue
            row = prior.sort_values("_date").iloc[-1]
        row_dict = {k: str(v) for k, v in row.to_dict().items() if not str(k).startswith("_")}
        if not str(row_dict.get("close", "")).strip():
            missing_tickers.append(ticker)
            continue
        rows_by_ticker[ticker] = row_dict
        dates_used[ticker] = str(row_dict.get("date", as_of_s))[:10]

    return {
        "market_date": as_of_s,
        "alpha_v2_universe_count": len(tickers),
        "tickers": tickers,
        "rows": rows_by_ticker,
        "dates_used": dates_used,
        "missing_tickers": sorted(missing_tickers),
        "extra_tickers_ignored": extra_tickers_ignored,
        "unrelated_rows_ignored": unrelated_rows_ignored,
    }


def normalize_price_subset_for_hash(subset: dict[str, Any]) -> list[dict[str, str]]:
    """Canonical rows for hashing — sorted ticker/date/value only."""
    normalized: list[dict[str, str]] = []
    for ticker in sorted(subset.get("rows", {})):
        row = subset["rows"][ticker]
        item: dict[str, str] = {
            "ticker": ticker,
            "date": str(subset.get("dates_used", {}).get(ticker, subset.get("market_date", "")))[:10],
        }
        for field in PRICE_HASH_FIELDS:
            item[field] = str(row.get(field, "")).strip()
        normalized.append(item)
    for ticker in sorted(subset.get("missing_tickers", [])):
        normalized.append(
            {
                "ticker": ticker,
                "date": str(subset.get("market_date", ""))[:10],
                "missing": "true",
            },
        )
    return normalized


def compute_prices_as_of_hash(data_dir: Path, as_of: str) -> str:
    """Semantic hash of alpha_v2 universe price subset for the market date."""
    as_of_s = as_of[:10]
    subset = extract_alpha_v2_price_subset(data_dir, as_of_s)
    payload = normalize_price_subset_for_hash(subset)
    if not payload and not subset.get("tickers"):
        return hashlib.sha256(f"{as_of_s}|empty_universe".encode("utf-8")).hexdigest()[:16]
    if not payload:
        return hashlib.sha256(f"{as_of_s}|missing".encode("utf-8")).hexdigest()[:16]
    normalized = normalize_for_semantic_hash({"market_date": as_of_s, "rows": payload})
    return hashlib.sha256(_canonical_json(normalized).encode("utf-8")).hexdigest()[:16]


def check_alpha_v2_price_coverage(data_dir: Path, as_of: str) -> dict[str, Any]:
    subset = extract_alpha_v2_price_subset(data_dir, as_of)
    missing = list(subset.get("missing_tickers") or [])
    total = int(subset.get("alpha_v2_universe_count") or 0)
    covered_count = total - len(missing)
    return {
        "covered": len(missing) == 0 and total > 0,
        "missing_tickers": missing,
        "covered_count": covered_count,
        "required_count": total,
    }


def compare_price_subset_drift(
    data_dir: Path,
    as_of: str,
    *,
    previous_hash: str = "",
    previous_subset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_subset = extract_alpha_v2_price_subset(data_dir, as_of)
    current_hash = compute_prices_as_of_hash(data_dir, as_of)
    prev_subset = previous_subset or {}
    if not prev_subset and previous_hash:
        prev_subset = {"rows": {}, "missing_tickers": [], "dates_used": {}}

    changed_tickers: list[str] = []
    changed_dates: list[str] = []
    prev_rows = prev_subset.get("rows") or {}
    curr_rows = current_subset.get("rows") or {}
    all_tickers = sorted(set(prev_rows) | set(curr_rows))
    for ticker in all_tickers:
        prev_row = prev_rows.get(ticker)
        curr_row = curr_rows.get(ticker)
        if prev_row is None or curr_row is None:
            changed_tickers.append(ticker)
            continue
        prev_norm = {f: str(prev_row.get(f, "")).strip() for f in PRICE_HASH_FIELDS}
        curr_norm = {f: str(curr_row.get(f, "")).strip() for f in PRICE_HASH_FIELDS}
        if prev_norm != curr_norm:
            changed_tickers.append(ticker)
        prev_date = str(prev_subset.get("dates_used", {}).get(ticker, ""))[:10]
        curr_date = str(current_subset.get("dates_used", {}).get(ticker, ""))[:10]
        if prev_date and curr_date and prev_date != curr_date:
            changed_dates.append(ticker)

    return {
        "market_date": as_of[:10],
        "alpha_v2_universe_count": current_subset.get("alpha_v2_universe_count", 0),
        "previous_price_hash": previous_hash,
        "current_price_hash": current_hash,
        "price_hash_match": bool(previous_hash and previous_hash == current_hash),
        "changed_tickers": sorted(set(changed_tickers)),
        "changed_dates": sorted(set(changed_dates)),
        "missing_tickers": list(current_subset.get("missing_tickers") or []),
        "extra_tickers_ignored": list(current_subset.get("extra_tickers_ignored") or []),
        "unrelated_rows_ignored": int(current_subset.get("unrelated_rows_ignored") or 0),
        "current_subset": current_subset,
    }


def write_price_hash_drift_debug(
    output_dir: Path,
    doc: dict[str, Any],
    *,
    run_id: str = "",
    run_mode: str = "standard",
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "run_id": run_id,
        "run_mode": run_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **doc,
    }
    path = output_dir / DRIFT_DEBUG_JSON
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_price_hash_drift_debug(output_dir: Path) -> dict[str, Any]:
    path = output_dir / DRIFT_DEBUG_JSON
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# Backward-compatible helpers used by legacy callers
def compute_flow_hash(data_dir: Path) -> str:
    return compute_semantic_file_hash(data_dir / "investor_flows.csv")


def compute_stable_input_hash(data_dir: Path, *, as_of: str) -> str:
    parts = [
        as_of[:10],
        compute_semantic_file_hash(data_dir / "universe.csv"),
        compute_prices_as_of_hash(data_dir, as_of),
        compute_semantic_file_hash(data_dir / "prices_history.csv"),
        compute_semantic_file_hash(data_dir / "fundamentals_pit.csv"),
        compute_semantic_file_hash(data_dir / "fundamentals.csv"),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def compute_alpha_v2_input_hash(data_dir: Path, *, as_of: str) -> str:
    parts = [compute_stable_input_hash(data_dir, as_of=as_of), compute_flow_hash(data_dir)]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def can_reuse_alpha_v2_outputs(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
) -> tuple[bool, str]:
    from src.alpha_v2.cache_decision import evaluate_alpha_v2_cache_decision

    doc = evaluate_alpha_v2_cache_decision(
        data_dir,
        output_dir,
        as_of=as_of,
        run_mode="standard",
        cache_reuse=True,
    )
    if doc.get("decision") == "reuse_cache":
        return True, str(doc.get("refresh_reason") or "input_hash_unchanged")
    return False, str(doc.get("refresh_reason") or "cache_blocked")
