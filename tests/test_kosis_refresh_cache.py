"""P1.6 — KOSIS tier2 refresh conditional skip tests."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from src.runtime.kosis_refresh_cache import (
    MANIFEST_JSON,
    evaluate_kosis_refresh_skip,
    maybe_run_kosis_tier2_refresh,
    write_kosis_refresh_manifest,
)
from src.runtime.profiler import RuntimeProfiler

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
KOSIS_DIAG = "kosis_tier2_refresh_diagnostics.json"


def _seed_kosis_deps(data: Path, out: Path) -> str:
    data.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    for name in (
        "tier2_sources.yaml",
        "tier2_provenance.json",
        "tier2_kosis_manual.yaml",
        "market_indicators.csv",
        "macro_tier2.csv",
    ):
        src = DATA_DIR / name
        if src.exists():
            shutil.copy(src, data / name)
        elif name == "tier2_kosis_manual.yaml":
            shutil.copy(DATA_DIR / "tier2_kosis_manual.yaml.example", data / name)
    (out / "pmi_kr_source_policy.json").write_text(
        json.dumps({"pmi_kr_status": "manual_required", "cpi_kr_yoy_status": "fresh"}),
        encoding="utf-8",
    )
    diag = {
        "manual_required_fields": ["pmi_kr"],
        "refreshed_fields": ["cpi_kr_yoy"],
        "failed_fields": [],
        "stale_after": [],
    }
    (out / KOSIS_DIAG).write_text(json.dumps(diag), encoding="utf-8")
    from src.runtime.kosis_refresh_cache import compute_kosis_dependency_hash

    dep_hash, dep_files, _ = compute_kosis_dependency_hash(data, out)
    write_kosis_refresh_manifest(
        out,
        run_id="warmup-run",
        run_mode="standard",
        kosis_refresh_executed=True,
        skip_reason="",
        dependency_hash=dep_hash,
        previous_dependency_hash="",
        dependency_files=dep_files,
        last_refresh_seconds=250.0,
        diag_doc=diag,
    )
    return dep_hash


def test_standard_same_dependency_skips_kosis_refresh(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_kosis_deps(data, out)
    skip, reason, _, _ = evaluate_kosis_refresh_skip(
        data, out, run_mode="standard", diagnostics_cache_hit_count=8, diagnostics_cache_miss_count=0,
    )
    assert skip is True
    assert reason in {"dependency_unchanged", "diagnostics_cache_hit"}

    prof = RuntimeProfiler(run_id="r2", run_mode="standard")
    with patch(
        "src.validation.kosis_tier2_refresh_diagnostics.run_kosis_tier2_refresh_with_diagnostics",
    ) as mock_run:
        maybe_run_kosis_tier2_refresh(
            data, out, run_id="r2", run_mode="standard",
            diagnostics_cache_hit_count=8, diagnostics_cache_miss_count=0, profiler=prof,
        )
        mock_run.assert_not_called()
    assert prof.kosis_refresh_executed is False
    assert prof.kosis_refresh_skip_reason in {"dependency_unchanged", "diagnostics_cache_hit"}
    assert prof.kosis_refresh_seconds_saved_estimate > 0
    manifest = json.loads((out / MANIFEST_JSON).read_text(encoding="utf-8"))
    assert manifest["kosis_refresh_executed"] is False
    assert manifest["reused_from_run_id"] == "warmup-run"


def test_deep_mode_always_executes(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_kosis_deps(data, out)
    skip, reason, _, _ = evaluate_kosis_refresh_skip(
        data, out, run_mode="deep", diagnostics_cache_hit_count=8, diagnostics_cache_miss_count=0,
    )
    assert skip is False
    assert reason == "deep_mode"

    prof = RuntimeProfiler(run_id="deep1", run_mode="deep")
    fake_diag = {"manual_required_fields": ["pmi_kr"], "refreshed_fields": [], "failed_fields": []}
    with patch(
        "src.validation.kosis_tier2_refresh_diagnostics.run_kosis_tier2_refresh_with_diagnostics",
        return_value=(None, fake_diag),
    ) as mock_run:
        maybe_run_kosis_tier2_refresh(
            data, out, run_id="deep1", run_mode="deep",
            diagnostics_cache_hit_count=8, diagnostics_cache_miss_count=0, profiler=prof,
        )
        mock_run.assert_called_once()
    assert prof.kosis_refresh_executed is True


def test_tier2_sources_change_forces_refresh(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_kosis_deps(data, out)
    yaml_path = data / "tier2_sources.yaml"
    yaml_path.write_text(
        yaml_path.read_text(encoding="utf-8").replace("DT_1J22042", "DT_1J99999"),
        encoding="utf-8",
    )
    skip, reason, _, _ = evaluate_kosis_refresh_skip(
        data, out, run_mode="standard", diagnostics_cache_hit_count=8, diagnostics_cache_miss_count=0,
    )
    assert skip is False
    assert reason == "dependency_hash_changed"


def test_tier2_kosis_manual_change_forces_refresh(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_kosis_deps(data, out)
    manual = data / "tier2_kosis_manual.yaml"
    manual.write_text(
        manual.read_text(encoding="utf-8").replace("verified: false", "verified: false\n    note: touched"),
        encoding="utf-8",
    )
    skip, reason, _, _ = evaluate_kosis_refresh_skip(
        data, out, run_mode="standard", diagnostics_cache_hit_count=8, diagnostics_cache_miss_count=0,
    )
    assert skip is False
    assert reason in {"dependency_hash_changed", "pmi_kr_verified_or_manual_changed"}


def test_pmi_kr_verified_transition_forces_refresh(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_kosis_deps(data, out)
    (data / "tier2_kosis_manual.yaml").write_text(
        """
