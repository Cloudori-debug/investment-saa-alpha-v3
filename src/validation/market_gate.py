"""Market layer gate inputs and blocker evaluation — transparency only, no buy logic changes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import yaml

from src.report.io_utils import read_output_json

LayerStatus = Literal["GREEN", "YELLOW", "RED"]

MARKET_YELLOW_NOTE = "Market YELLOW means SAA restart is not yet approved."
PULLBACK_WATCH_NOTE = "KOSPI pullback watch signal is not buy permission."
BUY_ALLOWED_OVERRIDE_NOTE = "Actual Buy Allowed=0 overrides watch signals."


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def _pct_drawdown(current: float, recent_high: float) -> float | None:
    if recent_high <= 0 or current <= 0:
        return None
    return round((current / recent_high - 1) * 100, 2)


def _kr_alpha_hard_stop_info(
    final_doc: dict[str, Any],
    data_dir: Path,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    hard_detail = final_doc.get("hard_stops_detail") or {}
    for item in hard_detail.get("risk_hard_stops") or []:
        detail = str(item.get("detail") or "")
        if "kr_alpha" in detail.lower():
            return {
                "exceeded": True,
                "detail": detail,
                "current_pct": None,
                "limit_pct": None,
                "source": "hard_stops_detail",
            }

    current: float | None = None
    for row in final_doc.get("group_gaps") or []:
        if isinstance(row, dict) and row.get("asset_group") == "kr_alpha":
            try:
                current = float(row.get("current"))
            except (TypeError, ValueError):
                pass
            break

    if current is None:
        out_dir = output_dir or (data_dir.parent / "outputs")
        perf_path = out_dir / "alpha_performance_dashboard.json"
        doc = read_output_json(perf_path)
        if doc and doc.get("kr_alpha_weight_pct") is not None:
            current = float(doc["kr_alpha_weight_pct"])

    limit = float(_load_yaml(data_dir / "portfolio_policy.yaml").get("risk_limits", {}).get("kr_alpha_max", 35))

    exceeded = current is not None and current > limit + 0.01
    return {
        "exceeded": exceeded,
        "detail": f"kr_alpha {current:.1f}% > {limit:.1f}%" if exceeded and current is not None else "",
        "current_pct": current,
        "limit_pct": limit,
        "source": "group_gaps_or_dashboard",
    }


def collect_market_gate_inputs(
    data_dir: Path,
    output_dir: Path,
    *,
    final_doc: dict[str, Any] | None = None,
    acceptance_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Gather read-only market gate inputs from existing artifacts."""
    final_doc = final_doc or read_output_json(output_dir / "final_execution_decision.json") or {}
    acceptance_doc = acceptance_doc or read_output_json(output_dir / "acceptance_report.json") or {}
    from src.report.authoritative_status import _acceptance_gate

    gates = (final_doc.get("execution_permissions") or {}).get("gates") or {}
    data_gate_detail = final_doc.get("data_gate_detail") or {}
    policy_cap = final_doc.get("policy_cap") or {}
    brief = read_output_json(output_dir / "daily_brief.json") or {}
    compass = read_output_json(output_dir / "compass_regime.json") or {}

    config_data_gate = str(
        final_doc.get("data_gate")
        or gates.get("data_gate")
        or data_gate_detail.get("data_gate")
        or "RED"
    )
    unified_data_gate = _acceptance_gate(acceptance_doc, ac_id="AC-02", name="unified_data_gate") or config_data_gate
    portfolio_gate = (
        _acceptance_gate(acceptance_doc, ac_id="AC-03", name="portfolio_gate")
        or str(gates.get("portfolio_gate") or data_gate_detail.get("portfolio_gate") or unified_data_gate)
    )
    alpha_gate = str(
        _acceptance_gate(acceptance_doc, ac_id="AC-04", name="alpha_gate")
        or final_doc.get("alpha_gate")
        or gates.get("alpha_gate")
        or data_gate_detail.get("alpha_gate")
        or final_doc.get("alpha_approval")
        or "—"
    )
    alpha_sector_gate = str((final_doc.get("execution_permissions") or {}).get("alpha_sector_data_gate") or "—")

    market_row: dict[str, Any] = {}
    mi_path = data_dir / "market_indicators.csv"
    if mi_path.exists():
        import pandas as pd

        df = pd.read_csv(mi_path, dtype=str, keep_default_na=False)
        if not df.empty:
            market_row = df.iloc[-1].to_dict()

    trigger_rules = _load_yaml(data_dir / "trigger_rules.yaml")
    compass_rules = _load_yaml(data_dir / "compass_rules.yaml")
    mt = trigger_rules.get("market_triggers", {})

    kospi = float(market_row.get("kospi") or 0)
    kospi_high = float(market_row.get("kospi_recent_high") or 0)
    kospi_dd = _pct_drawdown(kospi, kospi_high)
    kospi_rules = mt.get("kospi", {})
    crisis_zone = float(kospi_rules.get("crisis_zone", -20))
    pullback_buy_1 = float(kospi_rules.get("pullback_buy_1", -5))

    vix = float(market_row.get("vix") or 0)
    vix_rules = mt.get("vix", {})
    usdkrw = float(market_row.get("usdkrw") or 0)
    fx_risk = float(mt.get("usdkrw", {}).get("risk_level", compass_rules.get("usdkrw", {}).get("stress_above", 1550)))
    fx_stable = float(mt.get("usdkrw", {}).get("stable_level", 1500))

    foreign_flow = str(market_row.get("foreign_flow_3d") or "neutral").lower()
    flow_stale = False
    audit = final_doc.get("market_data_audit") or {}
    field_dates = audit.get("field_last_updated") or {}
    if field_dates.get("foreign_flow_3d") == "" and not market_row.get("foreign_flow_3d"):
        flow_stale = True

    kr_stop = _kr_alpha_hard_stop_info(final_doc, data_dir, output_dir)

    vix_status = "unknown"
    if vix <= 0:
        vix_status = "unknown"
    elif vix >= float(vix_rules.get("panic_above", 30)):
        vix_status = "panic"
    elif vix >= float(vix_rules.get("risk_off_above", 25)):
        vix_status = "risk_off"
    elif vix >= float(vix_rules.get("caution_above", 20)):
        vix_status = "caution"
    else:
        vix_status = "normal"

    usdkrw_status = "unknown"
    if usdkrw <= 0:
        usdkrw_status = "unknown"
    elif usdkrw >= fx_risk:
        usdkrw_status = "risk"
    elif usdkrw >= fx_stable:
        usdkrw_status = "watch"
    else:
        usdkrw_status = "stable"

    watch_signals = list(brief.get("watch_signals") or brief.get("active_watch_signals") or [])
    if not watch_signals:
        exec_block = brief.get("execution") or {}
        watch_signals = list(exec_block.get("watch_signals") or [])

    return {
        "data_gate": unified_data_gate,
        "unified_data_gate": unified_data_gate,
        "config_data_gate": config_data_gate,
        "portfolio_gate": portfolio_gate,
        "alpha_gate": alpha_gate,
        "alpha_sector_data_gate": alpha_sector_gate,
        "policy_cap": policy_cap,
        "execution_scope": str(final_doc.get("execution_scope") or ""),
        "conflict_detected": bool(final_doc.get("target_guard_conflict_detected")),
        "kospi_drawdown_pct": kospi_dd,
        "kospi_crisis_zone": crisis_zone,
        "kospi_pullback_watch_active": kospi_dd is not None and kospi_dd <= pullback_buy_1,
        "kospi_severe_risk_off": kospi_dd is not None and kospi_dd <= crisis_zone,
        "vix": vix if vix > 0 else None,
        "vix_status": vix_status,
        "usdkrw": usdkrw if usdkrw > 0 else None,
        "usdkrw_status": usdkrw_status,
        "usdkrw_risk_level": fx_risk,
        "foreign_flow": foreign_flow if market_row.get("foreign_flow_3d") else "unknown",
        "foreign_flow_stale": flow_stale,
        "kr_alpha_hard_stop": kr_stop,
        "compass_regime": str(compass.get("applied_regime") or compass.get("computed_regime") or ""),
        "market_data_stale_fields": list(field_dates.keys()) if audit else [],
        "watch_signals": watch_signals,
    }


