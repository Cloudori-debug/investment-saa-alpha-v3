"""Group-proxy returns and SAA vs SAA+TAA NAV paths."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.compass.saa_engine import get_saa_weights
from src.models import VALID_ASSET_GROUPS


def group_daily_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """Approximate sleeve returns (group-level proxies — not ticker-level)."""
    p = panel.copy()
    p["date"] = pd.to_datetime(p["date"])
    p = p.sort_values("date").reset_index(drop=True)

    kospi_ret = p["kospi"].pct_change()
    sp_ret = p["sp500"].pct_change()
    gold_ret = p["gold"].pct_change()
    fx_ret = p["usdkrw"].pct_change()  # KRW/USD up → USD sleeve gain in KRW terms
    # Cash carry from Korea 10Y (annual % → daily); yield delta duration for income_alt
    k10 = p["korea_10y"].astype(float)
    cash_carry = (k10 / 100.0) / 252.0
    dy = k10.diff() / 100.0
    bond_price_ret = -5.0 * dy  # ~duration 5
    income = 0.5 * cash_carry + 0.5 * bond_price_ret

    out = pd.DataFrame(
        {
            "date": p["date"].dt.strftime("%Y-%m-%d"),
            "domestic_beta": kospi_ret,
            "kr_alpha": kospi_ret,  # equity-like proxy (limitation)
            "global_beta": sp_ret,
            "hedge_alt": gold_ret,
            "fx_dollar": fx_ret,
            "cash_short_bond": cash_carry,
            "income_alt": income,
        }
    )
    return out


def _align_weights_and_returns(
    results: pd.DataFrame,
    ret: pd.DataFrame,
    saa_w: dict[str, float],
) -> pd.DataFrame:
    """Lag weights by 1 day (signal at t applies to return t→t+1)."""
    r = ret.copy()
    wcols = [f"w_{g}" for g in VALID_ASSET_GROUPS]
    merged = results[["date"] + wcols].merge(r, on="date", how="inner")
    merged = merged.sort_values("date").reset_index(drop=True)

    # lag weights
    for g in VALID_ASSET_GROUPS:
        merged[f"wlag_{g}"] = merged[f"w_{g}"].shift(1)
        merged[f"saa_{g}"] = float(saa_w.get(g, 0.0))

    merged = merged.iloc[1:].reset_index(drop=True)  # drop first NaN lag

    port_taa = np.zeros(len(merged))
    port_saa = np.zeros(len(merged))
    for g in VALID_ASSET_GROUPS:
        rg = merged[g].fillna(0.0).to_numpy()
        port_taa += (merged[f"wlag_{g}"].fillna(0.0).to_numpy() / 100.0) * rg
        port_saa += (merged[f"saa_{g}"].to_numpy() / 100.0) * rg

    merged["ret_taa"] = port_taa
    merged["ret_saa"] = port_saa
    merged["ret_excess"] = port_taa - port_saa
    merged["nav_taa"] = (1.0 + merged["ret_taa"].fillna(0.0)).cumprod()
    merged["nav_saa"] = (1.0 + merged["ret_saa"].fillna(0.0)).cumprod()
    return merged


def summarize_path(returns: pd.Series, *, ann_factor: float = 252.0) -> dict[str, float]:
    r = returns.dropna().astype(float)
    if r.empty:
        return {
            "n": 0,
            "cum_return": 0.0,
            "cagr": 0.0,
            "vol": 0.0,
            "mdd": 0.0,
            "sharpe": 0.0,
        }
    nav = (1.0 + r).cumprod()
    years = len(r) / ann_factor
    cum = float(nav.iloc[-1] - 1.0)
    cagr = float(nav.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 else 0.0
    vol = float(r.std(ddof=1) * np.sqrt(ann_factor)) if len(r) > 1 else 0.0
    peak = nav.cummax()
    dd = nav / peak - 1.0
    mdd = float(dd.min()) if len(dd) else 0.0
    sharpe = float(r.mean() / r.std(ddof=1) * np.sqrt(ann_factor)) if r.std(ddof=1) > 0 else 0.0
    return {
        "n": int(len(r)),
        "cum_return": cum,
        "cagr": cagr,
        "vol": vol,
        "mdd": mdd,
        "sharpe": sharpe,
    }


def compute_performance(
    panel: pd.DataFrame,
    results: pd.DataFrame,
    profiles: dict[str, Any],
    *,
    profile_name: str = "core_absolute_return",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    saa_w = get_saa_weights(profiles, profile_name)
    ret = group_daily_returns(panel)
    path = _align_weights_and_returns(results, ret, saa_w)

    taa = summarize_path(path["ret_taa"])
    saa = summarize_path(path["ret_saa"])
    excess = path["ret_excess"].dropna()
    excess_mean = float(excess.mean()) if len(excess) else 0.0
    excess_se = float(excess.std(ddof=1) / np.sqrt(len(excess))) if len(excess) > 1 else 0.0

    # Regime-conditional excess (applied_regime on signal day ≈ lag weight day)
    regime_stats: dict[str, Any] = {}
    tmp = results[["date", "applied_regime"]].merge(
        path[["date", "ret_excess"]], on="date", how="inner"
    )
    for reg, grp in tmp.groupby("applied_regime"):
        er = grp["ret_excess"].dropna()
        regime_stats[str(reg)] = {
            "n": int(len(er)),
            "mean_excess_daily": float(er.mean()) if len(er) else 0.0,
            "sum_excess": float(er.sum()) if len(er) else 0.0,
        }

    summary = {
        "taa": taa,
        "saa": saa,
        "excess_mean_daily": excess_mean,
        "excess_se_daily": excess_se,
        "excess_ann": excess_mean * 252.0,
        "proxy_notes": {
            "domestic_beta": "KOSPI pct_change",
            "kr_alpha": "KOSPI pct_change (same — limitation)",
            "global_beta": "S&P500 pct_change",
            "hedge_alt": "gold pct_change",
            "fx_dollar": "usdkrw pct_change",
            "cash_short_bond": "korea_10y/100/252 carry",
            "income_alt": "0.5*cash_carry + 0.5*(-5*dYield)",
        },
        "regime_excess": regime_stats,
        "saa_weights": saa_w,
    }
    return path, summary
