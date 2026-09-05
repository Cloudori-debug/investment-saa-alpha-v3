"""Drop names already at/above the mixed take-profit from the proposal book.

Same layer as OpenDART overlay gates: scores stay unchanged, next eligible
fills, target_portfolio.csv and exit YAML are not written.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
import yaml

from alpha_system.sizing.qual_overlay import norm_ticker
from src.alpha.quant_target_estimate import (
    estimate_from_maps,
    load_alpha_template_fundamentals,
)


def _to_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        x = float(val)
    except (TypeError, ValueError):
        return None
    if x != x or x <= 0:
        return None
    return x


def _yaml_entry(
    ticker: str,
    exit_yaml: Mapping[str, Any] | None,
) -> dict[str, Any]:
    tickers = (exit_yaml or {}).get("tickers") if isinstance(exit_yaml, Mapping) else None
    if not isinstance(tickers, Mapping):
        return {}
    raw = tickers.get(ticker)
    if raw is None and ticker.isdigit():
        raw = tickers.get(ticker.lstrip("0") or ticker)
    if raw is None:
        raw = tickers.get(str(int(ticker))) if ticker.isdigit() else None
    return dict(raw) if isinstance(raw, Mapping) else {}


def is_at_or_above_justified_target(
    *,
    current_price: Any = None,
    current_pbr: Any = None,
    yaml_targets: Mapping[str, Any] | None = None,
    roe: Any = None,
    payout: Any = None,
    dividend_yield: Any = None,
    roe_3y_avg: Any = None,
    sector: str = "",
) -> bool:
    """True when spot is at/above the take-profit line. Fail-open on thin data."""
    px = _to_float(current_price)
    pbr = _to_float(current_pbr)
    yaml_row = dict(yaml_targets) if isinstance(yaml_targets, Mapping) else {}
    pbr_max = _to_float((yaml_row.get("valuation") or {}).get("pbr_max"))
    yaml_px = _to_float(yaml_row.get("target_price"))
    has_yaml_line = pbr_max is not None or yaml_px is not None

    if has_yaml_line:
        if yaml_px is not None and px is not None:
            return px + 1e-9 >= yaml_px
        if pbr_max is not None and pbr is not None:
            return pbr + 1e-9 >= pbr_max
        return False

    est = estimate_from_maps(
        "",
        fund={
            "roe": roe,
            "roe_3y_avg": roe_3y_avg,
            "pbr": current_pbr,
            "payout": payout,
            "dividend_yield": dividend_yield,
            "sector": sector,
        },
        price=current_price,
        sector=sector,
    )
    if not est.ok:
        return False
    if est.pbr_draft is not None and pbr is not None:
        return pbr + 1e-9 >= float(est.pbr_draft)
    if est.price_mid is not None and px is not None:
        return px + 1e-9 >= float(est.price_mid)
    return False


def latest_price_map(prices_df: pd.DataFrame | None) -> dict[str, float]:
    if prices_df is None or prices_df.empty or "ticker" not in prices_df.columns:
        return {}
    work = prices_df.copy()
    work["ticker"] = work["ticker"].map(norm_ticker)
    if "date" in work.columns:
        work = work.sort_values("date")
    work = work.drop_duplicates("ticker", keep="last")
    out: dict[str, float] = {}
    for _, row in work.iterrows():
        px = _to_float(row.get("close") or row.get("price"))
        if px is not None:
            out[str(row["ticker"])] = px
    return out


def _fund_row_map(fundamentals_df: pd.DataFrame | None) -> dict[str, dict[str, Any]]:
    if fundamentals_df is None or fundamentals_df.empty:
        return {}
    if "ticker" not in fundamentals_df.columns:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for _, row in fundamentals_df.iterrows():
        tk = norm_ticker(row.get("ticker"))
        if tk:
            out[tk] = row.to_dict()
    return out


def collect_above_justified_target_tickers(
    tickers: Sequence[str],
    *,
    prices_df: pd.DataFrame | None = None,
    fundamentals_df: pd.DataFrame | None = None,
    template_fund_by: Mapping[str, Mapping[str, Any]] | None = None,
    exit_yaml: Mapping[str, Any] | None = None,
) -> set[str]:
    """Tickers whose spot is at/above yaml take-profit, else live justified P/B."""
    prices = latest_price_map(prices_df)
    funds = _fund_row_map(fundamentals_df)
    template = {
        norm_ticker(k): dict(v)
        for k, v in (template_fund_by or {}).items()
        if norm_ticker(k)
    }
    hit: set[str] = set()
    for raw in tickers:
        tk = norm_ticker(raw)
        if not tk:
            continue
        fund = dict(template.get(tk) or {})
        fund.update(funds.get(tk) or {})
        if is_at_or_above_justified_target(
            current_price=prices.get(tk),
            current_pbr=fund.get("pbr"),
            yaml_targets=_yaml_entry(tk, exit_yaml),
            roe=fund.get("roe"),
            roe_3y_avg=fund.get("roe_3y_avg"),
            sector=str(fund.get("sector") or ""),
            payout=fund.get("payout_ratio") or fund.get("payout"),
            dividend_yield=fund.get("dividend_yield"),
        ):
            hit.add(tk)
    return hit


def collect_above_justified_target_tickers_from_root(
    tickers: Sequence[str],
    root: Path,
    *,
    prices_df: pd.DataFrame | None = None,
    fundamentals_df: pd.DataFrame | None = None,
    exit_yaml: Mapping[str, Any] | None = None,
) -> set[str]:
    root = Path(root)
    if prices_df is None:
        path = root / "data" / "prices.csv"
        prices_df = pd.read_csv(path) if path.exists() else pd.DataFrame()
    if fundamentals_df is None:
        path = root / "data" / "fundamentals.csv"
        fundamentals_df = pd.read_csv(path) if path.exists() else pd.DataFrame()
    if exit_yaml is None:
        path = root / "data" / "kr_alpha_exit_targets.yaml"
        if path.exists():
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            exit_yaml = loaded if isinstance(loaded, dict) else {}
        else:
            exit_yaml = {}
    return collect_above_justified_target_tickers(
        tickers,
        prices_df=prices_df,
        fundamentals_df=fundamentals_df,
        template_fund_by=load_alpha_template_fundamentals(root),
        exit_yaml=exit_yaml,
    )


def ops_proposal_membership(
    proposal_tickers: Sequence[str],
    *,
    held_tickers: Sequence[str],
    above_target: Sequence[str],
) -> set[str]:
    """S2a set: proposal names, plus holdings dropped only for take-profit."""
    prop = {norm_ticker(t) for t in proposal_tickers if str(t).strip()}
    held = {norm_ticker(t) for t in held_tickers if str(t).strip()}
    above = {norm_ticker(t) for t in above_target if str(t).strip()}
    return prop | (held & above)
