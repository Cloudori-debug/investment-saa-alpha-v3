"""KOSIS tier2 refresh diagnostics — outputs/kosis_tier2_refresh_diagnostics.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.data_refresh.kosis_tier2_manual import KOSIS_TARGET_FIELDS, list_manual_field_status
from src.data_refresh.kosis_tier2_refresh import KosisTier2RefreshResult, refresh_kosis_tier2_fields
from src.validation.tier2_refresh_diagnostics import _stale_field_names

DIAGNOSTICS_JSON = "outputs/kosis_tier2_refresh_diagnostics.json"


def _gate_impact(stale_after: list[str], manual_required: list[str]) -> tuple[str, str]:
    kosis_stale = [f for f in stale_after if f in KOSIS_TARGET_FIELDS]
    if not kosis_stale and not manual_required:
        return (
            "tier2_kosis_stale_cleared_may_relieve_alpha_gate",
            "data_gate_may_improve_if_market_mixed_also_resolved",
        )
    if manual_required:
        return (
            "alpha_gate_may_remain_YELLOW_kosis_manual_required",
            "data_gate_YELLOW_unchanged_kosis_manual_required",
        )
    return (
        "alpha_gate_may_remain_YELLOW_tier2_stale",
        "data_gate_YELLOW_unchanged_tier2_stale",
    )


def build_kosis_tier2_refresh_diagnostics(
    result: KosisTier2RefreshResult,
    *,
    data_dir: Path,
) -> dict[str, Any]:
    prov_path = data_dir / "tier2_provenance.json"
    provenance: dict[str, Any] = {}
    if prov_path.exists():
        provenance = json.loads(prov_path.read_text(encoding="utf-8"))

    alpha_impact, data_gate_impact = _gate_impact(result.stale_after, result.manual_required_fields)
    recommended: list[str] = []
    if result.manual_required_fields:
        recommended.append(
            "KOSIS fetch failed — manual provenance update required for: "
            + ", ".join(result.manual_required_fields)
        )
        recommended.append(
            "Set verified=true in data/tier2_kosis_manual.yaml only after confirming official value/date/source"
        )
    if result.kosis_fetch_errors:
        recommended.append("KOSIS table/query may be invalid — review data/tier2_sources.yaml tblId")
    if not result.stale_after:
        recommended.append("Re-run data_gate_diagnostics and verify tier2_stale cleared")
    elif result.refreshed_fields:
        recommended.append(
            f"Refreshed: {', '.join(result.refreshed_fields)}; remaining stale: {', '.join(result.stale_after)}"
        )
    if not recommended:
        recommended.append("Monitor KOSIS tier2 fields on next refresh cycle")

    field_detail = {
        name: (provenance.get("fields") or {}).get(name)
        for name in KOSIS_TARGET_FIELDS
    }

    return {
        "schema_version": "1.0",
        "as_of": result.as_of,
        "target_fields": list(KOSIS_TARGET_FIELDS),
        "refreshed_fields": result.refreshed_fields,
        "failed_fields": result.failed_fields,
        "manual_required_fields": result.manual_required_fields,
        "manual_applied_fields": result.manual_applied_fields,
        "stale_before": result.stale_before,
        "stale_after": result.stale_after,
        "provenance_updated": result.provenance_updated,
        "kosis_fetch_errors": result.kosis_fetch_errors,
        "field_provenance": field_detail,
        "manual_yaml_status": list_manual_field_status(data_dir),
        "data_paths": result.data_paths,
        "alpha_gate_expected_impact": alpha_impact,
        "data_gate_expected_impact": data_gate_impact,
        "recommended_next_action": recommended,
        "warnings": result.warnings,
        "diagnostics_path": DIAGNOSTICS_JSON,
    }


def write_kosis_tier2_refresh_diagnostics(
    result: KosisTier2RefreshResult,
    *,
    data_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    doc = build_kosis_tier2_refresh_diagnostics(result, data_dir=data_dir)
    path = output_dir / "kosis_tier2_refresh_diagnostics.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc


def run_kosis_tier2_refresh_with_diagnostics(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
    run_discovery_if_invalid: bool = True,
) -> tuple[KosisTier2RefreshResult, dict[str, Any]]:
    """Fail-soft KOSIS refresh + diagnostics; does not stop pipeline."""
    if run_discovery_if_invalid:
        from src.data_refresh.kosis_tblid_discovery import (
            INVALID_TBL_IDS,
            apply_selected_to_tier2_sources,
            discover_kosis_tblids,
            write_kosis_tblid_discovery,
        )
        from src.config import load_yaml

        cfg = load_yaml(data_dir / "tier2_sources.yaml") if (data_dir / "tier2_sources.yaml").exists() else {}
        queries = (cfg.get("kosis") or {}).get("queries") or {}
        needs_discovery = any(
            str((queries.get(f) or {}).get("tblId") or "") in INVALID_TBL_IDS
            for f in ("cpi_kr_yoy", "pmi_kr")
        )
        if needs_discovery:
            doc = discover_kosis_tblids(data_dir)
            write_kosis_tblid_discovery(data_dir, output_dir)
            apply_selected_to_tier2_sources(data_dir, doc)

    prov_path = data_dir / "tier2_provenance.json"
    stale_before: list[str] = []
    if prov_path.exists():
        before_doc = json.loads(prov_path.read_text(encoding="utf-8"))
        stale_before = [f for f in _stale_field_names(before_doc) if f in KOSIS_TARGET_FIELDS]

    try:
        result = refresh_kosis_tier2_fields(data_dir, as_of=as_of)
        if stale_before and not result.stale_before:
            result.stale_before = stale_before
        diag = write_kosis_tier2_refresh_diagnostics(result, data_dir=data_dir, output_dir=output_dir)
        return result, diag
    except Exception as exc:
        diag = {
            "schema_version": "1.0",
            "as_of": as_of,
            "target_fields": list(KOSIS_TARGET_FIELDS),
            "refreshed_fields": [],
            "failed_fields": list(KOSIS_TARGET_FIELDS),
            "manual_required_fields": list(KOSIS_TARGET_FIELDS),
            "stale_before": stale_before,
            "stale_after": stale_before,
            "provenance_updated": False,
            "kosis_fetch_errors": [str(exc)],
            "alpha_gate_expected_impact": "refresh_failed",
            "data_gate_expected_impact": "unchanged",
            "recommended_next_action": [str(exc), "manual provenance update required"],
            "diagnostics_path": DIAGNOSTICS_JSON,
        }
        path = output_dir / "kosis_tier2_refresh_diagnostics.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(diag, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return KosisTier2RefreshResult(as_of=as_of or "", kosis_fetch_errors=[str(exc)]), diag
