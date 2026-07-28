"""Statistical significance — Deflated Sharpe (Bailey & López de Prado) + IS/OOS split.

Uses stdlib math only (no scipy dependency in this environment).
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Approximate inverse CDF of standard normal (rational approximation)."""
    if p <= 0.0:
        return float("-inf")
    if p >= 1.0:
        return float("inf")
    # Abramowitz & Stegun 26.2.23
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614736e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    ]
    plow = 0.02425
    phigh = 1.0 - plow
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if phigh < p:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    q = p - 0.5
    r = q * q
    return (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
    ) / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)


def _psr(
    sr_hat: float,
    *,
    t: int,
    sr_benchmark: float = 0.0,
    skew: float = 0.0,
    kurt: float = 3.0,
) -> float:
    """Probabilistic Sharpe Ratio (Bailey & López de Prado)."""
    if t <= 1 or not math.isfinite(sr_hat):
        return float("nan")
    sr = sr_hat
    sb = sr_benchmark
    numer = (sr - sb) * math.sqrt(t - 1)
    denom = math.sqrt(max(1e-12, 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr))
    return float(_norm_cdf(numer / denom))


def expected_max_sr(
    n_trials: int,
    *,
    t: int,
    skew: float = 0.0,
    kurt: float = 3.0,
) -> float:
    """Expected maximum SR under N independent null trials (Euler-Mascheroni approx)."""
    if n_trials < 1 or t <= 1:
        return 0.0
    em = 0.5772156649
    z = _norm_ppf(1.0 - 1.0 / n_trials)
    z_e = _norm_ppf(1.0 - 1.0 / (n_trials * math.e))
    v_sr = (1.0 - skew * 0.0 + ((kurt - 1.0) / 4.0) * 0.0) / (t - 1)
    sr_star = math.sqrt(v_sr) * ((1.0 - em) * z + em * z_e)
    return float(sr_star)


def deflated_sharpe_ratio(
    returns: pd.Series,
    *,
    n_trials: int = 16,
    ann_factor: float = 252.0,
) -> dict[str, float]:
    """Deflated Sharpe Ratio — n_trials ≈ independent hypotheses (≥15 DOF proxy)."""
    r = returns.dropna().astype(float)
    t = int(len(r))
    if t < 30:
        return {
            "n_obs": t,
            "sr_hat_ann": float("nan"),
            "sr_hat_daily": float("nan"),
            "n_trials": float(n_trials),
            "sr_star_daily": float("nan"),
            "dsr": float("nan"),
            "psr_vs_0": float("nan"),
        }
    mean = float(r.mean())
    std = float(r.std(ddof=1))
    sr_daily = mean / std if std > 0 else 0.0
    sr_ann = sr_daily * math.sqrt(ann_factor)
    skew = float(r.skew()) if t > 2 else 0.0
    kurt = float(r.kurtosis() + 3.0) if t > 3 else 3.0
    sr_star = expected_max_sr(n_trials, t=t, skew=skew, kurt=kurt)
    dsr = _psr(sr_daily, t=t, sr_benchmark=sr_star, skew=skew, kurt=kurt)
    psr0 = _psr(sr_daily, t=t, sr_benchmark=0.0, skew=skew, kurt=kurt)
    return {
        "n_obs": t,
        "sr_hat_ann": float(sr_ann),
        "sr_hat_daily": float(sr_daily),
        "n_trials": float(n_trials),
        "sr_star_daily": float(sr_star),
        "skew": skew,
        "kurtosis": kurt,
        "dsr": float(dsr),
        "psr_vs_0": float(psr0),
    }


def count_regime_cycles(results: pd.DataFrame) -> dict[str, Any]:
    regs = results["applied_regime"].astype(str).tolist()
    flips = sum(1 for i in range(1, len(regs)) if regs[i] != regs[i - 1])
    unique = sorted(set(regs))
    return {
        "unique_regimes": unique,
        "regime_flips": flips,
        "approx_half_cycles": flips,
        "n_judgment_days": int(len(regs)),
    }


def is_oos_split(
    path: pd.DataFrame,
    *,
    split_date: str = "2021-01-01",
    n_trials: int = 16,
) -> dict[str, Any]:
    """In-sample / out-of-sample excess-return Sharpe compare (PBO-lite)."""
    p = path.copy()
    p["date"] = pd.to_datetime(p["date"])
    is_mask = p["date"] < pd.Timestamp(split_date)
    oos_mask = ~is_mask
    out: dict[str, Any] = {"split_date": split_date}
    for name, mask in (("is", is_mask), ("oos", oos_mask)):
        sub = p.loc[mask, "ret_excess"]
        dsr = deflated_sharpe_ratio(sub, n_trials=n_trials)
        mean = float(sub.mean()) if len(sub) else 0.0
        out[name] = {
            "n": int(mask.sum()),
            "excess_mean_daily": mean,
            "excess_ann": mean * 252.0,
            **dsr,
        }
    out["same_sign_excess"] = bool(
        np.sign(out["is"]["excess_mean_daily"]) == np.sign(out["oos"]["excess_mean_daily"])
        and out["is"]["n"] > 0
        and out["oos"]["n"] > 0
    )
    return out
