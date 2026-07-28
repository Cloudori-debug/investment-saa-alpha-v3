"""Run mode definitions — quick / standard / deep / bundle_only."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RunMode(str, Enum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"
    BUNDLE_ONLY = "bundle_only"


@dataclass(frozen=True)
class RunModeConfig:
    run_mode: RunMode
    refresh_network: bool
    run_alpha_v1: bool
    run_alpha_v2: bool
    run_flow_dashboard: bool
    run_backtest: bool
    run_alpha_backtest: bool
    run_research_outputs: bool
    run_shadow_history: bool
    run_bundle_reconcile: bool
    run_ai_export: bool
    run_zip_bundle: bool
    run_full_diagnostics: bool
    kosdaq_universe_sync: bool
    flow_refresh_mode: str  # skip | cache_first | full
    pykrx_flow_refresh: bool
    alpha_v2_cache_reuse: bool
    advisory_note: str

    @property
    def is_bundle_only(self) -> bool:
        return self.run_mode == RunMode.BUNDLE_ONLY


def resolve_run_config(run_mode: str | RunMode | None = None) -> RunModeConfig:
    if isinstance(run_mode, RunMode):
        mode = run_mode
    else:
        mode = RunMode(str(run_mode or RunMode.STANDARD.value))
    if mode == RunMode.QUICK:
        return RunModeConfig(
            run_mode=mode,
            refresh_network=False,
            run_alpha_v1=False,
            run_alpha_v2=False,
            run_flow_dashboard=False,
            run_backtest=False,
            run_alpha_backtest=False,
            run_research_outputs=False,
            run_shadow_history=False,
            run_bundle_reconcile=False,
            run_ai_export=False,
            run_zip_bundle=False,
            run_full_diagnostics=True,
            kosdaq_universe_sync=False,
            flow_refresh_mode="skip",
            pykrx_flow_refresh=False,
            alpha_v2_cache_reuse=True,
            advisory_note="Quick advisory run — cache-only, no network refresh.",
        )
    if mode == RunMode.DEEP:
        return RunModeConfig(
            run_mode=mode,
            refresh_network=True,
            run_alpha_v1=True,
            run_alpha_v2=True,
            run_flow_dashboard=True,
            run_backtest=True,
            run_alpha_backtest=True,
            run_research_outputs=True,
            run_shadow_history=True,
            run_bundle_reconcile=True,
            run_ai_export=True,
            run_zip_bundle=True,
            run_full_diagnostics=True,
            kosdaq_universe_sync=True,
            flow_refresh_mode="full",
            pykrx_flow_refresh=True,
            alpha_v2_cache_reuse=False,
            advisory_note="Deep refresh — full data and bundle generation.",
        )
    if mode == RunMode.BUNDLE_ONLY:
        return RunModeConfig(
            run_mode=mode,
            refresh_network=False,
            run_alpha_v1=False,
            run_alpha_v2=False,
            run_flow_dashboard=False,
            run_backtest=False,
            run_alpha_backtest=False,
            run_research_outputs=False,
            run_shadow_history=False,
            run_bundle_reconcile=False,
            run_ai_export=True,
            run_zip_bundle=True,
            run_full_diagnostics=False,
            kosdaq_universe_sync=False,
            flow_refresh_mode="skip",
            pykrx_flow_refresh=False,
            alpha_v2_cache_reuse=True,
            advisory_note="Bundle only — existing outputs used, no recalculation.",
        )
    return RunModeConfig(
        run_mode=RunMode.STANDARD,
        refresh_network=False,
        run_alpha_v1=True,
        run_alpha_v2=True,
        run_flow_dashboard=True,
        run_backtest=False,
        run_alpha_backtest=True,
        run_research_outputs=True,
        run_shadow_history=True,
        run_bundle_reconcile=True,
        run_ai_export=False,
        run_zip_bundle=False,
        run_full_diagnostics=True,
        kosdaq_universe_sync=False,
        flow_refresh_mode="cache_first",
        pykrx_flow_refresh=False,
        alpha_v2_cache_reuse=True,
        advisory_note="Standard daily analysis — cache-first network policy.",
    )
