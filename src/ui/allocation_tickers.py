from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.compass.profile_aliases import resolve_profile_name
from src.compass.saa_engine import get_saa_weights, load_saa_profiles
from src.data_loader import load_target_portfolio
from src.models import VALID_ASSET_GROUPS

ASSET_GROUP_LABELS: dict[str, str] = {
    "cash_short_bond": "현금·채권",
    "domestic_beta": "국내 베타",
    "global_beta": "글로벌 베타",
    "fx_dollar": "달러·FX",
    "hedge_alt": "헤지(금 등)",
    "income_alt": "인컴",
    "kr_alpha": "국내 알파",
}


def _normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip()
    return t.zfill(6) if t.isdigit() else t


def _group_template(template: list) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for row in template:
        grouped.setdefault(row.asset_group, []).append(row)
    return grouped


def build_saa_ticker_targets(data_dir: Path, profile: str | None = None) -> pd.DataFrame:
    """SAA 기준 자산군 비중 → 템플릿 종목 target (TAA 미적용)."""
    profiles = load_saa_profiles(data_dir / "saa_profiles.yaml")
    saa = get_saa_weights(profiles, profile)
    template = load_target_portfolio(data_dir / "target_portfolio.csv")
    grouped = _group_template(template)
    rows: list[dict] = []

    for group in sorted(VALID_ASSET_GROUPS):
        group_rows = grouped.get(group, [])
        if not group_rows:
            continue
        template_sum = sum(r.target_weight for r in group_rows)
        if template_sum <= 0:
            continue
        group_target = saa.get(group, 0.0)
        scale = group_target / template_sum
        label = ASSET_GROUP_LABELS.get(group, group)
        for row in group_rows:
            rows.append(
                {
                    "ticker": _normalize_ticker(row.ticker),
                    "name": row.name,
                    "asset_group": group,
                    "자산군": label,
                    "role": row.role,
                    "SAA목표(%)": round(row.target_weight * scale, 2),
                    "템플릿비중(%)": round(row.target_weight, 2),
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["asset_group", "SAA목표(%)"], ascending=[True, False])


def build_taa_ticker_targets(output_dir: Path, data_dir: Path) -> pd.DataFrame:
    """TAA 반영 최종 종목 target (`generated_target_portfolio.csv`)."""
    path = output_dir / "generated_target_portfolio.csv"
    if path.exists():
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    else:
        df = pd.read_csv(data_dir / "target_portfolio.csv", dtype=str, keep_default_na=False)

    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["ticker"] = df["ticker"].map(_normalize_ticker)
    df["target_weight"] = pd.to_numeric(df["target_weight"], errors="coerce").fillna(0)
    df["자산군"] = df["asset_group"].map(ASSET_GROUP_LABELS).fillna(df["asset_group"])
    cols = ["ticker", "name", "자산군", "asset_group", "role", "target_weight", "min_weight", "max_weight"]
    cols = [c for c in cols if c in df.columns]
    out = df[cols].rename(columns={"target_weight": "TAA목표(%)"})
    return out.sort_values(["asset_group", "TAA목표(%)"], ascending=[True, False])
