from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml

from src.exposure.core_saa_reference import load_core_saa_reference

CORE_SAA_MANDATE_DISCLAIMER = (
    "Core SAA benchmark-centered operating mode (excess return vs passive Core 14 ETF mix). "
    "Not a lossless or always-positive mandate. v1.0.2 execution requires data_gate, "
    "dry-run, throttle limits, scope, and human approval."
)
# Backward-compatible alias
ABSOLUTE_RETURN_DISCLAIMER = CORE_SAA_MANDATE_DISCLAIMER

KR_ALPHA_DEFAULTS: list[dict[str, str]] = [
    {"ticker": "030200", "name": "KT", "sector": "telecom", "role": "quality_dividend", "raw_weight": "7.02"},
    {"ticker": "021240", "name": "코웨이", "sector": "consumer", "role": "quality_defensive", "raw_weight": "7.02"},
    {"ticker": "005830", "name": "DB손해보험", "sector": "insurance", "role": "shareholder_return", "raw_weight": "4.9"},
    {"ticker": "000660", "name": "SK하이닉스", "sector": "semiconductor", "role": "defensive_consumer", "raw_weight": "3.52"},
    {"ticker": "006040", "name": "동원산업", "sector": "consumer", "role": "dividend_value", "raw_weight": "1.8"},
    {"ticker": "271560", "name": "오리온", "sector": "consumer", "role": "quality_defensive", "raw_weight": "1.8"},
    {"ticker": "036530", "name": "SNT홀딩스", "sector": "holding", "role": "shareholder_return", "raw_weight": "1.8"},
    {"ticker": "005440", "name": "현대지에프홀딩스", "sector": "holding", "role": "value_rerating", "raw_weight": "1.38"},
]


def load_absolute_return_policy(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "absolute_return_policy.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_core_etf_group_map(data_dir: Path) -> dict[str, str]:
    path = data_dir / "core_etf_asset_group_map.yaml"
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k).zfill(6): str(v) for k, v in raw.items() if k}


def _normalize_ticker(ticker: str | None) -> str | None:
    if not ticker:
        return None
    t = str(ticker).strip().upper()
    return t if t == "CASH" else t.zfill(6)


def build_absolute_return_target_rows(data_dir: Path) -> list[dict[str, Any]]:
    """Build target_portfolio rows: Core 75% + kr_alpha 25% + cash buffer."""
    policy = load_absolute_return_policy(data_dir)
    ref = load_core_saa_reference(data_dir)
    if not ref:
        raise ValueError("core_saa_reference.yaml required for absolute return target")

    structure = policy.get("portfolio_structure") or {}
    core_pct = float(structure.get("core_sleeve_target_pct") or 75.0)
    alpha_pct = float(structure.get("kr_alpha_overlay_max_pct") or 25.0)
    cash_buffer = float(structure.get("cash_buffer_max_pct") or 3.0)
    investable_scale = (100.0 - cash_buffer) / (core_pct + alpha_pct)
    core_deploy_pct = round(core_pct * investable_scale, 4)
    alpha_deploy_pct = round(alpha_pct * investable_scale, 4)
    unresolved_to = str(structure.get("unresolved_weight_to_ticker") or "157450").zfill(6)
    group_map = load_core_etf_group_map(data_dir)

    unresolved_weight = 0.0
    core_rows: list[dict[str, Any]] = []
    for asset in ref.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        tw = float(asset.get("target_weight_pct") or 0)
        ticker = _normalize_ticker(asset.get("ticker"))
        if tw <= 0 or not ticker:
            if tw > 0 and not ticker:
                unresolved_weight += tw
            continue
        if not asset.get("tradable", True):
            continue
        core_rows.append({"asset": asset, "ticker": ticker, "ref_weight": tw})

    for row in core_rows:
        if row["ticker"] == unresolved_to:
            row["ref_weight"] += unresolved_weight
            break

    rows: list[dict[str, Any]] = []
    for item in core_rows:
        asset = item["asset"]
        ticker = item["ticker"]
        tw = round(item["ref_weight"] * core_deploy_pct / 100.0, 2)
        if tw <= 0:
            continue
        group = group_map.get(ticker, "global_beta")
        rows.append({
            "ticker": ticker,
            "name": asset.get("name", ticker),
            "asset_group": group,
            "sector": asset.get("sleeve", group),
            "role": asset.get("role", "core_benchmark"),
            "target_weight": tw,
            "min_weight": round(tw * 0.7, 2),
            "max_weight": round(min(tw * 1.3, tw + 5), 2),
        })

    raw_alpha = sum(float(x["raw_weight"]) for x in KR_ALPHA_DEFAULTS)
    for item in KR_ALPHA_DEFAULTS:
        tw = round(float(item["raw_weight"]) / raw_alpha * alpha_deploy_pct, 2)
        rows.append({
            "ticker": item["ticker"],
            "name": item["name"],
            "asset_group": "kr_alpha",
            "sector": item["sector"],
            "role": item["role"],
            "target_weight": tw,
            "min_weight": round(tw * 0.5, 2),
            "max_weight": round(min(tw * 1.5, alpha_pct), 2),
        })

    rows.append({
        "ticker": "CASH",
        "name": "예수금/CMA/MMF",
        "asset_group": "cash_short_bond",
        "sector": "cash",
        "role": "cash_buffer",
        "target_weight": cash_buffer,
        "min_weight": 1.0,
        "max_weight": round(cash_buffer * 2, 2),
    })

    total = round(sum(r["target_weight"] for r in rows), 2)
    drift = round(100.0 - total, 2)
    if drift != 0:
        idx = max(range(len(rows)), key=lambda i: rows[i]["target_weight"])
        rows[idx]["target_weight"] = round(rows[idx]["target_weight"] + drift, 2)

    return rows


