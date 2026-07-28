"""Runtime profiling — step timings and cache counters."""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

RUNTIME_PROFILE_JSON = "outputs/runtime_profile.json"


@dataclass
class RuntimeProfiler:
    run_id: str
    run_mode: str
    entrypoint: str = "unknown"
    step_timings: dict[str, float] = field(default_factory=dict)
    cache_hit_count: int = 0
    cache_miss_count: int = 0
    pykrx_call_count: int = 0
    pykrx_failed_tickers: list[str] = field(default_factory=list)
    generated_files_count: int = 0
    bundle_size_mb: float = 0.0
    notes: list[str] = field(default_factory=list)
    on_step: Callable[[str, str, float], None] | None = None
    diagnostics_cache_hit_count: int = 0
    diagnostics_cache_miss_count: int = 0
    diagnostics_reused: list[str] = field(default_factory=list)
    diagnostics_recomputed: list[str] = field(default_factory=list)
    diagnostics_cache_saved_seconds_estimate: float = 0.0
    diagnostics_invocation_count: int = 0
    diagnostics_hash_mode: str = "subset_semantic"
    diagnostics_semantic_cache_enabled: bool = False
    bundle_reconcile_cache_hit_count: int = 0
    bundle_reconcile_cache_miss_count: int = 0
    bundle_reconcile_reused_files: list[str] = field(default_factory=list)
    bundle_reconcile_rechecked_files: list[str] = field(default_factory=list)
    bundle_reconcile_saved_seconds_estimate: float = 0.0
    kosis_refresh_executed: bool = False
    kosis_refresh_skip_reason: str = ""
    kosis_refresh_seconds_saved_estimate: float = 0.0
    kosis_dependency_hash_changed: bool = False
    alpha_v2_reused_from_cache: bool = False
    alpha_v2_refresh_reason: str = ""
    alpha_v2_full_refresh_executed: bool = False
    flow_refresh_executed: bool = False
    flow_refresh_reason: str = ""
    flow_full_refresh_executed: bool = False
    flow_cache_hit_count: int = 0
    flow_cache_miss_count: int = 0
    kosdaq_sync_executed: bool = False
    alpha_v2_cache_decision: str = ""
    alpha_v2_cache_blockers: list[str] = field(default_factory=list)
    alpha_v2_input_hash_match: bool = False
    alpha_v2_required_outputs_present: bool = False
    alpha_v2_as_of_covered: bool = False
    shadow_flow_refresh_executed: bool = False
    shadow_flow_reused_from_cache: bool = False
    shadow_flow_refresh_reason: str = ""
    shadow_flow_cache_blockers: list[str] = field(default_factory=list)
    shadow_flow_as_of_covered: bool = False
    price_fetch_executed: bool = False
    price_write_executed: bool = False
    price_fetch_reason: str = ""
    price_hash_match: bool = False
    price_hash_current: str = ""
    price_hash_previous: str = ""
    price_network_fetch_executed: bool = False
    price_check_only: bool = False
    price_hash_drift_reason: str = ""
    pipeline_core_total_seconds_reconciled: float = 0.0
    pipeline_core_step_timings: dict[str, float] = field(default_factory=dict)
    pipeline_core_slowest_steps: list[dict[str, Any]] = field(default_factory=list)
    pipeline_core_cache_hits: list[str] = field(default_factory=list)
    pipeline_core_skipped_steps: list[str] = field(default_factory=list)
    pipeline_core_pykrx_calls_by_step: dict[str, int] = field(default_factory=dict)
    final_decision_core_seconds: float = 0.0
    post_decision_artifacts_seconds: float = 0.0
    post_decision_artifacts_cache_hit: bool = False
    post_decision_artifacts_reused: bool = False
    post_decision_artifacts_recomputed: list[str] = field(default_factory=list)
    research_outputs_cache_hit: bool = False
    research_outputs_reused: bool = False
    research_outputs_recomputed: list[str] = field(default_factory=list)
    research_outputs_saved_seconds_estimate: float = 0.0
    research_outputs_dependency_hash_changed: bool = False
    shadow_history_cache_hit: bool = False
    shadow_history_append_executed: bool = False
    shadow_history_appended_rows: int = 0
    shadow_history_outcome_recomputed_rows: int = 0
    shadow_history_saved_seconds_estimate: float = 0.0
    shadow_history_snapshot_key_match: bool = False
    report_export_cache_hit: bool = False
    report_export_reused: bool = False
    report_export_recomputed: list[str] = field(default_factory=list)
    report_export_saved_seconds_estimate: float = 0.0
    report_export_dependency_hash_changed: bool = False

    def record_diagnostics_cache_hit(self, name: str, saved_seconds: float = 0.0) -> None:
        self.diagnostics_cache_hit_count += 1
        self.record_cache_hit()
        if name and name not in self.diagnostics_reused:
            self.diagnostics_reused.append(name)
        self.diagnostics_cache_saved_seconds_estimate = round(
            self.diagnostics_cache_saved_seconds_estimate + saved_seconds, 2,
        )

    def record_diagnostics_cache_miss(self, name: str) -> None:
        self.diagnostics_cache_miss_count += 1
        self.record_cache_miss()
        if name and name not in self.diagnostics_recomputed:
            self.diagnostics_recomputed.append(name)

    @contextmanager
    def step(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        if self.on_step:
            self.on_step("start", name, 0.0)
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self.step_timings[name] = round(self.step_timings.get(name, 0.0) + elapsed, 4)
            if self.on_step:
                self.on_step("end", name, elapsed)

    def record_cache_hit(self, count: int = 1) -> None:
        self.cache_hit_count += count

    def record_cache_miss(self, count: int = 1) -> None:
        self.cache_miss_count += count

    def record_pykrx_call(self, count: int = 1) -> None:
        self.pykrx_call_count += count

    def record_pykrx_failure(self, ticker: str) -> None:
        if ticker and ticker not in self.pykrx_failed_tickers:
            self.pykrx_failed_tickers.append(ticker)

    def add_note(self, note: str) -> None:
        if note and note not in self.notes:
            self.notes.append(note)

    def _slowest_steps(self, top_n: int = 5) -> list[dict[str, Any]]:
        ranked = sorted(self.step_timings.items(), key=lambda x: x[1], reverse=True)
        return [{"step": name, "seconds": sec} for name, sec in ranked[:top_n]]

    def _recommended_speedup(self) -> list[str]:
        rec: list[str] = []
        slow = self._slowest_steps(3)
        for item in slow:
            if item["seconds"] >= 5.0:
                rec.append(f"Consider cache-first or quick mode for slow step: {item['step']} ({item['seconds']}s)")
        if self.pykrx_call_count > 50:
            rec.append(f"PyKRX calls high ({self.pykrx_call_count}) — enable flow cache-first")
        if self.cache_miss_count > self.cache_hit_count and self.cache_miss_count > 10:
            rec.append("Cache miss ratio high — review incremental refresh policy")
        if not rec:
            rec.append("No major bottleneck flagged — profile within normal range")
        return rec

    def to_dict(self) -> dict[str, Any]:
        total = round(sum(self.step_timings.values()), 4)
        return {
            "schema_version": "1.0",
            "run_id": self.run_id,
            "run_mode": self.run_mode,
            "entrypoint": self.entrypoint,
            "total_seconds": total,
            "step_timings": dict(self.step_timings),
            "cache_hit_count": self.cache_hit_count,
            "cache_miss_count": self.cache_miss_count,
            "pykrx_call_count": self.pykrx_call_count,
            "pykrx_failed_tickers": self.pykrx_failed_tickers,
            "generated_files_count": self.generated_files_count,
            "bundle_size_mb": self.bundle_size_mb,
            "slowest_steps": self._slowest_steps(),
            "recommended_speedup": self._recommended_speedup(),
            "notes": self.notes,
            "diagnostics_cache_hit_count": self.diagnostics_cache_hit_count,
            "diagnostics_cache_miss_count": self.diagnostics_cache_miss_count,
            "diagnostics_reused": list(self.diagnostics_reused),
            "diagnostics_recomputed": list(self.diagnostics_recomputed),
            "diagnostics_cache_saved_seconds_estimate": self.diagnostics_cache_saved_seconds_estimate,
            "diagnostics_invocation_count": self.diagnostics_invocation_count,
            "diagnostics_hash_mode": self.diagnostics_hash_mode,
            "diagnostics_semantic_cache_enabled": self.diagnostics_semantic_cache_enabled,
            "bundle_reconcile_cache_hit_count": self.bundle_reconcile_cache_hit_count,
            "bundle_reconcile_cache_miss_count": self.bundle_reconcile_cache_miss_count,
            "bundle_reconcile_reused_files": list(self.bundle_reconcile_reused_files),
            "bundle_reconcile_rechecked_files": list(self.bundle_reconcile_rechecked_files),
            "bundle_reconcile_saved_seconds_estimate": self.bundle_reconcile_saved_seconds_estimate,
            "kosis_refresh_executed": self.kosis_refresh_executed,
            "kosis_refresh_skip_reason": self.kosis_refresh_skip_reason,
            "kosis_refresh_seconds_saved_estimate": self.kosis_refresh_seconds_saved_estimate,
            "kosis_dependency_hash_changed": self.kosis_dependency_hash_changed,
            "alpha_v2_reused_from_cache": self.alpha_v2_reused_from_cache,
            "alpha_v2_refresh_reason": self.alpha_v2_refresh_reason,
            "alpha_v2_full_refresh_executed": self.alpha_v2_full_refresh_executed,
            "flow_refresh_executed": self.flow_refresh_executed,
            "flow_refresh_reason": self.flow_refresh_reason,
            "flow_full_refresh_executed": self.flow_full_refresh_executed,
            "flow_cache_hit_count": self.flow_cache_hit_count,
            "flow_cache_miss_count": self.flow_cache_miss_count,
            "kosdaq_sync_executed": self.kosdaq_sync_executed,
            "alpha_v2_cache_decision": self.alpha_v2_cache_decision,
            "alpha_v2_cache_blockers": list(self.alpha_v2_cache_blockers),
            "alpha_v2_input_hash_match": self.alpha_v2_input_hash_match,
            "alpha_v2_required_outputs_present": self.alpha_v2_required_outputs_present,
            "alpha_v2_as_of_covered": self.alpha_v2_as_of_covered,
            "shadow_flow_refresh_executed": self.shadow_flow_refresh_executed,
            "shadow_flow_reused_from_cache": self.shadow_flow_reused_from_cache,
            "shadow_flow_refresh_reason": self.shadow_flow_refresh_reason,
            "shadow_flow_cache_blockers": list(self.shadow_flow_cache_blockers),
            "shadow_flow_as_of_covered": self.shadow_flow_as_of_covered,
            "price_fetch_executed": self.price_fetch_executed,
            "price_write_executed": self.price_write_executed,
            "price_fetch_reason": self.price_fetch_reason,
            "price_hash_match": self.price_hash_match,
            "price_hash_current": self.price_hash_current,
            "price_hash_previous": self.price_hash_previous,
            "price_network_fetch_executed": self.price_network_fetch_executed,
            "price_check_only": self.price_check_only,
            "price_hash_drift_reason": self.price_hash_drift_reason,
            "pipeline_core_step_timings": dict(self.pipeline_core_step_timings),
            "pipeline_core_slowest_steps": list(self.pipeline_core_slowest_steps),
            "pipeline_core_cache_hits": list(self.pipeline_core_cache_hits),
            "pipeline_core_skipped_steps": list(self.pipeline_core_skipped_steps),
            "pipeline_core_pykrx_calls_by_step": dict(self.pipeline_core_pykrx_calls_by_step),
            "pipeline_core_total_seconds_reconciled": self.pipeline_core_total_seconds_reconciled,
            "final_decision_core_seconds": self.final_decision_core_seconds,
            "post_decision_artifacts_seconds": self.post_decision_artifacts_seconds,
            "post_decision_artifacts_cache_hit": self.post_decision_artifacts_cache_hit,
            "post_decision_artifacts_reused": self.post_decision_artifacts_reused,
            "post_decision_artifacts_recomputed": list(self.post_decision_artifacts_recomputed),
            "research_outputs_cache_hit": self.research_outputs_cache_hit,
            "research_outputs_reused": self.research_outputs_reused,
            "research_outputs_recomputed": list(self.research_outputs_recomputed),
            "research_outputs_saved_seconds_estimate": self.research_outputs_saved_seconds_estimate,
            "research_outputs_dependency_hash_changed": self.research_outputs_dependency_hash_changed,
            "shadow_history_cache_hit": self.shadow_history_cache_hit,
            "shadow_history_append_executed": self.shadow_history_append_executed,
            "shadow_history_appended_rows": self.shadow_history_appended_rows,
            "shadow_history_outcome_recomputed_rows": self.shadow_history_outcome_recomputed_rows,
            "shadow_history_saved_seconds_estimate": self.shadow_history_saved_seconds_estimate,
            "shadow_history_snapshot_key_match": self.shadow_history_snapshot_key_match,
            "report_export_cache_hit": self.report_export_cache_hit,
            "report_export_reused": self.report_export_reused,
            "report_export_recomputed": list(self.report_export_recomputed),
            "report_export_saved_seconds_estimate": self.report_export_saved_seconds_estimate,
            "report_export_dependency_hash_changed": self.report_export_dependency_hash_changed,
            "diagnostics_path": RUNTIME_PROFILE_JSON,
        }

    def write(self, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "runtime_profile.json"
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path