def evaluate_market_layer(
    inputs: dict[str, Any],
    *,
    actual_buy_allowed: int,
    conflict_detected: bool,
) -> dict[str, Any]:
    """Evaluate Market GREEN/YELLOW/RED and detailed blockers."""
    blockers: list[str] = []
    yellow_flags: list[str] = []
    red_flags: list[str] = []
    unknowns: list[str] = []
    green_reasons: list[str] = []

    unified_gate = str(inputs.get("unified_data_gate") or inputs.get("data_gate") or "RED")
    portfolio_gate = str(inputs.get("portfolio_gate") or unified_gate)
    alpha_gate = inputs.get("alpha_gate", "—")
    policy_cap = inputs.get("policy_cap") or {}
    execution_scope = inputs.get("execution_scope", "")

    if unified_gate == "RED":
        blockers.append("unified_data_gate=RED")
        red_flags.append("unified_data_gate=RED")
    elif unified_gate == "YELLOW":
        blockers.append("unified_data_gate=YELLOW")
        yellow_flags.append("unified_data_gate=YELLOW")
    else:
        green_reasons.append("unified_data_gate=GREEN")

    if portfolio_gate == "RED":
        blockers.append("portfolio_gate=RED")
        red_flags.append("portfolio_gate=RED")
    elif portfolio_gate == "YELLOW":
        blockers.append("portfolio_gate=YELLOW")
        yellow_flags.append("portfolio_gate=YELLOW")
    elif portfolio_gate == "GREEN":
        green_reasons.append("portfolio_gate=GREEN")

    if alpha_gate == "RED":
        blockers.append(f"alpha_gate={alpha_gate}")
        red_flags.append(f"alpha_gate=RED")
    elif alpha_gate not in ("GREEN", "PASS", "—", ""):
        blockers.append(f"alpha_gate={alpha_gate}")
        yellow_flags.append(f"alpha_gate={alpha_gate}")

    sector_gate = inputs.get("alpha_sector_data_gate")
    if sector_gate and sector_gate not in ("GREEN", "PASS", "—", ""):
        blockers.append(f"alpha_sector_data_gate={sector_gate}")
        yellow_flags.append(f"alpha_sector_data_gate={sector_gate}")

    kr = inputs.get("kr_alpha_hard_stop") or {}
    if kr.get("exceeded"):
        cur = kr.get("current_pct")
        lim = kr.get("limit_pct")
        if cur is not None and lim is not None:
            blockers.append(f"kr_alpha_over_hard_stop={cur}% > {lim}%")
        else:
            detail = str(kr.get("detail") or "exceeded")
            blockers.append(f"kr_alpha_over_hard_stop={detail}")
        yellow_flags.append("kr_alpha_hard_stop_exceeded")
    elif kr.get("current_pct") is not None:
        green_reasons.append(f"kr_alpha={kr.get('current_pct')}%<={kr.get('limit_pct')}%")

    if policy_cap.get("active"):
        regime = policy_cap.get("cap_regime") or "ACTIVE"
        blockers.append(f"policy_cap={regime}")
        yellow_flags.append(f"policy_cap={regime}")
        cap_upper = str(regime).upper()
        if "CRISIS" in cap_upper or cap_upper == "RISK_OFF":
            red_flags.append(f"policy_cap_regime={regime}")

    usdkrw_status = inputs.get("usdkrw_status")
    usdkrw = inputs.get("usdkrw")
    risk_level = inputs.get("usdkrw_risk_level")
    if usdkrw_status == "unknown":
        unknowns.append("usdkrw=unknown")
    elif usdkrw_status == "risk" and usdkrw is not None and risk_level is not None:
        blockers.append(f"usdkrw_risk:{usdkrw}>={risk_level}")
        yellow_flags.append("usdkrw_risk")
    elif usdkrw_status == "watch" and usdkrw is not None:
        yellow_flags.append(f"usdkrw_watch:{usdkrw}")

    kospi_dd = inputs.get("kospi_drawdown_pct")
    if kospi_dd is None:
        unknowns.append("kospi_drawdown=unknown")
    else:
        if inputs.get("kospi_severe_risk_off"):
            blockers.append(f"kospi_drawdown={kospi_dd}%")
            red_flags.append(f"kospi_crisis_drawdown={kospi_dd}%")
        elif inputs.get("kospi_pullback_watch_active"):
            yellow_flags.append(f"kospi_drawdown={kospi_dd}%")
            yellow_flags.append("kospi_pullback_watch_active=True")

    vix_status = inputs.get("vix_status")
    if vix_status == "unknown":
        unknowns.append("vix=unknown")
    elif vix_status in {"panic", "risk_off"}:
        blockers.append(f"vix_risk={vix_status}")
        red_flags.append(f"vix_risk={vix_status}")
    elif vix_status == "caution":
        yellow_flags.append(f"vix_risk={vix_status}")

    flow = inputs.get("foreign_flow")
    if inputs.get("foreign_flow_stale") or flow == "unknown":
        unknowns.append("foreign_flow=unknown")
        yellow_flags.append("foreign_flow=unknown")
    elif flow in {"heavy_selling", "sell", "negative", "outflow"}:
        blockers.append(f"foreign_flow={flow}")
        yellow_flags.append(f"foreign_flow={flow}")

    if conflict_detected:
        blockers.append("target_guard_conflict_detected=True")
        red_flags.append("target_guard_conflict=True")

    if execution_scope == "NO_TRADE":
        blockers.append("execution_scope=NO_TRADE")
        red_flags.append("NO_TRADE")

    applied = str(inputs.get("compass_regime") or "").upper()
    if "CRISIS" in applied:
        blockers.append(f"market_regime={applied}")
        red_flags.append(f"market_regime={applied}")

    if actual_buy_allowed <= 0:
        yellow_flags.append("actual_buy_allowed=0")

    severe_blockers = [b for b in blockers if b not in yellow_flags]

    market_red = bool(red_flags) or unified_gate == "RED" or execution_scope == "NO_TRADE" or conflict_detected

    market_green = (
        not market_red
        and unified_gate == "GREEN"
        and portfolio_gate == "GREEN"
        and not severe_blockers
        and not kr.get("exceeded")
        and not policy_cap.get("active")
        and not (usdkrw_status == "risk")
        and not inputs.get("kospi_severe_risk_off")
        and vix_status not in {"panic", "risk_off", "unknown"}
        and flow not in {"heavy_selling", "sell", "negative", "outflow", "unknown"}
    )

    if market_red:
        status: LayerStatus = "RED"
    elif market_green:
        status = "GREEN"
    else:
        status = "YELLOW"

    all_blockers = list(dict.fromkeys(blockers + yellow_flags + unknowns))

    saa_ready = (
        status == "GREEN"
        and unified_gate == "GREEN"
        and portfolio_gate == "GREEN"
        and not policy_cap.get("active")
        and not kr.get("exceeded")
        and actual_buy_allowed > 0
    )
    kr_alpha_ready = (
        not kr.get("exceeded")
        and alpha_gate == "GREEN"
        and unified_gate == "GREEN"
        and actual_buy_allowed > 0
    )

    return {
        "market_status": status,
        "market_blockers": all_blockers,
        "market_blocker_count": len(all_blockers),
        "market_unknowns": unknowns,
        "market_red_flags": red_flags,
        "market_yellow_flags": yellow_flags,
        "market_green_reasons": green_reasons,
        "market_gate_detail": inputs,
        "market_reason_compact": "; ".join(all_blockers + unknowns) if all_blockers or unknowns else "conditions met",
        "saa_restart_readiness": "READY_FOR_REVIEW" if saa_ready else "NOT_READY",
        "kr_alpha_restart_readiness": "READY_FOR_REVIEW" if kr_alpha_ready else "NOT_READY",
        "market_notes": [
            PULLBACK_WATCH_NOTE,
            MARKET_YELLOW_NOTE,
            BUY_ALLOWED_OVERRIDE_NOTE,
        ],
    }
