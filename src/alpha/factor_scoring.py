from __future__ import annotations

from typing import Any

import numpy as np

from src.alpha.schemas import FundamentalRecord, PriceRecord, UniverseRecord


def _percentile_rank(values: list[float | None], higher_is_better: bool = True) -> dict[int, float]:
    valid = [(i, v) for i, v in enumerate(values) if v is not None and not (isinstance(v, float) and np.isnan(v))]
    if not valid:
        return {i: 50.0 for i in range(len(values))}
    arr = np.array([v for _, v in valid], dtype=float)
    if not higher_is_better:
        arr = -arr
    ranks = np.argsort(np.argsort(arr))
    n = len(arr)
    return {idx: (ranks[j] / max(n - 1, 1)) * 100 for j, (idx, _) in enumerate(valid)}


def _metric_value(
    field: str,
    fund: FundamentalRecord | None,
    px: PriceRecord | None,
) -> float | None:
    if fund and hasattr(fund, field):
        val = getattr(fund, field)
        if val is not None:
            return float(val)
    if px and hasattr(px, field):
        val = getattr(px, field)
        if val is not None:
            return float(val)
    if field == "fcf_positive" and fund and fund.fcf is not None:
        return 1.0 if fund.fcf > 0 else 0.0
    if field == "fcf_yield" and fund and fund.fcf is not None and px and px.market_cap > 0:
        return (fund.fcf / px.market_cap) * 100.0
    if field == "ocf_quality" and fund and fund.operating_cash_flow is not None and fund.net_income:
        if fund.net_income != 0:
            return fund.operating_cash_flow / abs(fund.net_income)
    return None


def _pillar_scores(
    universe: list[UniverseRecord],
    fundamentals: dict[str, FundamentalRecord],
    prices: dict[str, PriceRecord],
    metrics_cfg: dict[str, Any],
) -> list[float | None]:
    field_names = list(metrics_cfg.keys())
    per_field: dict[str, list[float | None]] = {f: [] for f in field_names}
    for rec in universe:
        fund = fundamentals.get(rec.ticker)
        px = prices.get(rec.ticker)
        for field in field_names:
            val = _metric_value(field, fund, px)
            if field in {"per", "pbr", "pcr", "psr", "ev_ebitda"} and val is not None and val > 0:
                val = 1.0 / val
            per_field[field].append(val)

    pct_by_field: dict[str, dict[int, float]] = {}
    for field, vals in per_field.items():
        higher = metrics_cfg[field].get("higher_better", True)
        if field in {"per", "pbr", "pcr", "psr", "ev_ebitda"}:
            higher = True
        pct_by_field[field] = _percentile_rank(vals, higher_is_better=higher)

    composite: list[float | None] = []
    for i in range(len(universe)):
        total_w = 0.0
        weighted = 0.0
        for field, cfg in metrics_cfg.items():
            w = float(cfg.get("weight", 1.0))
            pct = pct_by_field[field].get(i, 50.0)
            weighted += pct * w
            total_w += w
        composite.append(weighted / total_w if total_w else None)
    return composite


def score_factors(
    universe: list[UniverseRecord],
    fundamentals: dict[str, FundamentalRecord],
    prices: dict[str, PriceRecord],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    weights = config.get(
        "score_weights",
        {"quality": 0.30, "valuation": 0.25, "momentum": 0.20, "shareholder_return": 0.15},
    )
    q_metrics = config.get("quality_metrics", {})
    v_metrics = config.get("valuation_metrics", {})
    m_metrics = config.get("momentum_metrics", {})
    sr_metrics = config.get("shareholder_return_metrics", {})

    q_composite = _pillar_scores(universe, fundamentals, prices, q_metrics) if q_metrics else [50.0] * len(universe)
    v_composite = _pillar_scores(universe, fundamentals, prices, v_metrics) if v_metrics else [50.0] * len(universe)
    m_composite = _pillar_scores(universe, fundamentals, prices, m_metrics) if m_metrics else [50.0] * len(universe)
    sr_composite = _pillar_scores(universe, fundamentals, prices, sr_metrics) if sr_metrics else [50.0] * len(universe)

    wq = float(weights.get("quality", 0.30))
    wv = float(weights.get("valuation", 0.25))
    wm = float(weights.get("momentum", 0.20))
    wsr = float(weights.get("shareholder_return", 0.15))

    results: list[dict[str, Any]] = []
    for i, rec in enumerate(universe):
        qs = round(q_composite[i] or 50.0, 2)
        vs = round(v_composite[i] or 50.0, 2)
        ms = round(m_composite[i] or 50.0, 2)
        srs = round(sr_composite[i] or 50.0, 2)
        base = round(qs * wq + vs * wv + ms * wm + srs * wsr, 2)
        results.append(
            {
                "ticker": rec.ticker,
                "name": rec.name,
                "sector": rec.sector,
                "quality_score": qs,
                "valuation_score": vs,
                "momentum_score": ms,
                "shareholder_return_score": srs,
                "base_score": base,
            }
        )
    return results
