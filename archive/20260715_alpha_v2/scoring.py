from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.alpha.factor_scoring import score_factors
from src.alpha.loaders import load_fundamentals, load_prices
from src.alpha.penalty_engine import apply_penalties, assign_grades
from src.alpha.schemas import FundamentalRecord, PriceRecord, UniverseRecord
from src.config import load_yaml

from src.alpha_v2.schemas import GRADE_A_MIN, GRADE_B_MIN, GRADE_C_MIN, GRADE_D_MIN


def assign_grade_v2(total_score_v1: float) -> str:
    if total_score_v1 >= GRADE_A_MIN:
        return "A"
    if total_score_v1 >= GRADE_B_MIN:
        return "B"
    if total_score_v1 >= GRADE_C_MIN:
        return "C"
    if total_score_v1 >= GRADE_D_MIN:
        return "D"
    return "Reject"


def _load_v1_scored(output_dir: Path) -> dict[str, dict[str, Any]]:
    path = output_dir / "alpha_scored_universe.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return {str(rec.get("ticker", "")).zfill(6): dict(rec) for rec in df.to_dict(orient="records")}


def score_alpha_v2_universe(
    universe: list[UniverseRecord],
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
) -> list[dict[str, Any]]:
    """Reuse v1 Q/V/M/SR scoring; v2 grade on total_score_v1 only."""
    config_path = data_dir / "alpha_scoring.yaml"
    config = load_yaml(config_path) if config_path.exists() else {}
    fundamentals = {r.ticker: r for r in load_fundamentals(data_dir / "fundamentals.csv")}
    prices = {r.ticker: r for r in load_prices(data_dir / "prices.csv", as_of=as_of)}
    universe_by_ticker = {u.ticker: u for u in universe}
    v1_scored = _load_v1_scored(output_dir)

    missing = [rec for rec in universe if rec.ticker not in v1_scored]
    freshly_scored: dict[str, dict[str, Any]] = {}
    if missing:
        base = score_factors(missing, fundamentals, prices, config)
        penalized = apply_penalties(base, universe_by_ticker, fundamentals, prices, config)
        for row in assign_grades(penalized, config):
            freshly_scored[row["ticker"]] = row

    scored: list[dict[str, Any]] = []
    for rec in universe:
        src = v1_scored.get(rec.ticker) or freshly_scored.get(rec.ticker)
        if not src:
            continue
        row = dict(src)
        row["ticker"] = rec.ticker
        row["name"] = row.get("name") or rec.name
        row["sector"] = row.get("sector") or rec.sector
        row["market"] = rec.market
        ts = float(row.get("total_score") or row.get("base_score") or 0)
        row["total_score_v1"] = round(ts, 2)
        row["grade_v1"] = str(row.get("grade") or assign_grade_v2(ts))
        row["grade"] = assign_grade_v2(ts)
        row["value_trap_flag"] = "가치함정" in str(row.get("key_reason", ""))
        scored.append(row)
    return scored
