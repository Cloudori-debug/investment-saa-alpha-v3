"""P2 — granular pipeline_core step timing and observability."""
from __future__ import annotations

import json
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from src.runtime.pipeline_step_contract import (
    PIPELINE_CORE_STEPS_JSON,
    PIPELINE_CORE_STEP_NAMES,
    STEP_STATUS_CACHE_HIT,
    STEP_STATUS_EXECUTED,
    STEP_STATUS_FAILED,
    STEP_STATUS_SKIPPED,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_actual_buy_allowed(output_dir: Path | None) -> int:
    if output_dir is None:
        return 0
    try:
        from src.report.execution_metrics import count_executable_actions
        from src.report.io_utils import read_output_json

        final_doc = read_output_json(output_dir / "final_execution_decision.json") or {}
        if not final_doc:
            return 0
        return int(count_executable_actions(final_doc).get("actual_buy_allowed_count") or 0)
    except Exception:
        return 0


@dataclass
class PipelineStepRecord:
    step_name: str
    status: str
    started_at: str
    ended_at: str
    elapsed_seconds: float
    run_mode: str
    skip_reason: str = ""
    cache_hit: bool = False
    cache_source: str = ""
    input_hash: str = ""
    output_hash: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    pykrx_calls_delta: int = 0
    target_write_delta: int = 0
    actual_buy_allowed_before: int = 0
    actual_buy_allowed_after: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_name": self.step_name,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "elapsed_seconds": round(self.elapsed_seconds, 4),
            "run_mode": self.run_mode,
            "skip_reason": self.skip_reason,
            "cache_hit": self.cache_hit,
            "cache_source": self.cache_source,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "pykrx_calls_delta": self.pykrx_calls_delta,
            "target_write_delta": self.target_write_delta,
            "actual_buy_allowed_before": self.actual_buy_allowed_before,
            "actual_buy_allowed_after": self.actual_buy_allowed_after,
        }


