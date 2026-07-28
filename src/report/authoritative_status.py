"""Single authoritative status snapshot — green_layers + acceptance + final."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.report.io_utils import read_output_json

EXECUTION_SCOPE_EXPLANATION = (
    "ETF_ONLY is scope restriction, not ETF buy permission. "
    "Actual Buy Allowed=0 means no new buys including ETF."
)

NO_TRADE_USER_LABEL = "NO_TRADE — 신규매수 없음"
ETF_ONLY_DISPLAY_NOTE = "ETF_ONLY는 ETF 매수 허가가 아님"


def _acceptance_gate(acceptance: dict[str, Any] | None, *, ac_id: str, name: str) -> str:
    for item in (acceptance or {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        if item.get("id") == ac_id or item.get("name") == name:
            msg = str(item.get("message") or "")
            if "gate=" in msg:
                return msg.split("gate=", 1)[-1].strip()
            detail = item.get("detail") or {}
            if isinstance(detail, dict) and detail.get("gate"):
                return str(detail["gate"])
    return ""


def _gate_is_red(gate: str) -> bool:
    return str(gate or "").strip().upper() == "RED"


def resolve_authoritative_execution(
    data_dir: Path,
    output_dir: Path,
    *,
    final_doc: dict[str, Any] | None = None,
    acceptance_doc: dict[str, Any] | None = None,
    green: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Conservative execution scope/status — acceptance + gates beat stale final fields."""
    final_doc = final_doc or read_output_json(output_dir / "final_execution_decision.json") or {}
    acceptance_doc = acceptance_doc or read_output_json(output_dir / "acceptance_report.json") or {}

    if green is None:
        from src.validation.green_layers import evaluate_green_layers

        health = read_output_json(output_dir / "system_health.json")
        green = evaluate_green_layers(
            data_dir,
            output_dir,
            health_doc=health,
            acceptance_doc=acceptance_doc,
            final_doc=final_doc,
        )

    unified_gate = _acceptance_gate(acceptance_doc, ac_id="AC-02", name="unified_data_gate")
    portfolio_gate = _acceptance_gate(acceptance_doc, ac_id="AC-03", name="portfolio_gate")
    acceptance_overall = str(acceptance_doc.get("overall") or "").upper()
    acceptance_scope = str(acceptance_doc.get("execution_scope") or "")
    final_scope = str(final_doc.get("execution_scope") or "")
    policy_cap = final_doc.get("policy_cap") or {}
    capped_scope = str(policy_cap.get("capped_execution_scope") or final_scope)

    force_no_trade = (
        acceptance_overall == "RED"
        or _gate_is_red(unified_gate)
        or _gate_is_red(portfolio_gate)
        or green.get("full_status") == "RED"
        or green.get("operational_status") == "RED"
    )

    if force_no_trade:
        execution_scope = "NO_TRADE"
    elif acceptance_scope:
        execution_scope = acceptance_scope
    elif final_scope:
        execution_scope = final_scope
    else:
        execution_scope = capped_scope or "NO_TRADE"

    actual_buy = int(green.get("actual_buy_allowed") or 0)
    no_trade = execution_scope == "NO_TRADE"

    operational_verdict = str(
        acceptance_doc.get("operational_verdict")
        or final_doc.get("operational_verdict")
        or ""
    )
    if force_no_trade and not operational_verdict:
        operational_verdict = (
            f"Overall {acceptance_overall or green.get('full_status', 'RED')} · "
            f"Scope NO_TRADE · Actual Buy Allowed={actual_buy}"
        )

    return {
        "execution_scope": execution_scope,
        "authoritative_execution_scope": execution_scope,
        "display_execution_scope": acceptance_scope or final_scope or capped_scope,
        "no_trade": no_trade,
        "actual_buy_allowed": actual_buy,
        "operational_status": green.get("operational_status"),
        "technical_status": green.get("technical_status"),
        "market_status": green.get("market_status"),
        "full_status": green.get("full_status"),
        "acceptance_overall": acceptance_doc.get("overall") or acceptance_overall,
        "operational_verdict": operational_verdict,
        "unified_data_gate": unified_gate,
        "portfolio_gate": portfolio_gate,
        "technical_execution_scope": final_scope,
        "capped_execution_scope": capped_scope,
        "etf_buy_permission": actual_buy > 0 and not no_trade,
        "execution_scope_explanation": EXECUTION_SCOPE_EXPLANATION,
        "authoritative_source": "acceptance+green_layers",
    }


