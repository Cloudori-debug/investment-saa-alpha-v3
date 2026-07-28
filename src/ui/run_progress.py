"""UI 7-step progress — maps runtime profiler steps to Streamlit display."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.runtime.run_mode import RunMode

UI_STEP_ORDER: tuple[str, ...] = (
    "target_guard",
    "data_refresh_or_cache",
    "alpha_scoring",
    "flow_dashboard",
    "diagnostics",
    "report_generation",
    "bundle_export",
)

UI_STEP_LABELS: dict[str, str] = {
    "target_guard": "Target guard",
    "data_refresh_or_cache": "Data refresh / cache",
    "alpha_scoring": "Alpha scoring",
    "flow_dashboard": "Flow dashboard",
    "diagnostics": "Diagnostics",
    "report_generation": "Report",
    "bundle_export": "Bundle export",
}

PROFILER_STEP_TO_UI: dict[str, str] = {
    "target_guard": "target_guard",
    "authoritative_status": "target_guard",
    "actual_buy_allowed": "target_guard",
    "report_clarity_validation": "target_guard",
    "market_refresh": "data_refresh_or_cache",
    "tier_a_prices": "data_refresh_or_cache",
    "data_refresh": "data_refresh_or_cache",
    "data_hooks": "data_refresh_or_cache",
    "kosdaq_universe_sync": "data_refresh_or_cache",
    "flow_dashboard": "flow_dashboard",
    "pipeline_core": "alpha_scoring",
    "alpha_v2": "alpha_scoring",
    "research_outputs": "report_generation",
    "diagnostics": "diagnostics",
    "daily_report": "report_generation",
    "shadow_history": "diagnostics",
    "bundle_reconcile": "bundle_export",
    "ai_export_bundle": "bundle_export",
    "zip_bundle": "bundle_export",
    "runtime_profile": "bundle_export",
}

MODE_ACTIVE_STEPS: dict[str, frozenset[str]] = {
    RunMode.QUICK.value: frozenset({"target_guard", "diagnostics", "report_generation"}),
    RunMode.STANDARD.value: frozenset({
        "target_guard",
        "data_refresh_or_cache",
        "alpha_scoring",
        "flow_dashboard",
        "diagnostics",
        "report_generation",
    }),
    RunMode.DEEP.value: frozenset(UI_STEP_ORDER),
    RunMode.BUNDLE_ONLY.value: frozenset({"target_guard", "bundle_export"}),
}

MODE_STEP_LABELS: dict[str, dict[str, str]] = {
    RunMode.QUICK.value: {
        "data_refresh_or_cache": "Cache summary (skipped)",
        "alpha_scoring": "Alpha scoring (skipped)",
        "flow_dashboard": "Flow dashboard (skipped)",
        "bundle_export": "Bundle export (skipped)",
    },
    RunMode.BUNDLE_ONLY.value: {
        "data_refresh_or_cache": "Data refresh (skipped)",
        "alpha_scoring": "Alpha scoring (skipped)",
        "flow_dashboard": "Flow dashboard (skipped)",
        "diagnostics": "Diagnostics (skipped)",
        "report_generation": "Report (skipped)",
        "target_guard": "Target guard & status validation",
        "bundle_export": "Bundle export",
    },
}


@dataclass
class StepProgress:
    key: str
    label: str
    status: str = "pending"
    seconds: float = 0.0


@dataclass
class RunProgressState:
    run_mode: str
    steps: list[StepProgress] = field(default_factory=list)
    current_step: str = ""

    def __post_init__(self) -> None:
        if not self.steps:
            active = MODE_ACTIVE_STEPS.get(self.run_mode, frozenset(UI_STEP_ORDER))
            labels = MODE_STEP_LABELS.get(self.run_mode, {})
            self.steps = []
            for key in UI_STEP_ORDER:
                label = labels.get(key, UI_STEP_LABELS[key])
                status = "skipped" if key not in active else "pending"
                self.steps.append(StepProgress(key=key, label=label, status=status))

    def step_index(self, key: str) -> int:
        for i, s in enumerate(self.steps):
            if s.key == key:
                return i
        return -1

    def mark_running(self, key: str) -> None:
        idx = self.step_index(key)
        if idx < 0:
            return
        active = MODE_ACTIVE_STEPS.get(self.run_mode, frozenset(UI_STEP_ORDER))
        for s in self.steps:
            if s.status == "running" and s.key in active:
                s.status = "done"
        if self.steps[idx].status != "skipped":
            self.steps[idx].status = "running"
            self.current_step = key

    def mark_done(self, key: str, seconds: float = 0.0) -> None:
        idx = self.step_index(key)
        if idx < 0:
            return
        step = self.steps[idx]
        if step.status == "skipped":
            return
        step.status = "done"
        if seconds > 0:
            step.seconds = round(step.seconds + seconds, 2)
        if self.current_step == key:
            self.current_step = ""

    def progress_ratio(self) -> float:
        active = [s for s in self.steps if s.status != "skipped"]
        if not active:
            return 1.0
        done = sum(1 for s in active if s.status == "done")
        running = sum(0.5 for s in active if s.status == "running")
        return min(1.0, (done + running) / len(active))

    def apply_profiler_step(self, event: str, profiler_step: str, elapsed: float = 0.0) -> None:
        ui_key = PROFILER_STEP_TO_UI.get(profiler_step)
        if not ui_key:
            return
        if event == "start":
            self.mark_running(ui_key)
        elif event == "end":
            self.mark_done(ui_key, elapsed)

    def apply_runtime_profile(self, prof: dict[str, Any]) -> None:
        timings = prof.get("step_timings") or {}
        ui_seconds: dict[str, float] = {k: 0.0 for k in UI_STEP_ORDER}
        for prof_step, sec in timings.items():
            ui_key = PROFILER_STEP_TO_UI.get(prof_step)
            if ui_key and ui_key in ui_seconds:
                ui_seconds[ui_key] += float(sec or 0)
        active = MODE_ACTIVE_STEPS.get(self.run_mode, frozenset(UI_STEP_ORDER))
        for step in self.steps:
            if step.key not in active:
                step.status = "skipped"
                continue
            sec = ui_seconds.get(step.key, 0.0)
            if sec > 0:
                step.seconds = round(sec, 2)
                step.status = "done"
            elif step.status == "pending":
                step.status = "done"


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    sec = float(seconds)
    if sec < 60:
        return f"{sec:.1f}s"
    mins = int(sec // 60)
    rem = int(sec % 60)
    return f"{mins}m {rem:02d}s"


def build_profiler_callback(state: RunProgressState) -> Callable[[str, str, float], None]:
    def _cb(event: str, step_name: str, elapsed: float = 0.0) -> None:
        state.apply_profiler_step(event, step_name, elapsed)

    return _cb


SAFETY_DISCLAIMERS: tuple[str, ...] = (
    "Actual Buy Allowed=0이면 신규매수 없음.",
    "ETF_ONLY는 ETF 매수 허가가 아니라 실행 범위 제한입니다.",
    "Quick mode는 cache 기반 빠른 점검이며 full refresh가 아닙니다.",
)
