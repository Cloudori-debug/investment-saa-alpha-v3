from __future__ import annotations

from typing import Any

import pandas as pd

from src.math_utils import linear_score, percentile_score, weighted_mean


def _sector_series(df: pd.DataFrame, sector: str, col: str) -> pd.Series:
    if "sector" not in df.columns:
        return df[col] if col in df.columns else pd.Series(dtype=float)
    subset = df[df["sector"] == sector][col]
    if len(subset.dropna()) >= 5:
        return subset
    return df[col] if col in df.columns else pd.Series(dtype=float)


def score_quality(row: pd.Series, df: pd.DataFrame, cfg: dict[str, Any]) -> float:
    q_cfg = cfg.get("quality", {})
    weights = q_cfg.get("sub_weights", {}).get("default", {})
    if bool(row.get("is_holding")):
        weights = q_cfg.get("sub_weights", {}).get("holding", weights)

    roe_cfg = q_cfg.get("roe_linear", {})
    roe_val = row.get("roe_3y_avg")
    if roe_val is None or pd.isna(roe_val):
        roe_val = row.get("roe")
    q1 = linear_score(roe_val, roe_cfg.get("low", 5), roe_cfg.get("high", 20))

    sector = str(row.get("sector", ""))
    q2 = percentile_score(row.get("opm"), _sector_series(df, sector, "opm"))

    debt_cfg = q_cfg.get("debt_linear", {})
    if bool(row.get("is_financial")):
        q3 = 50.0
    else:
        q3 = linear_score(
            row.get("debt_ratio"),
            debt_cfg.get("low", 50),
            debt_cfg.get("high", 200),
            invert=debt_cfg.get("invert", True),
        )

    y1, y2 = row.get("net_income_y1"), row.get("net_income_y2")
    if y1 is not None and y2 is not None and not pd.isna(y1) and not pd.isna(y2):
        if float(y1) > 0 and float(y2) > 0:
            q4 = 85.0
        elif float(y1) < 0 or float(y2) < 0:
            q4 = 40.0
        else:
            q4 = 60.0
    else:
        q4 = 60.0

    return weighted_mean([
        (q1, weights.get("roe", 0.4)),
        (q2, weights.get("opm", 0.25)),
        (q3, weights.get("debt", 0.2)),
        (q4, weights.get("earnings_stability", 0.15)),
    ])


def score_value(row: pd.Series, df: pd.DataFrame, cfg: dict[str, Any]) -> float:
    v_cfg = cfg.get("value", {})
    weights = v_cfg.get("sub_weights", {}).get("default", {})
    if bool(row.get("is_holding")):
        weights = v_cfg.get("sub_weights", {}).get("holding", weights)

    sector = str(row.get("sector", ""))
    per = row.get("per")
    pbr = row.get("pbr")
    per_med = row.get("sector_per_median")
    pbr_med = row.get("sector_pbr_median")

    if per_med is None or pd.isna(per_med):
        per_med = df[df["sector"] == sector]["per"].median() if sector else df["per"].median()
    if pbr_med is None or pd.isna(pbr_med):
        pbr_med = df[df["sector"] == sector]["pbr"].median() if sector else df["pbr"].median()

    if per is not None and not pd.isna(per) and float(per) <= 0:
        v1 = 0.0
    elif per_med and not pd.isna(per_med) and per is not None and not pd.isna(per):
        v1 = percentile_score(float(per) / float(per_med), df["per"] / df["sector_per_median"].fillna(per_med), invert=True)
    else:
        v1 = percentile_score(per, _sector_series(df, sector, "per"), invert=True)

    if pbr is not None and not pd.isna(pbr) and float(pbr) <= 0:
        v2 = 0.0
    elif pbr_med and not pd.isna(pbr_med) and pbr is not None and not pd.isna(pbr):
        ratio_series = df["pbr"] / df["sector_pbr_median"].fillna(pbr_med)
        v2 = percentile_score(float(pbr) / float(pbr_med), ratio_series, invert=True)
    else:
        v2 = percentile_score(pbr, _sector_series(df, sector, "pbr"), invert=True)

    ev = row.get("ev_ebitda")
    v3 = percentile_score(ev, _sector_series(df, sector, "ev_ebitda"), invert=True) if ev is not None and not pd.isna(ev) else None

    fcf_cfg = v_cfg.get("fcf_yield_linear", {})
    v4 = linear_score(row.get("fcf_yield"), fcf_cfg.get("low", 0), fcf_cfg.get("high", 8))

    pairs: list[tuple[float | None, float]] = [
        (v1, weights.get("per", 0.35)),
        (v2, weights.get("pbr", 0.35)),
        (v4, weights.get("fcf_yield", 0.15)),
    ]
    if v3 is not None:
        pairs.append((v3, weights.get("ev_ebitda", 0.15)))
    else:
        w_ev = weights.get("ev_ebitda", 0.15)
        pairs[0] = (v1, pairs[0][1] + w_ev * 0.5)
        pairs[1] = (v2, pairs[1][1] + w_ev * 0.5)

    return weighted_mean(pairs)