def write_absolute_return_target_portfolio(data_dir: Path, *, approve: bool = False) -> Path:
    """Writes data/target_portfolio.csv only when approve=True (explicit human/CLI approval)."""
    from src.alpha.target_portfolio_guard import (
        TargetPortfolioWriteBlockedError,
        write_target_portfolio_approved,
    )

    if not approve:
        raise TargetPortfolioWriteBlockedError(
            "target_portfolio.csv auto-overwrite blocked. "
            "Use --approve-target or write_target_portfolio_approved(approve=True)."
        )
    rows = build_absolute_return_target_rows(data_dir)
    return write_target_portfolio_approved(
        data_dir,
        rows,
        approved_by="absolute_return_policy",
        reason="approve=True",
        source="manual_admin_override",
    )


def aggregate_group_targets(rows: list[dict[str, Any]]) -> dict[str, float]:
    groups: dict[str, float] = {}
    for row in rows:
        g = str(row.get("asset_group", ""))
        groups[g] = round(groups.get(g, 0) + float(row["target_weight"]), 2)
    return groups


def build_absolute_return_status(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    policy = load_absolute_return_policy(data_dir)
    target_rows = build_absolute_return_target_rows(data_dir)
    group_targets = aggregate_group_targets(target_rows)

    from src.exposure.core_saa_reference import build_core_saa_reference_diagnostic

    diag = build_core_saa_reference_diagnostic(data_dir, as_of="") or {}
    summary = diag.get("summary") or {}

    underweights = sorted(
        [
            r for r in (diag.get("core_assets") or [])
            if r.get("tradable") and float(r.get("core_target_weight_pct") or 0) > 0
            and float(r.get("gap_pct") or 0) < -1.0
        ],
        key=lambda x: float(x.get("gap_pct") or 0),
    )[:5]

    structure = policy.get("portfolio_structure") or {}
    cash_buffer = float(structure.get("cash_buffer_max_pct") or 3.0)
    core_nominal = float(structure.get("core_sleeve_target_pct") or 75.0)
    alpha_nominal = float(structure.get("kr_alpha_overlay_max_pct") or 25.0)
    core_scaled = round(
        sum(
            float(r["target_weight"])
            for r in target_rows
            if r.get("asset_group") != "kr_alpha" and r.get("ticker") != "CASH"
        ),
        2,
    )
    alpha_scaled = round(group_targets.get("kr_alpha", 0), 2)

    return {
        "mode": "core_saa_benchmark_mandate",
        "mode_label_ko": (policy.get("mode_label_ko") or "Core SAA 기준 초과수익 운영 모드"),
        "primary_objective": policy.get("primary_objective"),
        "disclaimer": CORE_SAA_MANDATE_DISCLAIMER,
        "benchmark_source": "data/core_saa_reference.yaml",
        "framework_label": (policy.get("framework") or {}).get("label"),
        "nominal_core_sleeve_pct": core_nominal,
        "nominal_kr_alpha_overlay_max_pct": alpha_nominal,
        "portfolio_scaled_core_sleeve_pct": core_scaled,
        "portfolio_scaled_kr_alpha_pct": alpha_scaled,
        "cash_buffer_pct": cash_buffer,
        "core_sleeve_target_pct": core_nominal,
        "kr_alpha_overlay_max_pct": alpha_nominal,
        "group_targets": group_targets,
        "core_held_count": summary.get("core_held_count"),
        "core_reference_count": summary.get("core_reference_count"),
        "core_current_weight_sum_pct": summary.get("core_current_weight_sum_pct"),
        "core_target_weight_sum_pct": summary.get("core_target_weight_sum_pct"),
        "top_core_underweights": underweights,
        "target_ticker_count": len(target_rows),
    }


def write_absolute_return_status(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    if not load_core_saa_reference(data_dir):
        return {"skipped": True, "reason": "core_saa_reference.yaml missing or invalid"}
    status = build_absolute_return_status(data_dir, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "absolute_return_mandate_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return status
