from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from src.models import GapRow, MarketIndicators, TradeAction, TriggerAlert, TriggerStatus
from src.trigger_engine import _pct_drawdown, is_buy_trigger_active, is_stop_buy
from src.trigger_metrics import (
    list_all_active_triggers,
    list_risk_reduce_active_triggers,
    list_suppressed_signals,
    list_watch_triggers,
)

from src.decision.shadow_performance import build_performance_fields, derive_primary_blocker
from src.decision.duration_diagnostic import format_duration_report_line

SHADOW_SCHEMA_VERSION = "1.0"
SHADOW_MODE = "shadow"
EXECUTION_AUTHORITY = "v1.0.2"

# 진단 전용 — v1.0.2 실행 로직 변경 없음
LADDER_RESERVE_CAP_PPT = 25.0
LADDER_STAGE_PCT: dict[str, float] = {
    "WATCH": 0.0,
    "L1": 0.20,
    "L2": 0.50,
    "L3": 0.80,
    "L4": 1.0,
}

OPS_SHADOW_LOG_FIELDS = [
    "date",
    "run_id",
    "buy_trigger_active",
    "signal_execution_mismatch",
    "execution_status",
    "primary_blocker",
    "blocked_by_primary",
    "blocked_by_all",
    "dip_stage",
    "theoretical_gap_krw",
    "reviewable_amount_krw",
    "actual_allowed_krw",
    "portfolio_value_krw",
    "benchmark_saa_return_1d",
    "benchmark_saa_return_mtd",
    "portfolio_return_mtd",
    "vs_saa_mtd",
    "missed_buy_return_after_5d",
    "missed_buy_return_after_20d",
    "blocked_decision_outcome",
    "execution_scope",
    "data_gate",
    "operational_status",
    "theoretical_buy_count",
    "executable_buy_count",
    "etf_fully_blocked",
    "alpha_only_blocked",
    "cash_short_current_pct",
    "kr_duration_current_pct",
    "duration_gap",
    "duration_diagnosis",
]


def _portfolio_value(positions: list[Any]) -> float:
    return sum(float(getattr(p, "current_value", 0) or 0) for p in positions)


def _cash_short_target_pct(allocation_groups: list[Any] | None) -> float:
    if not allocation_groups:
        return 40.0
    for g in allocation_groups:
        group = getattr(g, "asset_group", None) or (g.get("asset_group") if isinstance(g, dict) else None)
        if group == "cash_short_bond":
            return float(
                getattr(g, "final_target", None)
                or (g.get("final_target") if isinstance(g, dict) else 0)
                or 0
            )
    return 40.0


def _sum_buy_gap_krw(
    actions: list[TradeAction],
    portfolio_value: float,
) -> tuple[float, int]:
    total = 0.0
    count = 0
    for act in actions:
        if act.action not in {"Buy-allowed", "Add"}:
            continue
        if act.allowed_size_pct <= 0:
            continue
        total += portfolio_value * act.allowed_size_pct / 100.0
        count += 1
    return round(total), count


def _sum_underweight_gap_krw(gap_rows: list[GapRow], portfolio_value: float) -> float:
    total = 0.0
    for row in gap_rows:
        if row.ticker.upper() == "CASH":
            continue
        if row.gap <= 0:
            continue
        total += portfolio_value * row.gap / 100.0
    return round(total)


