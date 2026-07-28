"""P4c — pytest tier markers and collection hooks."""
from __future__ import annotations

import pytest

# --- tier module sets ---

SMOKE_MODULES: frozenset[str] = frozenset({
    "test_smoke_acceptance",
    "test_run_mode_cli",
    "test_alpha_v2_gate",
    "test_diagnostics_cache",
    "test_diagnostics_deduplication",
    "test_kosis_refresh_cache",
    "test_bundle_reconcile_cache",
    "test_hakedaka_gate",
    "test_research_outputs_cache",
    "test_shadow_history_cache",
    "test_report_export_cache",
    "test_post_decision_artifacts",
    "test_pipeline_step_runner",
})

INTEGRATION_MODULES: frozenset[str] = frozenset({
    "test_v2_features",
    "test_alpha_screener",
    "test_alpha_shadow_config",
    "test_alpha_v0_2",
    "test_full_pipeline",
    "test_production_clean_run",
    "test_p0_alignment",
    "test_portfolio_selector",
    "test_compass",
    "test_report_consistency",
    "test_portfolio_gap",
    "test_benchmark_data_quality",
    "test_asset_accumulation_timing",
    "test_risk_limits",
    "test_ui_menus",
    "test_top10_sector_candidate",
    "test_action_planner",
    "test_tier_a_price_gate",
    "test_hakedaka_evidence_enrichment",
    "test_run_mode",
})

LEGACY_BACKLOG_MODULES: frozenset[str] = frozenset({
    "test_compass",
    "test_portfolio_selector",
    "test_p0_alignment",
    "test_report_consistency",
    "test_portfolio_gap",
    "test_benchmark_data_quality",
    "test_asset_accumulation_timing",
    "test_risk_limits",
    "test_ui_menus",
    "test_top10_sector_candidate",
    "test_action_planner",
    "test_tier_a_price_gate",
    "test_alpha_screener",
    "test_v2_features",
    "test_alpha_v0_2",
})

NETWORK_MODULES: frozenset[str] = frozenset({
    "test_benchmark_data_quality",
    "test_pykrx",
    "test_dart",
    "test_kosis",
})

PYKRX_MODULES: frozenset[str] = frozenset({
    "test_pykrx",
    "test_price_fetch",
})

EXTERNAL_DATA_MODULES: frozenset[str] = frozenset({
    "test_benchmark_data_quality",
    "test_p0_alignment",
    "test_risk_limits",
    "test_top10_sector_candidate",
})

SLOW_TEST_NAMES: frozenset[str] = frozenset({
    "test_full_pipeline",
    "test_full_pipeline_includes_alpha",
    "test_pipeline_outputs",
    "test_standard_alpha_v2_skips_when_input_hash_unchanged",
})


def _module_stem(item: pytest.Item) -> str:
    return item.module.__name__.split(".")[-1]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        mod = _module_stem(item)
        marks: list[str] = []

        if mod in SMOKE_MODULES:
            marks.append("smoke")
        if mod in INTEGRATION_MODULES or "full_pipeline" in item.name:
            marks.append("integration")
        if mod in LEGACY_BACKLOG_MODULES:
            marks.append("legacy_backlog")
        if mod in NETWORK_MODULES or "network" in item.name:
            marks.append("network")
        if mod in PYKRX_MODULES or "pykrx" in item.name:
            marks.append("pykrx")
        if mod in EXTERNAL_DATA_MODULES:
            marks.append("external_data")
        if item.name in SLOW_TEST_NAMES or mod in INTEGRATION_MODULES:
            marks.append("slow")

        if not marks or mod in SMOKE_MODULES:
            if "integration" not in marks and "slow" not in marks and "legacy_backlog" not in marks:
                marks.append("fast")

        for name in marks:
            if not item.get_closest_marker(name):
                item.add_marker(getattr(pytest.mark, name))
