from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.alpha.loaders import load_prices
from src.models import PositionRow, TargetRow
from src.report.io_utils import read_output_json

from src.alpha_v2.final_selector import select_final_candidates, select_top30
from src.alpha_v2.flow_overlay import apply_flow_overlay
from src.alpha_v2.institutional_flow_loader import load_institutional_flows
from src.alpha_v2.market_filters import classify_market_tier
from src.alpha_v2.profit_sweep import build_profit_sweep_candidates
from src.alpha_v2.scoring import score_alpha_v2_universe
from src.alpha_v2.scored_comparison import build_scored_count_comparison
from src.alpha_v2.schemas import ALPHA_V2_MODE, ALPHA_V2_SCHEMA, KOSDAQ_FINAL_MAX, KOSDAQ_SLEEVE_MAX_PCT, POLICY_NOTES
from src.alpha_v2.trigger_engine import build_flow_triggers, build_positions_meta
from src.alpha_v2.trim_watch_audit import (
    TRIM_DETAIL_COLUMNS,
    build_trim_watch_detail_rows,
    validate_trim_watch_detail,
)
from src.alpha_v2.universe_builder import build_alpha_v2_universe


def _execution_context(output_dir: Path) -> dict[str, Any]:
    final = read_output_json(output_dir / "final_execution_decision.json") or {}
    from src.report.execution_metrics import count_executable_actions

    metrics = count_executable_actions(final)
    scope = str(final.get("execution_scope") or "NO_TRADE")
    return {
        "actual_buy_allowed": int(metrics.get("actual_buy_allowed_count") or 0),
        "no_trade": scope == "NO_TRADE",
        "execution_scope": scope,
        "market_status": str(final.get("system_status") or final.get("operational_status") or "—"),
    }


def _liquidity_ok(filt: Any) -> bool:
    if filt.tier == "Exclude":
        return False
    if filt.market == "KOSDAQ":
        return filt.avg_turnover_20d >= 1_000_000_000
    return filt.avg_turnover_20d >= 2_000_000_000


def _compute_kosdaq_tier_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"Core": 0, "Mid": 0, "Shadow": 0, "Exclude": 0}
    for row in rows:
        if str(row.get("market", "")).upper() != "KOSDAQ":
            continue
        tier = str(row.get("tier") or "Exclude")
        counts[tier] = counts.get(tier, 0) + 1
    return counts


def _validate_kosdaq_integration(
    kosdaq_n: int,
    tier_counts: dict[str, int],
    final: list[dict[str, Any]],
    ctx: dict[str, Any],
) -> tuple[bool, list[str], str]:
    if kosdaq_n == 0:
        return False, ["kosdaq_universe_count=0"], "KOSPI-only shadow validated; KOSDAQ not yet loaded"

    failures: list[str] = []
    kosdaq_final = [r for r in final if str(r.get("market", "")).upper() == "KOSDAQ"]
    if len(kosdaq_final) > KOSDAQ_FINAL_MAX:
        failures.append(f"kosdaq_final_count={len(kosdaq_final)} > {KOSDAQ_FINAL_MAX}")

    if ctx.get("no_trade"):
        for row in kosdaq_final:
            if row.get("buy_permission"):
                failures.append(f"KOSDAQ {row.get('ticker')} buy_permission under NO_TRADE")

    for row in kosdaq_final:
        if row.get("shadow_watch") and row.get("buy_permission"):
            failures.append(f"KOSDAQ Shadow {row.get('ticker')} has buy_permission")

    kosdaq_weight = sum(float(r.get("suggested_shadow_weight") or 0) for r in kosdaq_final)
    if kosdaq_weight > KOSDAQ_SLEEVE_MAX_PCT:
        failures.append(f"kosdaq_sleeve_weight={kosdaq_weight:.1f} > {KOSDAQ_SLEEVE_MAX_PCT}")

    tier_computed = sum(tier_counts.values()) > 0
    complete = kosdaq_n > 0 and tier_computed and not failures
    if complete:
        status = "KOSPI+KOSDAQ unified shadow validated"
    else:
        status = "KOSDAQ loaded; unified shadow validation pending"
    return complete, failures, status