def collect_blocked_by(
    *,
    data_gate: str,
    health_gate: str,
    portfolio_gate: str,
    alpha_gate: str | None,
    execution_scope: str,
    core_price_gate: str,
    dry_run_days: int,
    dry_run_required: int,
    policy_cap_active: bool,
    cap_regime: str | None,
    alpha_trade_permission: str,
    stop_buy: bool,
    systemic_stress: bool,
) -> list[str]:
    blocked: list[str] = []
    if core_price_gate == "fail":
        blocked.append("core_price_gate")
    if data_gate == "RED":
        blocked.append("data_gate_red")
    elif data_gate == "YELLOW":
        blocked.append("data_gate_yellow")
    if health_gate == "RED":
        blocked.append("health_gate_red")
    elif health_gate == "YELLOW":
        blocked.append("health_gate_yellow")
    if portfolio_gate == "RED":
        blocked.append("portfolio_gate_red")
    if alpha_gate == "RED":
        blocked.append("alpha_gate_red")
    if execution_scope == "NO_TRADE":
        blocked.append("execution_scope_no_trade")
    elif execution_scope == "ETF_ONLY":
        blocked.append("execution_scope_etf_only")
    elif execution_scope == "ETF_ONLY_ALPHA_REVIEW":
        blocked.append("execution_scope_etf_review")
    if dry_run_days < dry_run_required:
        blocked.append("dry_run")
    if policy_cap_active:
        blocked.append("policy_cap")
        if cap_regime:
            blocked.append(f"policy_cap_{cap_regime.lower()}")
    if alpha_trade_permission in {"BLOCK_NEW_BUY", "BLOCK_ALL"}:
        blocked.append("alpha_trade_blocked")
    if stop_buy:
        blocked.append("stop_buy")
    if systemic_stress:
        blocked.append("systemic_stress")
    return blocked


def derive_dip_ladder_stage(
    kospi_dd: float | None,
    *,
    systemic_stress: bool,
) -> tuple[str, list[str]]:
    if kospi_dd is None:
        return "UNKNOWN", ["kospi_drawdown_unavailable"]
    if systemic_stress:
        return "INACTIVE", ["systemic_stress"]
    if kospi_dd > -5:
        return "WATCH", []
    if kospi_dd > -10:
        return "L1", []
    if kospi_dd > -15:
        return "L2", []
    if kospi_dd > -20:
        return "L3", []
    return "L4", []


def compute_buy_reserve_krw(
    portfolio_value: float,
    cash_short_target_pct: float,
) -> float:
    by_cap = portfolio_value * LADDER_RESERVE_CAP_PPT / 100.0
    by_group = portfolio_value * cash_short_target_pct / 100.0 * 0.625
    return round(min(by_cap, by_group))


def compute_reviewable_amount_krw(
    *,
    portfolio_value: float,
    cash_short_target_pct: float,
    dip_stage: str,
    systemic_stress: bool,
    blocked_by: list[str],
) -> float:
    if systemic_stress or dip_stage in {"WATCH", "UNKNOWN", "INACTIVE"}:
        return 0
    hard_block = {"data_gate_red", "core_price_gate", "execution_scope_no_trade", "systemic_stress"}
    if hard_block.intersection(blocked_by):
        return 0
    reserve = compute_buy_reserve_krw(portfolio_value, cash_short_target_pct)
    pct = LADDER_STAGE_PCT.get(dip_stage, 0.0)
    return round(reserve * pct)


def derive_execution_status(
    *,
    actual_allowed_krw: float,
    blocked_by: list[str],
    buy_trigger_active: bool,
) -> str:
    if actual_allowed_krw > 0:
        return "ALLOWED"
    if buy_trigger_active or any(b.startswith("dip_") for b in blocked_by):
        return "REVIEW_ONLY"
    if blocked_by:
        return "BLOCKED"
    return "ALLOWED"


def _etf_buy_blocked(blocked_by: list[str], execution_scope: str) -> bool:
    if execution_scope in {"NO_TRADE", "ETF_ONLY"} and "execution_scope_no_trade" in blocked_by:
        return True
    if execution_scope == "NO_TRADE":
        return True
    etf_blocks = {
        "data_gate_red",
        "core_price_gate",
        "health_gate_red",
        "dry_run",
        "stop_buy",
        "systemic_stress",
    }
    return bool(etf_blocks.intersection(blocked_by))


def _alpha_only_blocked(
    blocked_by: list[str],
    *,
    buy_trigger_active: bool,
    alpha_trade_permission: str,
    execution_scope: str,
) -> bool:
    alpha_blocks = {
        "alpha_trade_blocked",
        "alpha_gate_red",
        "execution_scope_etf_only",
        "execution_scope_etf_review",
        "execution_scope_no_trade",
    }
    if not alpha_blocks.intersection(blocked_by):
        return False
    if not buy_trigger_active:
        return False
    etf_scope_blocks = {"execution_scope_no_trade", "data_gate_red", "core_price_gate", "dry_run"}
    return not etf_scope_blocks.intersection(blocked_by) or execution_scope not in {"NO_TRADE"}