def score_shareholder(row: pd.Series, cfg: dict[str, Any]) -> tuple[float, str]:
    from src.execution_continuity import resolve_execution_continuity

    sr_cfg = cfg.get("shareholder_return", {})
    sr4, sr4_prov = resolve_execution_continuity(row)

    bare = (
        pd.isna(row.get("dividend_yield"))
        and pd.isna(row.get("payout_ratio"))
        and pd.isna(row.get("buyback_3y"))
        and sr4_prov == "neutral"
    )
    if bare:
        return float(sr_cfg.get("missing_neutral_score", 50)), "YELLOW"

    div_cfg = sr_cfg.get("dividend_linear", {})
    sr1 = linear_score(row.get("dividend_yield"), div_cfg.get("low", 1), div_cfg.get("high", 5))

    pay_cfg = sr_cfg.get("payout_linear", {})
    payout = row.get("payout_ratio")
    sr2 = linear_score(payout, pay_cfg.get("low", 10), pay_cfg.get("high", 60))
    cap = sr_cfg.get("payout_cap_above", 80)
    if payout is not None and not pd.isna(payout) and float(payout) > cap:
        sr2 = min(sr2, 40.0)

    buyback = row.get("buyback_3y")
    sr3 = 80.0 if _truthy(buyback) else 30.0

    w = sr_cfg.get("sub_weights", {})
    score = weighted_mean([
        (sr1, w.get("dividend_yield", 0.30)),
        (sr2, w.get("payout_ratio", 0.15)),
        (sr3, w.get("buyback", 0.25)),
        (sr4, w.get("execution_continuity", 0.30)),
    ])
    gate = "YELLOW" if sr4_prov == "neutral" and pd.isna(row.get("dividend_yield")) else "GREEN"
    return score, gate


def score_risk(row: pd.Series, cfg: dict[str, Any]) -> float:
    r_cfg = cfg.get("risk", {})
    w = r_cfg.get("sub_weights", {})
    vol_cfg = r_cfg.get("vol_linear", {})
    r1 = linear_score(row.get("volatility_1y"), vol_cfg.get("low", 15), vol_cfg.get("high", 45), invert=True)

    close = row.get("close")
    high = row.get("high_52w")
    low = row.get("low_52w")
    if close and high and low and not pd.isna(close) and float(high) > float(low):
        pos = (float(close) - float(low)) / (float(high) - float(low)) * 100.0
        cap_ratio = r_cfg.get("high_52w_cap_ratio", 0.95)
        if close and high and float(close) / float(high) >= cap_ratio:
            pos = min(pos, 30.0)
        r2 = pos
    else:
        r2 = 50.0

    beta = row.get("beta_kospi200")
    if beta is None or pd.isna(beta):
        r3 = float(r_cfg.get("beta_missing_neutral", 50))
    else:
        r3 = linear_score(abs(float(beta) - 1.0), 0, 0.8, invert=True)

    return weighted_mean([
        (r1, w.get("volatility", 0.5)),
        (r2, w.get("position_52w", 0.3)),
        (r3, w.get("beta", 0.2)),
    ])


def score_momentum(row: pd.Series, df: pd.DataFrame, cfg: dict[str, Any]) -> float:
    m_cfg = cfg.get("momentum", {})
    w = m_cfg.get("sub_weights", {})
    m1 = percentile_score(row.get("return_6m"), df["return_6m"] if "return_6m" in df.columns else pd.Series(dtype=float))

    close = row.get("close")
    high = row.get("high_52w")
    if close and high and not pd.isna(close) and not pd.isna(high) and float(high) > 0:
        ratio = float(close) / float(high)
        m2 = linear_score(ratio, 0.70, 0.95)
    else:
        m2 = 50.0

    return weighted_mean([
        (m1, w.get("return_6m", 0.6)),
        (m2, w.get("high_52w", 0.4)),
    ])


def _truthy(val) -> bool:
    if pd.isna(val):
        return False
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in {"true", "1", "yes", "y"}
