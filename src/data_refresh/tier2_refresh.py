from __future__ import annotations

import json
import os
import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from src.compass.tier2_macro import MacroTier2
from src.config import load_yaml
from src.data_refresh.external_market import business_days_between
from src.data_refresh.fred_client import fetch_fred_field
from src.data_refresh.kosis_client import fetch_kosis_field

TIER2_COLUMNS = [
    "date", "pmi_kr", "pmi_us", "cpi_kr_yoy", "cpi_us_yoy",
    "yield_spread_2y10y", "hy_oas_bp", "real_rate_kr",
]


@dataclass
class Tier2FieldProvenance:
    source: str
    last_updated: str = ""
    stale_business_days: int = 0
    value: float | None = None
    fallback_used: bool = False
    error: str | None = None


@dataclass
class Tier2RefreshResult:
    as_of: str
    updated_fields: list[str] = field(default_factory=list)
    preserved_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    path: str = ""
    provenance_path: str = ""
    api_fields_fetched: int = 0
    stale_before: list[str] = field(default_factory=list)
    stale_after: list[str] = field(default_factory=list)


def _fred_api_key(data_dir: Path) -> str:
    from src.settings.user_secrets import apply_secrets_to_env

    apply_secrets_to_env(data_dir)
    return os.environ.get("FRED_API_KEY", "").strip()


def _kosis_api_key(data_dir: Path) -> str:
    from src.settings.user_secrets import apply_secrets_to_env

    apply_secrets_to_env(data_dir)
    return os.environ.get("KOSIS_API_KEY", "").strip()


def _load_existing_row(path: Path) -> dict[str, str]:
    if not path.exists():
        return {c: "" for c in TIER2_COLUMNS}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if df.empty:
        return {c: "" for c in TIER2_COLUMNS}
    return {c: str(df.iloc[-1].get(c, "")) for c in TIER2_COLUMNS}


def _load_korea_10y(data_dir: Path) -> float | None:
    mi_path = data_dir / "market_indicators.csv"
    if not mi_path.exists():
        return None
    df = pd.read_csv(mi_path, dtype=str, keep_default_na=False)
    if df.empty:
        return None
    raw = str(df.iloc[-1].get("korea_10y", "")).strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def _period_to_iso(period: str) -> str:
    """KOSIS YYYYMM → 해당 월 말일 근사."""
    p = period.strip()
    if len(p) >= 6 and p[:6].isdigit():
        y, m = int(p[:4]), int(p[4:6])
        if m == 12:
            return f"{y}-12-31"
        nxt = date(y, m + 1, 1) - timedelta(days=1)
        return nxt.isoformat()
    return period[:10] if len(p) >= 10 else ""


def _month_end_date(iso_date: str) -> str:
    """Observation month-end for monthly macro staleness (not month-start)."""
    if not iso_date or len(iso_date) < 7:
        return iso_date[:10] if iso_date else ""
    try:
        y, m = int(iso_date[:4]), int(iso_date[5:7])
        last = calendar.monthrange(y, m)[1]
        return f"{y:04d}-{m:02d}-{last:02d}"
    except ValueError:
        return iso_date[:10]


def _stale_reference_date(obs_date: str, frequency: str) -> str:
    if frequency == "monthly" and obs_date:
        return _month_end_date(obs_date)
    return obs_date[:10] if obs_date else ""


def _provenance_status(
    *,
    stale_days: int,
    threshold: int,
    fallback_used: bool,
    error: str | None,
    manual_required: bool = False,
) -> str:
    if manual_required:
        return "manual_required"
    if error and fallback_used:
        return "stale"
    if stale_days > threshold:
        return "stale"
    return "fresh"


def _load_provenance_stale_fields(path: Path, threshold: int) -> list[str]:
    if not path.exists():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    stale: list[str] = []
    for name, meta in (doc.get("fields") or {}).items():
        if not isinstance(meta, dict):
            continue
        status = str(meta.get("status") or "")
        if status in {"stale", "manual_required"}:
            stale.append(name)
        elif status != "fresh" and int(meta.get("stale_business_days") or 0) > threshold:
            stale.append(name)
    return stale