fields:
  pmi_kr:
    verified: true
    value: 49.2
    value_date: "2026-06-01"
    source: "manual:test"
    source_url_or_note: "https://example.com"
    updated_by: "test"
    update_reason: "verified"
  cpi_kr_yoy:
    verified: false
""",
        encoding="utf-8",
    )
    skip, reason, _, _ = evaluate_kosis_refresh_skip(
        data, out, run_mode="standard", diagnostics_cache_hit_count=8, diagnostics_cache_miss_count=0,
    )
    assert skip is False
    assert reason == "pmi_kr_verified_or_manual_changed"


def test_missing_kosis_diagnostics_forces_refresh(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_kosis_deps(data, out)
    (out / KOSIS_DIAG).unlink()
    skip, reason, _, _ = evaluate_kosis_refresh_skip(
        data, out, run_mode="standard", diagnostics_cache_hit_count=8, diagnostics_cache_miss_count=0,
    )
    assert skip is False
    assert reason == "kosis_diagnostics_missing"


def test_skip_preserves_manual_required_in_manifest(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_kosis_deps(data, out)
    maybe_run_kosis_tier2_refresh(
        data, out, run_id="skip-run", run_mode="standard",
        diagnostics_cache_hit_count=8, diagnostics_cache_miss_count=0,
    )
    manifest = json.loads((out / MANIFEST_JSON).read_text(encoding="utf-8"))
    assert "pmi_kr" in manifest["manual_required_fields"]
    assert manifest["pmi_kr_verified"] is False


def test_incomplete_diagnostics_cache_still_skips_kosis_when_dep_unchanged(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_kosis_deps(data, out)
    skip, reason, _, _ = evaluate_kosis_refresh_skip(
        data, out, run_mode="standard", diagnostics_cache_hit_count=4, diagnostics_cache_miss_count=4,
    )
    assert skip is True
    assert reason == "dependency_unchanged"


def test_profiler_records_executed_on_refresh(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed_kosis_deps(data, out)
    (out / MANIFEST_JSON).unlink()
    prof = RuntimeProfiler(run_id="exec1", run_mode="standard")
    fake_diag = {"manual_required_fields": ["pmi_kr"], "refreshed_fields": ["cpi_kr_yoy"], "failed_fields": []}
    with patch(
        "src.validation.kosis_tier2_refresh_diagnostics.run_kosis_tier2_refresh_with_diagnostics",
        return_value=(None, fake_diag),
    ):
        maybe_run_kosis_tier2_refresh(
            data, out, run_id="exec1", run_mode="standard",
            diagnostics_cache_hit_count=8, diagnostics_cache_miss_count=0, profiler=prof,
        )
    assert prof.kosis_refresh_executed is True
    assert prof.kosis_refresh_skip_reason == ""
    manifest = json.loads((out / MANIFEST_JSON).read_text(encoding="utf-8"))
    assert manifest["kosis_refresh_executed"] is True
    assert manifest["last_refresh_seconds"] >= 0
