from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.alpha_v2.schemas import CANDIDATE_ONLY_NOTE, POLICY_NOTES
from src.field_normalize import sanitize_json_value


def _read_csv_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        return []
    if df.empty:
        return []
    return [sanitize_json_value(dict(r)) for r in df.to_dict(orient="records")]


def _candidate_export_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": row.get("rank") or row.get("final_rank"),
        "ticker": row.get("ticker"),
        "name": row.get("name"),
        "market": row.get("market"),
        "sector": row.get("sector"),
        "market_cap": row.get("market_cap"),
        "avg_turnover_20d": row.get("avg_turnover_20d"),
        "grade": row.get("grade"),
        "total_score_v1": row.get("total_score_v1"),
        "flow_score": row.get("flow_score"),
        "total_score_v2_shadow": row.get("total_score_v2_shadow"),
        "quality_score": row.get("quality_score"),
        "valuation_score": row.get("valuation_score"),
        "momentum_score": row.get("momentum_score"),
        "shareholder_return_score": row.get("shareholder_return_score"),
        "pension_net_buy_20d": row.get("pension_net_buy_20d"),
        "pension_streak_days": row.get("pension_streak_days"),
        "foreign_net_buy_20d": row.get("foreign_net_buy_20d"),
        "pension_foreign_co_buy": row.get("pension_foreign_co_buy"),
        "pension_foreign_co_sell": row.get("pension_foreign_co_sell"),
        "flow_signal_state": row.get("flow_signal_state"),
        "buy_watch": row.get("buy_watch", False),
        "trim_watch": row.get("trim_watch", False),
        "buy_permission": row.get("buy_permission", False),
        "suggested_shadow_weight": row.get("suggested_shadow_weight"),
        "reason": row.get("reason") or CANDIDATE_ONLY_NOTE,
        "note": CANDIDATE_ONLY_NOTE,
    }


def build_alpha_v2_export_sections(output_dir: Path) -> dict[str, Any]:
    summary_path = output_dir / "alpha_v2_summary.json"
    if not summary_path.exists():
        return {}
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    cov = summary.get("coverage") or {}
    top30 = [_candidate_export_row(r) for r in _read_csv_records(output_dir / "alpha_v2_top30.csv")]
    final = [_candidate_export_row(r) for r in _read_csv_records(output_dir / "alpha_v2_final_candidates.csv")]
    triggers = _read_csv_records(output_dir / "alpha_v2_flow_triggers.csv")
    buy_watch = [t for t in triggers if str(t.get("buy_watch", "")).lower() in {"true", "1"} or t.get("buy_watch") is True]
    trim_watch = [t for t in triggers if str(t.get("trim_watch", "")).lower() in {"true", "1"} or t.get("trim_watch") is True]
    sweep = _read_csv_records(output_dir / "alpha_v2_profit_sweep_candidates.csv")
    kosdaq_final_count = cov.get("kosdaq_candidate_count", 0)
    policy_notes = list(summary.get("policy_notes") or POLICY_NOTES)

    return {
        "alpha_v2_coverage": {
            **cov,
            "kosdaq_validation_status": summary.get("validation_status"),
            "kospi_kosdaq_unified_validation_complete": summary.get(
                "kospi_kosdaq_unified_validation_complete", False
            ),
        },
        "alpha_v2_top30": top30,
        "alpha_v2_final_5_8": {
            "candidates": final,
            "kosdaq_final_count": kosdaq_final_count,
            "kospi_final_count": max(0, len(final) - kosdaq_final_count),
        },
        "alpha_v2_flow_buy_watch": buy_watch,
        "alpha_v2_flow_trim_watch": trim_watch,
        "alpha_v2_profit_sweep_candidates": sweep,
        "alpha_v2_policy_notes": policy_notes,
        "alpha_v2_summary": summary,
    }