def _provenance_entry(
    prov: Tier2FieldProvenance,
    *,
    field_name: str,
    as_of: str,
    threshold: int,
    frequency: str = "daily",
    fetch_method: str = "fred",
    fetch_status: str | None = None,
    source_url_or_note: str = "",
    updated_by: str = "",
    update_reason: str = "",
    recommended_fix: str = "",
    manual_required: bool = False,
) -> dict[str, Any]:
    ref_date = _stale_reference_date(prov.last_updated, frequency)
    stale_days = business_days_between(ref_date, as_of) if ref_date else int(prov.stale_business_days or 0)
    status = _provenance_status(
        stale_days=stale_days,
        threshold=threshold,
        fallback_used=prov.fallback_used,
        error=prov.error,
        manual_required=manual_required,
    )
    if fetch_status is None:
        if prov.error and prov.fallback_used:
            fetch_status = "failed"
        elif fetch_method == "manual_verified":
            fetch_status = "manual_verified"
        else:
            fetch_status = "success"
    entry: dict[str, Any] = {
        "field": field_name,
        "value": prov.value,
        "source": prov.source,
        "value_date": prov.last_updated,
        "stale_reference_date": ref_date,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "last_updated": prov.last_updated,
        "stale_business_days": stale_days,
        "stale_days": stale_days,
        "threshold_days": threshold,
        "status": status,
        "fetch_method": fetch_method,
        "fetch_status": fetch_status,
        "fallback_used": prov.fallback_used,
    }
    if source_url_or_note:
        entry["source_url_or_note"] = source_url_or_note
    if updated_by:
        entry["updated_by"] = updated_by
    if update_reason:
        entry["update_reason"] = update_reason
    if recommended_fix:
        entry["recommended_fix"] = recommended_fix
    if prov.error:
        entry["error"] = prov.error
    if frequency != "daily":
        entry["frequency"] = frequency
    return entry


