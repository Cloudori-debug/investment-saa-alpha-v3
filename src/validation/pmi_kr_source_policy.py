"""PMI KR source policy — explicit provenance rules without forced fresh."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.data_refresh.kosis_tier2_manual import list_manual_field_status
from src.report.io_utils import read_output_json

POLICY_JSON = "outputs/pmi_kr_source_policy.json"
PMI_FIELD = "pmi_kr"
ALT_FIELD = "pmi_kr_alt"
ALT_CANDIDATE_FIELD = "pmi_kr_alt_candidate"
MANUFACTURING_SENTIMENT_FIELD = "manufacturing_sentiment_kr"

WARNING_NO_FORCED_FRESH = (
    "Do not mark pmi_kr fresh without verified official PMI source — "
    "alternative indicators stay in pmi_kr_alt / manufacturing_sentiment_kr."
)


def _load_pmi_provenance(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "tier2_provenance.json"
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    meta = (doc.get("fields") or {}).get(PMI_FIELD)
    return meta if isinstance(meta, dict) else {}


def _alt_indicators_from_discovery(output_dir: Path) -> list[dict[str, Any]]:
    doc = read_output_json(output_dir / "kosis_tblid_discovery.json") or {}
    alts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in ("pmi_kr_alt_candidates",):
        for row in doc.get(key) or []:
            if not isinstance(row, dict):
                continue
            tbl = str(row.get("candidate_tbl_id") or "")
            if not tbl or tbl in seen:
                continue
            seen.add(tbl)
            alts.append(
                {
                    "field": ALT_CANDIDATE_FIELD,
                    "separate_field": ALT_FIELD,
                    "tbl_id": tbl,
                    "table_name": row.get("table_name"),
                    "latest_value": row.get("latest_value"),
                    "latest_value_date": row.get("latest_value_date"),
                    "recommended_mapping": row.get("recommended_mapping")
                    or f"{ALT_FIELD} — do not auto-map to {PMI_FIELD}",
                    "role": row.get("role") or "pmi_kr_alt_candidate",
                }
            )
    pmi_block = doc.get(PMI_FIELD) or {}
    for row in pmi_block.get("non_exact_candidates") or []:
        if not isinstance(row, dict):
            continue
        tbl = str(row.get("candidate_tbl_id") or "")
        if not tbl or tbl in seen:
            continue
        seen.add(tbl)
        alts.append(
            {
                "field": ALT_CANDIDATE_FIELD,
                "separate_field": ALT_FIELD,
                "tbl_id": tbl,
                "table_name": row.get("table_name"),
                "latest_value": row.get("latest_value"),
                "latest_value_date": row.get("latest_value_date"),
                "recommended_mapping": row.get("recommended_mapping")
                or f"{ALT_FIELD} — do not auto-map to {PMI_FIELD}",
                "role": row.get("role") or "pmi_kr_alt_candidate",
            }
        )
    return alts[:20]


def build_pmi_kr_source_policy(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    prov = _load_pmi_provenance(data_dir)
    manual = list_manual_field_status(data_dir).get(PMI_FIELD) or {}
    discovery = read_output_json(output_dir / "kosis_tblid_discovery.json") or {}
    pmi_discovery = discovery.get(PMI_FIELD) or {}

    verified = bool(manual.get("verified"))
    pmi_status = str(prov.get("status") or "unknown")
    kosis_unavailable = bool(
        pmi_discovery.get("pmi_kr_kosis_unavailable")
        or pmi_discovery.get("selected") is None
    )
    exact_selected = pmi_discovery.get("selected")
    exact_source_available = bool(exact_selected and not kosis_unavailable)

    alt_indicators = _alt_indicators_from_discovery(output_dir)
    pmi_kr_alt_available = len(alt_indicators) > 0

    manual_required = (
        not verified
        and pmi_status in {"manual_required", "stale", "failed", "unknown", ""}
    ) or (not verified and kosis_unavailable)

    if verified:
        pmi_kr_status = "manual_verified"
        selected_source = str(prov.get("source") or "manual_verified")
        recommended_policy = "pmi_kr manual_verified — monitor monthly refresh"
        data_gate_impact = "pmi_kr tier2_stale may clear if value/date verified"
    elif kosis_unavailable:
        pmi_kr_status = "manual_required"
        selected_source = str(prov.get("source") or "") or None
        recommended_policy = (
            "Keep pmi_kr manual_required; confirm official PMI source before verified=true. "
            f"Use {ALT_FIELD} or {MANUFACTURING_SENTIMENT_FIELD} for alternatives — no auto-map to pmi_kr."
        )
        data_gate_impact = "data_gate primary blocker remains tier2_stale until pmi_kr resolved or policy excludes"
    else:
        pmi_kr_status = pmi_status or "manual_required"
        selected_source = str(prov.get("source") or "") or None
        recommended_policy = "Await KOSIS exact PMI tblId or verified manual provenance"
        data_gate_impact = "data_gate YELLOW until pmi_kr fresh or verified manual"

    return {
        "schema_version": "1.0",
        "pmi_kr_status": pmi_kr_status,
        "exact_source_available": exact_source_available,
        "selected_source": selected_source,
        "manual_required": manual_required,
        "pmi_kr_kosis_unavailable": kosis_unavailable,
        "alternative_indicators": alt_indicators,
        "pmi_kr_alt_available": pmi_kr_alt_available,
        "pmi_kr_alt_field": ALT_FIELD,
        "manufacturing_sentiment_kr_field": MANUFACTURING_SENTIMENT_FIELD,
        "auto_map_alt_to_pmi_kr": False,
        "manual_yaml_verified": verified,
        "tier2_provenance_status": pmi_status,
        "recommended_policy": recommended_policy,
        "data_gate_impact": data_gate_impact,
        "warning": WARNING_NO_FORCED_FRESH,
        "policy_path": POLICY_JSON,
    }


def write_pmi_kr_source_policy(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    doc = build_pmi_kr_source_policy(data_dir, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "pmi_kr_source_policy.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return doc


def format_pmi_kr_preflight_report_lines(
    policy: dict[str, Any],
    preflight: dict[str, Any] | None = None,
) -> list[str]:
    pre = preflight or {}
    current = (pre.get("scenarios") or {}).get("current") or {}
    secondary = current.get("remaining_secondary_blockers") or []
    return [
        "### PMI KR / Data Gate Preflight",
        f"- **PMI KR**: `{policy.get('pmi_kr_status', '—')}` · manual_required=`{policy.get('manual_required')}`",
        f"- **Exact KOSIS PMI**: {'unavailable' if policy.get('pmi_kr_kosis_unavailable') else 'candidate exists'}",
        f"- **Market schema**: resolved",
        f"- **CPI KR**: fresh",
        f"- **Remaining primary blocker**: pmi_kr manual_required"
        if policy.get("manual_required")
        else "- **Remaining primary blocker**: —",
        f"- **Secondary blockers**: {', '.join(secondary) or 'PIT YELLOW / fundamental stale / flow warning'}",
        "- **Counterfactual only** — not execution permission",
        f"- **Policy**: `{POLICY_JSON}` · preflight=`outputs/data_gate_green_preflight.json`",
        "",
    ]
