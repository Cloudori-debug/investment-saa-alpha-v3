from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


FILTER_POLICY_DIFF = (
    "v1: alpha_pipeline universe_filter + data_gate PIT + alpha_scoring.yaml grades. "
    "v2: common_stock KOSPI/KOSDAQ + market cap/turnover tier (no PIT gate in shadow). "
    "v2 excludes preferred/ETF/REIT/SPAC; v1 may differ. KOSDAQ requires universe.csv sync."
)


def _load_v1_scored_tickers(output_dir: Path) -> tuple[int, set[str], dict[str, str]]:
    path = output_dir / "alpha_scored_universe.csv"
    if not path.exists():
        return 0, set(), {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    tickers = {str(r.get("ticker", "")).zfill(6) for r in df.to_dict(orient="records") if r.get("ticker")}
    grades = {
        str(r.get("ticker", "")).zfill(6): str(r.get("grade", ""))
        for r in df.to_dict(orient="records")
        if r.get("ticker")
    }
    return len(df), tickers, grades


def build_scored_count_comparison(
    output_dir: Path,
    v2_scored_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    v1_count, v1_tickers, v1_grades = _load_v1_scored_tickers(output_dir)
    v2_tickers = {str(r["ticker"]).zfill(6) for r in v2_scored_rows}
    v2_count = len(v2_scored_rows)
    added = sorted(v2_tickers - v1_tickers)
    removed = sorted(v1_tickers - v2_tickers)

    added_reasons: dict[str, str] = {}
    for ticker in added[:50]:
        row = next((r for r in v2_scored_rows if r["ticker"] == ticker), {})
        tier = row.get("tier", "")
        market = row.get("market", "KOSPI")
        if market == "KOSDAQ":
            added_reasons[ticker] = "v2_kosdaq_universe_or_market_filter"
        elif tier in {"Watch", "Mid", "Core"}:
            added_reasons[ticker] = "v2_market_tier_pass_not_in_v1_scored"
        else:
            added_reasons[ticker] = "v2_shadow_universe_wider_than_v1"

    removed_reasons: dict[str, str] = {}
    for ticker in removed[:50]:
        if v1_grades.get(ticker) == "Reject":
            removed_reasons[ticker] = "v1_reject_excluded_from_v2_top_pool"
        else:
            removed_reasons[ticker] = "v2_market_cap_turnover_exclude_or_missing_price"

    return {
        "v1_scored_count": v1_count,
        "v2_scored_count": v2_count,
        "difference_count": v2_count - v1_count,
        "added_tickers_sample": added[:20],
        "removed_tickers_sample": removed[:20],
        "added_by_reason": added_reasons,
        "removed_by_reason": removed_reasons,
        "filter_policy_diff": FILTER_POLICY_DIFF,
    }