def _enrich_market_fields(
    scored: list[dict[str, Any]],
    universe_map: dict[str, Any],
    prices: dict[str, Any],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in scored:
        rec = universe_map.get(row["ticker"])
        if not rec:
            continue
        price = prices.get(row["ticker"])
        filt = classify_market_tier(rec, price)
        merged = dict(row)
        merged.update({
            "market": filt.market,
            "market_cap": filt.market_cap,
            "avg_turnover_20d": filt.avg_turnover_20d,
            "tier": filt.tier,
            "executable_universe": filt.executable_universe,
            "liquidity_flag": _liquidity_ok(filt),
            "shadow_watch": filt.shadow_watch,
            "market_filter_reason": filt.reason,
        })
        out.append(merged)
    return out


def _apply_permissions(rows: list[dict[str, Any]], ctx: dict[str, Any]) -> None:
    for row in rows:
        buy_perm = bool(
            ctx["actual_buy_allowed"] > 0
            and not ctx["no_trade"]
            and not row.get("shadow_watch")
            and row.get("grade") not in {"Reject", "D"}
            and row.get("tier") != "Exclude"
        )
        row["buy_permission"] = buy_perm
        row["review_only"] = ctx["no_trade"] or ctx["execution_scope"] == "NO_TRADE"


def _write_csv(rows: list[dict[str, Any]], path: Path, columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        pd.DataFrame(columns=columns or []).to_csv(path, index=False, encoding="utf-8-sig")
        return
    df = pd.DataFrame(rows)
    if columns:
        for col in columns:
            if col not in df.columns:
                df[col] = ""
        df = df[columns]
    df.to_csv(path, index=False, encoding="utf-8-sig")


def run_alpha_v2_shadow(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    positions: list[PositionRow],
    targets: list[TargetRow] | None = None,
    cache_reuse: bool = False,
    force_refresh: bool = False,
    flow_refresh_mode: str = "cache_first",
    run_mode: str = "standard",
    run_id: str = "",
    profiler: object | None = None,
) -> dict[str, Any]:
    """Alpha v2 shadow — outputs only under outputs/alpha_v2_*; no target write."""
    from src.alpha_v2.cache_decision import (
        apply_decision_to_profiler,
        evaluate_alpha_v2_cache_decision,
        finalize_decision_pykrx_after,
        store_input_hash,
        write_alpha_v2_cache_decision,
    )
    from src.runtime.run_mode_contract import (
        _record_alpha_v2_full,
        _record_alpha_v2_reuse,
        _record_flow_run,
        _record_flow_skip,
        investor_flows_covers_as_of,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    pykrx_before = int(getattr(profiler, "pykrx_call_count", 0) or 0) if profiler else 0

    decision_doc = evaluate_alpha_v2_cache_decision(
        data_dir,
        output_dir,
        as_of=as_of,
        run_mode=run_mode,
        run_id=run_id,
        force_refresh=force_refresh,
        cache_reuse=cache_reuse,
        pykrx_before=pykrx_before,
    )
    apply_decision_to_profiler(profiler, decision_doc)
    write_alpha_v2_cache_decision(output_dir, decision_doc)

    if decision_doc.get("decision") == "reuse_cache":
        summary_path = output_dir / "alpha_v2_summary.json"
        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            if profiler is not None and hasattr(profiler, "add_note"):
                profiler.add_note("Alpha v2 scoring: reused from cache")
                if hasattr(profiler, "record_cache_hit"):
                    profiler.record_cache_hit()
            _record_alpha_v2_reuse(profiler, reason=str(decision_doc.get("refresh_reason") or "input_hash_unchanged"))
            summary["cache_reused"] = True
            summary["cache_reuse_reason"] = decision_doc.get("refresh_reason")
            summary_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            decision_doc = finalize_decision_pykrx_after(profiler, decision_doc)
            from src.alpha_v2.cache_decision import commit_alpha_v2_cache_state

            decision_doc = commit_alpha_v2_cache_state(
                output_dir, data_dir, decision_doc, as_of=as_of, run_id=run_id or "",
            )
            write_alpha_v2_cache_decision(output_dir, decision_doc)
            return summary

    if decision_doc.get("decision") == "blocked_no_cache":
        _record_alpha_v2_full(profiler, reason=str(decision_doc.get("refresh_reason") or "quick_cache_only"))
        decision_doc = finalize_decision_pykrx_after(profiler, decision_doc)
        write_alpha_v2_cache_decision(output_dir, decision_doc)
        return {
            "mode": "shadow",
            "as_of": as_of,
            "cache_reused": False,
            "cache_blocked": True,
            "refresh_reason": decision_doc.get("refresh_reason"),
            "target_write_occurred": False,
        }

    _record_alpha_v2_full(
        profiler,
        reason=str(decision_doc.get("refresh_reason") or "full_scoring"),
    )
    ctx = _execution_context(output_dir)
    positions_meta = build_positions_meta(positions)

    universe = build_alpha_v2_universe(data_dir)
    universe_map = {u.ticker: u for u in universe}
    prices = {p.ticker: p for p in load_prices(data_dir / "prices.csv", as_of=as_of)}

    kospi_n = sum(1 for u in universe if (u.market or "KOSPI").upper() == "KOSPI")
    kosdaq_n = sum(1 for u in universe if (u.market or "").upper() == "KOSDAQ")

    scored = score_alpha_v2_universe(universe, data_dir, output_dir, as_of=as_of)
    scored = _enrich_market_fields(scored, universe_map, prices)
    kosdaq_tier_counts = _compute_kosdaq_tier_counts(scored)
    scored = [r for r in scored if r.get("tier") != "Exclude"]

    try:
        from src.alpha.flow_refresh import run_flow_refresh
        from src.alpha_flow.watched_universe import resolve_watched_universe_tickers

        watch = resolve_watched_universe_tickers(
            data_dir, output_dir, scored_rows=scored, max_tickers=80,
        )
        if watch:
            use_cache = flow_refresh_mode != "full"
            if flow_refresh_mode == "cache_first" and investor_flows_covers_as_of(data_dir, as_of):
                _record_flow_skip(profiler, "investor_flows_unchanged")
            else:
                flow_result = run_flow_refresh(
                    data_dir,
                    output_dir,
                    as_of=as_of,
                    tickers=watch,
                    use_cache=use_cache,
                )
                _record_flow_run(
                    profiler,
                    executed=True,
                    reason="cache_miss" if flow_result.pykrx_call_count else "cache_hit",
                    full_refresh=flow_refresh_mode == "full",
                    cache_hits=int(flow_result.cache_hit_count or 0),
                    cache_misses=int(flow_result.cache_miss_count or 0),
                )
    except Exception:
        pass

    flows = load_institutional_flows(data_dir)
    scored = apply_flow_overlay(scored, flows)
    from src.alpha_flow.flow_classifier import count_fresh_stale

    _freshness = count_fresh_stale(scored)
    stale_flow_count = _freshness["stale_flow_count"]
    fresh_flow_count = _freshness["fresh_flow_count"]

    from src.alpha_flow.watched_universe import resolve_watched_universe_tickers

    watch_tickers = {
        t["ticker"] for t in resolve_watched_universe_tickers(
            data_dir, output_dir, scored_rows=scored, max_tickers=80,
        )
    }
    watched_scored = [r for r in scored if r["ticker"] in watch_tickers]
    watched_fs = count_fresh_stale(watched_scored)
    held_tickers = {
        str(p.ticker).zfill(6)
        for p in positions
        if float(p.quantity or 0) > 0 and str(p.ticker).upper() != "CASH"
    }
    for row in scored:
        if row.get("flow_data_stale") and row["ticker"] in held_tickers:
            row["flow_data_stale_warning"] = True
        else:
            row["flow_data_stale_warning"] = False
    for row in scored:
        if "total_score_v2_shadow" not in row:
            row["total_score_v2_shadow"] = round(
                float(row.get("total_score_v1") or 0) + float(row.get("flow_score") or 0), 2
            )

    universe_rows = [
        {
            "ticker": r["ticker"],
            "name": r.get("name", ""),
            "market": r.get("market", "KOSPI"),
            "tier": r.get("tier", ""),
            "market_cap": r.get("market_cap", 0),
            "avg_turnover_20d": r.get("avg_turnover_20d", 0),
            "executable_universe": r.get("executable_universe", False),
            "shadow_watch": r.get("shadow_watch", False),
        }
        for r in scored
    ]
    _write_csv(universe_rows, output_dir / "alpha_v2_universe.csv")

    _write_csv(scored, output_dir / "alpha_v2_scored.csv")

    top30 = select_top30(scored)
    _apply_permissions(top30, ctx)
    _write_csv(top30, output_dir / "alpha_v2_top30.csv")

    final = select_final_candidates(top30)
    _apply_permissions(final, ctx)
    _write_csv(final, output_dir / "alpha_v2_final_candidates.csv")

    buy_watch, trim_watch, stale_warnings = build_flow_triggers(
        scored,
        actual_buy_allowed=ctx["actual_buy_allowed"],
        no_trade=ctx["no_trade"],
        execution_scope=ctx["execution_scope"],
        held_tickers=held_tickers,
        positions_meta=positions_meta,
    )
    scored_by_ticker = {str(r["ticker"]).zfill(6): r for r in scored}
    trim_detail = build_trim_watch_detail_rows(
        trim_watch,
        scored_by_ticker,
        positions=positions,
        targets=targets,
        positions_meta=positions_meta,
    )
    trim_validation = validate_trim_watch_detail(trim_detail)
    _write_csv(trim_detail, output_dir / "alpha_v2_trim_watch_detail.csv", columns=TRIM_DETAIL_COLUMNS)
    _write_csv(
        [r for r in trim_detail if r.get("trim_category") == "held_or_target"],
        output_dir / "alpha_v2_trim_watch_held.csv",
        columns=TRIM_DETAIL_COLUMNS,
    )
    _write_csv(
        [r for r in trim_detail if r.get("trim_category") == "informational"],
        output_dir / "alpha_v2_trim_watch_informational.csv",
        columns=TRIM_DETAIL_COLUMNS,
    )
    _write_csv(buy_watch + trim_watch, output_dir / "alpha_v2_flow_triggers.csv", columns=[
        "ticker", "name", "market", "grade", "flow_signal_state", "flow_score", "flow_confidence",
        "buy_watch", "trim_watch", "buy_permission", "review_only", "note", "reason",
    ])
    if stale_warnings:
        _write_csv(stale_warnings, output_dir / "alpha_v2_flow_stale_warnings.csv", columns=[
            "ticker", "name", "flow_data_stale_warning", "flow_confidence", "flow_signal_state", "note",
        ])

    sweep = build_profit_sweep_candidates(
        positions,
        market_status=ctx["market_status"],
        no_trade=ctx["no_trade"],
    )
    _write_csv(sweep, output_dir / "alpha_v2_profit_sweep_candidates.csv")

    scored_comparison = build_scored_count_comparison(output_dir, scored)
    kosdaq_missing = kosdaq_n == 0
    unified_complete, kosdaq_validation_failures, validation_status = _validate_kosdaq_integration(
        kosdaq_n, kosdaq_tier_counts, final, ctx
    )

    summary = {
        "schema_version": ALPHA_V2_SCHEMA,
        "mode": ALPHA_V2_MODE,
        "as_of": as_of,
        "execution_authority": "v1.0.2",
        "policy_notes": POLICY_NOTES,
        "kosdaq_universe_missing": kosdaq_missing,
        "kospi_kosdaq_unified_validation_complete": unified_complete,
        "validation_status": validation_status,
        "kosdaq_validation_failures": kosdaq_validation_failures,
        "scored_count_comparison": {
            **scored_comparison,
            "v2_broader_universe_note": (
                "v2 scored universe is broader than v1 because it uses market tier filters, "
                "not the full v1 PIT/data gate."
            ),
        },
        "trim_watch_validation": trim_validation,
        "coverage": {
            "kospi_universe_count": kospi_n,
            "kosdaq_universe_count": kosdaq_n,
            "kosdaq_core_count": kosdaq_tier_counts.get("Core", 0),
            "kosdaq_mid_count": kosdaq_tier_counts.get("Mid", 0),
            "kosdaq_shadow_count": kosdaq_tier_counts.get("Shadow", 0),
            "kosdaq_exclude_count": kosdaq_tier_counts.get("Exclude", 0),
            "scored_count": len(scored),
            "stale_flow_count": stale_flow_count,
            "stale_flow_warning_count": len(stale_warnings),
            "top30_count": len(top30),
            "final_candidates_count": len(final),
            "kosdaq_candidate_count": sum(1 for r in final if str(r.get("market", "")).upper() == "KOSDAQ"),
            "buy_watch_count": len(buy_watch),
            "trim_watch_count": len(trim_watch),
            "trim_watch_held_count": trim_validation.get("trim_watch_held_or_target", 0),
            "trim_watch_informational_count": trim_validation.get("trim_watch_informational", 0),
            "fresh_flow_count": fresh_flow_count,
            "watched_fresh_flow_count": watched_fs["fresh_flow_count"],
            "watched_stale_flow_count": watched_fs["stale_flow_count"],
            "watched_ticker_count": len(watch_tickers),
            "coverage_scope_v2_all_scored": "all_scored",
            "coverage_scope_watched": "watched_universe",
            "profit_sweep_count": len(sweep),
        },
        "execution_context": ctx,
        "target_write_occurred": False,
    }
    (output_dir / "alpha_v2_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    from src.alpha_v2.cache_decision import (
        commit_alpha_v2_cache_state,
        finalize_decision_pykrx_after,
        write_alpha_v2_cache_decision,
    )

    decision_doc["alpha_v2_full_refresh_executed"] = True
    decision_doc["alpha_v2_reused_from_cache"] = False
    decision_doc = finalize_decision_pykrx_after(profiler, decision_doc)
    decision_doc = commit_alpha_v2_cache_state(
        output_dir, data_dir, decision_doc, as_of=as_of, run_id=run_id or "",
    )
    write_alpha_v2_cache_decision(output_dir, decision_doc)
    from src.alpha_v2.cache_decision import apply_decision_to_profiler

    apply_decision_to_profiler(profiler, decision_doc)
    return summary
