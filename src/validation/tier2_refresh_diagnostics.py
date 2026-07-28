"""Tier2 refresh diagnostics — outputs/tier2_refresh_diagnostics.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.report.io_utils import read_output_json

TIER2_STALE_THRESHOLD_DAYS = 45


def _stale_field_names(provenance: dict[str, Any], *, threshold: int = TIER2_STALE_THRESHOLD_DAYS) -> list[str]:
    fields = provenance.get("fields") or {}
    stale: list[str] = []
    for name, meta in fields.items():
        if not isinstance(meta, dict):
            continue
        status = str(meta.get("status") or "")
        if status == "stale" or status == "manual_required":
            stale.append(name)
        elif status != "fresh" and int(meta.get("stale_business_days") or 0) > threshold:
            stale.append(name)
    return stale


def build_tier2_refresh_diagnostics(
    *,
    refresh_result: Any,
    data_dir: Path,
    output_dir: Path,
    stale_before: list[str] | None = None,
) -> dict[str, Any]:
    prov_path = data_dir / "tier2_provenance.json"
    provenance: dict[str, Any] = {}
    if prov_path.exists():
        provenance = json.loads(prov_path.read_text(encoding="utf-8"))

    stale_after = _stale_field_names(provenance)
    before = stale_before if stale_before is not None else stale_after

    refreshed = [
        f for f in (refresh_result.updated_fields or [])
        if f in {"cpi_us_yoy", "pmi_us", "yield_spread_2y10y", "hy_oas_bp", "cpi_kr_yoy", "pmi_kr"}
    ]
    failed = [
        e.split(":", 1)[0].strip()
        for e in (refresh_result.errors or [])
    ]

    target_fields = ("cpi_us_yoy", "pmi_us")
    target_meta = {f: (provenance.get("fields") or {}).get(f) for f in target_fields}

    alpha_impact = "none"
    if any(f in stale_after for f in target_fields):
        alpha_impact = "alpha_gate_may_remain_YELLOW_tier2_stale"
    elif any(f in before for f in target_fields) and not any(f in stale_after for f in target_fields):
        alpha_impact = "tier2_stale_cleared_expected_alpha_gate_relief"
    elif not stale_after:
        alpha_impact = "tier2_all_fresh"

    recommended: list[str] = []
    if stale_after:
        recommended.append(f"Stale tier2 fields remain: {', '.join(stale_after)}")
        if "cpi_us_yoy" in stale_after:
            recommended.append("CPI US: wait for BLS monthly release or verify FRED CPIAUCSL latest observation")
        if "pmi_us" in stale_after:
            recommended.append("PMI US proxy: verify FRED UMCSENT latest observation or review tier2_sources.yaml")
    else:
        recommended.append("Re-run full_pipeline and verify alpha_gate_diagnostics tier2_provenance_status")

    return {
        "schema_version": "1.0",
        "as_of": refresh_result.as_of,
        "refreshed_fields": refreshed,
        "failed_fields": failed,
        "stale_before": before,
        "stale_after": stale_after,
        "provenance_updated": prov_path.exists(),
        "provenance_path": str(prov_path),
        "macro_tier2_path": str(data_dir / "macro_tier2.csv"),
        "target_fields": {
            f: target_meta.get(f) for f in target_fields
        },
        "alpha_gate_expected_impact": alpha_impact,
        "recommended_next_action": recommended,
        "warnings": list(refresh_result.warnings or []),
        "errors": list(refresh_result.errors or []),
        "api_fields_fetched": refresh_result.api_fields_fetched,
    }


def write_tier2_refresh_diagnostics(
    *,
    refresh_result: Any,
    data_dir: Path,
    output_dir: Path,
    stale_before: list[str] | None = None,
) -> dict[str, Any]:
    doc = build_tier2_refresh_diagnostics(
        refresh_result=refresh_result,
        data_dir=data_dir,
        output_dir=output_dir,
        stale_before=stale_before,
    )
    path = output_dir / "tier2_refresh_diagnostics.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc


def run_tier2_refresh_with_diagnostics(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Refresh tier2 from FRED/KOSIS and write diagnostics (fail-soft)."""
    from src.data_refresh.tier2_refresh import refresh_macro_tier2

    prov_path = data_dir / "tier2_provenance.json"
    stale_before: list[str] = []
    if prov_path.exists():
        before_doc = json.loads(prov_path.read_text(encoding="utf-8"))
        stale_before = _stale_field_names(before_doc)

    try:
        result = refresh_macro_tier2(data_dir, as_of=as_of)
        diag = write_tier2_refresh_diagnostics(
            refresh_result=result,
            data_dir=data_dir,
            output_dir=output_dir,
            stale_before=stale_before,
        )
        return result, diag
    except Exception as exc:
        diag = {
            "schema_version": "1.0",
            "as_of": as_of,
            "refreshed_fields": [],
            "failed_fields": ["tier2_refresh"],
            "stale_before": stale_before,
            "stale_after": stale_before,
            "provenance_updated": False,
            "alpha_gate_expected_impact": "refresh_failed",
            "recommended_next_action": [str(exc)],
            "errors": [str(exc)],
        }
        path = output_dir / "tier2_refresh_diagnostics.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(diag, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        from src.data_refresh.tier2_refresh import Tier2RefreshResult

        return Tier2RefreshResult(as_of=as_of or "", errors=[str(exc)]), diag
