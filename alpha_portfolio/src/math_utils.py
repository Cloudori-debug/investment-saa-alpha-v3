from __future__ import annotations

import pandas as pd


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def linear_score(value: float | None, low: float, high: float, *, invert: bool = False) -> float:
    if value is None or pd.isna(value):
        return 50.0
    if high == low:
        return 50.0
    raw = (float(value) - low) / (high - low) * 100.0
    score = clamp(raw)
    return 100.0 - score if invert else score


def percentile_score(
    value: float | None,
    series: pd.Series,
    *,
    invert: bool = False,
) -> float:
    if value is None or pd.isna(value):
        return 50.0
    clean = series.dropna()
    if clean.empty:
        return 50.0
    rank = (clean <= float(value)).sum() / len(clean) * 100.0
    score = clamp(rank)
    return 100.0 - score if invert else score


def weighted_mean(pairs: list[tuple[float | None, float]]) -> float:
    total_w = 0.0
    total = 0.0
    for score, weight in pairs:
        if score is None or pd.isna(score):
            continue
        total_w += weight
        total += float(score) * weight
    if total_w == 0:
        return 50.0
    return total / total_w
