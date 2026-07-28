"""P2 — pipeline_core step decomposition contract."""
from __future__ import annotations

from typing import Final

PIPELINE_CORE_STEPS_JSON = "pipeline_core_steps.json"

STEP_STATUS_EXECUTED: Final[str] = "executed"
STEP_STATUS_SKIPPED: Final[str] = "skipped"
STEP_STATUS_CACHE_HIT: Final[str] = "cache_hit"
STEP_STATUS_FAILED: Final[str] = "failed"

PIPELINE_CORE_STEP_NAMES: tuple[str, ...] = (
    "target_guard_precheck",
    "market_data_refresh",
    "tier_a_refresh",
    "tier_b_refresh",
    "portfolio_state_build",
    "saa_taa_allocation",
    "alpha_v1_pipeline",
    "alpha_v2_pipeline",
    "flow_dashboard",
    "research_outputs",
    "shadow_history",
    "final_decision_core",
    "post_decision_artifacts",
    "report_exports",
    "post_run_commit_snapshot",
)
