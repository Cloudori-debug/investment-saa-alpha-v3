from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

CheckResult = Literal["pass", "warn", "fail"]


@dataclass
class CrossValidationItem:
    check_id: str
    name: str
    status: CheckResult
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class CrossValidationReport:
    as_of: str
    overall: CheckResult
    items: list[CrossValidationItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "as_of": self.as_of,
            "overall": self.overall,
            "items": [
                {
                    "check_id": i.check_id,
                    "name": i.name,
                    "status": i.status,
                    "message": i.message,
                    "detail": i.detail,
                }
                for i in self.items
            ],
        }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _health_check(health: dict[str, Any], name: str) -> dict[str, Any]:
    for c in health.get("checks") or []:
        if c.get("name") == name:
            return c
    return {}


def _kr_alpha_executable_buys(trade_csv: Path) -> list[str]:
    if not trade_csv.exists():
        return []
    import pandas as pd

    df = pd.read_csv(trade_csv, dtype=str, keep_default_na=False)
    if df.empty:
        return []
    buys: list[str] = []
    for _, row in df.iterrows():
        action = str(row.get("action", ""))
        ticker = str(row.get("ticker", ""))
        reason = str(row.get("reason", ""))
        if action in {"Buy-allowed", "Add", "Replace"} and "Review-only" not in reason:
            buys.append(ticker)
    return buys


def validate_outputs_cross_check(output_dir: Path) -> CrossValidationReport:
    """system_health → price_coverage → final_decision → trade_actions 일관성."""
    health = _load_json(output_dir / "system_health.json")
    price_cov = _load_json(output_dir / "price_coverage_report.json")
    final = _load_json(output_dir / "final_execution_decision.json")
    as_of = str(final.get("as_of") or health.get("as_of") or price_cov.get("as_of") or "")

    items: list[CrossValidationItem] = []

    core_h = _health_check(health, "core_price_gate")
    alpha_h = _health_check(health, "alpha_price_gate")
    core_cov = price_cov.get("core_price_gate") or {}
    alpha_cov = price_cov.get("alpha_price_gate") or {}

    if core_h and core_cov:
        match = core_h.get("status") == core_cov.get("status")
        items.append(CrossValidationItem(
            "CV-01", "health_price_core_status",
            "pass" if match else "fail",
            f"system_health core={core_h.get('status')} price_report core={core_cov.get('status')}",
        ))

    if alpha_h and alpha_cov:
        match = (
            alpha_h.get("status") == alpha_cov.get("status")
            and (alpha_h.get("detail") or {}).get("action") == alpha_cov.get("action")
        )
        items.append(CrossValidationItem(
            "CV-02", "health_price_alpha_status",
            "pass" if match else "fail",
            f"alpha gate action={alpha_cov.get('action')} status={alpha_cov.get('status')}",
        ))

    meta_modes = set((health.get("meta") or {}).get("restricted_modes") or [])
    cov_modes = set(price_cov.get("restricted_modes") or [])
    if price_cov:
        items.append(CrossValidationItem(
            "CV-03", "restricted_modes_sync",
            "pass" if not cov_modes or cov_modes <= meta_modes or meta_modes == cov_modes else "warn",
            f"health={sorted(meta_modes)} price={sorted(cov_modes)}",
        ))

    from src.operational_gate import gate_from_health_checks
    from src.validation.system_health import HealthCheck

    checks = [
        HealthCheck(
            c.get("module", ""),
            c.get("name", ""),
            c.get("status", "skip"),
            c.get("message", ""),
            c.get("detail") or {},
        )
        for c in (health.get("checks") or [])
    ]
    expected_health_gate = gate_from_health_checks(checks) if checks else "GREEN"
    actual_data_gate = str(final.get("data_gate", ""))
    health_detail = final.get("data_gate_detail") or {}
    actual_health_gate = str(health_detail.get("health_gate") or "")
    perm_gates = (final.get("execution_permissions") or {}).get("gates") or {}
    perm_health_gate = str(perm_gates.get("health_gate") or "")

    if final:
        hg_ok = actual_health_gate == expected_health_gate or not actual_health_gate
        items.append(CrossValidationItem(
            "CV-04", "health_gate_consistency",
            "pass" if hg_ok else "fail",
            f"expected={expected_health_gate} final.health_gate={actual_health_gate}",
        ))
        if perm_health_gate:
            items.append(CrossValidationItem(
                "CV-04b", "permissions_health_gate_sync",
                "pass" if perm_health_gate == actual_health_gate else "fail",
                f"permissions={perm_health_gate} final={actual_health_gate}",
            ))

        scope = str(final.get("execution_scope", ""))
        if expected_health_gate == "RED" or core_h.get("status") == "fail":
            items.append(CrossValidationItem(
                "CV-05", "core_fail_blocks_trade",
                "pass" if scope == "NO_TRADE" or actual_data_gate == "RED" else "fail",
                f"core={core_h.get('status')} scope={scope} data_gate={actual_data_gate}",
            ))
        elif alpha_h.get("status") in ("fail", "warn") and core_h.get("status") == "pass":
            items.append(CrossValidationItem(
                "CV-06", "alpha_restrict_not_no_trade",
                "pass" if scope != "NO_TRADE" else "fail",
                f"alpha={alpha_h.get('status')} scope={scope} (ETF-only 허용)",
            ))

    alpha_action = str(alpha_cov.get("action") or (alpha_h.get("detail") or {}).get("action") or "")
    perms = final.get("execution_permissions") or {}
    if alpha_action and perms:
        items.append(CrossValidationItem(
            "CV-07", "final_alpha_price_action",
            "pass" if perms.get("alpha_price_action") == alpha_action else "fail",
            f"final={perms.get('alpha_price_action')} report={alpha_action}",
        ))

    trade_path = output_dir / "trade_actions.csv"
    kr_buys = _kr_alpha_executable_buys(trade_path)
    if alpha_action in ("ALPHA_DISABLED", "ALPHA_REVIEW_ONLY") and kr_buys:
        items.append(CrossValidationItem(
            "CV-08", "no_kr_alpha_buy_when_alpha_restricted",
            "fail",
            f"blocked alpha but executable buys: {kr_buys[:5]}",
        ))
    elif alpha_action in ("ALPHA_DISABLED", "ALPHA_REVIEW_ONLY"):
        items.append(CrossValidationItem(
            "CV-08", "no_kr_alpha_buy_when_alpha_restricted",
            "pass",
            "kr_alpha Buy/Replace executable 없음",
        ))

    perm_blocked = set(perms.get("blocked_capabilities") or [])
    if "KR_ALPHA_NEW_BUY" in perm_blocked and kr_buys:
        items.append(CrossValidationItem(
            "CV-09", "permissions_match_trades",
            "fail",
            f"permissions block buys but trade_actions has {kr_buys[:3]}",
        ))

    overall: CheckResult = "pass"
    if any(i.status == "fail" for i in items):
        overall = "fail"
    elif any(i.status == "warn" for i in items):
        overall = "warn"

    return CrossValidationReport(as_of=as_of, overall=overall, items=items)


def write_cross_validation_report(report: CrossValidationReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
