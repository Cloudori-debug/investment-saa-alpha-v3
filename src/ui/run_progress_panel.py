"""Streamlit run progress bar — 7-step pipeline UX."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import streamlit as st

from src.ui.run_progress import (
    SAFETY_DISCLAIMERS,
    RunProgressState,
    format_duration,
)


def render_run_summary(
    output_dir: Path,
    *,
    run_mode: str,
    actual_buy_allowed: int,
    advisory_note: str = "",
    prof: dict[str, Any] | None = None,
) -> None:
    """Post-run summary block (safe to call after rerun via session_state)."""
    if prof is None:
        from src.ui.helpers import load_output_json

        prof = load_output_json(output_dir, "runtime_profile.json") or {}

    progress = StreamlitRunProgress(run_mode)
    progress.render_summary(
        output_dir,
        actual_buy_allowed=actual_buy_allowed,
        advisory_note=advisory_note,
        prof=prof,
    )


class StreamlitRunProgress:
    """Live progress display for pipeline runs (display-only, no logic changes)."""

    def __init__(self, run_mode: str) -> None:
        self.run_mode = run_mode
        self.state = RunProgressState(run_mode=run_mode)
        self._holder = st.empty()
        self._render()

    @property
    def profiler_callback(self) -> Callable[[str, str, float], None]:
        def _cb(event: str, step_name: str, elapsed: float = 0.0) -> None:
            self.state.apply_profiler_step(event, step_name, elapsed)
            self._render()

        return _cb

    def on_pre_step(self, step_name: str, *, phase: str = "start") -> None:
        if phase == "start":
            self.state.apply_profiler_step("start", step_name)
        else:
            self.state.apply_profiler_step("end", step_name)
        self._render()

    def _render(self) -> None:
        with self._holder.container():
            st.markdown(f"**Run mode:** `{self.run_mode}`")
            if self.state.current_step:
                label = next(
                    (s.label for s in self.state.steps if s.key == self.state.current_step),
                    self.state.current_step,
                )
                st.caption(f"현재 단계: {label}")
            st.progress(self.state.progress_ratio())
            icons = {"pending": "⬜", "running": "🔄", "done": "✅", "skipped": "⏭️"}
            for step in self.state.steps:
                icon = icons.get(step.status, "⬜")
                timing = f" ({format_duration(step.seconds)})" if step.seconds > 0 else ""
                suffix = " · skipped" if step.status == "skipped" else ""
                st.markdown(f"{icon} **{step.label}**{timing}{suffix}")

    def render_summary(
        self,
        output_dir: Path,
        *,
        actual_buy_allowed: int,
        advisory_note: str = "",
        prof: dict[str, Any] | None = None,
    ) -> None:
        if prof is None:
            from src.ui.helpers import load_output_json

            prof = load_output_json(output_dir, "runtime_profile.json") or {}

        self.state.apply_runtime_profile(prof)
        self._render()

        diag: dict[str, Any] = {}
        nap = output_dir / "no_action_diagnostics.json"
        if nap.exists():
            import json

            diag = json.loads(nap.read_text(encoding="utf-8"))

        slowest = prof.get("slowest_steps") or []
        slowest_name = slowest[0]["step"] if slowest else "—"
        total = prof.get("total_seconds")

        st.markdown("#### 실행 결과")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total runtime", format_duration(total))
        c2.metric("Slowest step", slowest_name)
        c3.metric("Actual Buy Allowed", actual_buy_allowed)

        c4, c5, c6, c7 = st.columns(4)
        c4.metric("PyKRX calls", prof.get("pykrx_call_count", 0))
        c5.metric("Cache hits", prof.get("cache_hit_count", 0))
        c6.metric("Cache misses", prof.get("cache_miss_count", 0))
        c7.metric("Bundle size (MB)", prof.get("bundle_size_mb", 0))

        target_writes = _target_write_for_run(str(prof.get("run_id") or ""), output_dir)
        st.caption(
            f"Target write: {target_writes} · "
            f"No-action expected: {diag.get('no_action_is_expected', '—')}"
        )
        if advisory_note:
            st.caption(advisory_note)

        rows = [
            {"Step": step.label, "Status": step.status, "Seconds": step.seconds or "—"}
            for step in self.state.steps
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)

        if slowest:
            st.caption(
                "Slowest steps: "
                + ", ".join(f"{s['step']}={format_duration(s['seconds'])}" for s in slowest[:5])
            )

        for line in SAFETY_DISCLAIMERS:
            st.info(line)


def _target_write_for_run(run_id: str, output_dir: Path) -> int:
    if not run_id:
        return 0
    path = output_dir / "target_write_audit.jsonl"
    if not path.exists():
        return 0
    import json

    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        if ev.get("run_id") == run_id and ev.get("target_write_allowed") is True:
            n += 1
    return n
