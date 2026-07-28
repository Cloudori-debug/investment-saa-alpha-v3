from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

MANUAL_OVERRIDE_COLUMNS = [
    "ticker",
    "name",
    "net_cash_override",
    "treasury_share_ratio_override",
    "holding_company_nav_discount_override",
    "real_estate_asset_value_override",
    "activist_event_override",
    "listed_subsidiary_ticker",
    "ownership_pct",
    "subsidiary_market_value",
    "ownership_adjusted_value",
    "evidence_note",
    "source_date",
    "source_url",
    "manual_override_flag",
]


def ensure_manual_overrides_template(data_dir: Path) -> Path:
    path = data_dir / "hakedaka_manual_overrides.csv"
    if not path.exists():
        pd.DataFrame(columns=MANUAL_OVERRIDE_COLUMNS).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def _manual_has_valid_source(row: dict[str, Any]) -> bool:
    if not str(row.get("source_date", "")).strip():
        return False
    return bool(str(row.get("source_url", "")).strip() or str(row.get("evidence_note", "")).strip())


def load_manual_overrides(data_dir: Path) -> dict[str, dict[str, Any]]:
    path = ensure_manual_overrides_template(data_dir)
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    out: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        t = str(row.get("ticker", "")).zfill(6)
        if not t:
            continue
        flag = str(row.get("manual_override_flag", "")).lower() in {"true", "1", "yes"}
        if not flag and not str(row.get("evidence_note", "")).strip():
            continue
        row_dict = dict(row)
        if not _manual_has_valid_source(row_dict):
            continue
        out[t] = row_dict
        out[t]["manual_override_flag"] = True
    return out


def validate_manual_overrides(data_dir: Path) -> list[str]:
    warnings: list[str] = []
    path = ensure_manual_overrides_template(data_dir)
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for _, row in df.iterrows():
        t = str(row.get("ticker", "")).zfill(6)
        if not t:
            continue
        flag = str(row.get("manual_override_flag", "")).lower() in {"true", "1", "yes"}
        if not flag and not str(row.get("evidence_note", "")).strip():
            continue
        if not str(row.get("source_date", "")).strip():
            warnings.append(f"{t}:manual_missing_source_date")
        if not str(row.get("source_url", "")).strip() and not str(row.get("evidence_note", "")).strip():
            warnings.append(f"{t}:manual_missing_source")
        elif not _manual_has_valid_source(dict(row)):
            warnings.append(f"{t}:manual_not_applied_missing_source")
    return warnings


def apply_manual_to_fundamentals(
    fund: dict[str, Any] | None,
    manual: dict[str, Any] | None,
) -> dict[str, Any]:
    base = dict(fund or {})
    if not manual or not manual.get("manual_override_flag"):
        return base
    mapping = {
        "net_cash_override": "net_cash",
        "treasury_share_ratio_override": "treasury_share_ratio",
        "holding_company_nav_discount_override": "holding_company_discount_proxy",
        "real_estate_asset_value_override": "asset_value_discount_proxy",
    }
    for src, dst in mapping.items():
        val = manual.get(src, "")
        if val not in (None, ""):
            base[dst] = val
            base[f"{dst}_manual"] = True
    if manual.get("activist_event_override"):
        base["governance_event_flag"] = True
        base["governance_event_manual"] = True
    base["manual_evidence_note"] = manual.get("evidence_note", "")
    base["manual_source_date"] = manual.get("source_date", "")
    base["manual_source_url"] = manual.get("source_url", "")
    return base
