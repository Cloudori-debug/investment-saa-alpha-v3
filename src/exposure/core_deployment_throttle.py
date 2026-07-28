"""Core SAA benchmark ETF deployment throttle (Phase AR-1).

Caps Core ETF buy sizing per run / week / month. Does not bypass data_gate,
dry-run, or execution_scope — applies only after those gates allow Buy-allowed.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.exposure.absolute_return_policy import load_absolute_return_policy
from src.exposure.core_saa_reference import load_core_saa_reference
from src.models import GapRow, TradeAction

CORE_SAA_MANDATE_DISCLAIMER = (
    "Core SAA benchmark-centered operating mode (excess return vs passive Core 14 ETF mix). "
    "Not a lossless or always-positive mandate. v1.0.2 execution requires data_gate, "
    "dry-run, throttle limits, scope, and human approval."
)

DEFAULT_THROTTLE = {
    "per_trade_max_pct": 3.0,
    "per_run_total_max_pct": 3.0,
    "weekly_max_pct": 5.0,
    "monthly_max_pct": 10.0,
    "gate_required": "GREEN",
    "dry_run_required": True,
}


def load_core_benchmark_tickers(data_dir: Path) -> frozenset[str]:
    ref = load_core_saa_reference(data_dir)
    if not ref:
        return frozenset()
    tickers: set[str] = set()
    for asset in ref.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        if not asset.get("tradable", True):
            continue
        tw = float(asset.get("target_weight_pct") or 0)
        ticker = asset.get("ticker")
        if tw > 0 and ticker:
            tickers.add(str(ticker).strip().zfill(6))
    return frozenset(tickers)


def load_deployment_throttle(data_dir: Path) -> dict[str, Any]:
    policy = load_absolute_return_policy(data_dir)
    raw = policy.get("deployment_throttle") or {}
    merged = {**DEFAULT_THROTTLE, **raw}
    return merged


def _parse_date(s: str) -> datetime | None:
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _ledger_path(output_dir: Path) -> Path:
    return output_dir / "core_deployment_ledger.jsonl"


def sum_executed_deployment(
    output_dir: Path,
    *,
    as_of: str,
    window_days: int,
) -> float:
    """Sum executed Core ETF deployment from ledger within window_days (inclusive)."""
    path = _ledger_path(output_dir)
    if not path.exists():
        return 0.0
    as_dt = _parse_date(as_of)
    if not as_dt:
        return 0.0
    cutoff = as_dt - timedelta(days=window_days - 1)
    total = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("status") != "executed":
            continue
        entry_dt = _parse_date(str(entry.get("date") or entry.get("executed_at", "")))
        if not entry_dt or entry_dt < cutoff or entry_dt > as_dt:
            continue
        total += float(entry.get("deployed_pct") or 0)
    return round(total, 2)


def record_core_deployment_execution(
    output_dir: Path,
    *,
    date: str,
    ticker: str,
    deployed_pct: float,
    note: str = "",
) -> Path:
    """Append an executed Core ETF deployment (manual or post-trade)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = _ledger_path(output_dir)
    entry = {
        "schema_version": "core_deployment_ledger.v1",
        "status": "executed",
        "date": date[:10],
        "ticker": str(ticker).strip().zfill(6),
        "deployed_pct": round(float(deployed_pct), 2),
        "note": note,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def _gate_allows_throttle(
    *,
    data_gate: str,
    dry_run_days: int,
    dry_run_required: int,
    throttle: dict[str, Any],
) -> tuple[bool, str | None]:
    required_gate = str(throttle.get("gate_required") or "GREEN")
    if data_gate != required_gate:
        return False, f"data_gate {data_gate} — Core ETF deploy blocked (requires {required_gate})"
    if throttle.get("dry_run_required") and dry_run_days < dry_run_required:
        return False, (
            f"dry-run {dry_run_days}/{dry_run_required} incomplete — Core ETF deploy blocked"
        )
    return True, None


def apply_core_deployment_throttle(
    actions: list[TradeAction],
    gap_rows: list[GapRow],
    *,
    data_dir: Path,
    output_dir: Path,
    data_gate: str,
    dry_run_days: int,
    dry_run_required: int = 10,
    as_of: str = "",
) -> tuple[list[TradeAction], dict[str, Any]]:
    """Cap or downgrade Core benchmark Buy-allowed actions under throttle policy."""
    throttle = load_deployment_throttle(data_dir)
    core_tickers = load_core_benchmark_tickers(data_dir)
    gap_map = {r.ticker: r for r in gap_rows}

    allowed, block_reason = _gate_allows_throttle(
        data_gate=data_gate,
        dry_run_days=dry_run_days,
        dry_run_required=dry_run_required,
        throttle=throttle,
    )

    weekly_used = sum_executed_deployment(output_dir, as_of=as_of, window_days=7) if as_of else 0.0
    monthly_used = sum_executed_deployment(output_dir, as_of=as_of, window_days=30) if as_of else 0.0
    weekly_remain = max(0.0, float(throttle["weekly_max_pct"]) - weekly_used)
    monthly_remain = max(0.0, float(throttle["monthly_max_pct"]) - monthly_used)
    budget_remain = round(min(weekly_remain, monthly_remain), 2)

    per_trade = float(throttle["per_trade_max_pct"])
    per_run_total = float(throttle["per_run_total_max_pct"])

    adjusted: list[TradeAction] = []
    run_budget = per_run_total if allowed else 0.0
    throttled_count = 0
    blocked_count = 0

    core_buys = [
        a for a in actions
        if a.action == "Buy-allowed" and a.ticker in core_tickers
    ]
    other = [a for a in actions if a not in core_buys]
    core_buys.sort(
        key=lambda a: float(getattr(gap_map.get(a.ticker), "gap", 0) or 0),
        reverse=True,
    )

    for act in other:
        adjusted.append(act)

    for act in core_buys:
        if not allowed:
            adjusted.append(
                act.model_copy(
                    update={
                        "action": "Wait",
                        "reason": block_reason or "Core ETF deploy throttle — gate blocked",
                        "allowed_size_pct": 0,
                        "priority": "Medium",
                    }
                )
            )
            blocked_count += 1
            continue

        if budget_remain <= 0 or run_budget <= 0:
            adjusted.append(
                act.model_copy(
                    update={
                        "action": "Wait",
                        "reason": (
                            f"Core ETF throttle — weekly/monthly budget exhausted "
                            f"(used 7D {weekly_used}%p / 30D {monthly_used}%p)"
                        ),
                        "allowed_size_pct": 0,
                        "priority": "Medium",
                    }
                )
            )
            blocked_count += 1
            continue

        cap = min(
            float(act.allowed_size_pct),
            per_trade,
            run_budget,
            budget_remain,
        )
        row = gap_map.get(act.ticker)
        if row:
            cap = min(cap, float(row.gap), float(row.max_weight) - float(row.current_weight))

        cap = round(max(0.0, cap), 2)
        if cap < 0.5:
            adjusted.append(
                act.model_copy(
                    update={
                        "action": "Wait",
                        "reason": (
                            f"Core ETF throttle — deploy cap {cap}%p below minimum "
                            f"(per-trade {per_trade}%p, run remain {run_budget}%p)"
                        ),
                        "allowed_size_pct": 0,
                        "priority": "Medium",
                    }
                )
            )
            blocked_count += 1
            continue

        if cap < float(act.allowed_size_pct):
            throttled_count += 1
            reason = (
                f"{act.reason} — Core throttle cap {cap}%p "
                f"(per-trade {per_trade}%p, run max {per_run_total}%p)"
            )
        else:
            reason = act.reason

        adjusted.append(
            act.model_copy(
                update={
                    "reason": reason,
                    "allowed_size_pct": cap,
                }
            )
        )
        run_budget = round(run_budget - cap, 2)
        budget_remain = round(budget_remain - cap, 2)

    meta = {
        "mode": "core_saa_deployment_throttle",
        "active": True,
        "gate_allowed": allowed,
        "block_reason": block_reason,
        "limits": {
            "per_trade_max_pct": per_trade,
            "per_run_total_max_pct": per_run_total,
            "weekly_max_pct": float(throttle["weekly_max_pct"]),
            "monthly_max_pct": float(throttle["monthly_max_pct"]),
        },
        "usage": {
            "weekly_executed_pct": weekly_used,
            "monthly_executed_pct": monthly_used,
            "weekly_remaining_pct": weekly_remain,
            "monthly_remaining_pct": monthly_remain,
        },
        "core_buy_allowed_count": sum(
            1 for a in adjusted if a.action == "Buy-allowed" and a.ticker in core_tickers
        ),
        "core_buy_throttled_count": throttled_count,
        "core_buy_blocked_count": blocked_count,
        "disclaimer": CORE_SAA_MANDATE_DISCLAIMER,
    }
    return adjusted, meta


def _executable_final_trades(actions: list[TradeAction]) -> list[TradeAction]:
    """Real deployment trades — excludes Wait/Hold/Park and zero-size rows."""
    return [
        a for a in actions
        if a.action in {"Buy-allowed", "Add", "Trim"}
        and float(a.allowed_size_pct or 0) > 0
        and a.ticker not in {"PORTFOLIO", "CASH"}
    ]


def build_ar1_parity_check(
    data_dir: Path,
    output_dir: Path,
    *,
    actions: list[TradeAction] | None = None,
    gap_rows: list[GapRow] | None = None,
    data_gate: str = "",
    execution_scope: str = "",
    dry_run_days: int = 0,
    dry_run_required: int = 10,
    throttle_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Phase AR-1 / AR-1.1 parity checklist vs target/trade/execution layers."""
    from src.data_loader import load_target_portfolio
    from src.exposure.ar11_target_integrity import compute_target_integrity
    from src.exposure.absolute_return_policy import (
        aggregate_group_targets,
        build_absolute_return_target_rows,
        load_absolute_return_policy,
    )

    policy = load_absolute_return_policy(data_dir)
    structure = policy.get("portfolio_structure") or {}
    cash_buffer = float(structure.get("cash_buffer_max_pct") or 3.0)
    investable = 100.0 - cash_buffer
    core_nominal = float(structure.get("core_sleeve_target_pct") or 75.0)
    alpha_nominal = float(structure.get("kr_alpha_overlay_max_pct") or 25.0)
    scale = investable / (core_nominal + alpha_nominal)

    rows = build_absolute_return_target_rows(data_dir)
    groups = aggregate_group_targets(rows)
    total = round(sum(r["target_weight"] for r in rows), 2)
    cash_row = next((r for r in rows if r["ticker"] == "CASH"), None)
    core_rows = [r for r in rows if r["ticker"] not in {"CASH"} and r["asset_group"] != "kr_alpha"]
    core_sum = round(sum(r["target_weight"] for r in core_rows), 2)
    alpha_sum = round(groups.get("kr_alpha", 0), 2)

    act_list = actions or []
    core_tickers = load_core_benchmark_tickers(data_dir)
    gap_map = {r.ticker: r for r in (gap_rows or [])}
    kr_alpha_tickers = {r["ticker"] for r in rows if r.get("asset_group") == "kr_alpha"}

    core_buys = [
        a for a in act_list
        if a.action == "Buy-allowed" and a.ticker in core_tickers
    ]
    bulk_core_buy = any(float(a.allowed_size_pct) > 3.0 for a in core_buys)
    kr_alpha_buys = [
        a for a in act_list
        if a.action == "Buy-allowed" and a.ticker in kr_alpha_tickers
    ]
    executable_buys = [
        a for a in act_list
        if a.action in {"Buy-allowed", "Add"} and float(a.allowed_size_pct) > 0
    ]
    executable_final_trades = _executable_final_trades(act_list)

    throttle = throttle_meta or {}
    if not throttle and (output_dir / "core_deployment_throttle_status.json").exists():
        try:
            throttle = json.loads(
                (output_dir / "core_deployment_throttle_status.json").read_text(encoding="utf-8")
            )
        except json.JSONDecodeError:
            throttle = {}

    framework = policy.get("framework") or {}
    proxy = policy.get("unresolved_weight_proxy") or {}

    template_path = data_dir / "target_portfolio.csv"
    template_rows = load_target_portfolio(template_path) if template_path.exists() else []
    template_sum = round(sum(r.target_weight for r in template_rows), 2)

    generated_rows: list[Any] = []
    gen_path = output_dir / "generated_target_portfolio.csv"
    if gen_path.exists():
        generated_rows = load_target_portfolio(gen_path)
    pipeline_rows = generated_rows if generated_rows else template_rows
    pipeline_sum = round(sum(r.target_weight for r in pipeline_rows), 2)

    domestic_final = 0.0
    unallocated = 0.0
    group_sec_gap = 0.0
    alloc_csv = output_dir / "target_asset_allocation.csv"
    group_sum_from_alloc = 0.0
    if alloc_csv.exists():
        import csv
        with alloc_csv.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("asset_group") == "domestic_beta":
                    domestic_final = float(row.get("final_target") or 0)
                group_sum_from_alloc += float(row.get("final_target") or 0)
        group_sum_from_alloc = round(group_sum_from_alloc, 2)
    integrity = compute_target_integrity(
        security_targets=pipeline_rows,
        allocation=None,
        template=template_rows,
    )
    if group_sum_from_alloc > 0:
        integrity = {**integrity, "asset_group_target_sum_pct": group_sum_from_alloc}
    elif float(integrity.get("asset_group_target_sum_pct") or 0) == 0 and pipeline_sum > 0:
        integrity = {**integrity, "asset_group_target_sum_pct": pipeline_sum}
    unallocated = float(integrity.get("unallocated_target_pct") or 0)
    group_sec_gap = abs(float(integrity.get("asset_group_vs_security_gap_pct") or 0))

    validation_errors: list[str] = []
    log_path = output_dir / "decision_log.jsonl"
    if log_path.exists():
        for line in reversed(log_path.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            validation_errors = list(entry.get("validation_errors") or [])
            break

    has_target_sum_error = any("target weights must sum" in e for e in validation_errors)

    checks = {
        "target_portfolio_template_sum_100": abs(template_sum - 100.0) < 0.01,
        "target_portfolio_sum_100_actual": abs(pipeline_sum - 100.0) < 0.01,
        "asset_group_vs_security_target_sum_match": group_sec_gap <= 0.05,
        "domestic_beta_zero_when_excluded": abs(domestic_final) < 0.01,
        "no_unallocated_target_pct": unallocated <= 0.01,
        "target_sum_100": abs(total - 100.0) < 0.01,
        "core_sleeve_scaled": abs(core_sum - round(core_nominal * scale, 2)) < 0.2,
        "core_scaled_pct_matches_actual_rows": abs(core_sum - round(core_nominal * scale, 2)) < 0.2,
        "alpha_sleeve_scaled": abs(alpha_sum - round(alpha_nominal * scale, 2)) < 0.2,
        "cash_buffer_3": cash_row is not None and abs(float(cash_row["target_weight"]) - cash_buffer) < 0.1,
        "no_bulk_core_buy_over_3pct": not bulk_core_buy,
        "kr_alpha_new_buy_blocked": len(kr_alpha_buys) == 0,
        "core_etf_buy_zero": len(core_buys) == 0,
        "no_executable_buy_actions": len(executable_buys) == 0,
        "no_validation_target_sum_error": not has_target_sum_error,
        "gate_red_final_trades_empty": (
            data_gate != "RED" or len(executable_final_trades) == 0
        ),
        "gate_red_no_trade_scope": (
            data_gate != "RED" or execution_scope in {"NO_TRADE", ""}
        ),
        "throttle_gate_blocked_when_not_green": (
            data_gate == "GREEN" or throttle.get("gate_allowed") is False
        ),
        "gate_yellow_blocks_core_buy": not (data_gate == "YELLOW" and len(core_buys) > 0),
        "dry_run_incomplete_blocks": not (
            dry_run_days < dry_run_required and len(core_buys) > 0
        ),
        "execution_scope_etf_only_ok": execution_scope in {
            "ETF_ONLY", "ETF_ONLY_ALPHA_REVIEW", "NO_TRADE", "ETF_AND_BETA", "FULL_WITH_ALPHA", ""
        },
        "no_069500_in_template": not any(r.ticker == "069500" for r in template_rows),
    }

    return {
        "phase": "AR-1.1",
        "mode": "core_saa_mandate_parity",
        "framework_label": framework.get("label"),
        "active_core_etf_target_count": framework.get("active_core_etf_target_count"),
        "unresolved_proxy_warning": proxy.get("warning"),
        "nominal_core_sleeve_pct": core_nominal,
        "portfolio_scaled_core_sleeve_pct": core_sum,
        "nominal_kr_alpha_overlay_max_pct": alpha_nominal,
        "portfolio_scaled_kr_alpha_pct": alpha_sum,
        "target_total_pct": total,
        "template_target_sum_pct": template_sum,
        "pipeline_target_sum_pct": pipeline_sum,
        "unallocated_target_pct": unallocated,
        "domestic_beta_final_pct": domestic_final,
        "core_sleeve_pct": core_sum,
        "alpha_sleeve_pct": alpha_sum,
        "cash_buffer_pct": float(cash_row["target_weight"]) if cash_row else None,
        "group_targets": groups,
        "target_integrity": integrity,
        "validation_errors_last": validation_errors,
        "data_gate": data_gate,
        "execution_scope": execution_scope,
        "dry_run_days": dry_run_days,
        "dry_run_required": dry_run_required,
        "core_buy_allowed_count": len(core_buys),
        "executable_buy_count": len(executable_buys),
        "executable_final_trade_count": len(executable_final_trades),
        "final_trade_count": len(executable_final_trades),
        "throttle_gate_allowed": throttle.get("gate_allowed"),
        "checks": checks,
        "all_pass": all(checks.values()),
        "note": (
            "AR-1.1: all_pass requires pipeline security target sum = 100%, domestic_beta = 0, "
            "no orphan unallocated group weight. Gate RED/NO_TRADE → zero execution."
        ),
    }


def write_core_deployment_throttle_status(
    output_dir: Path,
    meta: dict[str, Any],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "core_deployment_throttle_status.json"
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_ar1_parity_check(
    output_dir: Path,
    parity: dict[str, Any],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "ar1_parity_check.json"
    path.write_text(json.dumps(parity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
