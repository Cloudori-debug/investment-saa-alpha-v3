"""Hakedaka / value_list feature gate (cleanup phase 1).

ENABLE_HAKEDAKA=False by default after archive. Set env ENABLE_HAKEDAKA=1 to
re-enable when src.value_list is restored from archive/.
Stubs preserve pure_qvm + AC-HK liquidity rules without value_list.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Cleanup phase 1 default — package lives under archive/20260715_value_list.
ENABLE_HAKEDAKA = False

_DISABLED_NOTE = "Hakedaka research disabled (ENABLE_HAKEDAKA=False / value_list archived)."


def hakedaka_enabled() -> bool:
    env = str(os.environ.get("ENABLE_HAKEDAKA", "")).strip().lower()
    if env in {"1", "true", "yes", "on"}:
        return True
    if env in {"0", "false", "no", "off"}:
        return False
    return bool(ENABLE_HAKEDAKA)


def _try_import(mod: str):
    if not hakedaka_enabled():
        return None
    try:
        import importlib

        return importlib.import_module(f"src.value_list.{mod}")
    except ImportError:
        return None


# --- disclaimers / brief helpers (export_daily_brief) ---
RERATING_DISCLAIMER = _DISABLED_NOTE
DATA_QUALITY_DISCLAIMER = _DISABLED_NOTE
EVIDENCE_DISCLAIMER = _DISABLED_NOTE
COVERAGE_AUDIT_DISCLAIMER = _DISABLED_NOTE
ACCOUNTS_DEBUG_DISCLAIMER = _DISABLED_NOTE
NAV_TREASURY_DISCLAIMER = _DISABLED_NOTE
MANUAL_VERIFICATION_DISCLAIMER = _DISABLED_NOTE
CATALYST_EVIDENCE_DISCLAIMER = _DISABLED_NOTE
CALIBRATION_DISCLAIMER = _DISABLED_NOTE
FORWARD_RETURN_DISCLAIMER = _DISABLED_NOTE
FORWARD_RETURN_QA_DISCLAIMER = _DISABLED_NOTE
HAKEDAKA_STATUS_DISCLAIMER = _DISABLED_NOTE


def write_latest_hakedaka_status(output_dir: Path) -> dict[str, Any]:
    real = _try_import("hakedaka_status_summary")
    if real is not None:
        return real.write_latest_hakedaka_status(output_dir)
    return {
        "enabled": False,
        "status": "disabled",
        "note": _DISABLED_NOTE,
    }


def load_integration_config(data_dir: Path) -> dict[str, Any]:
    real = _try_import("ticker_registry")
    if real is not None:
        return real.load_integration_config(data_dir)
    # Invariant defaults — pure_qvm, no tie-breaker, no hard slot.
    path = data_dir / "hakedaka_integration.yaml"
    if path.exists():
        try:
            import yaml

            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                out = dict(raw)
                out["enabled"] = False
                out.setdefault("proposal_mode", "pure_qvm")
                out.setdefault("hakedaka_tiebreaker_enabled", False)
                return out
        except Exception:
            pass
    return {
        "enabled": False,
        "proposal_mode": "pure_qvm",
        "hakedaka_tiebreaker_enabled": False,
        "hard_slot_enabled": False,
    }


def resolve_hakedaka_registry(data_dir: Path) -> list[dict]:
    real = _try_import("ticker_registry")
    if real is not None:
        return real.resolve_hakedaka_registry(data_dir)
    return []


def merge_hakedaka_into_universe(universe: list, data_dir: Path) -> list:
    real = _try_import("alpha_bridge")
    if real is not None:
        return real.merge_hakedaka_into_universe(universe, data_dir)
    return universe


def build_liquidity_pass_map(passed_universe, excluded_universe, data_dir: Path) -> dict[str, bool]:
    real = _try_import("alpha_bridge")
    if real is not None:
        return real.build_liquidity_pass_map(passed_universe, excluded_universe, data_dir)
    out: dict[str, bool] = {}
    for u in passed_universe or []:
        t = getattr(u, "ticker", None) or (u.get("ticker") if isinstance(u, dict) else None)
        if t:
            out[str(t)] = True
    for e in excluded_universe or []:
        t = getattr(e, "ticker", None) or (e.get("ticker") if isinstance(e, dict) else None)
        rule = getattr(e, "rule_id", None) or (e.get("rule_id") if isinstance(e, dict) else "")
        if t and str(rule) in {
            "min_market_cap",
            "min_20d_trading_value",
            "min_60d_trading_value",
            "missing_price",
        }:
            out[str(t)] = False
    return out


def apply_hakedaka_alpha_bonus(
    graded: list[dict[str, Any]],
    data_dir: Path,
    *,
    liquidity_pass_by_ticker: dict[str, bool] | None = None,
) -> list[dict[str, Any]]:
    real = _try_import("alpha_bridge")
    if real is not None:
        return real.apply_hakedaka_alpha_bonus(
            graded, data_dir, liquidity_pass_by_ticker=liquidity_pass_by_ticker,
        )
    # Mark liquidity_pass when known; leave scores untouched (pure_qvm).
    out = []
    for row in graded:
        r = dict(row)
        t = str(r.get("ticker") or "")
        if liquidity_pass_by_ticker is not None and t in liquidity_pass_by_ticker:
            r["liquidity_pass"] = bool(liquidity_pass_by_ticker[t])
        r.setdefault("in_hakedaka", False)
        r.setdefault("hakedaka_bonus", 0.0)
        r.setdefault("hakedaka_priority", False)
        r.setdefault("qvm_pure_score", r.get("total_score", 0))
        out.append(r)
    return out


def hakedaka_alpha_limitations(
    data_dir: Path,
    graded: list[dict[str, Any]],
    *,
    overlap_count: int = 0,
) -> list[str]:
    real = _try_import("alpha_bridge")
    if real is not None:
        return real.hakedaka_alpha_limitations(
            data_dir, graded, overlap_count=overlap_count,
        )
    return [_DISABLED_NOTE]


def proposal_sort_score(
    row: dict[str, Any],
    cfg: dict[str, Any] | None,
    *,
    incumbent_bonus: float = 0.0,
    is_incumbent: bool = False,
) -> float:
    real = _try_import("alpha_bridge")
    if real is not None:
        return real.proposal_sort_score(
            row, cfg, incumbent_bonus=incumbent_bonus, is_incumbent=is_incumbent,
        )
    base = float(row.get("qvm_pure_score", row.get("total_score", 0)) or 0)
    if is_incumbent:
        base += float(incumbent_bonus)
    return base


def tie_breaker_sort_boost(
    row: dict[str, Any],
    leader_score: float,
    cfg: dict[str, Any] | None,
) -> float:
    real = _try_import("alpha_bridge")
    if real is not None:
        return real.tie_breaker_sort_boost(row, leader_score, cfg)
    return 0.0


def eligible_for_proposal_row(row: dict[str, Any], cfg: dict[str, Any] | None) -> bool:
    real = _try_import("alpha_bridge")
    if real is not None:
        return real.eligible_for_proposal_row(row, cfg)
    if row.get("price_coverage_pass") is False:
        return False
    if row.get("liquidity_pass") is False:
        return False
    if str(row.get("grade", "Reject")) == "Reject":
        return False
    if str(row.get("eligible_action", "")) == "NO_NEW":
        return False
    return True


def write_hakedaka_overlap_diagnostics(*args: Any, **kwargs: Any) -> None:
    real = _try_import("overlap_diagnostics")
    if real is not None:
        real.write_hakedaka_overlap_diagnostics(*args, **kwargs)


def prepare_hakedaka_dart_pipeline(data_dir: Path, output_dir: Path) -> None:
    real = _try_import("dart_prep")
    if real is not None:
        real.prepare_hakedaka_dart_pipeline(data_dir, output_dir)


def run_research_automation(data_dir: Path, output_dir: Path) -> None:
    real = _try_import("research_pipeline")
    if real is not None:
        real.run_research_automation(data_dir, output_dir)


def write_macro_scenario(data_dir: Path, output_dir: Path) -> None:
    real = _try_import("macro_scenarios")
    if real is not None:
        real.write_macro_scenario(data_dir, output_dir)


def write_research_checklist(data_dir: Path, output_dir: Path) -> None:
    real = _try_import("research_checklist")
    if real is not None:
        real.write_research_checklist(data_dir, output_dir)