class PipelineStepRunner:
    """Records fine-grained pipeline_core steps without changing pipeline semantics."""

    def __init__(
        self,
        *,
        run_mode: str,
        run_id: str,
        profiler: Any | None = None,
        output_dir: Path | None = None,
    ) -> None:
        self.run_mode = str(run_mode or "standard")
        self.run_id = str(run_id or "")
        self.profiler = profiler
        self.output_dir = output_dir
        self.steps: list[PipelineStepRecord] = []

    @contextmanager
    def step(
        self,
        step_name: str,
        *,
        skip: bool = False,
        skip_reason: str = "",
        cache_hit: bool = False,
        cache_source: str = "",
        input_hash: str = "",
        output_hash: str = "",
        warnings: list[str] | None = None,
    ) -> Iterator[None]:
        if skip:
            self.record_skip(
                step_name,
                skip_reason or "skipped",
                cache_hit=cache_hit,
                cache_source=cache_source,
            )
            yield
            return

        started = _utc_now()
        t0 = time.perf_counter()
        pykrx_before = int(getattr(self.profiler, "pykrx_call_count", 0) or 0) if self.profiler else 0
        buy_before = _read_actual_buy_allowed(self.output_dir)
        status = STEP_STATUS_CACHE_HIT if cache_hit else STEP_STATUS_EXECUTED
        errors: list[str] = []
        prof_cm = None
        if self.profiler is not None and hasattr(self.profiler, "step"):
            prof_cm = self.profiler.step(step_name)
            prof_cm.__enter__()
        try:
            yield
        except Exception as exc:
            status = STEP_STATUS_FAILED
            errors.append(str(exc))
            errors.append(traceback.format_exc(limit=3))
            raise
        finally:
            elapsed = time.perf_counter() - t0
            if prof_cm is not None:
                prof_cm.__exit__(None, None, None)
            pykrx_after = int(getattr(self.profiler, "pykrx_call_count", 0) or 0) if self.profiler else 0
            buy_after = _read_actual_buy_allowed(self.output_dir)
            self.steps.append(
                PipelineStepRecord(
                    step_name=step_name,
                    status=status,
                    started_at=started,
                    ended_at=_utc_now(),
                    elapsed_seconds=elapsed,
                    run_mode=self.run_mode,
                    skip_reason=skip_reason,
                    cache_hit=cache_hit,
                    cache_source=cache_source,
                    input_hash=input_hash,
                    output_hash=output_hash,
                    warnings=list(warnings or []),
                    errors=errors,
                    pykrx_calls_delta=pykrx_after - pykrx_before,
                    target_write_delta=0,
                    actual_buy_allowed_before=buy_before,
                    actual_buy_allowed_after=buy_after,
                ),
            )

    def record_skip(
        self,
        step_name: str,
        skip_reason: str,
        *,
        cache_hit: bool = False,
        cache_source: str = "",
    ) -> None:
        now = _utc_now()
        self.steps.append(
            PipelineStepRecord(
                step_name=step_name,
                status=STEP_STATUS_CACHE_HIT if cache_hit else STEP_STATUS_SKIPPED,
                started_at=now,
                ended_at=now,
                elapsed_seconds=0.0,
                run_mode=self.run_mode,
                skip_reason=skip_reason,
                cache_hit=cache_hit,
                cache_source=cache_source,
            ),
        )

    def annotate_last_step(self, step_name: str, **updates: Any) -> None:
        for record in reversed(self.steps):
            if record.step_name != step_name:
                continue
            for key, val in updates.items():
                if hasattr(record, key):
                    setattr(record, key, val)
            if updates.get("cache_hit"):
                record.status = STEP_STATUS_CACHE_HIT
            break

    def summarize(self) -> dict[str, Any]:
        timings: dict[str, float] = {}
        for s in self.steps:
            timings[s.step_name] = round(timings.get(s.step_name, 0.0) + s.elapsed_seconds, 4)
        skipped = [s.step_name for s in self.steps if s.status == STEP_STATUS_SKIPPED]
        cache_hits = [s.step_name for s in self.steps if s.cache_hit or s.status == STEP_STATUS_CACHE_HIT]
        pykrx_by_step = {
            s.step_name: s.pykrx_calls_delta for s in self.steps if s.pykrx_calls_delta
        }
        ranked = sorted(timings.items(), key=lambda x: x[1], reverse=True)
        pre_pipeline = {"target_guard_precheck", "market_data_refresh"}
        inner_timings = {k: v for k, v in timings.items() if k not in pre_pipeline}
        total = round(sum(inner_timings.values()), 4)
        total_all_steps = round(sum(timings.values()), 4)
        return {
            "schema_version": "1.0",
            "run_id": self.run_id,
            "run_mode": self.run_mode,
            "generated_at": _utc_now(),
            "steps": [s.to_dict() for s in self.steps],
            "pipeline_core_step_timings": timings,
            "pipeline_core_slowest_steps": [
                {"step": name, "seconds": sec} for name, sec in ranked[:8]
            ],
            "pipeline_core_cache_hits": cache_hits,
            "pipeline_core_skipped_steps": skipped,
            "pipeline_core_pykrx_calls_by_step": pykrx_by_step,
            "pipeline_core_total_seconds_reconciled": total,
            "pipeline_core_all_steps_seconds": total_all_steps,
            "pipeline_core_step_names": list(PIPELINE_CORE_STEP_NAMES),
        }

    def apply_to_profiler(self) -> None:
        if self.profiler is None:
            return
        summary = self.summarize()
        mapping = {
            "pipeline_core_step_timings": summary["pipeline_core_step_timings"],
            "pipeline_core_slowest_steps": summary["pipeline_core_slowest_steps"],
            "pipeline_core_cache_hits": summary["pipeline_core_cache_hits"],
            "pipeline_core_skipped_steps": summary["pipeline_core_skipped_steps"],
            "pipeline_core_pykrx_calls_by_step": summary["pipeline_core_pykrx_calls_by_step"],
            "pipeline_core_total_seconds_reconciled": summary["pipeline_core_total_seconds_reconciled"],
        }
        for key, val in mapping.items():
            if hasattr(self.profiler, key):
                setattr(self.profiler, key, val)

    def write(self, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        doc = self.summarize()
        path = output_dir / PIPELINE_CORE_STEPS_JSON
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.apply_to_profiler()
        return path


def null_step_runner() -> PipelineStepRunner | None:
    return None
