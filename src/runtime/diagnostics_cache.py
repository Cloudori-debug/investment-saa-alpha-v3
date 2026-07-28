"""Diagnostics hash cache — reuse outputs when dependency inputs unchanged."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

MANIFEST_JSON = "diagnostics_cache_manifest.json"
from src.runtime.diagnostics_subset_hash import (  # noqa: E402
    HASH_MODE,
    compute_subset_dependency_hash,
    explain_subset_hash_changes,
    load_dependency_inputs,
    write_subset_hash_debug_manifest,
)

VOLATILE_KEYS: frozenset[str] = frozenset({
    "run_id",
    "generated_at",
    "created_at",
    "updated_at",
    "timestamp",
    "as_of_generated_at",
    "elapsed_seconds",
    "duration_seconds",
    "runtime_seconds",
    "profile",
    "step_timings",
    "slowest_steps",
    "cache_hit_count",
    "cache_miss_count",
    "diagnostics_cache_hit_count",
    "diagnostics_cache_miss_count",
    "bundle_reconcile_cache_hit_count",
    "bundle_reconcile_cache_miss_count",
    "source_mtime",
    "file_mtime",
    "health_snapshot_id",
    "reused_from_run_id",
    "last_compute_seconds",
    "last_checked_at",
})

DEPENDENCY_KEYS: tuple[str, ...] = (
    "target_portfolio",
    "user_target_portfolio",
    "final_execution_decision",
    "acceptance_report",
    "daily_brief",
    "alpha_candidates",
    "alpha_signal_board",
    "alpha_v2_summary",
    "flow_dashboard_summary",
    "market_data_provenance",
    "tier2_provenance",
    "portfolio_policy",
    "pmi_kr_manual",
)

_DATA_GATE_ALIASES = frozenset({"pmi_kr_source_policy", "data_gate_green_preflight"})


def load_json_semantic(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _normalize_scalar(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return round(value, 10)
    if isinstance(value, str):
        return value.strip()
    return value


def normalize_for_semantic_hash(obj: Any) -> Any:
    """Strip volatile keys; preserve list order."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key in sorted(obj.keys()):
            if key in VOLATILE_KEYS:
                continue
            out[key] = normalize_for_semantic_hash(obj[key])
        return out
    if isinstance(obj, list):
        return [normalize_for_semantic_hash(item) for item in obj]
    return _normalize_scalar(obj)


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _csv_semantic_hash(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    try:
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames:
            rows = sorted(reader, key=lambda r: tuple(r.get(c, "") for c in reader.fieldnames))
            payload = {"columns": list(reader.fieldnames), "rows": rows}
            return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:16]
    except Exception:
        pass
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def compute_semantic_file_hash(path: Path) -> str:
    if not path.exists():
        return "missing"
    suffix = path.suffix.lower()
    if suffix == ".json":
        doc = load_json_semantic(path)
        if doc is None:
            return "invalid"
        normalized = normalize_for_semantic_hash(doc)
        return hashlib.sha256(_canonical_json(normalized).encode("utf-8")).hexdigest()[:16]
    if suffix in {".yaml", ".yml"}:
        try:
            from src.config import load_yaml

            doc = load_yaml(path)
            normalized = normalize_for_semantic_hash(doc)
            return hashlib.sha256(_canonical_json(normalized).encode("utf-8")).hexdigest()[:16]
        except Exception:
            return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    if suffix == ".csv":
        return _csv_semantic_hash(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def compute_dependency_semantic_hash(
    data_dir: Path,
    output_dir: Path,
    *,
    dep_keys: tuple[str, ...] = DEPENDENCY_KEYS,
) -> tuple[str, list[str], dict[str, str]]:
    paths = resolve_dependency_paths(data_dir, output_dir)
    per_file: dict[str, str] = {}
    files_used: list[str] = []
    root = data_dir.parent
    parts: list[str] = []
    for key in dep_keys:
        path = paths.get(key)
        if path is None:
            per_file[key] = "missing"
            parts.append(f"{key}:missing")
            continue
        fh = compute_semantic_file_hash(path)
        per_file[key] = fh
        parts.append(f"{key}:{fh}")
        if path.exists():
            try:
                files_used.append(str(path.relative_to(root)))
            except ValueError:
                files_used.append(str(path))
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return digest, files_used, per_file


def changed_dependency_files(
    prev_hashes: dict[str, str],
    curr_hashes: dict[str, str],
) -> list[str]:
    changed: list[str] = []
    for key, curr in curr_hashes.items():
        if prev_hashes.get(key) != curr:
            changed.append(key)
    return changed


def resolve_dependency_paths(data_dir: Path, output_dir: Path) -> dict[str, Path]:
    from src.alpha.target_portfolio_guard import user_target_portfolio_path

    return {
        "target_portfolio": data_dir / "target_portfolio.csv",
        "user_target_portfolio": user_target_portfolio_path(data_dir),
        "final_execution_decision": output_dir / "final_execution_decision.json",
        "acceptance_report": output_dir / "acceptance_report.json",
        "daily_brief": output_dir / "daily_brief.json",
        "alpha_candidates": output_dir / "alpha_candidates.csv",
        "alpha_signal_board": output_dir / "alpha_signal_board.csv",
        "alpha_v2_summary": output_dir / "alpha_v2_summary.json",
        "flow_dashboard_summary": output_dir / "flow_dashboard_summary.json",
        "market_data_provenance": output_dir / "market_data_provenance.json",
        "tier2_provenance": output_dir / "tier2_provenance.json",
        "portfolio_policy": data_dir / "portfolio_policy.yaml",
        "pmi_kr_manual": data_dir / "tier2_kosis_manual.yaml",
    }


def compute_dependency_hash(
    data_dir: Path,
    output_dir: Path,
    *,
    dep_keys: tuple[str, ...] = DEPENDENCY_KEYS,
) -> tuple[str, list[str]]:
    digest, files_used, _ = compute_dependency_semantic_hash(
        data_dir, output_dir, dep_keys=dep_keys,
    )
    return digest, files_used


def _outputs_exist(output_dir: Path, output_files: tuple[str, ...]) -> bool:
    return all((output_dir / name).exists() for name in output_files)


@dataclass(frozen=True)
class DiagnosticSpec:
    name: str
    output_files: tuple[str, ...]
    dep_keys: tuple[str, ...] = DEPENDENCY_KEYS


DIAGNOSTIC_SPECS: tuple[DiagnosticSpec, ...] = (
    DiagnosticSpec("alpha_shortlist_diagnostics", ("alpha_shortlist_diagnostics.csv", "alpha_shortlist_summary.json")),
    DiagnosticSpec("policy_cap_counterfactual", ("policy_cap_counterfactual.json",)),
    DiagnosticSpec("core_etf_permission_diagnostics", ("core_etf_permission_diagnostics.json", "core_etf_candidate_trace.csv")),
    DiagnosticSpec(
        "data_gate_diagnostics",
        (
            "data_gate_diagnostics.json",
            "data_gate_field_status.csv",
            "data_gate_to_permission_trace.json",
            "market_indicator_schema_diagnostics.json",
            "market_field_status.csv",
            "pmi_kr_source_policy.json",
            "data_gate_green_preflight.json",
        ),
    ),
    DiagnosticSpec("pmi_kr_source_policy", ("pmi_kr_source_policy.json",)),
    DiagnosticSpec("data_gate_green_preflight", ("data_gate_green_preflight.json",)),
    DiagnosticSpec("alpha_gate_diagnostics", ("alpha_gate_diagnostics.json",)),
    DiagnosticSpec("no_action_diagnostics", ("no_action_diagnostics.json",)),
)


def load_manifest(output_dir: Path) -> dict[str, Any]:
    path = output_dir / MANIFEST_JSON
    if not path.exists():
        return {"schema_version": "1.0", "entries": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": "1.0", "entries": {}}


def _manifest_entries(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = doc.get("entries") or {}
    if isinstance(raw, list):
        return {e["diagnostics_name"]: e for e in raw if isinstance(e, dict) and e.get("diagnostics_name")}
    return dict(raw)


def verify_no_action_cached(data_dir: Path, output_dir: Path) -> tuple[bool, str]:
    from src.report.authoritative_status import resolve_authoritative_execution
    from src.report.execution_metrics import count_executable_actions
    from src.report.io_utils import read_output_json

    doc = read_output_json(output_dir / "no_action_diagnostics.json") or {}
    if not doc:
        return False, "output_missing"
    final = read_output_json(output_dir / "final_execution_decision.json") or {}
    current_buy = int(count_executable_actions(final).get("actual_buy_allowed_count") or 0)
    trace = doc.get("actual_buy_trace") or {}
    cached_buy = trace.get("final_actual_buy_allowed")
    if cached_buy is not None and int(cached_buy) != current_buy:
        return False, f"actual_buy_mismatch cached={cached_buy} current={current_buy}"

    auth = resolve_authoritative_execution(data_dir, output_dir, final_doc=final)
    align = doc.get("status_alignment") or {}
    auth_scope = str(auth.get("execution_scope") or "")
    cached_scope = str(align.get("authoritative_execution_scope") or align.get("execution_scope") or "")
    if auth_scope and cached_scope and auth_scope != cached_scope:
        return False, f"scope_mismatch cached={cached_scope} current={auth_scope}"
    if doc.get("status_alignment_pass") is False:
        return False, "status_alignment_pass_false"
    return True, "ok"


def refresh_no_action_diagnostics_if_stale(
    data_dir: Path,
    output_dir: Path,
    *,
    clarity: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Recompute no_action_diagnostics when cached scope/buy count diverges from current."""
    ok, reason = verify_no_action_cached(data_dir, output_dir)
    if ok:
        return False, "ok"
    from src.validation.no_action_diagnostics import write_no_action_diagnostics

    write_no_action_diagnostics(data_dir, output_dir, clarity=clarity, light=True)
    manifest_path = output_dir / MANIFEST_JSON
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            entries = manifest.get("entries") or {}
            if isinstance(entries, dict) and "no_action_diagnostics" in entries:
                entry = dict(entries["no_action_diagnostics"])
                entry["cache_hit"] = False
                entry["recompute_required"] = True
                entry["stale_safe"] = False
                entry["cache_miss_reason"] = f"authoritative_scope_refresh:{reason}"
                entries["no_action_diagnostics"] = entry
                manifest["entries"] = entries
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        except (json.JSONDecodeError, OSError, TypeError):
            pass
    ok_after, reason_after = verify_no_action_cached(data_dir, output_dir)
    if ok_after:
        return True, reason
    return True, f"refresh_incomplete:{reason_after}"


VERIFY_FNS: dict[str, Callable[[Path, Path], tuple[bool, str]]] = {
    "no_action_diagnostics": verify_no_action_cached,
}

_REQUIRED_JSON_FIELDS: dict[str, tuple[str, ...]] = {
    "no_action_diagnostics.json": ("status_alignment_pass", "actual_buy_trace"),
    "data_gate_diagnostics.json": ("data_gate_status",),
    "alpha_gate_diagnostics.json": ("alpha_gate_status",),
    "policy_cap_counterfactual.json": ("policy_cap",),
    "core_etf_permission_diagnostics.json": ("core_etf_permission",),
}


def verify_diagnostics_outputs(
    data_dir: Path,
    output_dir: Path,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Lightweight presence/consistency check — never regenerates diagnostics."""
    from src.report.io_utils import read_output_json

    missing: list[str] = []
    warnings: list[str] = []
    checked: list[str] = []

    seen_files: set[str] = set()
    for spec in DIAGNOSTIC_SPECS:
        for fname in spec.output_files:
            if fname in seen_files:
                continue
            seen_files.add(fname)
            path = output_dir / fname
            if not path.exists():
                missing.append(fname)
                continue
            checked.append(fname)
            if fname.endswith(".json"):
                doc = read_output_json(path) or {}
                for field in _REQUIRED_JSON_FIELDS.get(fname, ()):
                    if field not in doc:
                        warnings.append(f"{fname}: missing field {field}")

    ok_na, na_reason = verify_no_action_cached(data_dir, output_dir)
    if not ok_na:
        if na_reason == "output_missing":
            if "no_action_diagnostics.json" not in missing:
                missing.append("no_action_diagnostics.json")
        else:
            warnings.append(f"no_action_verify:{na_reason}")

    ready = len(missing) == 0
    passed = ready and not warnings
    return {
        "pass": passed,
        "diagnostics_ready": ready,
        "missing_outputs": missing,
        "warnings": warnings,
        "checked_outputs": checked,
        "no_action_verify_ok": ok_na,
        "no_action_verify_reason": na_reason if not ok_na else "",
        "run_id": run_id or "",
        "verify_only": True,
    }


def should_cache_hit(
    spec: DiagnosticSpec,
    *,
    data_dir: Path,
    output_dir: Path,
    dep_hash: str,
    prev_entries: dict[str, dict[str, Any]],
    subset_snapshot: dict[str, Any] | None = None,
    per_file_hashes: dict[str, str] | None = None,
) -> tuple[bool, str, str | None, list[str]]:
    if not _outputs_exist(output_dir, spec.output_files):
        return False, "output_missing", None, []
    prev = prev_entries.get(spec.name) or {}
    prev_hash = str(
        prev.get("subset_dependency_hash")
        or prev.get("semantic_dependency_hash")
        or prev.get("dependency_hash")
        or "",
    )
    if prev_hash != dep_hash:
        prev_snap = prev.get("subset_snapshot") or {}
        changed = (
            explain_subset_hash_changes(prev_snap, subset_snapshot or {})
            if prev_snap and subset_snapshot
            else (changed_dependency_files(prev.get("file_semantic_hashes") or {}, per_file_hashes or {})
                  if per_file_hashes else ["subset_changed"])
        )
        return False, "subset_hash_changed", None, changed
    verify = VERIFY_FNS.get(spec.name)
    if verify:
        ok, reason = verify(data_dir, output_dir)
        if not ok:
            return False, reason, None, []
    return True, "hash_match", str(prev.get("run_id") or ""), []


@dataclass
class DiagnosticsCacheResult:
    entries: list[dict[str, Any]] = field(default_factory=list)
    cache_hit_count: int = 0
    cache_miss_count: int = 0
    reused: list[str] = field(default_factory=list)
    recomputed: list[str] = field(default_factory=list)
    saved_seconds_estimate: float = 0.0


def run_diagnostics_with_cache(
    data_dir: Path,
    output_dir: Path,
    *,
    run_id: str,
    clarity: dict[str, Any] | None = None,
    run_full_diag: bool = True,
    run_mode: str = "standard",
    profiler: Any | None = None,
) -> DiagnosticsCacheResult:
    """Run diagnostics writers with hash cache; safety gates are not cached."""
    if profiler is not None and hasattr(profiler, "diagnostics_invocation_count"):
        profiler.diagnostics_invocation_count += 1
    if profiler is not None:
        if hasattr(profiler, "diagnostics_hash_mode"):
            profiler.diagnostics_hash_mode = HASH_MODE
        if hasattr(profiler, "diagnostics_semantic_cache_enabled"):
            profiler.diagnostics_semantic_cache_enabled = True
    prev_entries = _manifest_entries(load_manifest(output_dir))
    loaded_inputs = load_dependency_inputs(data_dir, output_dir)
    result = DiagnosticsCacheResult()
    new_entries: dict[str, dict[str, Any]] = {}
    debug_entries: dict[str, Any] = {}
    volatile_excluded = sorted(VOLATILE_KEYS)

    def _entry_base(
        spec: DiagnosticSpec,
        dep_hash: str,
        dep_files: list[str],
        subset_snapshot: dict[str, Any],
        subset_fields: list[str],
        prev: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "diagnostic_name": spec.name,
            "diagnostics_name": spec.name,
            "output_files": list(spec.output_files),
            "dependency_files": dep_files,
            "dependency_hash": dep_hash,
            "hash_mode": HASH_MODE,
            "volatile_keys_excluded": volatile_excluded,
            "semantic_dependency_hash": dep_hash,
            "subset_dependency_hash": dep_hash,
            "previous_subset_dependency_hash": str(
                prev.get("subset_dependency_hash")
                or prev.get("semantic_dependency_hash")
                or prev.get("dependency_hash")
                or "",
            ),
            "subset_fields_used": subset_fields,
            "subset_snapshot": subset_snapshot,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _record_hit(
        spec: DiagnosticSpec,
        dep_hash: str,
        dep_files: list[str],
        subset_snapshot: dict[str, Any],
        subset_fields: list[str],
        reused_from: str | None,
    ) -> None:
        prev = prev_entries.get(spec.name) or {}
        saved = float(prev.get("last_compute_seconds") or 60)
        result.cache_hit_count += 1
        result.reused.append(spec.name)
        result.saved_seconds_estimate += saved
        if profiler is not None and hasattr(profiler, "record_diagnostics_cache_hit"):
            profiler.record_diagnostics_cache_hit(spec.name, saved)
        entry = {
            **_entry_base(spec, dep_hash, dep_files, subset_snapshot, subset_fields, prev),
            "cache_hit": True,
            "cache_miss_reason": "",
            "subset_changed_paths": [],
            "changed_dependency_files": [],
            "reused_from_run_id": reused_from or "",
            "stale_safe": True,
            "recompute_required": False,
            "safety_fields_verified": True,
            "last_compute_seconds": float(prev.get("last_compute_seconds") or saved),
        }
        new_entries[spec.name] = entry
        debug_entries[spec.name] = entry

    def _record_miss(
        spec: DiagnosticSpec,
        dep_hash: str,
        dep_files: list[str],
        subset_snapshot: dict[str, Any],
        subset_fields: list[str],
        reason: str,
        elapsed: float,
        changed_paths: list[str],
    ) -> None:
        prev = prev_entries.get(spec.name) or {}
        result.cache_miss_count += 1
        result.recomputed.append(spec.name)
        if profiler is not None and hasattr(profiler, "record_diagnostics_cache_miss"):
            profiler.record_diagnostics_cache_miss(spec.name)
        entry = {
            **_entry_base(spec, dep_hash, dep_files, subset_snapshot, subset_fields, prev),
            "cache_hit": False,
            "cache_miss_reason": reason,
            "subset_changed_paths": changed_paths,
            "changed_dependency_files": changed_paths,
            "reused_from_run_id": "",
            "stale_safe": False,
            "recompute_required": True,
            "safety_fields_verified": False,
            "last_compute_seconds": round(elapsed, 4),
        }
        new_entries[spec.name] = entry
        debug_entries[spec.name] = entry

    def _dep_context(spec: DiagnosticSpec) -> tuple[str, list[str], dict[str, Any], list[str]]:
        dep_hash, subset_snapshot, subset_fields = compute_subset_dependency_hash(spec.name, loaded_inputs)
        all_paths = resolve_dependency_paths(data_dir, output_dir)
        root = data_dir.parent
        files_used: list[str] = []
        for key in spec.dep_keys:
            path = all_paths.get(key)
            if path and path.exists():
                try:
                    files_used.append(str(path.relative_to(root)))
                except ValueError:
                    files_used.append(str(path))
        return dep_hash, files_used, subset_snapshot, subset_fields

    def _run_cached(spec: DiagnosticSpec, writer: Callable[[], Any]) -> bool:
        if spec.name in _DATA_GATE_ALIASES:
            dg = new_entries.get("data_gate_diagnostics") or {}
            if dg.get("cache_hit"):
                dep_hash, dep_files, subset_snapshot, subset_fields = _dep_context(spec)
                if _outputs_exist(output_dir, spec.output_files):
                    _record_hit(spec, dep_hash, dep_files, subset_snapshot, subset_fields, str(dg.get("reused_from_run_id") or run_id))
                    return True
            return False

        dep_hash, dep_files, subset_snapshot, subset_fields = _dep_context(spec)
        hit, reason, reused_from, changed = should_cache_hit(
            spec,
            data_dir=data_dir,
            output_dir=output_dir,
            dep_hash=dep_hash,
            prev_entries=prev_entries,
            subset_snapshot=subset_snapshot,
        )
        if hit:
            _record_hit(spec, dep_hash, dep_files, subset_snapshot, subset_fields, reused_from)
            return True

        t0 = time.perf_counter()
        writer()
        elapsed = time.perf_counter() - t0
        _record_miss(spec, dep_hash, dep_files, subset_snapshot, subset_fields, reason, elapsed, changed)
        return False

    from src.validation.alpha_shortlist_diagnostics import write_alpha_shortlist_diagnostics
    from src.validation.policy_cap_counterfactual import write_policy_cap_counterfactual
    from src.validation.core_etf_permission_diagnostics import write_core_etf_permission_diagnostics
    from src.validation.data_gate_diagnostics import write_data_gate_diagnostics
    from src.validation.alpha_gate_diagnostics import write_alpha_gate_diagnostics
    from src.validation.no_action_diagnostics import write_no_action_diagnostics

    writers: list[tuple[DiagnosticSpec, Callable[[], Any]]] = [
        (DIAGNOSTIC_SPECS[0], lambda: write_alpha_shortlist_diagnostics(data_dir, output_dir)),
        (DIAGNOSTIC_SPECS[1], lambda: write_policy_cap_counterfactual(data_dir, output_dir)),
        (DIAGNOSTIC_SPECS[2], lambda: write_core_etf_permission_diagnostics(data_dir, output_dir)),
        (DIAGNOSTIC_SPECS[3], lambda: write_data_gate_diagnostics(data_dir, output_dir)),
    ]

    for spec, writer in writers:
        _run_cached(spec, writer)

    for alias_spec in (DIAGNOSTIC_SPECS[4], DIAGNOSTIC_SPECS[5]):
        dg = new_entries.get("data_gate_diagnostics") or {}
        dep_hash, dep_files, subset_snapshot, subset_fields = _dep_context(alias_spec)
        if dg.get("cache_hit") and _outputs_exist(output_dir, alias_spec.output_files):
            _record_hit(alias_spec, dep_hash, dep_files, subset_snapshot, subset_fields, str(dg.get("reused_from_run_id") or run_id))
        elif _outputs_exist(output_dir, alias_spec.output_files):
            if dg.get("cache_hit") is False:
                _record_miss(alias_spec, dep_hash, dep_files, subset_snapshot, subset_fields, "data_gate_recomputed", 0.0, [])
            else:
                hit, reason, reused_from, changed = should_cache_hit(
                    alias_spec,
                    data_dir=data_dir,
                    output_dir=output_dir,
                    dep_hash=dep_hash,
                    prev_entries=prev_entries,
                    subset_snapshot=subset_snapshot,
                )
                if hit:
                    _record_hit(alias_spec, dep_hash, dep_files, subset_snapshot, subset_fields, reused_from)
                else:
                    _record_miss(alias_spec, dep_hash, dep_files, subset_snapshot, subset_fields, reason, 0.0, changed)

    _run_cached(DIAGNOSTIC_SPECS[6], lambda: write_alpha_gate_diagnostics(data_dir, output_dir))
    _run_cached(
        DIAGNOSTIC_SPECS[7],
        lambda: write_no_action_diagnostics(data_dir, output_dir, clarity=clarity, light=True),
    )

    if run_full_diag:
        from src.runtime.kosis_refresh_cache import maybe_run_kosis_tier2_refresh

        mode = run_mode
        if profiler is not None and hasattr(profiler, "run_mode") and profiler.run_mode:
            mode = str(profiler.run_mode)
        maybe_run_kosis_tier2_refresh(
            data_dir,
            output_dir,
            run_id=run_id,
            run_mode=mode,
            run_full_diag=True,
            diagnostics_cache_hit_count=result.cache_hit_count,
            diagnostics_cache_miss_count=result.cache_miss_count,
            profiler=profiler,
        )

    result.entries = list(new_entries.values())
    manifest = {
        "schema_version": "1.2",
        "hash_mode": HASH_MODE,
        "volatile_keys_excluded": volatile_excluded,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entries": new_entries,
        "summary": {
            "cache_hit_count": result.cache_hit_count,
            "cache_miss_count": result.cache_miss_count,
            "reused": result.reused,
            "recomputed": result.recomputed,
            "saved_seconds_estimate": round(result.saved_seconds_estimate, 2),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / MANIFEST_JSON).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_subset_hash_debug_manifest(output_dir, run_id=run_id, entries=debug_entries)
    return result
