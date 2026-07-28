"""Market indicator provenance schema — normalized value_date / updated_at semantics."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.data_refresh.external_market import business_days_between

SCHEMA_VERSION = "2.0"
PROVENANCE_FILE = "market_data_provenance.json"
DEFAULT_THRESHOLD_DAYS = 2
US_EQUITY_ALLOWED_LAG_BD = 3

MARKET_FIELD_CONFIG: dict[str, dict[str, Any]] = {
    "sp500": {
        "market_calendar": "US_EQUITY",
        "timezone": "America/New_York",
        "threshold_days": US_EQUITY_ALLOWED_LAG_BD,
        "source_file": "data/market_data_provenance.json",
    },
    "vix": {
        "market_calendar": "US_EQUITY",
        "timezone": "America/New_York",
        "threshold_days": US_EQUITY_ALLOWED_LAG_BD,
        "source_file": "data/market_data_provenance.json",
    },
    "usdkrw": {
        "market_calendar": "FX_DAILY",
        "timezone": "UTC",
        "threshold_days": DEFAULT_THRESHOLD_DAYS,
        "source_file": "data/market_data_provenance.json",
    },
    "gold": {
        "market_calendar": "COMMODITY_FUTURES",
        "timezone": "America/New_York",
        "threshold_days": DEFAULT_THRESHOLD_DAYS,
        "source_file": "data/market_data_provenance.json",
    },
    "oil_brent": {
        "market_calendar": "COMMODITY_FUTURES",
        "timezone": "America/New_York",
        "threshold_days": DEFAULT_THRESHOLD_DAYS,
        "source_file": "data/market_data_provenance.json",
    },
    "kospi": {
        "market_calendar": "KR_EQUITY",
        "timezone": "Asia/Seoul",
        "threshold_days": DEFAULT_THRESHOLD_DAYS,
        "source_file": "data/market_indicators.csv",
    },
    "korea_10y": {
        "market_calendar": "KR_BOND",
        "timezone": "Asia/Seoul",
        "threshold_days": DEFAULT_THRESHOLD_DAYS,
        "source_file": "data/market_indicators.csv",
    },
    "foreign_flow_3d": {
        "market_calendar": "KR_EQUITY",
        "timezone": "Asia/Seoul",
        "threshold_days": DEFAULT_THRESHOLD_DAYS,
        "source_file": "data/market_indicators.csv",
    },
}


def _date_only(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if "T" in text:
        return text.split("T", 1)[0][:10]
    return text[:10]


def _detect_schema_mixed(field: str, meta: dict[str, Any], value_date: str, updated_at: str) -> tuple[bool, str]:
    if not value_date:
        return True, "missing_value_date"

    raw_vd = meta.get("value_date")
    raw_lu = meta.get("last_updated")
    if raw_lu and not raw_vd:
        return False, ""

    if updated_at and raw_vd and _date_only(updated_at) == value_date:
        if "T" not in updated_at and len(str(updated_at)) == 10 and not meta.get("fetched_at"):
            return True, "updated_at_used_as_value_date"

    sv = str(meta.get("schema_version") or "")
    if sv and sv not in {SCHEMA_VERSION, "1.0"}:
        return True, "schema_version_mismatch"

    tz = str(meta.get("timezone") or "")
    cal = str(meta.get("market_calendar") or "")
    if updated_at and "T" in updated_at and not tz and cal not in {"", "UNKNOWN"}:
        return True, "timezone_missing_for_datetime"

    return False, ""


def normalize_field_meta(
    field: str,
    meta: dict[str, Any],
    *,
    as_of: str,
    prov_updated_at: str = "",
) -> tuple[dict[str, Any], bool, str]:
    """Return (normalized_meta, mixed_schema_flag, fail_reason)."""
    cfg = MARKET_FIELD_CONFIG.get(field, {})
    threshold = int(meta.get("threshold_days") or cfg.get("threshold_days") or DEFAULT_THRESHOLD_DAYS)

    value_date = _date_only(meta.get("value_date") or meta.get("last_updated") or "")
    updated_at = str(meta.get("updated_at") or prov_updated_at or "")
    fetched_at = str(meta.get("fetched_at") or "")

    mixed, fail_reason = _detect_schema_mixed(field, meta, value_date, updated_at)

    stale_ref = _date_only(meta.get("stale_reference_date") or value_date)
    stale_days = int(meta.get("stale_business_days") or meta.get("stale_days") or 0)
    if stale_ref and as_of:
        stale_days = business_days_between(stale_ref, as_of[:10])

    status = "schema_mixed" if mixed else ("stale" if stale_days > threshold else "fresh")

    quality_flag = "ok"
    if meta.get("fallback_used"):
        quality_flag = "fallback"
    if str(meta.get("confidence") or "").lower() == "low":
        quality_flag = "low_confidence"

    normalized: dict[str, Any] = {
        "field": field,
        "value": meta.get("value"),
        "value_date": value_date,
        "updated_at": updated_at or prov_updated_at,
        "source": str(meta.get("source") or ""),
        "source_file": cfg.get("source_file") or PROVENANCE_FILE,
        "fetch_method": str(meta.get("fetch_method") or meta.get("source") or "unknown"),
        "stale_reference_date": stale_ref,
        "stale_days": stale_days,
        "stale_business_days": stale_days,
        "threshold_days": threshold,
        "status": status,
        "market_calendar": cfg.get("market_calendar") or "UNKNOWN",
        "timezone": cfg.get("timezone") or "UTC",
        "quality_flag": quality_flag,
        "fail_reason": fail_reason,
        "mixed_schema_flag": mixed,
        "schema_version": SCHEMA_VERSION,
        "symbol": meta.get("symbol"),
        "confidence": meta.get("confidence"),
        "fallback_used": bool(meta.get("fallback_used")),
    }
    if fetched_at:
        normalized["fetched_at"] = fetched_at
    if meta.get("last_updated"):
        normalized["last_updated"] = meta.get("last_updated")
    return normalized, mixed, fail_reason


def normalize_provenance_doc(prov: dict[str, Any], *, as_of: str | None = None) -> dict[str, Any]:
    as_of_date = _date_only(as_of or prov.get("as_of") or "")
    prov_updated = str(prov.get("updated_at") or datetime.now().isoformat(timespec="seconds"))
    fields_in = prov.get("fields") or {}
    fields_out: dict[str, Any] = {}
    for name, meta in fields_in.items():
        if not isinstance(meta, dict):
            continue
        norm, _, _ = normalize_field_meta(name, meta, as_of=as_of_date, prov_updated_at=prov_updated)
        fields_out[name] = norm
    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": as_of_date or prov.get("as_of"),
        "updated_at": prov_updated,
        "fields": fields_out,
    }


def load_normalized_provenance(data_dir: Path) -> dict[str, Any] | None:
    path = data_dir / PROVENANCE_FILE
    if not path.exists():
        return None
    prov = json.loads(path.read_text(encoding="utf-8"))
    return normalize_provenance_doc(prov, as_of=str(prov.get("as_of") or ""))


def reconcile_market_provenance_schema(data_dir: Path, *, as_of: str | None = None) -> Path | None:
    path = data_dir / PROVENANCE_FILE
    if not path.exists():
        return None
    prov = json.loads(path.read_text(encoding="utf-8"))
    normalized = normalize_provenance_doc(prov, as_of=as_of or str(prov.get("as_of") or ""))
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def assess_market_schema_mixed(fields: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """Return (mixed_fields, normalized_fields, timezone_warnings)."""
    mixed_fields: list[str] = []
    normalized_fields: list[str] = []
    timezone_warnings: list[str] = []

    for name, meta in fields.items():
        if not isinstance(meta, dict):
            continue
        if meta.get("mixed_schema_flag"):
            mixed_fields.append(name)
        else:
            normalized_fields.append(name)
        cal = str(meta.get("market_calendar") or "")
        if cal == "US_EQUITY" and meta.get("value_date"):
            timezone_warnings.append(
                f"{name}: US_EQUITY value_date={meta.get('value_date')} "
                f"(lag vs as_of acceptable up to {US_EQUITY_ALLOWED_LAG_BD}bd)"
            )
    return mixed_fields, normalized_fields, timezone_warnings


def market_mixed_blocker_fields(fields: dict[str, Any]) -> list[str]:
    """Fields contributing to data_gate market_field_mixed blocker."""
    return [n for n, m in fields.items() if isinstance(m, dict) and m.get("mixed_schema_flag")]


def build_normalized_field_from_snapshot(
    field: str,
    *,
    value: float,
    value_date: str,
    source: str,
    fetch_method: str,
    as_of: str,
    symbol: str = "",
    confidence: str = "medium",
    fallback_used: bool = False,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    cfg = MARKET_FIELD_CONFIG.get(field, {})
    threshold = int(cfg.get("threshold_days") or DEFAULT_THRESHOLD_DAYS)
    vd = _date_only(value_date)
    stale_ref = vd
    stale_days = business_days_between(stale_ref, as_of[:10]) if stale_ref and as_of else 0
    now = fetched_at or datetime.now().isoformat(timespec="seconds")
    meta = {
        "field": field,
        "value": value,
        "value_date": vd,
        "updated_at": now,
        "source": source,
        "source_file": cfg.get("source_file") or PROVENANCE_FILE,
        "fetch_method": fetch_method,
        "stale_reference_date": stale_ref,
        "stale_days": stale_days,
        "stale_business_days": stale_days,
        "threshold_days": threshold,
        "status": "stale" if stale_days > threshold else "fresh",
        "market_calendar": cfg.get("market_calendar") or "UNKNOWN",
        "timezone": cfg.get("timezone") or "UTC",
        "quality_flag": "fallback" if fallback_used else "ok",
        "fail_reason": "",
        "mixed_schema_flag": False,
        "schema_version": SCHEMA_VERSION,
        "symbol": symbol,
        "confidence": confidence,
        "fallback_used": fallback_used,
        "fetched_at": now,
    }
    if confidence == "low":
        meta["quality_flag"] = "low_confidence"
    return meta
