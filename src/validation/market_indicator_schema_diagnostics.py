"""Market indicator schema diagnostics — normalize provenance and report mixed schema."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from src.data_provenance import audit_market_data_consistency
from src.validation.market_indicator_schema import (
    SCHEMA_VERSION,
    assess_market_schema_mixed,
    load_normalized_provenance,
    market_mixed_blocker_fields,
    reconcile_market_provenance_schema,
)

DIAGNOSTICS_JSON = "outputs/market_indicator_schema_diagnostics.json"
FIELD_CSV = "outputs/market_field_status.csv"


def _field_status_rows(fields: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, meta in sorted(fields.items()):
        if not isinstance(meta, dict):
            continue
        mixed = bool(meta.get("mixed_schema_flag"))
        stale_days = int(meta.get("stale_days") or meta.get("stale_business_days") or 0)
        threshold = int(meta.get("threshold_days") or 2)
        status = str(meta.get("status") or "unknown")
        fail_reason = str(meta.get("fail_reason") or "")
        recommended = ""
        if mixed:
            recommended = f"Normalize schema for {name}: set value_date separate from updated_at"
        elif status == "stale":
            recommended = f"Refresh stale market field {name}"
        rows.append(
            {
                "field": name,
                "value": meta.get("value"),
                "value_date": meta.get("value_date") or "",
                "updated_at": meta.get("updated_at") or "",
                "source": meta.get("source") or "",
                "source_file": meta.get("source_file") or "",
                "stale_reference_date": meta.get("stale_reference_date") or "",
                "stale_days": stale_days,
                "threshold_days": threshold,
                "status": status,
                "mixed_schema_flag": mixed,
                "fail_reason": fail_reason,
                "recommended_fix": recommended,
            }
        )
    return rows


def build_market_indicator_schema_diagnostics(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    reconcile_market_provenance_schema(data_dir)
    normalized = load_normalized_provenance(data_dir)
    audit = audit_market_data_consistency(data_dir)

    if not normalized:
        return {
            "schema_version": SCHEMA_VERSION,
            "market_schema_status": "MISSING",
            "mixed_fields": [],
            "normalized_fields": [],
            "unresolved_fields": ["market_data_provenance"],
            "stale_fields": [],
            "timezone_warnings": [],
            "source_file_status": {"market_data_provenance.json": "MISSING"},
            "recommended_fix": ["Refresh market indicators and provenance"],
            "data_gate_expected_impact": "market_field_mixed until provenance exists",
            "field_rows": [],
        }

    fields = normalized.get("fields") or {}
    as_of = str(normalized.get("as_of") or "")
    mixed_fields, normalized_fields, timezone_warnings = assess_market_schema_mixed(fields)
    stale_fields = [
        n
        for n, m in fields.items()
        if isinstance(m, dict) and str(m.get("status") or "") == "stale"
    ]
    unresolved = market_mixed_blocker_fields(fields)

    if mixed_fields:
        market_status = "MIXED"
        gate_impact = f"market_field_mixed: {', '.join(mixed_fields)}"
    elif stale_fields:
        market_status = "STALE"
        gate_impact = "no market_field_mixed; stale fields may affect health_gate"
    else:
        market_status = "NORMALIZED"
        gate_impact = "market_field_mixed blocker cleared for normalized fields"

    recommended: list[str] = []
    if mixed_fields:
        recommended.append(
            f"Fix mixed schema fields ({', '.join(mixed_fields[:5])}) — separate value_date from updated_at"
        )
    if stale_fields:
        recommended.append(f"Refresh stale market fields ({', '.join(stale_fields[:5])})")
    if not mixed_fields and not stale_fields:
        recommended.append("Market schema normalized — calendar lag across US/KR fields is expected")

    field_rows = _field_status_rows(fields)

    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": as_of,
        "market_schema_status": market_status,
        "mixed_fields": mixed_fields,
        "normalized_fields": normalized_fields,
        "unresolved_fields": unresolved,
        "stale_fields": stale_fields,
        "timezone_warnings": timezone_warnings,
        "source_file_status": {
            "market_data_provenance.json": "OK" if (data_dir / "market_data_provenance.json").exists() else "MISSING",
            "market_indicators.csv": "OK" if (data_dir / "market_indicators.csv").exists() else "MISSING",
        },
        "audit_issues": audit.get("issues") or [],
        "field_value_dates": {
            n: m.get("value_date") for n, m in fields.items() if isinstance(m, dict)
        },
        "recommended_fix": recommended,
        "data_gate_expected_impact": gate_impact,
        "diagnostics_path": DIAGNOSTICS_JSON,
        "field_csv_path": FIELD_CSV,
        "field_rows": field_rows,
    }


def write_market_indicator_schema_diagnostics(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    doc = build_market_indicator_schema_diagnostics(data_dir, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    field_rows = doc.pop("field_rows", [])

    json_path = output_dir / "market_indicator_schema_diagnostics.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    csv_path = output_dir / "market_field_status.csv"
    if field_rows:
        fields = list(field_rows[0].keys())
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in field_rows:
                writer.writerow(row)
    else:
        csv_path.write_text("field,value_date,status\n", encoding="utf-8-sig")

    doc["field_rows"] = field_rows
    return doc


def format_market_schema_report_lines(doc: dict[str, Any]) -> list[str]:
    mixed = doc.get("mixed_fields") or []
    stale = doc.get("stale_fields") or []
    fixes = doc.get("recommended_fix") or []
    return [
        "### Market Indicator Schema",
        f"- **Schema status**: `{doc.get('market_schema_status', '—')}` · "
        f"normalized={len(doc.get('normalized_fields') or [])} · "
        f"mixed={len(mixed)}",
        f"- **Mixed fields**: {', '.join(mixed) or '—'}",
        f"- **Stale fields**: {', '.join(stale) or '—'}",
        f"- **Gate impact**: {doc.get('data_gate_expected_impact', '—')}",
        f"- **Fix**: {fixes[0] if fixes else '—'}",
        f"- **Detail**: `{DIAGNOSTICS_JSON}` · `{FIELD_CSV}`",
        "",
    ]