def _build_provenance(
    fields: dict[str, Tier2FieldProvenance],
    as_of: str,
    *,
    thresholds: dict[str, int],
    frequencies: dict[str, str],
    fetch_methods: dict[str, str],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, prov in fields.items():
        threshold = int(thresholds.get(name, 45))
        freq = frequencies.get(name, "daily")
        method = fetch_methods.get(name, "fred" if prov.source.startswith("fred:") else "cache")
        if prov.fallback_used:
            method = "cache"
        if prov.source.startswith("kosis:"):
            method = "kosis"
        if prov.source.startswith("derived:"):
            method = "derived"
        out[name] = _provenance_entry(
            prov,
            field_name=name,
            as_of=as_of,
            threshold=threshold,
            frequency=freq,
            fetch_method=method,
        )
    return {
        "as_of": as_of,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "fields": out,
    }


def _field_config_maps(cfg: dict[str, Any]) -> tuple[dict[str, int], dict[str, str]]:
    thresholds: dict[str, int] = {}
    frequencies: dict[str, str] = {}
    fred_cfg = cfg.get("fred") or {}
    fred_stale = int(fred_cfg.get("stale_warn_days", 45))
    for _key, spec in (fred_cfg.get("series") or {}).items():
        if not isinstance(spec, dict):
            continue
        target = str(spec.get("target_field", _key))
        thresholds[target] = fred_stale
        frequencies[target] = str(spec.get("frequency", "daily"))
    kosis_cfg = cfg.get("kosis") or {}
    kosis_stale = int(kosis_cfg.get("stale_warn_days", 60))
    for _key, query in (kosis_cfg.get("queries") or {}).items():
        if not isinstance(query, dict):
            continue
        target = str(query.get("target_field", _key))
        thresholds[target] = kosis_stale
        freq = str(query.get("frequency", ""))
        if not freq:
            freq = "monthly" if str(query.get("prdSe", "")).upper() == "M" else "daily"
        frequencies[target] = freq
    thresholds["real_rate_kr"] = fred_stale
    frequencies["real_rate_kr"] = "daily"
    return thresholds, frequencies


def reconcile_tier2_provenance_staleness(
    data_dir: Path,
    *,
    as_of: str | None = None,
) -> Path | None:
    """Recompute stale_days/status on existing provenance (no API fetch)."""
    prov_path = data_dir / "tier2_provenance.json"
    if not prov_path.exists():
        return None
    sources_path = data_dir / "tier2_sources.yaml"
    cfg = load_yaml(sources_path) if sources_path.exists() else {}
    thresholds, frequencies = _field_config_maps(cfg)
    as_of_date = as_of or date.today().isoformat()
    doc = json.loads(prov_path.read_text(encoding="utf-8"))
    fields = doc.get("fields") or {}
    rebuilt: dict[str, Tier2FieldProvenance] = {}
    for name, meta in fields.items():
        if not isinstance(meta, dict):
            continue
        prov = Tier2FieldProvenance(
            source=str(meta.get("source") or ""),
            last_updated=str(meta.get("value_date") or meta.get("last_updated") or ""),
            value=meta.get("value"),
            fallback_used=bool(meta.get("fallback_used")),
            error=meta.get("error"),
        )
        rebuilt[name] = prov
    prov_doc = _build_provenance(
        rebuilt,
        as_of_date,
        thresholds=thresholds,
        frequencies=frequencies,
        fetch_methods={},
    )
    return write_tier2_provenance(data_dir, prov_doc)


def write_tier2_provenance(data_dir: Path, provenance: dict[str, Any]) -> Path:
    path = data_dir / "tier2_provenance.json"
    path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def append_tier2_history(data_dir: Path, row: dict[str, str]) -> None:
    hist_path = data_dir / "macro_tier2_history.csv"
    if hist_path.exists():
        df = pd.read_csv(hist_path, dtype=str, keep_default_na=False)
        if not df.empty and row["date"] in df["date"].astype(str).values:
            return
    else:
        df = pd.DataFrame(columns=TIER2_COLUMNS)
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(hist_path, index=False)


def refresh_macro_tier2(
    data_dir: Path,
    *,
    as_of: str | None = None,
) -> Tier2RefreshResult:
    """FRED + KOSIS → macro_tier2.csv 갱신 (실패 시 기존값 유지)."""
    path = data_dir / "macro_tier2.csv"
    sources_path = data_dir / "tier2_sources.yaml"
    cfg = load_yaml(sources_path) if sources_path.exists() else {}
    thresholds, frequencies = _field_config_maps(cfg)
    existing = _load_existing_row(path)
    as_of_date = as_of or date.today().isoformat()
    prov_path = data_dir / "tier2_provenance.json"
    stale_before = _load_provenance_stale_fields(prov_path, int(thresholds.get("cpi_us_yoy", 45)))

    row = {c: existing.get(c, "") for c in TIER2_COLUMNS}
    row["date"] = as_of_date
    updated: list[str] = ["date"]
    preserved: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    provenance_fields: dict[str, Tier2FieldProvenance] = {}
    api_count = 0

    fred_cfg = cfg.get("fred") or {}
    fred_base = str(fred_cfg.get("base_url", "https://api.stlouisfed.org/fred/series/observations"))
    fred_key = _fred_api_key(data_dir)
    fred_stale_warn = int(fred_cfg.get("stale_warn_days", 45))

    for key, spec in (fred_cfg.get("series") or {}).items():
        if not isinstance(spec, dict):
            continue
        target = str(spec.get("target_field", key))
        series_id = str(spec.get("id", ""))
        transform = str(spec.get("transform", "last"))
        freq = frequencies.get(target, "daily")
        threshold = int(thresholds.get(target, fred_stale_warn))
        val, last_dt, err = fetch_fred_field(
            fred_base,
            series_id=series_id,
            api_key=fred_key,
            transform=transform,
        )
        prov = Tier2FieldProvenance(source=f"fred:{series_id}", last_updated=last_dt)
        if val is not None and err is None:
            row[target] = str(val)
            updated.append(target)
            prov.value = val
            ref_date = _stale_reference_date(last_dt, freq)
            prov.stale_business_days = business_days_between(ref_date, as_of_date) if ref_date else 99
            api_count += 1
            if prov.stale_business_days > threshold:
                warnings.append(
                    f"{target} stale {prov.stale_business_days}bd (FRED {series_id}, ref={ref_date})"
                )
        else:
            if existing.get(target):
                row[target] = existing[target]
                preserved.append(target)
                prov.fallback_used = True
                prov.value = float(existing[target]) if existing[target] else None
                prov.source = "preserved"
            msg = err or f"FRED {series_id} 실패"
            errors.append(f"{target}: {msg}")
            prov.error = msg
            warnings.append(f"{target} 미갱신 — 이전값 유지")
        provenance_fields[target] = prov

    kosis_cfg = cfg.get("kosis") or {}
    kosis_base = str(kosis_cfg.get("base_url", "https://kosis.kr/openapi/Param/statisticsParameterData.do"))
    kosis_key = _kosis_api_key(data_dir)
    kosis_stale_warn = int(kosis_cfg.get("stale_warn_days", 60))

    for key, query in (kosis_cfg.get("queries") or {}).items():
        if not isinstance(query, dict):
            continue
        target = str(query.get("target_field", key))
        freq = frequencies.get(target, "monthly")
        threshold = int(thresholds.get(target, kosis_stale_warn))
        val, period, err = fetch_kosis_field(kosis_base, query, api_key=kosis_key)
        last_dt = _period_to_iso(period) if period else ""
        prov = Tier2FieldProvenance(source=f"kosis:{query.get('tblId', key)}", last_updated=last_dt)
        if val is not None and err is None:
            row[target] = str(val)
            updated.append(target)
            prov.value = val
            ref_date = _stale_reference_date(last_dt, freq)
            prov.stale_business_days = business_days_between(ref_date, as_of_date) if ref_date else 99
            api_count += 1
            if prov.stale_business_days > threshold:
                warnings.append(f"{target} stale {prov.stale_business_days}bd (KOSIS, ref={ref_date})")
        else:
            if existing.get(target):
                row[target] = existing[target]
                preserved.append(target)
                prov.fallback_used = True
                prov.value = float(existing[target]) if existing[target] else None
                prov.source = "preserved"
            msg = err or f"KOSIS {key} 실패"
            errors.append(f"{target}: {msg}")
            prov.error = msg
            warnings.append(f"{target} 미갱신 — 이전값 유지")
        provenance_fields[target] = prov

    # derived: real_rate_kr
    k10y = _load_korea_10y(data_dir)
    cpi_kr_raw = row.get("cpi_kr_yoy", "")
    prov_rr = Tier2FieldProvenance(source="derived:korea_10y_minus_cpi_kr")
    try:
        if k10y is not None and cpi_kr_raw.strip():
            rr = round(k10y - float(cpi_kr_raw), 2)
            row["real_rate_kr"] = str(rr)
            updated.append("real_rate_kr")
            prov_rr.value = rr
            prov_rr.last_updated = as_of_date
        elif existing.get("real_rate_kr"):
            row["real_rate_kr"] = existing["real_rate_kr"]
            preserved.append("real_rate_kr")
            prov_rr.fallback_used = True
            prov_rr.value = float(existing["real_rate_kr"])
            prov_rr.source = "preserved"
            warnings.append("real_rate_kr — korea_10y/cpi_kr 부족, 이전값 유지")
    except ValueError:
        warnings.append("real_rate_kr 계산 실패")
    provenance_fields["real_rate_kr"] = prov_rr

    for col in TIER2_COLUMNS:
        if col in ("date",) or col in updated or col in preserved:
            continue
        if existing.get(col) and not row.get(col):
            row[col] = existing[col]
            preserved.append(col)

    out_df = pd.DataFrame([row], columns=TIER2_COLUMNS)
    path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(path, index=False)
    append_tier2_history(data_dir, row)

    prov_doc = _build_provenance(
        provenance_fields,
        as_of_date,
        thresholds=thresholds,
        frequencies=frequencies,
        fetch_methods={},
    )
    prov_path = write_tier2_provenance(data_dir, prov_doc)
    stale_after = _load_provenance_stale_fields(prov_path, int(thresholds.get("cpi_us_yoy", 45)))

    if not fred_key and not kosis_key:
        warnings.append("FRED/KOSIS API 키 미설정 — 기존 Tier2 유지 (settings에서 키 등록)")

    return Tier2RefreshResult(
        as_of=as_of_date,
        updated_fields=sorted(set(updated)),
        preserved_fields=sorted(set(preserved)),
        warnings=warnings,
        errors=errors,
        path=str(path),
        provenance_path=str(prov_path),
        api_fields_fetched=api_count,
        stale_before=stale_before,
        stale_after=stale_after,
    )
