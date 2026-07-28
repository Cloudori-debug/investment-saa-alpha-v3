"""Rich gate detail for AC-02 unified_data_gate and AC-03 portfolio_gate."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.operational_gate import CRITICAL_HEALTH_NAMES, explain_operational_gate, health_warn_summaries
from src.report.io_utils import read_output_json
from src.validation.fail_soft_pipeline import _sector_coverage_from_gpt
from src.validation.fail_soft_permissions import ALPHA_SECTOR_TOP10_MIN_COVERAGE_PCT


def _stale_fields_from_provenance(data_dir: Path) -> tuple[list[str], dict[str, Any]]:
    from src.data_provenance import audit_market_data_consistency

    audit = audit_market_data_consistency(data_dir)
    prov_path = data_dir / "market_data_provenance.json"
    stale_fields: list[str] = []
    if prov_path.exists():
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
        for name, meta in (prov.get("fields") or {}).items():
            if int(meta.get("stale_business_days", 0)) > 2:
                stale_fields.append(name)
    return stale_fields, audit


def _health_price_coverage(health: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for chk in getattr(health, "checks", []) or []:
        name = getattr(chk, "name", "")
        if name in {"core_price_gate", "prices_coverage", "alpha_price_gate"}:
            out[name] = {
                "status": getattr(chk, "status", ""),
                "message": getattr(chk, "message", ""),
                "detail": getattr(chk, "detail", None) or {},
            }
    return out


def build_unified_data_gate_detail(
    *,
    gate: str,
    log: dict[str, Any] | None,
    health: Any,
    output_dir: Path,
    data_dir: Path,
) -> dict[str, Any]:
    log = log or {}
    portfolio_gate = str(log.get("portfolio_gate") or "—")
    alpha_gate = log.get("alpha_gate")
    health_gate = str(log.get("health_gate") or "GREEN")
    unified = str(gate or log.get("data_gate") or "RED")

    health_warns = health_warn_summaries(getattr(health, "checks", []) or [])
    explain = explain_operational_gate(
        portfolio_gate,
        str(alpha_gate) if alpha_gate else None,
        health_gate,  # type: ignore[arg-type]
        merge_alpha=True,
        health_warns=health_warns,
    )

    fail_reasons: list[str] = []
    if unified == "RED":
        fail_reasons.extend(str(d) for d in explain.get("drivers") or [])
        for chk in getattr(health, "checks", []) or []:
            if getattr(chk, "status", "") == "fail" and getattr(chk, "name", "") in CRITICAL_HEALTH_NAMES:
                fail_reasons.append(f"health_critical_fail={chk.name}")
    elif unified == "YELLOW":
        fail_reasons.extend(str(d) for d in explain.get("drivers") or [] if "GREEN" not in str(d))

    stale_fields, provenance_audit = _stale_fields_from_provenance(data_dir)

    return {
        "gate": unified,
        "fail_reasons": fail_reasons,
        "source_files": [
            "decision_log.jsonl",
            "system_health.json",
            "market_data_provenance.json",
        ],
        "stale_fields": stale_fields,
        "thresholds": {
            "external_stale_warn_days": 3,
            "external_stale_fail_days": 6,
            "health_critical_blocks_execution": True,
        },
        "blocking": unified == "RED",
        "portfolio_gate": explain.get("portfolio_gate"),
        "alpha_gate": explain.get("alpha_gate"),
        "health_gate": explain.get("health_gate"),
        "base_gate": explain.get("base_gate"),
        "data_gate": explain.get("data_gate"),
        "drivers": explain.get("drivers"),
        "summary": explain.get("summary"),
        "provenance_issues": (provenance_audit.get("issues") or [])[:5],
    }


def build_portfolio_gate_detail(
    *,
    gate: str,
    log: dict[str, Any] | None,
    health: Any,
    output_dir: Path,
    data_dir: Path,
    policy_cap_active: bool = False,
    policy_cap_reason: str | None = None,
) -> dict[str, Any]:
    log = log or {}
    pg = str(gate or log.get("portfolio_gate") or "RED")
    cov, sector_gate = _sector_coverage_from_gpt(output_dir)
    price_cov = _health_price_coverage(health)

    from src.data_loader import load_market_indicators

    mi_path = data_dir / "market_indicators.csv"
    regime = ""
    validation_gate = "GREEN"
    if mi_path.exists():
        market = load_market_indicators(mi_path)
        regime = market.regime
        from src.config import load_portfolio_policy
        from src.data_loader import load_positions, load_target_portfolio
        from src.validators import validate_inputs

        policy = load_portfolio_policy(data_dir / "portfolio_policy.yaml")
        positions = load_positions(data_dir / "positions.csv")
        targets = load_target_portfolio(data_dir / "target_portfolio.csv")
        validation = validate_inputs(positions, targets, policy)
        validation_gate = validation.data_gate
        from src.regime_classifier import classify_data_gate_from_regime

        derived_pg = classify_data_gate_from_regime(regime, validation.data_gate)
        if derived_pg != pg:
            regime_note = f"derived_from_regime={derived_pg} logged={pg}"
        else:
            regime_note = f"regime={regime} input_validation_gate={validation_gate}"
    else:
        regime_note = "market_indicators.csv missing"

    fail_reasons: list[str] = []
    portfolio_blockers: list[str] = []
    if pg == "RED":
        if "CRISIS" in regime.upper() or "RED" in regime.upper():
            portfolio_blockers.append(f"regime_risk_off={regime}")
            fail_reasons.append(f"regime={regime}")
        if validation_gate == "RED":
            portfolio_blockers.append("input_validation_RED")
            fail_reasons.append("input_validation=data_gate_RED")
        if not fail_reasons:
            fail_reasons.append(f"portfolio_gate={pg}")
            portfolio_blockers.append(f"portfolio_gate={pg}")
    elif pg == "YELLOW":
        fail_reasons.append(f"portfolio_gate=YELLOW ({regime_note})")

    final_doc = read_output_json(output_dir / "final_execution_decision.json") or {}
    perms = final_doc.get("execution_permissions") or {}
    policy_cap_doc = final_doc.get("policy_cap") or {}
    if policy_cap_doc.get("active") is not None:
        policy_cap_active = bool(policy_cap_doc.get("active"))
        policy_cap_reason = policy_cap_doc.get("cap_reason") or policy_cap_reason
    executable_block_reasons: list[str] = []
    if pg == "RED":
        executable_block_reasons.append("portfolio_gate=RED blocks core ETF and alpha auto-buy")
    if policy_cap_active:
        executable_block_reasons.append(f"policy_cap_active ({policy_cap_reason or 'cap'})")
    if str(final_doc.get("execution_scope") or "") == "NO_TRADE":
        executable_block_reasons.append("execution_scope=NO_TRADE")
    main_block = perms.get("main_block_reason")
    if main_block:
        executable_block_reasons.append(str(main_block))

    top10_cov = float(cov.get("top10_sector_coverage_pct") or 0)
    sector_note = None
    if top10_cov and top10_cov < ALPHA_SECTOR_TOP10_MIN_COVERAGE_PCT:
        sector_note = f"top10_sector_coverage={top10_cov}% < {ALPHA_SECTOR_TOP10_MIN_COVERAGE_PCT}%"

    return {
        "gate": pg,
        "fail_reasons": fail_reasons,
        "portfolio_blockers": portfolio_blockers,
        "price_coverage": price_cov,
        "sector_coverage": cov,
        "sector_gate": sector_gate,
        "sector_coverage_note": sector_note,
        "policy_cap_active": policy_cap_active,
        "policy_cap_reason": policy_cap_reason,
        "regime": regime,
        "input_validation_gate": validation_gate,
        "regime_derivation": regime_note,
        "executable_action_block_reasons": executable_block_reasons,
        "blocking": pg == "RED",
        "thresholds": {
            "top10_sector_coverage_min_pct": ALPHA_SECTOR_TOP10_MIN_COVERAGE_PCT,
            "crisis_regime_caps_portfolio_gate": True,
        },
        "source_files": [
            "decision_log.jsonl",
            "final_execution_decision.json",
            "gpt_context.json",
            "market_indicators.csv",
        ],
    }
