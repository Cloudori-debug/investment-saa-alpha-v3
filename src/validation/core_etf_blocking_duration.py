"""Core ETF permission blocking duration — diagnostic only (P5-A).

Does NOT change gate / policy_cap / Actual Buy Allowed / approval_bridge.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.report.io_utils import read_output_json

OUTPUT_NAME = "core_etf_blocking_duration.json"

_REASON_KEYS = (
    "data_gate_yellow",
    "policy_cap_active",
    "health_gate_yellow",
    "target_guard_conflict",
    "no_trade_scope",
)


def _parse_day(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return None


def _infer_reasons(row: dict[str, Any]) -> list[str]:
    """Infer restriction drivers from bundle_reconciliation (and similar) fields.

    decision_log historically lacks core_etf_permission; these are proxies.
    """
    reasons: list[str] = []
    health = str(row.get("health_gate") or "").upper()
    if health in {"YELLOW", "RED"}:
        reasons.append("health_gate_yellow")

    acceptance = str(row.get("acceptance_overall") or row.get("data_gate") or "").upper()
    if acceptance in {"YELLOW", "RED"}:
        reasons.append("data_gate_yellow")

    if row.get("target_guard_conflict_detected") or row.get("conflict_detected"):
        reasons.append("target_guard_conflict")

    operational = str(row.get("operational_status") or "").upper()
    if operational == "YELLOW":
        # YELLOW operational usually accompanies policy_cap / review-only ETF path
        reasons.append("policy_cap_active")

    scope = str(row.get("execution_scope") or "").upper()
    if scope == "NO_TRADE":
        reasons.append("no_trade_scope")

    # Explicit fields when present (future-enriched logs)
    perm = str(row.get("core_etf_permission") or "").upper()
    for reason in row.get("restriction_reasons") or []:
        r = str(reason).lower()
        if "health" in r:
            reasons.append("health_gate_yellow")
        elif "data_gate" in r or "portfolio_gate" in r:
            reasons.append("data_gate_yellow")
        elif "policy_cap" in r:
            reasons.append("policy_cap_active")
        elif "target_guard" in r or "conflict" in r:
            reasons.append("target_guard_conflict")
    if perm in {"RESTRICTED", "BLOCKED"} and not reasons:
        reasons.append("data_gate_yellow")

    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _is_restricted_day(reasons: list[str], row: dict[str, Any]) -> bool:
    if reasons:
        return True
    perm = str(row.get("core_etf_permission") or "").upper()
    return perm in {"RESTRICTED", "BLOCKED"}


def _load_decision_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            event = obj.get("event")
            # Prefer bundle_reconciliation; also accept legacy unknown rows with gate fields
            if event == "bundle_reconciliation" or (
                event is None and ("data_gate" in obj or "health_gate" in obj or "acceptance_overall" in obj)
            ):
                rows.append(obj)
    return rows


def _day_aggregate(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """One entry per as_of date — last event wins for status; union reasons."""
    by_day: dict[str, dict[str, Any]] = {}
    for row in rows:
        day = _parse_day(row.get("as_of")) or _parse_day(row.get("timestamp"))
        if not day:
            continue
        reasons = _infer_reasons(row)
        prev = by_day.get(day)
        if prev is None:
            by_day[day] = {
                "as_of": day,
                "reasons": list(reasons),
                "restricted": _is_restricted_day(reasons, row),
                "row": row,
            }
            continue
        merged = list(dict.fromkeys([*(prev["reasons"] or []), *reasons]))
        by_day[day] = {
            "as_of": day,
            "reasons": merged,
            "restricted": prev["restricted"] or _is_restricted_day(merged, row),
            "row": row,  # latest wins
        }
    return by_day


def compute_core_etf_blocking_duration(
    decision_log_path: Path,
    as_of: str,
    lookback_days: int = 30,
    *,
    core_etf_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """decision_log.jsonl 기반 Core ETF RESTRICTED 지속일·원인 빈도 진단."""
    as_of_day = _parse_day(as_of) or as_of[:10]
    try:
        as_of_dt = datetime.strptime(as_of_day, "%Y-%m-%d").date()
    except ValueError:
        as_of_dt = datetime.now().date()
        as_of_day = as_of_dt.isoformat()

    start = (as_of_dt - timedelta(days=max(lookback_days - 1, 0))).isoformat()
    by_day = _day_aggregate(_load_decision_rows(decision_log_path))
    days_sorted = sorted(d for d in by_day if start <= d <= as_of_day)

    reason_freq: Counter[str] = Counter()
    restricted_days = 0
    for d in days_sorted:
        entry = by_day[d]
        if not entry.get("restricted"):
            continue
        restricted_days += 1
        for r in entry.get("reasons") or []:
            if r in _REASON_KEYS:
                reason_freq[r] += 1
            else:
                reason_freq[r] += 1

    # Current streak: consecutive restricted logged days ending at last day <= as_of
    streak = 0
    for d in reversed(days_sorted):
        if d > as_of_day:
            continue
        if not by_day[d].get("restricted"):
            break
        streak += 1

    dominant = ""
    if reason_freq:
        dominant = sorted(reason_freq.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

    diag = core_etf_diagnostics or {}
    eligible = int(diag.get("eligible_etf_underweight_count") or 0)
    today_perm = str(diag.get("core_etf_permission") or "")
    today_reasons = [str(x) for x in (diag.get("restriction_reasons") or [])]

    # Prefer today's diagnostic reason mapping for dominant when available
    mapped_today: list[str] = []
    for r in today_reasons:
        low = r.lower()
        if "health" in low:
            mapped_today.append("health_gate_yellow")
        elif "data_gate" in low or "portfolio_gate" in low:
            mapped_today.append("data_gate_yellow")
        elif "policy_cap" in low:
            mapped_today.append("policy_cap_active")
        elif "actual_buy" in low:
            mapped_today.append("actual_buy_allowed_zero")
        elif "conflict" in low or "target_guard" in low:
            mapped_today.append("target_guard_conflict")
    if today_perm.upper() in {"RESTRICTED", "BLOCKED"}:
        if streak == 0:
            streak = 1
            restricted_days = max(restricted_days, 1)
        if mapped_today and (not dominant or dominant == "unknown"):
            dominant = mapped_today[0]

    freq_out = {k: int(reason_freq.get(k, 0)) for k in _REASON_KEYS}
    for k, v in reason_freq.items():
        if k not in freq_out:
            freq_out[k] = int(v)

    return {
        "schema_version": "1.0",
        "as_of": as_of_day,
        "lookback_days": lookback_days,
        "core_etf_permission_today": today_perm or None,
        "core_etf_restricted_days_current_streak": int(streak),
        "core_etf_restricted_days_last_30d": int(restricted_days),
        "dominant_restriction_reason": dominant or "unknown",
        "reason_frequency_last_30d": freq_out,
        "eligible_etf_underweight_count_today": eligible,
        "today_restriction_reasons": today_reasons,
        "logged_days_in_window": len(days_sorted),
        "method": "decision_log_bundle_reconciliation_proxy + today_core_etf_diagnostics",
        "limitation": (
            "Historical decision_log rows usually omit core_etf_permission; "
            "restriction days are inferred from health_gate/acceptance/conflict/operational proxies."
        ),
        "note": "진단 전용 — gate/policy_cap 미변경. Actual Buy Allowed에 영향 없음.",
    }


def write_core_etf_blocking_duration(
    output_dir: Path,
    *,
    as_of: str,
    lookback_days: int = 30,
    decision_log_path: Path | None = None,
    core_etf_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    log_path = decision_log_path or (output_dir / "decision_log.jsonl")
    diag = core_etf_diagnostics
    if diag is None:
        diag = read_output_json(output_dir / "core_etf_permission_diagnostics.json") or {}
    doc = compute_core_etf_blocking_duration(
        log_path,
        as_of,
        lookback_days=lookback_days,
        core_etf_diagnostics=diag,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / OUTPUT_NAME).write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return doc


def format_core_etf_blocking_duration_line(doc: dict[str, Any] | None) -> str:
    if not doc:
        return (
            "- **Core ETF 잠김 지속**: n/a — 진단 산출물 없음 "
            "(gate/policy 미변경)"
        )
    streak = doc.get("core_etf_restricted_days_current_streak")
    reason = doc.get("dominant_restriction_reason") or "unknown"
    eligible = doc.get("eligible_etf_underweight_count_today")
    return (
        f"- **Core ETF 잠김 지속**: {streak}일 연속 "
        f"(주 원인: `{reason}`) · 즉시 집행 가능 후보 {eligible}건 "
        f"— 진단 전용, Actual Buy Allowed 불변"
    )


__all__ = [
    "OUTPUT_NAME",
    "compute_core_etf_blocking_duration",
    "format_core_etf_blocking_duration_line",
    "write_core_etf_blocking_duration",
]
