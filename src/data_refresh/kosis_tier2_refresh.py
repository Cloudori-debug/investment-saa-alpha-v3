"""KOSIS tier2 refresh for cpi_kr_yoy / pmi_kr — fail-soft with manual provenance."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import load_yaml
from src.data_refresh.kosis_client import fetch_kosis_field
from src.data_refresh.kosis_tier2_manual import (
    KOSIS_TARGET_FIELDS,
    ensure_manual_template,
    load_verified_manual_overrides,
)
from src.data_refresh.tier2_refresh import (
    Tier2FieldProvenance,
    _field_config_maps,
    _load_existing_row,
    _load_korea_10y,
    _load_provenance_stale_fields,
    _period_to_iso,
    _provenance_entry,
    _stale_reference_date,
    append_tier2_history,
    write_tier2_provenance,
)

MANUAL_FIX = "manual provenance update required — verify value/source/date in data/tier2_kosis_manual.yaml"


@dataclass
class KosisTier2RefreshResult:
    as_of: str
    target_fields: list[str] = field(default_factory=lambda: list(KOSIS_TARGET_FIELDS))
    refreshed_fields: list[str] = field(default_factory=list)
    failed_fields: list[str] = field(default_factory=list)
    manual_required_fields: list[str] = field(default_factory=list)
    manual_applied_fields: list[str] = field(default_factory=list)
    preserved_fields: list[str] = field(default_factory=list)
    stale_before: list[str] = field(default_factory=list)
    stale_after: list[str] = field(default_factory=list)
    provenance_updated: bool = False
    kosis_fetch_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    data_paths: dict[str, str] = field(default_factory=dict)
    field_results: dict[str, dict[str, Any]] = field(default_factory=dict)


def _kosis_api_key(data_dir: Path) -> str:
    from src.data_refresh.tier2_refresh import _kosis_api_key as _key

    return _key(data_dir)


def _query_note(cfg: dict[str, Any], field_name: str) -> str:
    q = (cfg.get("kosis") or {}).get("queries") or {}
    for _key, meta in q.items():
        if isinstance(meta, dict) and str(meta.get("target_field", _key)) == field_name:
            return str(meta.get("note") or f"kosis:{meta.get('tblId', _key)}")
    return ""


def _query_for_field(cfg: dict[str, Any], field_name: str) -> dict[str, Any] | None:
    for _key, meta in ((cfg.get("kosis") or {}).get("queries") or {}).items():
        if isinstance(meta, dict) and str(meta.get("target_field", _key)) == field_name:
            return meta
    return None


def refresh_kosis_tier2_fields(
    data_dir: Path,
    *,
    as_of: str | None = None,
) -> KosisTier2RefreshResult:
    """Attempt KOSIS fetch for KR macro fields; apply verified manual overrides only."""
    ensure_manual_template(data_dir)
    sources_path = data_dir / "tier2_sources.yaml"
    cfg = load_yaml(sources_path) if sources_path.exists() else {}
    thresholds, frequencies = _field_config_maps(cfg)
    as_of_date = as_of or date.today().isoformat()
    macro_path = data_dir / "macro_tier2.csv"
    prov_path = data_dir / "tier2_provenance.json"
    existing = _load_existing_row(macro_path)
    stale_before = _load_provenance_stale_fields(
        prov_path, int(thresholds.get("cpi_kr_yoy", 60)),
    )
    stale_before = [f for f in stale_before if f in KOSIS_TARGET_FIELDS] or [
        f for f in KOSIS_TARGET_FIELDS if f in stale_before
    ]
    if not stale_before:
        stale_before = [f for f in KOSIS_TARGET_FIELDS]

    row = {k: existing.get(k, "") for k in existing}
    row["date"] = as_of_date
    kosis_cfg = cfg.get("kosis") or {}
    kosis_base = str(kosis_cfg.get("base_url", "https://kosis.kr/openapi/Param/statisticsParameterData.do"))
    kosis_key = _kosis_api_key(data_dir)
    kosis_stale_warn = int(kosis_cfg.get("stale_warn_days", 60))
    manual = load_verified_manual_overrides(data_dir)

    result = KosisTier2RefreshResult(
        as_of=as_of_date,
        stale_before=[f for f in KOSIS_TARGET_FIELDS if f in stale_before or f in KOSIS_TARGET_FIELDS],
        data_paths={
            "macro_tier2_csv": str(macro_path),
            "tier2_provenance_json": str(prov_path),
            "tier2_kosis_manual_yaml": str(data_dir / "tier2_kosis_manual.yaml"),
            "tier2_sources_yaml": str(sources_path),
        },
    )
    result.stale_before = [f for f in KOSIS_TARGET_FIELDS if f in _load_provenance_stale_fields(prov_path, 60)]

    provenance_fields: dict[str, Tier2FieldProvenance] = {}
    if prov_path.exists():
        doc = json.loads(prov_path.read_text(encoding="utf-8"))
        for name, meta in (doc.get("fields") or {}).items():
            if not isinstance(meta, dict):
                continue
            provenance_fields[name] = Tier2FieldProvenance(
                source=str(meta.get("source") or ""),
                last_updated=str(meta.get("value_date") or meta.get("last_updated") or ""),
                value=meta.get("value"),
                fallback_used=bool(meta.get("fallback_used")),
                error=meta.get("error"),
            )

    field_meta_out: dict[str, dict[str, Any]] = {}

    for field_name in KOSIS_TARGET_FIELDS:
        query = _query_for_field(cfg, field_name)
        freq = frequencies.get(field_name, "monthly")
        threshold = int(thresholds.get(field_name, kosis_stale_warn))
        note = _query_note(cfg, field_name)
        tbl_id = str((query or {}).get("tblId") or "")

        if field_name in manual:
            m = manual[field_name]
            val = float(m["value"])
            value_date = str(m["value_date"])
            row[field_name] = str(val)
            prov = Tier2FieldProvenance(
                source=str(m["source"]),
                last_updated=value_date,
                value=val,
                fallback_used=False,
                error=None,
            )
            entry = _provenance_entry(
                prov,
                field_name=field_name,
                as_of=as_of_date,
                threshold=threshold,
                frequency=freq,
                fetch_method="manual_verified",
                fetch_status="manual_verified",
                source_url_or_note=str(m.get("source_url_or_note") or note),
                updated_by=str(m.get("updated_by") or ""),
                update_reason=str(m.get("update_reason") or ""),
            )
            provenance_fields[field_name] = prov
            field_meta_out[field_name] = entry
            result.refreshed_fields.append(field_name)
            result.manual_applied_fields.append(field_name)
            result.warnings.append(f"{field_name} applied from manual_verified provenance")
            continue

        if not query:
            result.failed_fields.append(field_name)
            result.manual_required_fields.append(field_name)
            result.kosis_fetch_errors.append(f"{field_name}: missing query in tier2_sources.yaml")
            continue

        from src.data_refresh.kosis_tblid_discovery import INVALID_TBL_IDS

        if tbl_id in INVALID_TBL_IDS:
            preserved_val = existing.get(field_name, "")
            if preserved_val:
                row[field_name] = preserved_val
                result.preserved_fields.append(field_name)
            err = (
                f"KOSIS err=21: known-invalid tblId {tbl_id} "
                "(use manual yaml or tblId discovery)"
            )
            prov = Tier2FieldProvenance(
                source="preserved" if preserved_val else f"kosis:{tbl_id}",
                last_updated="",
                value=float(preserved_val) if preserved_val else None,
                fallback_used=bool(preserved_val),
                error=err,
            )
            entry = _provenance_entry(
                prov,
                field_name=field_name,
                as_of=as_of_date,
                threshold=threshold,
                frequency=freq,
                fetch_method="cache",
                fetch_status="failed",
                source_url_or_note=note,
                recommended_fix=MANUAL_FIX,
                manual_required=True,
            )
            provenance_fields[field_name] = prov
            field_meta_out[field_name] = entry
            result.field_results[field_name] = entry
            result.failed_fields.append(field_name)
            result.manual_required_fields.append(field_name)
            result.kosis_fetch_errors.append(f"{field_name}: {err}")
            result.warnings.append(f"{field_name} 미갱신 — 무효 tblId {tbl_id}")
            continue

        val, period, err = fetch_kosis_field(kosis_base, query, api_key=kosis_key)
        last_dt = _period_to_iso(period) if period else ""
        prov = Tier2FieldProvenance(
            source=f"kosis:{tbl_id}",
            last_updated=last_dt,
        )
        if val is not None and err is None:
            row[field_name] = str(val)
            prov.value = val
            ref_date = _stale_reference_date(last_dt, freq)
            from src.data_refresh.external_market import business_days_between

            prov.stale_business_days = business_days_between(ref_date, as_of_date) if ref_date else 99
            entry = _provenance_entry(
                prov,
                field_name=field_name,
                as_of=as_of_date,
                threshold=threshold,
                frequency=freq,
                fetch_method="kosis",
                fetch_status="success",
                source_url_or_note=note,
            )
            provenance_fields[field_name] = prov
            field_meta_out[field_name] = entry
            result.refreshed_fields.append(field_name)
            if entry.get("status") == "stale":
                result.warnings.append(
                    f"{field_name} fetched but stale {entry.get('stale_days')}bd (ref={ref_date})"
                )
        else:
            preserved_val = existing.get(field_name, "")
            if preserved_val:
                row[field_name] = preserved_val
                result.preserved_fields.append(field_name)
            prov.fallback_used = True
            prov.value = float(preserved_val) if preserved_val else None
            prov.source = "preserved"
            prov.error = err or f"KOSIS {field_name} 실패"
            msg = f"{field_name}: {prov.error}"
            result.kosis_fetch_errors.append(msg)
            result.failed_fields.append(field_name)
            result.manual_required_fields.append(field_name)
            result.warnings.append(f"{field_name} 미갱신 — 이전값 유지")
            entry = _provenance_entry(
                prov,
                field_name=field_name,
                as_of=as_of_date,
                threshold=threshold,
                frequency=freq,
                fetch_method="cache",
                fetch_status="failed",
                source_url_or_note=note,
                recommended_fix=MANUAL_FIX,
                manual_required=True,
            )
            provenance_fields[field_name] = prov
            field_meta_out[field_name] = entry

        result.field_results[field_name] = field_meta_out.get(field_name, {})

    # Recompute real_rate_kr when cpi_kr_yoy may have changed
    k10y = _load_korea_10y(data_dir)
    cpi_kr_raw = row.get("cpi_kr_yoy", "")
    prov_rr = provenance_fields.get("real_rate_kr") or Tier2FieldProvenance(
        source="derived:korea_10y_minus_cpi_kr",
    )
    try:
        if k10y is not None and cpi_kr_raw.strip():
            rr = round(k10y - float(cpi_kr_raw), 2)
            row["real_rate_kr"] = str(rr)
            prov_rr.value = rr
            prov_rr.last_updated = as_of_date
            prov_rr.fallback_used = False
            prov_rr.error = None
            provenance_fields["real_rate_kr"] = prov_rr
    except ValueError:
        result.warnings.append("real_rate_kr 계산 실패")

    from src.data_refresh.tier2_refresh import TIER2_COLUMNS

    out_df = pd.DataFrame([{c: row.get(c, "") for c in TIER2_COLUMNS}], columns=TIER2_COLUMNS)
    macro_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(macro_path, index=False)
    append_tier2_history(data_dir, {c: row.get(c, "") for c in TIER2_COLUMNS})

    if prov_path.exists():
        full_doc = json.loads(prov_path.read_text(encoding="utf-8"))
    else:
        full_doc = {"fields": {}}
    full_fields = dict(full_doc.get("fields") or {})

    for name, prov in provenance_fields.items():
        if name not in KOSIS_TARGET_FIELDS and name != "real_rate_kr":
            continue
        threshold = int(thresholds.get(name, kosis_stale_warn))
        freq = frequencies.get(name, "daily")
        if name in field_meta_out:
            full_fields[name] = field_meta_out[name]
        else:
            method = "derived" if name == "real_rate_kr" else "kosis"
            full_fields[name] = _provenance_entry(
                prov,
                field_name=name,
                as_of=as_of_date,
                threshold=threshold,
                frequency=freq,
                fetch_method=method,
            )

    prov_doc = {
        "as_of": as_of_date,
        "updated_at": date.today().isoformat(),
        "fields": full_fields,
    }
    write_tier2_provenance(data_dir, prov_doc)
    result.provenance_updated = True
    result.stale_after = [
        f for f in KOSIS_TARGET_FIELDS
        if f in _load_provenance_stale_fields(prov_path, int(thresholds.get("cpi_kr_yoy", 60)))
        or f in result.manual_required_fields
    ]
    # manual_required counts as unresolved stale for gate purposes
    for f in result.manual_required_fields:
        if f not in result.stale_after:
            result.stale_after.append(f)
    return result


def merge_kosis_field_results_into_provenance_doc(
    provenance_doc: dict[str, Any],
    field_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    fields = dict(provenance_doc.get("fields") or {})
    for name, entry in field_results.items():
        if entry:
            fields[name] = entry
    provenance_doc["fields"] = fields
    return provenance_doc
