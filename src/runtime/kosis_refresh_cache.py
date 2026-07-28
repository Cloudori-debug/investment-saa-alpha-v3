"""P1.6 — conditional KOSIS tier2 refresh when dependencies unchanged."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.data_refresh.kosis_tier2_manual import KOSIS_TARGET_FIELDS, list_manual_field_status
from src.runtime.diagnostics_subset_hash import compute_semantic_file_hash, normalize_for_semantic_hash

MANIFEST_JSON = "kosis_refresh_cache_manifest.json"
DEFAULT_SAVED_SECONDS = 240.0

KOSIS_DIAG_JSON = "kosis_tier2_refresh_diagnostics.json"
PMI_POLICY_JSON = "pmi_kr_source_policy.json"


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _provenance_subset(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "tier2_provenance.json"
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    fields = doc.get("fields") or {}
    out: dict[str, Any] = {}
    for name in KOSIS_TARGET_FIELDS:
        meta = fields.get(name)
        if isinstance(meta, dict):
            out[name] = {
                "status": meta.get("status"),
                "value": meta.get("value"),
                "value_date": meta.get("value_date"),
                "stale_business_days": meta.get("stale_business_days"),
                "fetch_status": meta.get("fetch_status"),
            }
    return out


def _pmi_policy_subset(output_dir: Path) -> dict[str, Any]:
    path = output_dir / PMI_POLICY_JSON
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {
        "pmi_kr_status": doc.get("pmi_kr_status") or (doc.get("pmi_kr") or {}).get("status"),
        "cpi_kr_yoy_status": doc.get("cpi_kr_yoy_status") or (doc.get("cpi_kr_yoy") or {}).get("status"),
        "policy": doc.get("policy"),
    }


def compute_kosis_dependency_hash(data_dir: Path, output_dir: Path) -> tuple[str, list[str], dict[str, str]]:
    parts: list[str] = []
    per_file: dict[str, str] = {}
    files_used: list[str] = []
    root = data_dir.parent

    sources = data_dir / "tier2_sources.yaml"
    manual = data_dir / "tier2_kosis_manual.yaml"
    fh_sources = compute_semantic_file_hash(sources)
    fh_manual = compute_semantic_file_hash(manual)
    per_file["tier2_sources.yaml"] = fh_sources
    per_file["tier2_kosis_manual.yaml"] = fh_manual
    parts.extend([f"tier2_sources:{fh_sources}", f"tier2_kosis_manual:{fh_manual}"])
    for p in (sources, manual):
        if p.exists():
            try:
                files_used.append(str(p.relative_to(root)))
            except ValueError:
                files_used.append(str(p))

    prov_subset = normalize_for_semantic_hash(_provenance_subset(data_dir))
    prov_hash = hashlib.sha256(_canonical_json(prov_subset).encode("utf-8")).hexdigest()[:16]
    per_file["tier2_provenance.json"] = prov_hash
    parts.append(f"tier2_provenance:{prov_hash}")
    if (data_dir / "tier2_provenance.json").exists():
        files_used.append(str((data_dir / "tier2_provenance.json").relative_to(root)))

    policy_subset = normalize_for_semantic_hash(_pmi_policy_subset(output_dir))
    policy_hash = hashlib.sha256(_canonical_json(policy_subset).encode("utf-8")).hexdigest()[:16]
    per_file[PMI_POLICY_JSON] = policy_hash
    parts.append(f"pmi_kr_source_policy:{policy_hash}")
    if (output_dir / PMI_POLICY_JSON).exists():
        try:
            files_used.append(str((output_dir / PMI_POLICY_JSON).relative_to(root)))
        except ValueError:
            files_used.append(str(output_dir / PMI_POLICY_JSON))

    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return digest, files_used, per_file


def load_kosis_refresh_manifest(output_dir: Path) -> dict[str, Any]:
    path = output_dir / MANIFEST_JSON
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _pmi_kr_status(data_dir: Path, output_dir: Path) -> str:
    prov = _provenance_subset(data_dir).get("pmi_kr") or {}
    if prov.get("status"):
        return str(prov["status"])
    policy = _pmi_policy_subset(output_dir)
    return str(policy.get("pmi_kr_status") or "unknown")


def _cpi_kr_status(data_dir: Path, output_dir: Path) -> str:
    prov = _provenance_subset(data_dir).get("cpi_kr_yoy") or {}
    if prov.get("status"):
        return str(prov["status"])
    policy = _pmi_policy_subset(output_dir)
    return str(policy.get("cpi_kr_yoy_status") or "unknown")


def _pmi_kr_verified(data_dir: Path) -> bool:
    return bool((list_manual_field_status(data_dir).get("pmi_kr") or {}).get("verified"))


def _verified_transition_requires_refresh(prev: dict[str, Any], data_dir: Path) -> bool:
    """Re-run when pmi_kr newly set to verified=true since last manifest."""
    current = _pmi_kr_verified(data_dir)
    prev_verified = bool(prev.get("pmi_kr_verified"))
    manual_hash = compute_semantic_file_hash(data_dir / "tier2_kosis_manual.yaml")
    prev_manual_hash = str(prev.get("tier2_kosis_manual_hash") or "")
    if current and manual_hash != prev_manual_hash:
        return True
    if current and not prev_verified:
        return True
    return False


def evaluate_kosis_refresh_skip(
    data_dir: Path,
    output_dir: Path,
    *,
    run_mode: str,
    diagnostics_cache_hit_count: int,
    diagnostics_cache_miss_count: int,
    diagnostics_all_hit: bool | None = None,
) -> tuple[bool, str, str, list[str]]:
    """Return (skip, skip_reason, dep_hash, dep_files)."""
    dep_hash, dep_files, _ = compute_kosis_dependency_hash(data_dir, output_dir)
    prev = load_kosis_refresh_manifest(output_dir)

    if str(run_mode).lower() == "deep":
        return False, "deep_mode", dep_hash, dep_files

    if not (output_dir / KOSIS_DIAG_JSON).exists():
        return False, "kosis_diagnostics_missing", dep_hash, dep_files

    if _verified_transition_requires_refresh(prev, data_dir):
        return False, "pmi_kr_verified_or_manual_changed", dep_hash, dep_files

    prev_hash = str(prev.get("dependency_hash") or "")
    if prev_hash and prev_hash != dep_hash:
        return False, "dependency_hash_changed", dep_hash, dep_files

    if not prev_hash:
        return False, "first_run_or_no_prior_manifest", dep_hash, dep_files

    mode = str(run_mode).lower()
    if mode in {"standard", "quick"} and prev_hash == dep_hash:
        if diagnostics_cache_miss_count == 0 and diagnostics_cache_hit_count >= 8:
            return True, "diagnostics_cache_hit", dep_hash, dep_files
        return True, "dependency_unchanged", dep_hash, dep_files

    all_hit = diagnostics_all_hit
    if all_hit is None:
        all_hit = diagnostics_cache_miss_count == 0 and diagnostics_cache_hit_count >= 8
    if not all_hit:
        return False, "diagnostics_cache_incomplete", dep_hash, dep_files

    return True, "dependency_unchanged", dep_hash, dep_files


def write_kosis_refresh_manifest(
    output_dir: Path,
    *,
    run_id: str,
    run_mode: str,
    kosis_refresh_executed: bool,
    skip_reason: str,
    dependency_hash: str,
    previous_dependency_hash: str,
    dependency_files: list[str],
    reused_from_run_id: str = "",
    last_refresh_seconds: float = 0.0,
    diag_doc: dict[str, Any] | None = None,
) -> None:
    data_dir_guess = output_dir.parent / "data"
    doc = {
        "schema_version": "1.0",
        "run_id": run_id,
        "run_mode": run_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kosis_refresh_executed": kosis_refresh_executed,
        "skip_reason": skip_reason,
        "dependency_hash": dependency_hash,
        "previous_dependency_hash": previous_dependency_hash,
        "dependency_files": dependency_files,
        "pmi_kr_status": _pmi_kr_status(data_dir_guess, output_dir),
        "pmi_kr_verified": _pmi_kr_verified(data_dir_guess),
        "cpi_kr_yoy_status": _cpi_kr_status(data_dir_guess, output_dir),
        "tier2_kosis_manual_hash": compute_semantic_file_hash(data_dir_guess / "tier2_kosis_manual.yaml"),
        "refreshed_fields": list((diag_doc or {}).get("refreshed_fields") or []),
        "failed_fields": list((diag_doc or {}).get("failed_fields") or []),
        "manual_required_fields": list((diag_doc or {}).get("manual_required_fields") or []),
        "reused_from_run_id": reused_from_run_id,
        "last_refresh_seconds": round(last_refresh_seconds, 2),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / MANIFEST_JSON).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _record_profiler(profiler: Any | None, *, executed: bool, skip_reason: str, saved: float, dep_changed: bool) -> None:
    if profiler is None:
        return
    if hasattr(profiler, "kosis_refresh_executed"):
        profiler.kosis_refresh_executed = executed
    if hasattr(profiler, "kosis_refresh_skip_reason"):
        profiler.kosis_refresh_skip_reason = skip_reason if not executed else ""
    if hasattr(profiler, "kosis_refresh_seconds_saved_estimate"):
        profiler.kosis_refresh_seconds_saved_estimate = round(saved, 2) if not executed else 0.0
    if hasattr(profiler, "kosis_dependency_hash_changed"):
        profiler.kosis_dependency_hash_changed = dep_changed
    if not executed and saved > 0 and hasattr(profiler, "add_note"):
        profiler.add_note(f"KOSIS refresh skipped ({skip_reason}), ~{saved:.0f}s saved")


def maybe_run_kosis_tier2_refresh(
    data_dir: Path,
    output_dir: Path,
    *,
    run_id: str,
    run_mode: str = "standard",
    run_full_diag: bool = True,
    diagnostics_cache_hit_count: int = 0,
    diagnostics_cache_miss_count: int = 0,
    profiler: Any | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Run KOSIS refresh or skip when cache/deps allow."""
    if not run_full_diag:
        write_kosis_refresh_manifest(
            output_dir,
            run_id=run_id,
            run_mode=run_mode,
            kosis_refresh_executed=False,
            skip_reason="run_full_diag_disabled",
            dependency_hash="",
            previous_dependency_hash="",
            dependency_files=[],
        )
        _record_profiler(profiler, executed=False, skip_reason="run_full_diag_disabled", saved=0.0, dep_changed=False)
        return {}

    prev = load_kosis_refresh_manifest(output_dir)
    skip, skip_reason, dep_hash, dep_files = evaluate_kosis_refresh_skip(
        data_dir,
        output_dir,
        run_mode=run_mode,
        diagnostics_cache_hit_count=diagnostics_cache_hit_count,
        diagnostics_cache_miss_count=diagnostics_cache_miss_count,
    )
    prev_hash = str(prev.get("dependency_hash") or "")
    dep_changed = bool(prev_hash and prev_hash != dep_hash)
    saved_est = float(prev.get("last_refresh_seconds") or DEFAULT_SAVED_SECONDS)

    if skip:
        diag_path = output_dir / KOSIS_DIAG_JSON
        diag_doc: dict[str, Any] = {}
        if diag_path.exists():
            try:
                diag_doc = json.loads(diag_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        write_kosis_refresh_manifest(
            output_dir,
            run_id=run_id,
            run_mode=run_mode,
            kosis_refresh_executed=False,
            skip_reason=skip_reason,
            dependency_hash=dep_hash,
            previous_dependency_hash=prev_hash,
            dependency_files=dep_files,
            reused_from_run_id=str(prev.get("run_id") or ""),
            diag_doc=diag_doc,
        )
        _record_profiler(profiler, executed=False, skip_reason=skip_reason, saved=saved_est, dep_changed=dep_changed)
        return diag_doc

    from src.validation.kosis_tier2_refresh_diagnostics import run_kosis_tier2_refresh_with_diagnostics

    t0 = time.perf_counter()
    _result, diag_doc = run_kosis_tier2_refresh_with_diagnostics(data_dir, output_dir, as_of=as_of)
    elapsed = time.perf_counter() - t0
    write_kosis_refresh_manifest(
        output_dir,
        run_id=run_id,
        run_mode=run_mode,
        kosis_refresh_executed=True,
        skip_reason="",
        dependency_hash=dep_hash,
        previous_dependency_hash=prev_hash,
        dependency_files=dep_files,
        last_refresh_seconds=elapsed,
        diag_doc=diag_doc,
    )
    _record_profiler(profiler, executed=True, skip_reason="", saved=0.0, dep_changed=dep_changed)
    return diag_doc
