"""Alpha shadow layer toggles — config-driven v0.2 / v2 / flow dashboard."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.config import load_portfolio_policy
from src.report.io_utils import read_output_json

V02_DISABLED_NOTE = "Alpha v0.2 shadow disabled by config."
V02_UNAVAILABLE_NOTE = "Alpha v0.2 shadow module unavailable (archived)."
V2_DISABLED_NOTE = "Alpha v2 / Flow disabled (ENABLE_ALPHA_V2=False / archived)."

# Optional: package may live under archive/ after cleanup phase 0.
try:
    from src.alpha_v0_2.pipeline import run_alpha_v0_2_shadow as _run_alpha_v0_2_shadow
except ImportError:  # pragma: no cover - expected after archive
    _run_alpha_v0_2_shadow: Callable[..., Any] | None = None


def alpha_shadow_flags(policy: dict[str, Any]) -> dict[str, bool]:
    raw = policy.get("alpha_shadow") or {}
    return {
        "v0_2_enabled": bool(raw.get("v0_2_enabled", False)),
        "v2_enabled": bool(raw.get("v2_enabled", True)),
        "flow_dashboard_enabled": bool(raw.get("flow_dashboard_enabled", True)),
    }


def load_alpha_shadow_flags(data_dir: Path) -> dict[str, bool]:
    path = data_dir / "portfolio_policy.yaml"
    if not path.exists():
        return alpha_shadow_flags({})
    return alpha_shadow_flags(load_portfolio_policy(path))


def resolve_alpha_v02_shadow_doc(
    output_dir: Path,
    *,
    data_dir: Path | None = None,
    run_id: str | None = None,
    policy: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str, bool]:
    """Return (shadow_doc, status, config_enabled).

    status: disabled | active | missing | stale
    Stale files from prior runs are ignored when run_id is provided.
    """
    if policy is None and data_dir is not None:
        path = data_dir / "portfolio_policy.yaml"
        policy = load_portfolio_policy(path) if path.exists() else {}
    flags = alpha_shadow_flags(policy or {})
    enabled = flags["v0_2_enabled"]
    if not enabled:
        return None, "disabled", False

    doc = read_output_json(output_dir / "alpha_v0_2_shadow.json")
    if not doc:
        return None, "missing", True

    doc_run_id = str(doc.get("run_id") or "")
    if run_id and doc_run_id and doc_run_id != run_id:
        return None, "stale", True
    return doc, "active", True


def alpha_v02_brief_section(
    output_dir: Path,
    *,
    data_dir: Path | None,
    run_id: str | None,
    kr_alpha_portfolio_pct: float | None,
) -> dict[str, Any]:
    doc, status, enabled = resolve_alpha_v02_shadow_doc(
        output_dir,
        data_dir=data_dir,
        run_id=run_id,
    )
    base = {
        "enabled": enabled,
        "status": status,
        "weight_basis": "investable_assets_ex_cash",
        "kr_alpha_v1_portfolio_pct": kr_alpha_portfolio_pct,
        "kr_alpha_v1_basis": "total_portfolio_nav",
        "weight_basis_note": (
            "hard stop·execution_scope는 v1.0.2 전체 포트 기준; "
            "v0.2 %는 현금 제외 투자자산 분모 (shadow 참고용)"
        ),
    }
    if status == "disabled":
        return {
            **base,
            "mode": "shadow",
            "note": V02_DISABLED_NOTE,
            "alpha_budget_status": "",
            "current_alpha_weight_pct": 0,
            "new_alpha_buy_allowed": False,
            "legacy_diff_count": 0,
            "holdings_summary": [],
        }
    if doc is None:
        note = "Alpha v0.2 shadow enabled but output missing for this run."
        if status == "stale":
            note = "Alpha v0.2 shadow output stale (prior run) — ignored for this report."
        return {
            **base,
            "mode": "shadow",
            "note": note,
            "alpha_budget_status": "",
            "current_alpha_weight_pct": 0,
            "new_alpha_buy_allowed": False,
            "legacy_diff_count": 0,
            "holdings_summary": [],
        }
    return {
        **base,
        "mode": doc.get("mode", "shadow"),
        "run_id": doc.get("run_id", ""),
        "generated_at": doc.get("generated_at", ""),
        "alpha_budget_status": doc.get("alpha_budget_status", ""),
        "current_alpha_weight_pct": doc.get("current_alpha_weight_pct", 0),
        "new_alpha_buy_allowed": doc.get("new_alpha_buy_allowed", False),
        "legacy_diff_count": doc.get("legacy_diff_count", 0),
        "holdings_summary": _alpha_v02_holdings_from_doc(doc),
    }


def _alpha_v02_holdings_from_doc(doc: dict[str, Any]) -> list[dict[str, Any]]:
    held = [r for r in doc.get("rows") or [] if r.get("in_portfolio")]
    return [
        {
            "ticker": r.get("ticker"),
            "name": r.get("name"),
            "classification": r.get("classification"),
            "weight_pct": r.get("current_weight_pct"),
        }
        for r in held[:10]
    ]


def stamp_alpha_v02_shadow_metadata(payload: dict[str, Any], *, run_id: str) -> dict[str, Any]:
    out = dict(payload)
    out["run_id"] = run_id
    out.setdefault(
        "generated_at",
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    return out


def run_configured_alpha_shadows(
    data_dir: Path,
    output_dir: Path,
    *,
    run_id: str,
    as_of: str,
    positions: list[Any],
    targets: list[Any],
    append_log: Any,
    run_mode_config: object | None = None,
    profiler: object | None = None,
    step_runner: Any | None = None,
) -> dict[str, bool]:
    """Run v0.2 / v2 / flow shadow layers per portfolio_policy alpha_shadow flags."""
    flags = load_alpha_shadow_flags(data_dir)
    ran: dict[str, bool] = {"v0_2": False, "v2": False, "flow": False}
    cfg = run_mode_config
    run_v2 = cfg is None or bool(getattr(cfg, "run_alpha_v2", True))
    run_flow = cfg is None or bool(getattr(cfg, "run_flow_dashboard", True))
    v2_cache_reuse = bool(getattr(cfg, "alpha_v2_cache_reuse", False)) if cfg else False
    v2_force_refresh = not v2_cache_reuse
    flow_mode = str(getattr(cfg, "flow_refresh_mode", "cache_first")) if cfg else "cache_first"

    if flags.get("v0_2_enabled"):
        if _run_alpha_v0_2_shadow is None:
            append_log(
                output_dir / "decision_log.jsonl",
                {
                    "event": "alpha_v0_2_shadow_skipped",
                    "run_id": run_id,
                    "reason": "module_unavailable",
                    "note": V02_UNAVAILABLE_NOTE,
                },
            )
        else:
            try:
                _run_alpha_v0_2_shadow(
                    data_dir,
                    output_dir,
                    as_of=as_of,
                    positions=positions,
                    targets=targets,
                    legacy_output_dir=output_dir,
                    run_id=run_id,
                )
                ran["v0_2"] = True
            except Exception:
                pass
    else:
        append_log(
            output_dir / "decision_log.jsonl",
            {
                "event": "alpha_v0_2_shadow_skipped",
                "run_id": run_id,
                "reason": "config_disabled",
            },
        )

    if flags.get("v2_enabled", True) and run_v2:
        from src.alpha_v2_gate import alpha_v2_enabled, run_alpha_v2_shadow

        if not alpha_v2_enabled():
            append_log(
                output_dir / "decision_log.jsonl",
                {
                    "event": "alpha_v2_shadow_skipped",
                    "run_id": run_id,
                    "reason": "module_unavailable",
                    "note": V2_DISABLED_NOTE,
                },
            )
        else:
            try:
                def _run_v2() -> None:
                    run_alpha_v2_shadow(
                        data_dir,
                        output_dir,
                        as_of=as_of,
                        positions=positions,
                        targets=targets,
                        cache_reuse=v2_cache_reuse,
                        force_refresh=v2_force_refresh,
                        flow_refresh_mode=flow_mode,
                        run_mode=str(getattr(getattr(cfg, "run_mode", None), "value", "standard")) if cfg else "standard",
                        run_id=run_id,
                        profiler=profiler,
                    )

                if step_runner is not None and hasattr(step_runner, "step"):
                    with step_runner.step("alpha_v2_pipeline"):
                        _run_v2()
                    if profiler is not None and getattr(profiler, "alpha_v2_reused_from_cache", False):
                        step_runner.annotate_last_step(
                            "alpha_v2_pipeline",
                            cache_hit=True,
                            cache_source=str(getattr(profiler, "alpha_v2_refresh_reason", "") or "cache_reuse"),
                        )
                else:
                    _run_v2()
                ran["v2"] = True
            except Exception:
                pass
    elif not run_v2:
        append_log(
            output_dir / "decision_log.jsonl",
            {
                "event": "alpha_v2_shadow_skipped",
                "run_id": run_id,
                "reason": "run_mode_disabled",
            },
        )
    else:
        append_log(
            output_dir / "decision_log.jsonl",
            {
                "event": "alpha_v2_shadow_skipped",
                "run_id": run_id,
                "reason": "config_disabled",
            },
        )

    if flags.get("flow_dashboard_enabled", True) and run_flow and flow_mode != "skip":
        from src.alpha_v2_gate import alpha_v2_enabled, maybe_run_shadow_flow_dashboard

        if not alpha_v2_enabled():
            append_log(
                output_dir / "decision_log.jsonl",
                {
                    "event": "flow_dashboard_skipped",
                    "run_id": run_id,
                    "reason": "module_unavailable",
                    "note": V2_DISABLED_NOTE,
                },
            )
        else:
            try:
                run_mode_str = str(getattr(getattr(cfg, "run_mode", None), "value", "standard")) if cfg else "standard"

                def _run_flow() -> None:
                    maybe_run_shadow_flow_dashboard(
                        data_dir,
                        output_dir,
                        as_of=as_of,
                        run_mode=run_mode_str,
                        run_id=run_id,
                        force_refresh=v2_force_refresh,
                        refresh_mode=flow_mode,
                        max_tickers=80,
                        profiler=profiler,
                    )

                if step_runner is not None and hasattr(step_runner, "step"):
                    with step_runner.step("flow_dashboard"):
                        _run_flow()
                    if profiler is not None and getattr(profiler, "shadow_flow_reused_from_cache", False):
                        step_runner.annotate_last_step(
                            "flow_dashboard",
                            cache_hit=True,
                            cache_source=str(getattr(profiler, "shadow_flow_refresh_reason", "") or "cache_reuse"),
                        )
                else:
                    _run_flow()
                ran["flow"] = True
            except Exception:
                pass
    elif flow_mode == "skip" or not run_flow:
        append_log(
            output_dir / "decision_log.jsonl",
            {
                "event": "flow_dashboard_skipped",
                "run_id": run_id,
                "reason": "run_mode_skip" if flow_mode == "skip" else "run_mode_disabled",
            },
        )
    else:
        append_log(
            output_dir / "decision_log.jsonl",
            {
                "event": "flow_dashboard_skipped",
                "run_id": run_id,
                "reason": "config_disabled",
            },
        )

    return ran