def build_daily_report_alpha_v2_section(output_dir: Path) -> list[str]:
    path = output_dir / "alpha_v2_summary.json"
    if not path.exists():
        return []
    summary = json.loads(path.read_text(encoding="utf-8"))
    cov = summary.get("coverage") or {}
    ctx = summary.get("execution_context") or {}
    kosdaq_missing = summary.get("kosdaq_universe_missing", False)
    validation_status = summary.get("validation_status", "")
    scored_cmp = summary.get("scored_count_comparison") or {}
    lines = [
        "## Alpha v2 Shadow (review-only)",
        "- Alpha v2 is shadow-only.",
        "- Flow signal is not buy permission.",
        "- Actual Buy Allowed=0 overrides all buy triggers.",
        "- NO_TRADE means review-only.",
        "",
    ]
    if kosdaq_missing:
        lines.append("- **KOSDAQ not yet loaded** — KOSPI-only shadow validated; 통합 검증 미완료.")
        lines.append("")
    else:
        lines.append("- **KOSDAQ candidates are shadow/review-only until separately approved.**")
        lines.append("- **KOSDAQ Shadow Watch is not buy permission.**")
        lines.append("- **Actual Buy Allowed=0 overrides all KOSDAQ signals.**")
        lines.append("")
    lines.extend([
        f"- **Validation**: {validation_status}",
        f"- **Coverage**: KOSPI {cov.get('kospi_universe_count', 0)} · "
        f"KOSDAQ {cov.get('kosdaq_universe_count', 0)} · scored {cov.get('scored_count', 0)} · "
        f"stale flow {cov.get('stale_flow_count', 0)}",
    ])
    if not kosdaq_missing:
        lines.append(
            f"- **KOSDAQ tiers**: Core {cov.get('kosdaq_core_count', 0)} · "
            f"Mid {cov.get('kosdaq_mid_count', 0)} · "
            f"Shadow {cov.get('kosdaq_shadow_count', 0)} · "
            f"Exclude {cov.get('kosdaq_exclude_count', 0)}"
        )
        lines.append(
            f"- **KOSDAQ validation**: "
            f"{'complete' if summary.get('kospi_kosdaq_unified_validation_complete') else 'pending'}"
        )
    lines.extend([
        f"- **Scored diff (v1→v2)**: v1={scored_cmp.get('v1_scored_count', '—')} · "
        f"v2={scored_cmp.get('v2_scored_count', '—')} · "
        f"Δ={scored_cmp.get('difference_count', '—')}",
    ])
    broader = scored_cmp.get("v2_broader_universe_note")
    if broader:
        lines.append(f"- **Universe note**: {broader}")
    trim_val = summary.get("trim_watch_validation") or {}
    if trim_val:
        status = "PASS" if trim_val.get("passed") else "FAIL"
        lines.append(
            f"- **Trim Watch audit**: {status} · total {trim_val.get('trim_watch_total', 0)} · "
            f"held/target {trim_val.get('trim_watch_held_or_target', 0)} · "
            f"informational {trim_val.get('trim_watch_informational', 0)}"
        )
    lines.extend([
        f"- **Top30 / Final 5~8**: {cov.get('top30_count', 0)} / {cov.get('final_candidates_count', 0)} "
        f"(KOSDAQ in final: {cov.get('kosdaq_candidate_count', 0)})",
        f"- **Watch (stale suppressed)**: Buy {cov.get('buy_watch_count', 0)} · "
        f"Trim {cov.get('trim_watch_count', 0)} "
        f"(held/target {cov.get('trim_watch_held_count', 0)} · "
        f"info {cov.get('trim_watch_informational_count', 0)}) · "
        f"stale warnings {cov.get('stale_flow_warning_count', 0)} · "
        f"fresh flow {cov.get('fresh_flow_count', 0)}",
        f"- **Execution context**: Actual Buy Allowed={ctx.get('actual_buy_allowed', 0)} · "
        f"scope `{ctx.get('execution_scope', '—')}` · NO_TRADE={ctx.get('no_trade', False)}",
        f"- **target write**: {summary.get('target_write_occurred', False)} (shadow — always false)",
        "",
    ])
    final_path = output_dir / "alpha_v2_final_candidates.csv"
    if final_path.exists():
        df = pd.read_csv(final_path, dtype=str, keep_default_na=False)
        if not df.empty:
            lines.append("| rank | ticker | market | grade | v2_shadow | flow | buy_perm |")
            lines.append("|-----:|--------|--------|-------|----------:|-----:|:--------:|")
            for _, r in df.head(8).iterrows():
                lines.append(
                    f"| {r.get('final_rank', r.get('rank', ''))} | {r.get('ticker')} | "
                    f"{r.get('market', '')} | {r.get('grade', '')} | "
                    f"{r.get('total_score_v2_shadow', '')} | {r.get('flow_signal_state', '')} | "
                    f"{r.get('buy_permission', False)} |"
                )
            lines.append("")
    trim_path = output_dir / "alpha_v2_trim_watch_detail.csv"
    if trim_path.exists():
        tdf = pd.read_csv(trim_path, dtype=str, keep_default_na=False)
        if not tdf.empty:
            lines.append("### Trim Watch detail (held/target first)")
            lines.append("| ticker | name | category | trim_reason | flow_conf | grade_chg | holding |")
            lines.append("|--------|------|----------|-------------|-----------|-----------|---------|")
            sort_order = {"held_or_target": 0, "informational": 1}
            if "trim_category" in tdf.columns:
                tdf = tdf.copy()
                tdf["_ord"] = tdf["trim_category"].map(sort_order).fillna(9)
            else:
                tdf = tdf.copy()
                tdf["_ord"] = 9
            for _, r in tdf.sort_values("_ord").iterrows():
                lines.append(
                    f"| {r.get('ticker')} | {r.get('name', '')[:12]} | {r.get('trim_category')} | "
                    f"{str(r.get('trim_reason', ''))[:40]} | {r.get('flow_confidence')} | "
                    f"{r.get('grade_change', '')} | {r.get('holding_flag')} |"
                )
            lines.append("")
    return lines