def patch_alpha_v2_execution_context(data_dir: Path, output_dir: Path) -> bool:
    """Align alpha_v2_summary.execution_context with authoritative status."""
    path = output_dir / "alpha_v2_summary.json"
    if not path.exists():
        return False
    import json

    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    auth = resolve_authoritative_execution(data_dir, output_dir)
    doc["execution_context"] = {
        "actual_buy_allowed": auth["actual_buy_allowed"],
        "no_trade": auth["no_trade"],
        "execution_scope": auth["execution_scope"],
        "market_status": auth.get("market_status"),
        "operational_status": auth.get("operational_status"),
        "full_status": auth.get("full_status"),
        "authoritative_source": auth.get("authoritative_source"),
    }
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def build_authoritative_status_snapshot(
    data_dir: Path,
    output_dir: Path,
    *,
    final_doc: dict[str, Any] | None = None,
    acceptance_doc: dict[str, Any] | None = None,
    green: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Align daily_brief, daily_report summary, and market gates on one source."""
    final_doc = final_doc or read_output_json(output_dir / "final_execution_decision.json") or {}
    acceptance_doc = acceptance_doc or read_output_json(output_dir / "acceptance_report.json") or {}

    if green is None:
        from src.validation.green_layers import evaluate_green_layers

        health = read_output_json(output_dir / "system_health.json")
        green = evaluate_green_layers(
            data_dir,
            output_dir,
            health_doc=health,
            acceptance_doc=acceptance_doc,
            final_doc=final_doc,
        )

    auth_exec = resolve_authoritative_execution(
        data_dir,
        output_dir,
        final_doc=final_doc,
        acceptance_doc=acceptance_doc,
        green=green,
    )

    unified_gate = auth_exec.get("unified_data_gate") or _acceptance_gate(
        acceptance_doc, ac_id="AC-02", name="unified_data_gate"
    )
    portfolio_gate = auth_exec.get("portfolio_gate") or _acceptance_gate(
        acceptance_doc, ac_id="AC-03", name="portfolio_gate"
    )
    alpha_gate = _acceptance_gate(acceptance_doc, ac_id="AC-04", name="alpha_gate")

    perms = final_doc.get("execution_permissions") or {}
    sector_gate = str(
        perms.get("alpha_sector_data_gate")
        or (final_doc.get("execution_permissions") or {}).get("alpha_sector_data_gate")
        or "—"
    )

    user_target_path = data_dir / "user_target_portfolio.csv"
    tickers_in_user_target: list[str] = []
    if user_target_path.exists():
        import csv

        with user_target_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                t = str(row.get("ticker") or "").strip()
                if t:
                    tickers_in_user_target.append(t)

    return {
        "technical_status": green.get("technical_status"),
        "operational_status": auth_exec.get("operational_status") or green.get("operational_status"),
        "market_status": auth_exec.get("market_status") or green.get("market_status"),
        "full_status": auth_exec.get("full_status") or green.get("full_status"),
        "acceptance_overall": auth_exec.get("acceptance_overall") or acceptance_doc.get("overall"),
        "operational_overall": acceptance_doc.get("operational_overall"),
        "technical_overall": acceptance_doc.get("technical_overall"),
        "execution_scope": auth_exec.get("execution_scope"),
        "authoritative_execution_scope": auth_exec.get("authoritative_execution_scope") or auth_exec.get("execution_scope"),
        "display_execution_scope": auth_exec.get("display_execution_scope"),
        "no_trade": auth_exec.get("no_trade"),
        "operational_verdict": auth_exec.get("operational_verdict"),
        "technical_execution_scope": auth_exec.get("technical_execution_scope"),
        "capped_execution_scope": auth_exec.get("capped_execution_scope"),
        "etf_buy_permission": auth_exec.get("etf_buy_permission"),
        "execution_scope_explanation": auth_exec.get("execution_scope_explanation"),
        "actual_buy_allowed": auth_exec.get("actual_buy_allowed", green.get("actual_buy_allowed", 0)),
        "buy_permission_status": green.get("buy_permission_status"),
        "unified_data_gate": unified_gate or str(final_doc.get("data_gate") or ""),
        "portfolio_gate": portfolio_gate or unified_gate or str(final_doc.get("data_gate") or ""),
        "alpha_gate": alpha_gate or str(perms.get("gates", {}).get("alpha_gate") or ""),
        "alpha_sector_data_gate": sector_gate,
        "policy_cap_active": bool((final_doc.get("policy_cap") or {}).get("active")),
        "policy_cap_regime": (final_doc.get("policy_cap") or {}).get("cap_regime"),
        "data_gate_config": str(final_doc.get("data_gate") or ""),
        "030190_in_user_target": "030190" in tickers_in_user_target,
        "030190_in_operational_target": _ticker_in_csv(data_dir / "target_portfolio.csv", "030190"),
        "authoritative_source": auth_exec.get("authoritative_source"),
    }


def _ticker_in_csv(path: Path, ticker: str) -> bool:
    if not path.exists():
        return False
    import csv

    with path.open(encoding="utf-8", newline="") as handle:
        return any(str(row.get("ticker", "")).strip() == ticker for row in csv.DictReader(handle))


def sync_acceptance_authoritative_scope_fields(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Add authoritative/display scope metadata to acceptance_report (no gate logic change)."""
    path = output_dir / "acceptance_report.json"
    if not path.exists():
        return {}
    acceptance_doc = read_output_json(path) or {}
    final_doc = read_output_json(output_dir / "final_execution_decision.json") or {}
    auth = resolve_authoritative_execution(
        data_dir,
        output_dir,
        final_doc=final_doc,
        acceptance_doc=acceptance_doc,
    )
    auth_scope = str(auth.get("execution_scope") or "")
    display_scope = str(
        auth.get("display_execution_scope")
        or acceptance_doc.get("execution_scope")
        or final_doc.get("execution_scope")
        or "",
    )
    acceptance_doc["authoritative_execution_scope"] = auth_scope
    acceptance_doc["display_execution_scope"] = display_scope
    acceptance_doc["execution_scope_explanation"] = EXECUTION_SCOPE_EXPLANATION
    if auth_scope == "NO_TRADE":
        acceptance_doc["execution_permission"] = "NO_TRADE"
    if auth_scope == "NO_TRADE" and display_scope and display_scope != "NO_TRADE":
        acceptance_doc["execution_permission_note"] = (
            f"authoritative={auth_scope}; policy/display scope={display_scope}; "
            f"Actual Buy Allowed={auth.get('actual_buy_allowed', 0)}"
        )
    path.write_text(json.dumps(acceptance_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return acceptance_doc


def refresh_daily_brief_authoritative(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Rewrite daily_brief.json using authoritative acceptance / green_layers."""
    from src.report.export_daily_brief import export_daily_brief, write_daily_brief

    brief = export_daily_brief(output_dir, as_of=as_of, run_id=run_id, data_dir=data_dir)
    write_daily_brief(output_dir / "daily_brief.json", brief)
    return brief
