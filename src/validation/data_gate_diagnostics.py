"""Unified data_gate YELLOW root-cause diagnostics."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from src.data_provenance import audit_market_data_consistency
from src.report.authoritative_status import resolve_authoritative_execution
from src.report.execution_metrics import count_executable_actions
from src.report.io_utils import read_output_json
from src.validation.alpha_gate_diagnostics import _tier2_stale_fields
from src.validation.fail_soft_pipeline import _sector_coverage_from_gpt
from src.validation.fail_soft_permissions import ALPHA_SECTOR_TOP10_MIN_COVERAGE_PCT

DIAGNOSTICS_JSON = "outputs/data_gate_diagnostics.json"
FIELD_CSV = "outputs/data_gate_field_status.csv"
TRACE_JSON = "outputs/data_gate_to_permission_trace.json"
ETF_ONLY_NOTE = "ETF_ONLY is execution scope constraint — not ETF buy permission."

CATEGORY_TIER2_STALE = "tier2_stale"
CATEGORY_MARKET_MIXED = "market_field_mixed"
CATEGORY_PRICE_COVERAGE = "price_coverage_issue"
CATEGORY_SECTOR_COVERAGE = "sector_coverage_issue"
CATEGORY_FUNDAMENTAL_STALE = "fundamental_stale"
CATEGORY_PIT_YELLOW = "pit_data_yellow"
CATEGORY_SOURCE_MISSING = "source_missing"
CATEGORY_SOURCE_PARSE = "source_parse_error"
CATEGORY_THRESHOLD = "threshold_not_met"
CATEGORY_FLOW_WARNING = "flow_data_warning"


def _health_check(health: dict[str, Any], name: str) -> dict[str, Any]:
    for chk in health.get("checks") or []:
        if isinstance(chk, dict) and chk.get("name") == name:
            return chk
    return {}


def _read_log(output_dir: Path) -> dict[str, Any]:
    log_path = output_dir / "decision_log.jsonl"
    if not log_path.exists():
        return {}
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return {}
    return json.loads(lines[-1])


def _gate_from_acceptance(acceptance: dict[str, Any], ac_id: str) -> str:
    for item in acceptance.get("items") or []:
        if not isinstance(item, dict) or item.get("id") != ac_id:
            continue
        msg = str(item.get("message") or "")
        if "gate=" in msg:
            return msg.split("gate=", 1)[-1].strip()
        detail = item.get("detail") or {}
        if isinstance(detail, dict) and detail.get("gate"):
            return str(detail["gate"])
    return ""


def _append_field_row(
    rows: list[dict[str, Any]],
    *,
    field_name: str,
    gate_area: str,
    source_file: str,
    required: bool,
    value: str = "",
    value_date: str = "",
    updated_at: str = "",
    stale_reference_date: str = "",
    stale_days: int | str = "",
    threshold_days: int | str = "",
    status: str,
    fail_reason: str = "",
    impacted_gate: str = "",
    impacted_permission: str = "",
    recommended_fix: str = "",
    category: str = "",
) -> None:
    rows.append({
        "field_name": field_name,
        "gate_area": gate_area,
        "source_file": source_file,
        "required": required,
        "value": value,
        "value_date": value_date,
        "updated_at": updated_at,
        "stale_reference_date": stale_reference_date,
        "stale_days": stale_days,
        "threshold_days": threshold_days,
        "status": status,
        "fail_reason": fail_reason or category,
        "impacted_gate": impacted_gate,
        "impacted_permission": impacted_permission,
        "recommended_fix": recommended_fix,
        "_category": category,
    })


def _build_tier2_field_rows(data_dir: Path) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    rows: list[dict[str, Any]] = []
    stale_names: list[str] = []
    categories: list[str] = []
    prov_path = data_dir / "tier2_provenance.json"
    if not prov_path.exists():
        categories.append(CATEGORY_SOURCE_MISSING)
        _append_field_row(
            rows,
            field_name="tier2_provenance",
            gate_area="tier2",
            source_file="data/tier2_provenance.json",
            required=True,
            status="MISSING",
            fail_reason=CATEGORY_SOURCE_MISSING,
            impacted_gate="health_gate,unified_data_gate",
            impacted_permission="core_etf_permission",
            recommended_fix="Run tier2 API refresh to create tier2_provenance.json",
            category=CATEGORY_SOURCE_MISSING,
        )
        return rows, stale_names, categories

    try:
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        categories.append(CATEGORY_SOURCE_PARSE)
        _append_field_row(
            rows,
            field_name="tier2_provenance",
            gate_area="tier2",
            source_file="data/tier2_provenance.json",
            required=True,
            status="PARSE_ERROR",
            fail_reason=CATEGORY_SOURCE_PARSE,
            impacted_gate="health_gate",
            impacted_permission="core_etf_permission",
            recommended_fix="Fix or regenerate tier2_provenance.json",
            category=CATEGORY_SOURCE_PARSE,
        )
        return rows, stale_names, categories

    tier2_status, stale_tier2 = _tier2_stale_fields(data_dir)
    for meta_row in stale_tier2:
        name = str(meta_row.get("stale_field") or "")
        stale_names.append(name)
        categories.append(CATEGORY_TIER2_STALE)
        fix = (
            "manual_provenance_update_required"
            if str(meta_row.get("status") or "") == "manual_required"
            else ("fix_api_or_manual_override" if meta_row.get("fallback_used") else "refresh_api_source")
        )
        fail_cat = (
            "manual_required"
            if str(meta_row.get("status") or "") == "manual_required"
            else CATEGORY_TIER2_STALE
        )
        _append_field_row(
            rows,
            field_name=name,
            gate_area="tier2",
            source_file="data/tier2_provenance.json",
            required=True,
            value=str(meta_row.get("source") or ""),
            value_date=str(meta_row.get("last_updated") or ""),
            updated_at=str(meta_row.get("last_updated") or ""),
            stale_reference_date=str(meta_row.get("stale_reference_date") or ""),
            stale_days=meta_row.get("stale_days", ""),
            threshold_days=meta_row.get("threshold_days", ""),
            status=str(meta_row.get("status") or "stale"),
            fail_reason=fail_cat,
            impacted_gate="health_gate,alpha_gate,unified_data_gate",
            impacted_permission="core_etf_permission",
            recommended_fix=f"{fix} for {name}",
            category=fail_cat,
        )

    for name, meta in (prov.get("fields") or {}).items():
        if not isinstance(meta, dict):
            continue
        if name in stale_names:
            continue
        _append_field_row(
            rows,
            field_name=name,
            gate_area="tier2",
            source_file="data/tier2_provenance.json",
            required=True,
            value=str(meta.get("source") or ""),
            value_date=str(meta.get("value_date") or meta.get("last_updated") or ""),
            updated_at=str(meta.get("last_updated") or ""),
            stale_reference_date=str(meta.get("stale_reference_date") or ""),
            stale_days=meta.get("stale_business_days", 0),
            threshold_days=meta.get("threshold_days", 45),
            status=str(meta.get("status") or "fresh"),
            fail_reason="",
            impacted_gate="",
            impacted_permission="",
            recommended_fix="",
            category="",
        )

    if tier2_status in {"STALE", "WARN"} and CATEGORY_TIER2_STALE not in categories:
        categories.append(CATEGORY_TIER2_STALE)
    return rows, stale_names, categories


def _build_market_field_rows(data_dir: Path) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    from src.validation.market_indicator_schema import (
        load_normalized_provenance,
        market_mixed_blocker_fields,
        reconcile_market_provenance_schema,
    )

    rows: list[dict[str, Any]] = []
    mixed_fields: list[str] = []
    categories: list[str] = []

    reconcile_market_provenance_schema(data_dir)
    prov_path = data_dir / "market_data_provenance.json"
    if not prov_path.exists():
        categories.append(CATEGORY_SOURCE_MISSING)
        _append_field_row(
            rows,
            field_name="market_data_provenance",
            gate_area="market",
            source_file="data/market_data_provenance.json",
            required=True,
            status="MISSING",
            fail_reason=CATEGORY_SOURCE_MISSING,
            impacted_gate="health_gate,unified_data_gate",
            impacted_permission="core_etf_permission",
            recommended_fix="Refresh market indicators and provenance",
            category=CATEGORY_SOURCE_MISSING,
        )
        return rows, mixed_fields, categories

    normalized = load_normalized_provenance(data_dir) or {}
    fields = normalized.get("fields") or {}
    mixed_blocker_names = set(market_mixed_blocker_fields(fields))
    as_of = str(normalized.get("as_of") or "")

    for name, meta in fields.items():
        if not isinstance(meta, dict):
            continue
        mixed = name in mixed_blocker_names
        if mixed:
            mixed_fields.append(name)
            if CATEGORY_MARKET_MIXED not in categories:
                categories.append(CATEGORY_MARKET_MIXED)
        value_date = str(meta.get("value_date") or "")
        updated_at = str(meta.get("updated_at") or "")
        stale_days = int(meta.get("stale_days") or meta.get("stale_business_days") or 0)
        threshold = int(meta.get("threshold_days") or 2)
        field_status = str(meta.get("status") or "fresh")
        if mixed:
            row_status = "mixed"
        elif field_status == "stale" or stale_days > threshold:
            row_status = "stale"
        else:
            row_status = "fresh"
        _append_field_row(
            rows,
            field_name=name,
            gate_area="market",
            source_file="data/market_data_provenance.json",
            required=True,
            value=str(meta.get("value") or ""),
            value_date=value_date,
            updated_at=updated_at,
            stale_reference_date=str(meta.get("stale_reference_date") or value_date),
            stale_days=stale_days,
            threshold_days=threshold,
            status=row_status,
            fail_reason=CATEGORY_MARKET_MIXED if mixed else (CATEGORY_THRESHOLD if stale_days > threshold else ""),
            impacted_gate="health_gate,unified_data_gate" if mixed or stale_days > threshold else "",
            impacted_permission="core_etf_permission" if mixed or stale_days > threshold else "",
            recommended_fix=(
                str(meta.get("fail_reason") or f"Normalize schema for {name}")
                if mixed
                else (f"Refresh stale market field {name}" if stale_days > threshold else "")
            ),
            category=CATEGORY_MARKET_MIXED if mixed else (CATEGORY_THRESHOLD if stale_days > threshold else ""),
        )

    audit = audit_market_data_consistency(data_dir)
    for issue in audit.get("issues") or []:
        if "schema mixed" in str(issue) and CATEGORY_MARKET_MIXED not in categories:
            categories.append(CATEGORY_MARKET_MIXED)
    return rows, mixed_fields, categories


def _build_price_field_rows(output_dir: Path, health: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    categories: list[str] = []
    price_report = read_output_json(output_dir / "price_coverage_report.json") or {}

    for check_name in ("core_price_gate", "alpha_price_gate", "prices_coverage"):
        chk = _health_check(health, check_name)
        if not chk and check_name in price_report:
            sub = price_report.get(check_name) or {}
            chk = {"status": sub.get("status", "pass"), "message": "; ".join(sub.get("reasons") or [])}
        if not chk:
            continue
        status = str(chk.get("status") or "pass")
        if status in {"fail", "warn"}:
            categories.append(CATEGORY_PRICE_COVERAGE)
        detail = chk.get("detail") or {}
        stale_lists = []
        for key in ("stale_core", "stale_core_critical", "stale_alpha_top30", "missing_alpha_top30"):
            stale_lists.extend(detail.get(key) or price_report.get(check_name, {}).get(key) or [])

        _append_field_row(
            rows,
            field_name=check_name,
            gate_area="price",
            source_file="outputs/price_coverage_report.json",
            required=check_name != "alpha_price_gate",
            value=str(chk.get("message") or ""),
            status=status,
            fail_reason=CATEGORY_PRICE_COVERAGE if status in {"fail", "warn"} else "",
            impacted_gate="health_gate,unified_data_gate" if status in {"fail", "warn"} else "alpha_gate",
            impacted_permission=(
                "core_etf_permission,actual_buy_allowed"
                if check_name == "core_price_gate" and status == "fail"
                else "alpha_auto_buy_permission"
            ),
            recommended_fix=str(chk.get("message") or "Improve price coverage"),
            category=CATEGORY_PRICE_COVERAGE if status in {"fail", "warn"} else "",
        )

        for ticker in stale_lists[:5]:
            categories.append(CATEGORY_PRICE_COVERAGE)
            _append_field_row(
                rows,
                field_name=str(ticker),
                gate_area="price",
                source_file="outputs/price_coverage_report.json",
                required=False,
                status="stale",
                fail_reason=CATEGORY_PRICE_COVERAGE,
                impacted_gate="health_gate",
                impacted_permission="core_etf_permission" if check_name == "core_price_gate" else "alpha_auto_buy",
                recommended_fix=f"Refresh price for {ticker}",
                category=CATEGORY_PRICE_COVERAGE,
            )
    return rows, categories


def _build_sector_field_rows(output_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    categories: list[str] = []
    cov, sector_gate = _sector_coverage_from_gpt(output_dir)
    top10 = float(cov.get("top10_sector_coverage_pct") or 0)
    resolved = top10 >= ALPHA_SECTOR_TOP10_MIN_COVERAGE_PCT
    status = "resolved" if resolved else "fail"
    if not resolved:
        categories.append(CATEGORY_SECTOR_COVERAGE)
    _append_field_row(
        rows,
        field_name="top10_sector_coverage_pct",
        gate_area="sector",
        source_file="outputs/gpt_context.json",
        required=True,
        value=str(top10),
        status=status if resolved else "below_threshold",
        fail_reason="" if resolved else CATEGORY_SECTOR_COVERAGE,
        impacted_gate=str(sector_gate or "alpha_sector_data_gate"),
        impacted_permission="alpha_auto_buy_permission",
        recommended_fix=(
            "Sector top10 coverage resolved — mapping patch effective"
            if resolved
            else f"Raise top10 sector coverage above {ALPHA_SECTOR_TOP10_MIN_COVERAGE_PCT}%"
        ),
        category="" if resolved else CATEGORY_SECTOR_COVERAGE,
    )
    return rows, categories


def _build_pit_fundamental_flow_rows(
    output_dir: Path,
    alpha_diag: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    categories: list[str] = []
    pit = alpha_diag.get("pit_data_status") or {}
    fund = alpha_diag.get("fundamental_data_status") or {}
    flow = alpha_diag.get("flow_data_status") or {}
    pit_gate = str(pit.get("gate") or "—")
    if pit_gate == "YELLOW":
        categories.append(CATEGORY_PIT_YELLOW)
    _append_field_row(
        rows,
        field_name="pit_fundamental_gate",
        gate_area="pit",
        source_file="outputs/gpt_context.json",
        required=True,
        value=pit_gate,
        status=pit_gate.lower() if pit_gate else "unknown",
        fail_reason=CATEGORY_PIT_YELLOW if pit_gate == "YELLOW" else "",
        impacted_gate="alpha_gate,unified_data_gate",
        impacted_permission="alpha_auto_buy_permission",
        recommended_fix="Refresh PIT fundamentals and resolve stale exclusions",
        category=CATEGORY_PIT_YELLOW if pit_gate == "YELLOW" else "",
    )
    excluded = fund.get("excluded_summary") or {}
    stale_n = int(excluded.get("stale_data") or 0)
    if stale_n > 0:
        categories.append(CATEGORY_FUNDAMENTAL_STALE)
        _append_field_row(
            rows,
            field_name="fundamental_stale_exclusions",
            gate_area="fundamental",
            source_file="outputs/gpt_context.json",
            required=False,
            value=str(stale_n),
            status="stale",
            fail_reason=CATEGORY_FUNDAMENTAL_STALE,
            impacted_gate="alpha_gate",
            impacted_permission="alpha_auto_buy_permission",
            recommended_fix="Refresh stale fundamental inputs for excluded tickers",
            category=CATEGORY_FUNDAMENTAL_STALE,
        )
    flow_status = str(flow.get("status") or "unknown")
    if flow_status == "degraded":
        categories.append(CATEGORY_FLOW_WARNING)
        _append_field_row(
            rows,
            field_name="flow_refresh",
            gate_area="flow",
            source_file="outputs/gpt_context.json",
            required=False,
            value=str(flow.get("fresh_ratio") or ""),
            status=flow_status,
            fail_reason=CATEGORY_FLOW_WARNING,
            impacted_gate="alpha_gate",
            impacted_permission="alpha_auto_buy_permission",
            recommended_fix="Improve flow data fresh_ratio above 0.8",
            category=CATEGORY_FLOW_WARNING,
        )
    return rows, categories


def _categorize_blockers(categories: list[str], field_rows: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    primary: list[str] = []
    secondary: list[str] = []
    cat_set = set(categories)
    if CATEGORY_TIER2_STALE in cat_set or "manual_required" in cat_set:
        primary.append("tier2_stale")
    if CATEGORY_MARKET_MIXED in cat_set:
        primary.append("market_field_mixed")
    if CATEGORY_PIT_YELLOW in cat_set:
        secondary.append("pit_data_yellow")
    if CATEGORY_PRICE_COVERAGE in cat_set:
        secondary.append("price_coverage_issue")
    if CATEGORY_SECTOR_COVERAGE in cat_set:
        secondary.append("sector_coverage_issue")
    if CATEGORY_FUNDAMENTAL_STALE in cat_set:
        secondary.append("fundamental_stale")
    if CATEGORY_SOURCE_MISSING in cat_set:
        primary.append("source_missing")
    if CATEGORY_SOURCE_PARSE in cat_set:
        primary.append("source_parse_error")
    if CATEGORY_THRESHOLD in cat_set:
        secondary.append("threshold_not_met")
    if CATEGORY_FLOW_WARNING in cat_set:
        secondary.append("flow_data_warning")

    stale_fields = [
        r["field_name"] for r in field_rows
        if r.get("_category") in {CATEGORY_TIER2_STALE, "manual_required"}
    ]
    mixed_fields = [r["field_name"] for r in field_rows if r.get("_category") == CATEGORY_MARKET_MIXED]
    return primary, secondary, stale_fields, mixed_fields


def _source_file_status(data_dir: Path, output_dir: Path) -> dict[str, str]:
    files = {
        "tier2_provenance.json": data_dir / "tier2_provenance.json",
        "market_data_provenance.json": data_dir / "market_data_provenance.json",
        "market_indicators.csv": data_dir / "market_indicators.csv",
        "system_health.json": output_dir / "system_health.json",
        "price_coverage_report.json": output_dir / "price_coverage_report.json",
        "gpt_context.json": output_dir / "gpt_context.json",
        "final_execution_decision.json": output_dir / "final_execution_decision.json",
    }
    out: dict[str, str] = {}
    for name, path in files.items():
        if not path.exists():
            out[name] = "MISSING"
        else:
            try:
                if path.suffix == ".json":
                    json.loads(path.read_text(encoding="utf-8"))
                out[name] = "OK"
            except (json.JSONDecodeError, OSError):
                out[name] = "PARSE_ERROR"
    return out


def build_data_gate_permission_trace(
    *,
    data_gate_status: str,
    alpha_gate_status: str,
    core_etf_doc: dict[str, Any],
    alpha_diag: dict[str, Any],
    counterfactual: dict[str, Any],
    actual_buy: int,
    final_doc: dict[str, Any],
) -> dict[str, Any]:
    perms = final_doc.get("execution_permissions") or {}
    core_actual = str(perms.get("core_etf_permission") or core_etf_doc.get("core_etf_permission") or "BLOCKED")
    all_soft = (counterfactual.get("scenarios") or {}).get("all_soft_blockers_cleared") or {}
    etf_unrestricted = (counterfactual.get("scenarios") or {}).get("policy_cap_removed_and_core_etf_unrestricted") or {}

    core_after = "REVIEW_ONLY" if data_gate_status == "YELLOW" else core_actual
    if data_gate_status == "YELLOW":
        core_before = str(all_soft.get("core_etf_permission") or "ALLOWED")
    else:
        core_before = core_actual

    shortlist = int(alpha_diag.get("shortlist_pool_diagnostic", {}).get("shortlist_eligible_count") or 0)
    alpha_blocked_by_data = alpha_gate_status in {"YELLOW", "RED"}
    etf_blocked_by_data = data_gate_status in {"YELLOW", "RED"}

    remaining_if_green = list(all_soft.get("remaining_blockers") or [])
    return {
        "data_gate_status": data_gate_status,
        "core_etf_permission_before": core_before,
        "core_etf_permission_after_data_gate": core_after if data_gate_status == "YELLOW" else core_actual,
        "core_etf_permission_actual": core_actual,
        "alpha_gate_before": alpha_gate_status,
        "alpha_gate_after_data_gate": alpha_gate_status,
        "alpha_gate_status": alpha_gate_status,
        "actual_buy_allowed_trace": {
            "actual_buy_allowed": actual_buy,
            "blocked_by_data_gate": actual_buy == 0 and etf_blocked_by_data,
            "note": "Actual Buy Allowed unchanged by diagnostics",
        },
        "etf_path_blocked_by_data_gate": etf_blocked_by_data,
        "alpha_path_blocked_by_data_gate": alpha_blocked_by_data,
        "alpha_path_separate_blocker": "shortlist_eligible=0" if shortlist == 0 else None,
        "remaining_blockers_if_data_gate_green": remaining_if_green,
        "counterfactual_data_gate_green": {
            "would_open_buy_path": all_soft.get("would_open_buy_path"),
            "etf_path_open": all_soft.get("etf_path_open"),
            "alpha_path_open": all_soft.get("alpha_path_open"),
            "hypothetical_actual_buy_allowed": all_soft.get("hypothetical_actual_buy_allowed"),
            "core_etf_permission": all_soft.get("core_etf_permission"),
            "first_remaining_blocker": all_soft.get("first_remaining_blocker"),
            "alpha_path_blocker": all_soft.get("alpha_path_blocker"),
        },
        "counterfactual_core_etf_unrestricted": {
            "hypothetical_etf_buys": etf_unrestricted.get("hypothetical_actual_buy_allowed"),
            "etf_path_open": etf_unrestricted.get("etf_path_open"),
        },
        "execution_scope_note": ETF_ONLY_NOTE,
    }


def build_data_gate_diagnostics(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    from src.validation.alpha_gate_diagnostics import build_alpha_gate_diagnostics
    from src.validation.core_etf_permission_diagnostics import build_core_etf_permission_diagnostics
    from src.validation.policy_cap_counterfactual import build_policy_cap_counterfactual

    final_doc = read_output_json(output_dir / "final_execution_decision.json") or {}
    acceptance = read_output_json(output_dir / "acceptance_report.json") or {}
    health = read_output_json(output_dir / "system_health.json") or {}
    log = _read_log(output_dir)
    auth = resolve_authoritative_execution(data_dir, output_dir, final_doc=final_doc, acceptance_doc=acceptance)

    alpha_diag = build_alpha_gate_diagnostics(data_dir, output_dir)
    core_etf_doc = read_output_json(output_dir / "core_etf_permission_diagnostics.json") or {}
    if not core_etf_doc:
        core_etf_doc = build_core_etf_permission_diagnostics(data_dir, output_dir)
    counterfactual = build_policy_cap_counterfactual(data_dir, output_dir)
    metrics = count_executable_actions(final_doc)
    actual_buy = int(metrics.get("actual_buy_allowed_count") or 0)

    data_gate_status = str(
        auth.get("unified_data_gate")
        or final_doc.get("data_gate")
        or log.get("data_gate")
        or "YELLOW"
    )
    unified_status = str(auth.get("unified_data_gate") or data_gate_status)
    portfolio_gate = str(
        auth.get("portfolio_gate")
        or log.get("portfolio_gate")
        or _gate_from_acceptance(acceptance, "AC-03")
        or "GREEN"
    )
    alpha_gate_status = str(alpha_diag.get("alpha_gate_status") or log.get("alpha_gate") or "—")
    health_gate_status = str(
        log.get("health_gate")
        or ("RED" if health.get("overall") == "fail" else "YELLOW" if health.get("overall") == "warn" else "GREEN")
    )

    field_rows: list[dict[str, Any]] = []
    all_categories: list[str] = []

    tier2_rows, stale_names, tier2_cats = _build_tier2_field_rows(data_dir)
    field_rows.extend(tier2_rows)
    all_categories.extend(tier2_cats)

    market_rows, mixed_names, market_cats = _build_market_field_rows(data_dir)
    field_rows.extend(market_rows)
    all_categories.extend(market_cats)

    price_rows, price_cats = _build_price_field_rows(output_dir, health)
    field_rows.extend(price_rows)
    all_categories.extend(price_cats)

    sector_rows, sector_cats = _build_sector_field_rows(output_dir)
    field_rows.extend(sector_rows)
    all_categories.extend(sector_cats)

    pit_rows, pit_cats = _build_pit_fundamental_flow_rows(output_dir, alpha_diag)
    field_rows.extend(pit_rows)
    all_categories.extend(pit_cats)

    primary_blockers, secondary_blockers, stale_fields, mixed_fields = _categorize_blockers(
        all_categories, field_rows,
    )
    if data_gate_status == "YELLOW" and not primary_blockers and not secondary_blockers:
        secondary_blockers.append("unified_data_gate=YELLOW")

    tier2_status, _ = _tier2_stale_fields(data_dir)
    tier2_health = _health_check(health, "tier2_provenance")
    market_audit = audit_market_data_consistency(data_dir)
    from src.validation.market_indicator_schema_diagnostics import build_market_indicator_schema_diagnostics

    market_schema_doc = build_market_indicator_schema_diagnostics(data_dir, output_dir)
    cov, sector_gate = _sector_coverage_from_gpt(output_dir)
    price_report = read_output_json(output_dir / "price_coverage_report.json") or {}

    impact_core_etf = {
        "data_gate_status": data_gate_status,
        "core_etf_permission": core_etf_doc.get("core_etf_permission"),
        "etf_new_buy_state": core_etf_doc.get("etf_new_buy_state"),
        "mechanism": "data_gate=YELLOW → core_etf=REVIEW_ONLY/RESTRICTED",
        "aligned_with_core_etf_diagnostics": (
            str(core_etf_doc.get("data_gate_status") or "") == data_gate_status
        ),
        "eligible_etf_underweight_if_unrestricted": core_etf_doc.get("eligible_etf_underweight_count"),
        "actual_etf_buy_allowed": core_etf_doc.get("actual_buy_allowed"),
    }
    impact_alpha = {
        "alpha_gate_status": alpha_gate_status,
        "aligned_with_alpha_gate_diagnostics": alpha_gate_status == alpha_diag.get("alpha_gate_status"),
        "shortlist_eligible_count": (alpha_diag.get("shortlist_pool_diagnostic") or {}).get("shortlist_eligible_count"),
        "separate_alpha_blocker": "shortlist_eligible=0",
        "tier2_contribution": tier2_status in {"STALE", "WARN"},
        "pit_contribution": (alpha_diag.get("pit_data_status") or {}).get("gate") == "YELLOW",
    }
    impact_buy = {
        "actual_buy_allowed": actual_buy,
        "data_gate_blocks_etf_execution": data_gate_status in {"YELLOW", "RED"},
        "note": ETF_ONLY_NOTE,
    }

    recommended: list[str] = []
    if stale_names:
        recommended.append(
            f"Refresh stale tier2 fields ({', '.join(stale_names[:5])}) — KOSIS fallback if API fails"
        )
    if mixed_names:
        recommended.append(
            f"Fix mixed market field schema ({', '.join(mixed_names[:5])}) — value_date/updated_at separation"
        )
    if (alpha_diag.get("pit_data_status") or {}).get("gate") == "YELLOW":
        recommended.append("Resolve PIT/fundamental YELLOW — stale exclusions and missing fundamentals")
    if float(cov.get("top10_sector_coverage_pct") or 0) >= ALPHA_SECTOR_TOP10_MIN_COVERAGE_PCT:
        recommended.append("Sector top10 coverage resolved — no sector mapping action required")
    if data_gate_status == "YELLOW":
        recommended.append(
            "data_gate=YELLOW keeps core_etf=RESTRICTED — fix data freshness before expecting ETF buys"
        )
    if not recommended:
        recommended.append("Monitor data_gate drivers; no single dominant category")

    permission_trace = build_data_gate_permission_trace(
        data_gate_status=data_gate_status,
        alpha_gate_status=alpha_gate_status,
        core_etf_doc=core_etf_doc,
        alpha_diag=alpha_diag,
        counterfactual=counterfactual,
        actual_buy=actual_buy,
        final_doc=final_doc,
    )

    return {
        "schema_version": "1.0",
        "as_of": final_doc.get("as_of") or acceptance.get("as_of") or log.get("as_of"),
        "run_id": final_doc.get("run_id") or acceptance.get("run_id") or log.get("run_id"),
        "data_gate_status": data_gate_status,
        "unified_data_gate_status": unified_status,
        "portfolio_gate_status": portfolio_gate,
        "alpha_gate_status": alpha_gate_status,
        "health_gate_status": health_gate_status,
        "primary_data_blockers": primary_blockers,
        "secondary_data_blockers": secondary_blockers,
        "stale_fields": stale_fields,
        "missing_fields": [k for k, v in _source_file_status(data_dir, output_dir).items() if v == "MISSING"],
        "mixed_market_fields": mixed_names,
        "source_file_status": _source_file_status(data_dir, output_dir),
        "freshness_thresholds": {
            "tier2_stale_warn_days": 45,
            "market_stale_warn_business_days": 2,
            "top10_sector_coverage_min_pct": ALPHA_SECTOR_TOP10_MIN_COVERAGE_PCT,
            "price_coverage_report": price_report.get("thresholds") or {},
        },
        "tier2_status": tier2_status,
        "tier2_health_message": tier2_health.get("message"),
        "market_data_status": {
            "audit_issues": market_audit.get("issues") or [],
            "max_stale_business_days": market_audit.get("max_stale_business_days"),
            "field_last_updated": market_audit.get("field_last_updated"),
            "field_value_dates": market_audit.get("field_value_dates"),
            "schema_mixed_fields": market_audit.get("schema_mixed_fields"),
        },
        "market_schema_status": {
            "status": market_schema_doc.get("market_schema_status"),
            "mixed_fields": market_schema_doc.get("mixed_fields"),
            "normalized_fields": market_schema_doc.get("normalized_fields"),
            "data_gate_expected_impact": market_schema_doc.get("data_gate_expected_impact"),
            "diagnostics_path": "outputs/market_indicator_schema_diagnostics.json",
        },
        "price_data_status": {
            "gate_status": price_report.get("gate_status"),
            "core_price_gate": price_report.get("core_price_gate", {}).get("status"),
            "alpha_price_gate": price_report.get("alpha_price_gate", {}).get("status"),
        },
        "sector_data_status": {
            "top10_sector_coverage_pct": cov.get("top10_sector_coverage_pct"),
            "alpha_sector_data_gate": sector_gate,
            "resolved": float(cov.get("top10_sector_coverage_pct") or 0) >= ALPHA_SECTOR_TOP10_MIN_COVERAGE_PCT,
        },
        "fundamental_data_status": alpha_diag.get("fundamental_data_status"),
        "pit_data_status": alpha_diag.get("pit_data_status"),
        "flow_data_status": alpha_diag.get("flow_data_status"),
        "impact_on_core_etf_permission": impact_core_etf,
        "impact_on_alpha_gate": impact_alpha,
        "impact_on_actual_buy_allowed": impact_buy,
        "recommended_fix": recommended,
        "diagnostics_path": DIAGNOSTICS_JSON,
        "field_csv_path": FIELD_CSV,
        "permission_trace_path": TRACE_JSON,
        "field_rows": field_rows,
        "permission_trace": permission_trace,
    }


def write_data_gate_diagnostics(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    from src.validation.market_indicator_schema_diagnostics import write_market_indicator_schema_diagnostics

    write_market_indicator_schema_diagnostics(data_dir, output_dir)
    doc = build_data_gate_diagnostics(data_dir, output_dir)

    from src.validation.pmi_kr_source_policy import write_pmi_kr_source_policy
    from src.validation.data_gate_green_preflight import write_data_gate_green_preflight

    write_pmi_kr_source_policy(data_dir, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    field_rows = doc.pop("field_rows", [])
    permission_trace = doc.pop("permission_trace", {})

    json_path = output_dir / "data_gate_diagnostics.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    write_data_gate_green_preflight(data_dir, output_dir)

    from src.validation.pmi_kr_manual_verified_reevaluation import write_pmi_kr_manual_verified_reevaluation

    write_pmi_kr_manual_verified_reevaluation(data_dir, output_dir)

    trace_path = output_dir / "data_gate_to_permission_trace.json"
    trace_path.write_text(json.dumps(permission_trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    csv_path = output_dir / "data_gate_field_status.csv"
    if field_rows:
        export_rows = [{k: v for k, v in row.items() if k != "_category"} for row in field_rows]
        fields = list(export_rows[0].keys())
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in export_rows:
                writer.writerow(row)
    else:
        csv_path.write_text("field_name,gate_area,status\n", encoding="utf-8-sig")

    doc["field_rows"] = field_rows
    doc["permission_trace"] = permission_trace
    return doc


def data_gate_summary_for_no_action(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "data_gate_status": doc.get("data_gate_status"),
        "unified_data_gate_status": doc.get("unified_data_gate_status"),
        "primary_data_blockers": doc.get("primary_data_blockers"),
        "secondary_data_blockers": doc.get("secondary_data_blockers"),
        "stale_fields": doc.get("stale_fields"),
        "mixed_market_fields": doc.get("mixed_market_fields"),
        "sector_coverage_resolved": (doc.get("sector_data_status") or {}).get("resolved"),
        "data_gate_diagnostics_path": DIAGNOSTICS_JSON,
    }


def data_gate_tags_for_no_action(doc: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    status = str(doc.get("data_gate_status") or "")
    if status:
        tags.append(f"data_gate={status}")
    for blocker in (doc.get("primary_data_blockers") or [])[:3]:
        tags.append(f"data_gate_primary:{blocker}")
    stale = doc.get("stale_fields") or []
    if stale:
        tags.append(f"data_gate_stale:{','.join(stale[:3])}")
    mixed = doc.get("mixed_market_fields") or []
    if mixed:
        tags.append(f"data_gate_mixed_market:{','.join(mixed[:3])}")
    sector = doc.get("sector_data_status") or {}
    if sector.get("resolved"):
        tags.append("sector_coverage=resolved")
    tags.append(f"see:{DIAGNOSTICS_JSON}")
    return tags


def format_data_gate_report_lines(doc: dict[str, Any]) -> list[str]:
    fixes = doc.get("recommended_fix") or []
    stale = doc.get("stale_fields") or []
    mixed = doc.get("mixed_market_fields") or []
    impact_etf = doc.get("impact_on_core_etf_permission") or {}
    impact_alpha = doc.get("impact_on_alpha_gate") or {}
    primary = doc.get("primary_data_blockers") or []
    mschema = doc.get("market_schema_status") or {}
    return [
        "### Data Gate Diagnostic",
        f"> **{ETF_ONLY_NOTE}**",
        f"- **Data gate**: `{doc.get('data_gate_status', '—')}` · "
        f"unified=`{doc.get('unified_data_gate_status', '—')}` · "
        f"health=`{doc.get('health_gate_status', '—')}` · "
        f"alpha=`{doc.get('alpha_gate_status', '—')}`",
        f"- **Main reasons**: {', '.join(primary) or '—'}",
        f"- **Stale fields**: {', '.join(stale) or '—'}",
        f"- **Mixed market fields**: {', '.join(mixed) or '—'}",
        f"- **Market schema**: `{mschema.get('status', '—')}` · "
        f"normalized={len(mschema.get('normalized_fields') or [])} · "
        f"impact={mschema.get('data_gate_expected_impact', '—')}",
        f"- **ETF permission impact**: data_gate → core_etf=`{impact_etf.get('core_etf_permission', '—')}` "
        f"(underweight if unrestricted={impact_etf.get('eligible_etf_underweight_if_unrestricted', 0)})",
        f"- **Alpha gate impact**: alpha_gate=`{impact_alpha.get('alpha_gate_status', '—')}` · "
        f"shortlist_eligible={impact_alpha.get('shortlist_eligible_count', 0)} "
        f"(separate blocker: {impact_alpha.get('separate_alpha_blocker', '—')})",
        f"- **Sector coverage**: "
        f"{'resolved' if (doc.get('sector_data_status') or {}).get('resolved') else 'open'} "
        f"({(doc.get('sector_data_status') or {}).get('top10_sector_coverage_pct', '—')}%)",
        f"- **Required fix**: {fixes[0] if fixes else '—'}",
        f"- **Detail**: `{DIAGNOSTICS_JSON}` · `{FIELD_CSV}` · `{TRACE_JSON}`",
        "",
    ]
