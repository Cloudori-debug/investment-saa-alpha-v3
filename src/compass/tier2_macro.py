from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from src.compass.models import ScoreBreakdownItem


class MacroTier2(BaseModel):
    date: str = ""
    pmi_kr: float | None = None
    pmi_us: float | None = None
    cpi_kr_yoy: float | None = None
    cpi_us_yoy: float | None = None
    yield_spread_2y10y: float | None = None
    hy_oas_bp: float | None = None
    real_rate_kr: float | None = None


def _pick_tier2_row(df: pd.DataFrame, as_of: str | None) -> dict:
    if as_of:
        matched = df[df["date"].astype(str) == as_of]
        if not matched.empty:
            return matched.iloc[-1].to_dict()
        prior = df[df["date"].astype(str) <= as_of]
        if not prior.empty:
            return prior.iloc[-1].to_dict()
    return df.iloc[-1].to_dict()


def load_macro_tier2(path: Path, as_of: str | None = None) -> MacroTier2 | None:
    hist_path = path.parent / "macro_tier2_history.csv"
    frames: list[pd.DataFrame] = []
    if path.exists():
        frames.append(pd.read_csv(path, dtype=str, keep_default_na=False))
    if hist_path.exists():
        frames.append(pd.read_csv(hist_path, dtype=str, keep_default_na=False))
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    if df.empty:
        return None
    row = _pick_tier2_row(df, as_of)
    floats = (
        "pmi_kr", "pmi_us", "cpi_kr_yoy", "cpi_us_yoy",
        "yield_spread_2y10y", "hy_oas_bp", "real_rate_kr",
    )
    for key in floats:
        if key in row and str(row.get(key, "")).strip():
            row[key] = float(row[key])
        else:
            row[key] = None
    return MacroTier2.model_validate(row)


def score_tier2_axes(
    macro: MacroTier2,
    rules: dict[str, Any],
) -> tuple[dict[str, float], list[ScoreBreakdownItem]]:
    """Tier2 매크로 → 4축 보조 점수 (-1~+1)."""
    cfg = rules.get("tier2", {})
    breakdown: list[ScoreBreakdownItem] = []
    growth = 0.0
    inflation = 0.0
    liquidity = 0.0
    risk = 0.0

    pmi_exp = float(cfg.get("pmi_expansion", 50))
    pmi_con = float(cfg.get("pmi_contraction", 48))
    if macro.pmi_kr is not None:
        if macro.pmi_kr >= pmi_exp:
            c = 0.3
            growth += c
        elif macro.pmi_kr < pmi_con:
            c = -0.3
            growth += c
        else:
            c = 0.0
        breakdown.append(
            ScoreBreakdownItem(axis="growth", indicator="tier2_pmi_kr", contribution=c, detail=f"PMI KR {macro.pmi_kr}")
        )
    if macro.pmi_us is not None:
        if macro.pmi_us >= pmi_exp:
            c = 0.2
            growth += c
        elif macro.pmi_us < pmi_con:
            c = -0.2
            growth += c
        else:
            c = 0.0
        breakdown.append(
            ScoreBreakdownItem(axis="growth", indicator="tier2_pmi_us", contribution=c, detail=f"PMI US {macro.pmi_us}")
        )

    cpi_high = float(cfg.get("cpi_high", 3.0))
    cpi_low = float(cfg.get("cpi_low", 1.5))
    if macro.cpi_kr_yoy is not None:
        if macro.cpi_kr_yoy >= cpi_high:
            c = 0.3
            inflation += c
        elif macro.cpi_kr_yoy <= cpi_low:
            c = -0.2
            inflation += c
        else:
            c = 0.0
        breakdown.append(
            ScoreBreakdownItem(
                axis="inflation", indicator="tier2_cpi_kr", contribution=c, detail=f"CPI KR {macro.cpi_kr_yoy}%"
            )
        )

    spread_pos = float(cfg.get("yield_spread_positive", 0.0))
    if macro.yield_spread_2y10y is not None:
        if macro.yield_spread_2y10y > spread_pos:
            c = 0.2
            growth += c
            liquidity += 0.1
        else:
            c = -0.2
            growth -= 0.1
            risk -= 0.1
        breakdown.append(
            ScoreBreakdownItem(
                axis="growth",
                indicator="tier2_yield_spread",
                contribution=c,
                detail=f"2Y-10Y {macro.yield_spread_2y10y:.2f}",
            )
        )

    hy_stress = float(cfg.get("hy_spread_stress", 500))
    hy_calm = float(cfg.get("hy_spread_calm", 350))
    if macro.hy_oas_bp is not None:
        if macro.hy_oas_bp >= hy_stress:
            c = -0.4
            liquidity += c
            risk += c
        elif macro.hy_oas_bp <= hy_calm:
            c = 0.2
            liquidity += c
            risk += c
        else:
            c = 0.0
        breakdown.append(
            ScoreBreakdownItem(
                axis="liquidity", indicator="tier2_hy_spread", contribution=c, detail=f"HY OAS {macro.hy_oas_bp}bp"
            )
        )

    real_tight = float(cfg.get("real_rate_tight", 2.5))
    if macro.real_rate_kr is not None:
        if macro.real_rate_kr >= real_tight:
            c = -0.2
            growth += c
            inflation += 0.1
        else:
            c = 0.1
            growth += c
        breakdown.append(
            ScoreBreakdownItem(
                axis="growth", indicator="tier2_real_rate", contribution=c, detail=f"실질금리 {macro.real_rate_kr}%"
            )
        )

    axes = {
        "growth": max(-1.0, min(1.0, growth)),
        "inflation": max(-1.0, min(1.0, inflation)),
        "liquidity": max(-1.0, min(1.0, liquidity)),
        "risk_appetite": max(-1.0, min(1.0, risk)),
    }
    return axes, breakdown


def blend_axis_scores(
    tier1: dict[str, float],
    tier2: dict[str, float],
    blend_weight: float,
) -> dict[str, float]:
    w2 = max(0.0, min(1.0, blend_weight))
    w1 = 1.0 - w2
    return {axis: round(tier1[axis] * w1 + tier2.get(axis, 0.0) * w2, 3) for axis in tier1}
