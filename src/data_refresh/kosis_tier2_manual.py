"""Verified manual provenance for KOSIS tier2 fields (cpi_kr_yoy, pmi_kr)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.config import load_yaml
from src.data_refresh.price_store import atomic_write_text

MANUAL_YAML = "tier2_kosis_manual.yaml"
KOSIS_TARGET_FIELDS = ("cpi_kr_yoy", "pmi_kr")
PMI_KR_FIELD = "pmi_kr"
PMI_KR_MANUAL_REQUIRED_KEYS = (
    "value",
    "value_date",
    "source",
    "source_url_or_note",
    "updated_by",
    "update_reason",
)


def manual_yaml_path(data_dir: Path) -> Path:
    return data_dir / MANUAL_YAML


def ensure_manual_template(data_dir: Path) -> Path:
    path = manual_yaml_path(data_dir)
    if path.exists():
        return path
    example = data_dir / "tier2_kosis_manual.yaml.example"
    if example.exists():
        _atomic_write_manual_yaml(path, example.read_text(encoding="utf-8"))
        return path
    template = "\n".join([
        "# KOSIS tier2 manual provenance — only verified=true entries are applied.",
        "# Do not set verified=true without confirming value, source, and observation date.",
        "fields:",
        "  cpi_kr_yoy:",
        "    verified: false",
        "    value: null",
        "    value_date: null",
        "    source: null",
        "    source_url_or_note: null",
        "    updated_by: null",
        "    update_reason: null",
        "  pmi_kr:",
        "    verified: false",
        "    value: null",
        "    value_date: null",
        "    source: null",
        "    source_url_or_note: null",
        "    updated_by: null",
        "    update_reason: null",
        "",
    ])
    _atomic_write_manual_yaml(path, template)
    return path


def _verify_manual_yaml_structure(path: Path) -> None:
    doc = load_yaml(path)
    fields = doc.get("fields")
    if not isinstance(fields, dict):
        raise RuntimeError("tier2_kosis_manual.yaml: missing fields mapping")
    if PMI_KR_FIELD not in fields:
        raise RuntimeError(f"tier2_kosis_manual.yaml: missing {PMI_KR_FIELD}")


def _atomic_write_manual_yaml(path: Path, content: str) -> None:
    atomic_write_text(
        path,
        content,
        encoding="utf-8",
        min_bytes=32,
        verify=_verify_manual_yaml_structure,
    )


def _is_verified(meta: dict[str, Any]) -> bool:
    return str(meta.get("verified", "")).lower() in {"true", "1", "yes"}


def load_verified_manual_overrides(data_dir: Path) -> dict[str, dict[str, Any]]:
    path = manual_yaml_path(data_dir)
    if not path.exists():
        return {}
    doc = load_yaml(path) or {}
    fields = doc.get("fields") or {}
    out: dict[str, dict[str, Any]] = {}
    for name in KOSIS_TARGET_FIELDS:
        meta = fields.get(name)
        if not isinstance(meta, dict) or not _is_verified(meta):
            continue
        value = meta.get("value")
        value_date = str(meta.get("value_date") or "").strip()
        source = str(meta.get("source") or "").strip()
        if value is None or not value_date or not source:
            continue
        out[name] = {
            "value": float(value),
            "value_date": value_date,
            "source": source,
            "source_url_or_note": str(meta.get("source_url_or_note") or ""),
            "updated_by": str(meta.get("updated_by") or ""),
            "update_reason": str(meta.get("update_reason") or ""),
        }
    return out


def validate_pmi_kr_manual_ready(data_dir: Path) -> dict[str, Any]:
    """Check whether pmi_kr manual_verified path is ready to apply."""
    path = manual_yaml_path(data_dir)
    missing: list[str] = []
    if not path.exists():
        return {
            "ready": False,
            "verified": False,
            "missing_fields": list(PMI_KR_MANUAL_REQUIRED_KEYS) + ["verified"],
            "reason": "tier2_kosis_manual.yaml missing",
        }

    doc = load_yaml(path) or {}
    meta = (doc.get("fields") or {}).get(PMI_KR_FIELD)
    if not isinstance(meta, dict):
        return {
            "ready": False,
            "verified": False,
            "missing_fields": list(PMI_KR_MANUAL_REQUIRED_KEYS) + ["verified"],
            "reason": "pmi_kr section missing",
        }

    verified = _is_verified(meta)
    if not verified:
        return {
            "ready": False,
            "verified": False,
            "missing_fields": [],
            "reason": "pmi_kr verified=false — manual_required maintained",
        }

    for key in PMI_KR_MANUAL_REQUIRED_KEYS:
        val = meta.get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(key)

    ready = verified and not missing
    return {
        "ready": ready,
        "verified": verified,
        "missing_fields": missing,
        "reason": "ready for manual_verified apply" if ready else "verified=true but required fields incomplete",
        "manual_meta": {
            k: meta.get(k) for k in (*PMI_KR_MANUAL_REQUIRED_KEYS, "verified")
        },
    }


def list_manual_field_status(data_dir: Path) -> dict[str, dict[str, Any]]:
    path = manual_yaml_path(data_dir)
    if not path.exists():
        return {f: {"verified": False, "present": False} for f in KOSIS_TARGET_FIELDS}
    doc = load_yaml(path) or {}
    fields = doc.get("fields") or {}
    out: dict[str, dict[str, Any]] = {}
    for name in KOSIS_TARGET_FIELDS:
        meta = fields.get(name) if isinstance(fields.get(name), dict) else {}
        out[name] = {
            "verified": _is_verified(meta),
            "present": bool(meta),
            "has_value": meta.get("value") is not None,
            "has_value_date": bool(str(meta.get("value_date") or "").strip()),
            "has_source": bool(str(meta.get("source") or "").strip()),
        }
    return out


def load_pmi_kr_manual_meta(data_dir: Path) -> dict[str, Any]:
    """Raw pmi_kr section from tier2_kosis_manual.yaml (verified may be false)."""
    path = manual_yaml_path(data_dir)
    if not path.exists():
        return {}
    doc = load_yaml(path) or {}
    meta = (doc.get("fields") or {}).get(PMI_KR_FIELD)
    return dict(meta) if isinstance(meta, dict) else {}


def save_pmi_kr_manual_fields(
    data_dir: Path,
    *,
    verified: bool,
    value: float | None = None,
    value_date: str | None = None,
    source: str | None = None,
    source_url_or_note: str | None = None,
    updated_by: str | None = None,
    update_reason: str | None = None,
) -> Path:
    """Persist pmi_kr manual fields — only verified=true entries affect tier2 refresh."""
    path = ensure_manual_template(data_dir)
    doc = load_yaml(path)
    fields = doc.setdefault("fields", {})
    meta = fields.setdefault(PMI_KR_FIELD, {})
    if value is not None:
        meta["value"] = float(value)
    if value_date is not None:
        meta["value_date"] = str(value_date).strip()
    if source is not None:
        meta["source"] = str(source).strip()
    if source_url_or_note is not None:
        meta["source_url_or_note"] = str(source_url_or_note).strip()
    if updated_by is not None:
        meta["updated_by"] = str(updated_by).strip()
    if update_reason is not None:
        meta["update_reason"] = str(update_reason).strip()
    meta["verified"] = bool(verified)
    _atomic_write_manual_yaml(
        path,
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
    )
    return path
