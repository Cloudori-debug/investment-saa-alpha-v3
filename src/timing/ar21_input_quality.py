"""Phase AR-2.1 — timing input quality and readiness QA helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.data_provenance import audit_market_data_consistency, field_stale_days

DEFAULT_STALE_FIELDS: dict[str, list[str]] = {
    "global_beta": ["sp500", "vix", "usdkrw"],
    "duration_bond": ["korea_10y"],
    "duration_kr": ["korea_10y"],
    "duration_us": ["sp500", "usdkrw"],
    "hedge_alt": ["gold", "usdkrw", "vix"],
    "income_alt": ["korea_10y", "sp500"],
    "cash_short_bond": ["korea_10y"],
    "kr_alpha": ["sp500"],
}

MISSING_PROXY_FIELDS: dict[str, list[str]] = {
    "duration_bond": ["us_10y_yield"],
    "duration_us": ["us_10y_yield"],
    "income_alt": ["reit_price_history"],
}


EXECUTION_PROHIBIT_STALE_MARKERS = (
    "reit_price_history_short",
)


def is_timing_execution_prohibited(stale_inputs: list[str] | None) -> bool:
    """Critical stale inputs — timing score remains shadow-only, execution prohibited."""
    for token in stale_inputs or []:
        if token in EXECUTION_PROHIBIT_STALE_MARKERS:
            return True
        if token.startswith("korea_10y_stale_"):
            return True
    return False


def timing_stale_execution_note(stale_inputs: list[str] | None) -> str:
    flagged = [s for s in (stale_inputs or []) if is_timing_execution_prohibited([s])]
    return (
        f"Stale critical input ({', '.join(flagged)}) — timing score shadow-only, execution prohibited"
        if flagged
        else ""
    )


def assess_input_quality(
    data_dir: Path,
    sleeve: str,
    config: dict[str, Any] | None = None,
    *,
    macro: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return input_quality, stale_inputs, input_quality_note for a timing sleeve."""
    cfg = config or {}
    field_map = cfg.get("stale_field_map") or DEFAULT_STALE_FIELDS
    missing_map = cfg.get("missing_proxy_fields") or MISSING_PROXY_FIELDS
    fields = field_map.get(sleeve, [])
    stale_inputs: list[str] = []

    for field in fields:
        is_stale, days = field_stale_days(data_dir, field)
        if is_stale:
            stale_inputs.append(f"{field}_stale_{days}d")

    for proxy in missing_map.get(sleeve, []):
        if proxy == "us_10y_yield":
            if not macro or "yield_spread_2y10y" not in (macro or {}):
                stale_inputs.append("us_10y_proxy_missing")
        elif proxy == "reit_price_history":
            stale_inputs.append("reit_price_history_short")

    audit = audit_market_data_consistency(data_dir)
    if audit.get("issues"):
        for issue in audit["issues"][:2]:
            stale_inputs.append(f"audit:{issue[:60]}")

    if not stale_inputs:
        quality = "ok"
        note = "입력 신선 — timing score 신뢰 가능"
    elif any("stale_" in s and s.endswith("d") and int(s.split("_")[-1].replace("d", "")) > 5 for s in stale_inputs if "stale_" in s):
        quality = "stale"
        note = "stale 입력 — timing score 보수 해석"
    else:
        quality = "warn"
        note = "일부 입력 주의 — timing score 참고용"

    if is_timing_execution_prohibited(stale_inputs):
        quality = "stale"
        note = timing_stale_execution_note(stale_inputs)

    return {
        "input_quality": quality,
        "stale_inputs": stale_inputs,
        "input_quality_note": note,
        "execution_prohibited_stale": is_timing_execution_prohibited(stale_inputs),
    }


def build_timing_execution_note(
    *,
    timing_status: str,
    execution_status: str,
    executable: bool,
    data_gate: str,
    dry_run_days: int,
    dry_run_required: int,
    execution_scope: str,
) -> str:
    if executable:
        return "Timing Ready + execution executable — final_execution_decision 확인 필요"
    parts = [f"Timing {timing_status} ≠ Buy"]
    if data_gate != "GREEN":
        parts.append(f"Gate {data_gate}")
    if dry_run_days < dry_run_required:
        parts.append(f"dry-run {dry_run_days}/{dry_run_required}")
    if execution_scope in {"NO_TRADE", ""}:
        parts.append(f"scope {execution_scope or 'NO_TRADE'}")
    parts.append("Execution blocked")
    return ". ".join(parts) + "."


def score_duration_subcomponents(
    *,
    kr_score: int,
    us_score: int,
    kr_signals: list[str],
    us_signals: list[str],
    kr_stale: list[str],
    us_stale: list[str],
) -> dict[str, Any]:
    """KR/US duration sub-sleeve breakdown (shadow, no separate execution)."""
    return {
        "duration_kr": {
            "ticker": "148070",
            "name": "KIWOOM 국고채10년",
            "timing_score": kr_score,
            "key_signals": kr_signals,
            "stale_inputs": kr_stale,
        },
        "duration_us": {
            "ticker": "308620",
            "name": "KODEX 미국10년국채선물",
            "timing_score": us_score,
            "key_signals": us_signals,
            "stale_inputs": us_stale,
            "note": "US 10Y direct feed 없음 — macro spread proxy",
        },
    }