def build_shadow_diagnostic(
    *,
    run_id: str,
    as_of: str,
    market: MarketIndicators,
    positions: list[Any],
    gap_rows: list[GapRow],
    alerts: list[TriggerAlert],
    actions: list[TradeAction],
    theoretical_actions: list[TradeAction],
    rules: dict,
    data_gate: str,
    health_gate: str,
    portfolio_gate: str,
    alpha_gate: str | None,
    execution_scope: str,
    core_price_gate: str,
    dry_run_days: int,
    policy_cap: dict[str, Any],
    alpha_trade_permission: str,
    operational_status: str,
    allocation_groups: list[Any] | None = None,
    applied_regime: str | None = None,
    saa_profile: str | None = None,
    dry_run_required: int = 10,
    data_dir: Path | None = None,
    shadow_log_path: Path | None = None,
    targets: list[Any] | None = None,
    asset_group_gaps: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """v1.0.2 변수만 읽어 shadow 진단 JSON 생성 — 실행 판단 변경 없음."""
    portfolio_value = _portfolio_value(positions)
    cash_target = _cash_short_target_pct(allocation_groups)

    buy_groups = [
        "domestic_beta",
        "global_beta",
        "hedge_alt",
        "fx_dollar",
        "income_alt",
        "cash_short_bond",
    ]
    buy_trigger_active = any(is_buy_trigger_active(alerts, g) for g in buy_groups)
    watch_triggers = list_watch_triggers(alerts, asset_group_gaps)
    active_triggers = list_all_active_triggers(alerts)
    suppressed_triggers = list_suppressed_signals(alerts)
    risk_reduce_triggers = list_risk_reduce_active_triggers(alerts)

    regime_upper = (market.regime or "").upper()
    systemic_stress = (
        data_gate == "RED"
        or regime_upper in {"CRISIS", "RED"}
        or core_price_gate == "fail"
    )
    kospi_dd = _pct_drawdown(market.kospi, market.kospi_recent_high)
    dip_stage, dip_gated = derive_dip_ladder_stage(kospi_dd, systemic_stress=systemic_stress)

    blocked_by = collect_blocked_by(
        data_gate=data_gate,
        health_gate=health_gate,
        portfolio_gate=portfolio_gate,
        alpha_gate=alpha_gate,
        execution_scope=execution_scope,
        core_price_gate=core_price_gate,
        dry_run_days=dry_run_days,
        dry_run_required=dry_run_required,
        policy_cap_active=bool(policy_cap.get("active")),
        cap_regime=policy_cap.get("cap_regime"),
        alpha_trade_permission=alpha_trade_permission,
        stop_buy=is_stop_buy(alerts),
        systemic_stress=systemic_stress,
    )

    theoretical_gap_krw = _sum_underweight_gap_krw(gap_rows, portfolio_value)
    actual_allowed_krw, executable_buy_count = _sum_buy_gap_krw(actions, portfolio_value)
    _, theoretical_buy_count = _sum_buy_gap_krw(theoretical_actions, portfolio_value)
    reviewable_amount_krw = compute_reviewable_amount_krw(
        portfolio_value=portfolio_value,
        cash_short_target_pct=cash_target,
        dip_stage=dip_stage,
        systemic_stress=systemic_stress,
        blocked_by=blocked_by,
    )

    exec_status = derive_execution_status(
        actual_allowed_krw=actual_allowed_krw,
        blocked_by=blocked_by,
        buy_trigger_active=buy_trigger_active,
    )

    reason_parts: list[str] = []
    if operational_status == "RED":
        reason_parts.append(f"operational {operational_status}")
    if execution_scope in {"NO_TRADE", "ETF_ONLY"}:
        reason_parts.append(f"scope {execution_scope}")
    if dry_run_days < dry_run_required:
        reason_parts.append(f"dry-run {dry_run_days}/{dry_run_required}")
    if not reason_parts and blocked_by:
        reason_parts.append(f"blocked: {blocked_by[0]}")
    reason_summary = ", ".join(reason_parts) if reason_parts else "no material block"

    reserve_krw = compute_buy_reserve_krw(portfolio_value, cash_target)
    stage_pct = LADDER_STAGE_PCT.get(dip_stage, 0.0)
    primary_blocker = derive_primary_blocker(blocked_by)
    signal_mismatch = buy_trigger_active and actual_allowed_krw == 0

    performance = build_performance_fields(
        data_dir=data_dir or Path("."),
        as_of=as_of,
        log_path=shadow_log_path or Path("."),
        portfolio_value=portfolio_value,
        blocked_by=blocked_by,
        profile=saa_profile,
    )
    performance["primary_blocker"] = primary_blocker

    from src.decision.duration_diagnostic import build_duration_bond_status, format_duration_report_line

    duration_status = build_duration_bond_status(
        positions=positions,  # type: ignore[arg-type]
        targets=targets,  # type: ignore[arg-type]
        gap_rows=gap_rows,
        allocation_groups=allocation_groups,
        data_dir=data_dir or Path("."),
    )

    report_lines = build_shadow_report_lines(
        saa_profile=saa_profile,
        applied_regime=applied_regime,
        allocation_groups=allocation_groups,
        duration_status=duration_status,
        shadow={
            "signals": {"dip_buy_stage": dip_stage},
            "amounts": {
                "reviewable_amount_krw": reviewable_amount_krw,
                "actual_allowed_krw": actual_allowed_krw,
            },
            "execution": {
                "blocked_by": blocked_by,
                "primary_blocker": primary_blocker,
                "reason_summary": reason_summary,
            },
            "gates": {"alpha_trade_permission": alpha_trade_permission},
            "performance": performance,
        },
    )
    return {
        "schema_version": SHADOW_SCHEMA_VERSION,
        "mode": SHADOW_MODE,
        "execution_authority": EXECUTION_AUTHORITY,
        "disclaimer": "참고용 shadow 진단 — v1.0.2 실거래 판단 변경 없음",
        "run_id": run_id,
        "as_of": as_of,
        "signals": {
            "buy_trigger_active": buy_trigger_active,
            "watch_triggers": watch_triggers,
            "watch_trigger_count": len(watch_triggers),
            "suppressed_triggers": suppressed_triggers,
            "risk_reduce_triggers": risk_reduce_triggers,
            "risk_reduce_trigger_count": len(risk_reduce_triggers),
            "active_triggers": active_triggers,
            "stop_buy": is_stop_buy(alerts),
            "kospi_drawdown_pct": kospi_dd,
            "dip_buy_stage": dip_stage,
        },
        "execution": {
            "status": exec_status,
            "scope": execution_scope,
            "operational_status": operational_status,
            "blocked_by": blocked_by,
            "primary_blocker": primary_blocker,
            "reason_summary": reason_summary,
        },
        "amounts": {
            "portfolio_value_krw": round(portfolio_value),
            "theoretical_gap_krw": theoretical_gap_krw,
            "reviewable_amount_krw": reviewable_amount_krw,
            "actual_allowed_krw": actual_allowed_krw,
        },
        "performance": performance,
        "gates": {
            "data_gate": data_gate,
            "health_gate": health_gate,
            "portfolio_gate": portfolio_gate,
            "alpha_gate": alpha_gate,
            "core_price_gate": core_price_gate,
            "dry_run_days": dry_run_days,
            "dry_run_required": dry_run_required,
            "policy_cap_active": bool(policy_cap.get("active")),
            "policy_cap_regime": policy_cap.get("cap_regime"),
            "alpha_trade_permission": alpha_trade_permission,
        },
        "drawdown_ladder": {
            "stage": dip_stage,
            "buy_reserve_krw": reserve_krw,
            "stage_pct_of_reserve": stage_pct,
            "reviewable_from_ladder_krw": reviewable_amount_krw,
            "systemic_stress": systemic_stress,
            "gated_reasons": dip_gated + ([primary_blocker] if systemic_stress and primary_blocker else []),
        },
        "observations": {
            "theoretical_buy_count": theoretical_buy_count,
            "executable_buy_count": executable_buy_count,
            "etf_fully_blocked": _etf_buy_blocked(blocked_by, execution_scope),
            "alpha_only_blocked": _alpha_only_blocked(
                blocked_by,
                buy_trigger_active=buy_trigger_active,
                alpha_trade_permission=alpha_trade_permission,
                execution_scope=execution_scope,
            ),
            "signal_execution_mismatch": signal_mismatch,
        },
        "duration_bond_status": duration_status,
        "report_lines": report_lines,
    }


def build_shadow_report_lines(
    *,
    saa_profile: str | None,
    applied_regime: str | None,
    allocation_groups: list[Any] | None,
    shadow: dict[str, Any],
    duration_status: dict[str, Any] | None = None,
) -> dict[str, str]:
    profile = saa_profile or "defensive_balanced"
    regime = applied_regime or "—"
    saa_parts: list[str] = []
    if allocation_groups:
        for g in allocation_groups:
            ag = getattr(g, "asset_group", None) or (g.get("asset_group") if isinstance(g, dict) else "")
            saa_w = getattr(g, "saa_weight", None) or (g.get("saa_weight") if isinstance(g, dict) else None)
            if saa_w is not None:
                saa_parts.append(f"{ag} {float(saa_w):.0f}%")
    saa_line = f"{profile} · " + (" · ".join(saa_parts[:4]) + (" …" if len(saa_parts) > 4 else "")) if saa_parts else profile

    taa_parts: list[str] = []
    if allocation_groups:
        for g in allocation_groups:
            ag = getattr(g, "asset_group", None) or (g.get("asset_group") if isinstance(g, dict) else "")
            if hasattr(g, "taa_tilt"):
                delta = float(g.taa_tilt)
            else:
                phase = float(g.get("phase_tilt", 0) if isinstance(g, dict) else getattr(g, "phase_tilt", 0) or 0)
                regime = float(g.get("regime_tilt", 0) if isinstance(g, dict) else getattr(g, "regime_tilt", 0) or 0)
                delta = phase + regime
            if abs(delta) >= 0.01:
                taa_parts.append(f"{ag} {delta:+.0f}p")
    taa_line = f"{regime} · " + (", ".join(taa_parts) if taa_parts else "delta 0")

    stage = shadow.get("signals", {}).get("dip_buy_stage", "—")
    amounts = shadow.get("amounts", {})
    reviewable = int(amounts.get("reviewable_amount_krw") or 0)
    actual = int(amounts.get("actual_allowed_krw") or 0)
    blocked = shadow.get("execution", {}).get("blocked_by") or []
    dip_line = (
        f"{stage} · reviewable {reviewable:,}원 · actual {actual:,}원"
        + (f" · blocked {blocked[0]}" if blocked else "")
    )

    alpha_perm = shadow.get("gates", {}).get("alpha_trade_permission", "—")
    reason = shadow.get("execution", {}).get("reason_summary", "")
    alpha_line = f"{alpha_perm} · {reason}"

    perf = shadow.get("performance") or {}
    vs = perf.get("vs_saa_mtd")
    vs_part = f" · vs SAA MTD {vs:+.2f}%p" if vs is not None else ""

    return {
        "saa_baseline": saa_line,
        "taa_delta": taa_line,
        "dip_buy_budget": dip_line,
        "alpha_permission": alpha_line,
        "performance_mtd": vs_part.strip(" · ") if vs_part else "—",
        "duration_sleeve": (
            format_duration_report_line(duration_status)
            if duration_status
            else "—"
        ),
    }


def write_shadow_diagnostic(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_ops_shadow_log(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    obs = doc.get("observations") or {}
    exec_block = doc.get("execution") or {}
    amounts = doc.get("amounts") or {}
    signals = doc.get("signals") or {}
    gates = doc.get("gates") or {}
    ladder = doc.get("drawdown_ladder") or {}
    perf = doc.get("performance") or {}
    duration = doc.get("duration_bond_status") or {}
    blocked = exec_block.get("blocked_by") or []
    primary = exec_block.get("primary_blocker") or perf.get("primary_blocker") or derive_primary_blocker(blocked)

    def _fmt(v: Any) -> str:
        if v is None or v == "":
            return ""
        return str(v)

    row = {
        "date": doc.get("as_of", ""),
        "run_id": doc.get("run_id", ""),
        "buy_trigger_active": signals.get("buy_trigger_active", False),
        "signal_execution_mismatch": obs.get("signal_execution_mismatch", False),
        "execution_status": exec_block.get("status", ""),
        "primary_blocker": primary,
        "blocked_by_primary": blocked[0] if blocked else "",
        "blocked_by_all": "|".join(blocked),
        "dip_stage": ladder.get("stage", signals.get("dip_buy_stage", "")),
        "theoretical_gap_krw": amounts.get("theoretical_gap_krw", 0),
        "reviewable_amount_krw": amounts.get("reviewable_amount_krw", 0),
        "actual_allowed_krw": amounts.get("actual_allowed_krw", 0),
        "portfolio_value_krw": perf.get("portfolio_value_krw", amounts.get("portfolio_value_krw", 0)),
        "benchmark_saa_return_1d": _fmt(perf.get("benchmark_saa_return_1d")),
        "benchmark_saa_return_mtd": _fmt(perf.get("benchmark_saa_return_mtd")),
        "portfolio_return_mtd": _fmt(perf.get("portfolio_return_mtd")),
        "vs_saa_mtd": _fmt(perf.get("vs_saa_mtd")),
        "missed_buy_return_after_5d": _fmt(perf.get("missed_buy_return_after_5d")),
        "missed_buy_return_after_20d": _fmt(perf.get("missed_buy_return_after_20d")),
        "blocked_decision_outcome": _fmt(perf.get("blocked_decision_outcome")),
        "execution_scope": exec_block.get("scope", ""),
        "data_gate": gates.get("data_gate", ""),
        "operational_status": exec_block.get("operational_status", ""),
        "theoretical_buy_count": obs.get("theoretical_buy_count", 0),
        "executable_buy_count": obs.get("executable_buy_count", 0),
        "etf_fully_blocked": obs.get("etf_fully_blocked", False),
        "alpha_only_blocked": obs.get("alpha_only_blocked", False),
        "cash_short_current_pct": duration.get("cash_short_current_pct", ""),
        "kr_duration_current_pct": duration.get("kr_duration_bond_current_pct", ""),
        "duration_gap": duration.get("duration_gap", ""),
        "duration_diagnosis": duration.get("diagnosis", ""),
    }

    write_header = not path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OPS_SHADOW_LOG_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def build_daily_report_shadow_section(shadow_path: Path | None) -> list[str]:
    if shadow_path is None or not shadow_path.exists():
        return []
    doc = json.loads(shadow_path.read_text(encoding="utf-8"))
    if doc.get("mode") != SHADOW_MODE:
        return []
    lines_map = doc.get("report_lines") or {}
    exec_block = doc.get("execution") or {}
    amounts = doc.get("amounts") or {}
    perf = doc.get("performance") or {}
    duration = doc.get("duration_bond_status") or {}
    vs = perf.get("vs_saa_mtd")
    vs_line = f" · vs SAA MTD {vs:+.2f}%p" if vs is not None else ""
    return [
        "## Shadow 진단 (v1.1a · 참고용)",
        f"- **SAA baseline**: {lines_map.get('saa_baseline', '—')}",
        f"- **TAA delta**: {lines_map.get('taa_delta', '—')}",
        f"- **Dip-buy budget**: {lines_map.get('dip_buy_budget', '—')}",
        f"- **Duration sleeve (shadow)**: {lines_map.get('duration_sleeve', '—')}",
        f"- **Alpha permission**: {lines_map.get('alpha_permission', '—')}",
        f"- **Signal vs execution**: status `{exec_block.get('status', '—')}` · "
        f"primary `{exec_block.get('primary_blocker') or '—'}` · "
        f"theoretical gap {int(amounts.get('theoretical_gap_krw') or 0):,}원 · "
        f"mismatch `{doc.get('observations', {}).get('signal_execution_mismatch', False)}`{vs_line}",
        f"- **authority**: `{doc.get('execution_authority', EXECUTION_AUTHORITY)}` — 실거래 판단 변경 없음",
        "",
    ]
