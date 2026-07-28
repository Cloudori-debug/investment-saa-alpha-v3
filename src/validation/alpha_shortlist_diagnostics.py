"""Alpha shortlist pool empty diagnostics — per-ticker B-grade fail decomposition."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from src.alpha.loaders import load_alpha_scoring_config, load_fundamentals
from src.alpha.portfolio_selector import (
    PILLAR_KEYS,
    PILLAR_SCORE_FIELDS,
    _in_shortlist_pool,
    _pillars_pass,
)
from src.report.io_utils import read_output_json

DIAGNOSTICS_CSV = "outputs/alpha_shortlist_diagnostics.csv"
SUMMARY_JSON = "outputs/alpha_shortlist_summary.json"

_PILLAR_DIAG = (
    ("q_pillar_pass", "quality_score", "quality", "q_pillar_fail"),
    ("v_pillar_pass", "valuation_score", "valuation", "v_pillar_fail"),
    ("m_pillar_pass", "momentum_score", "momentum", "m_pillar_fail"),
    ("shareholder_return_pass", "shareholder_return_score", "shareholder_return", "shareholder_return_fail"),
)

_LIQ_RULES = {
    "min_market_cap",
    "min_20d_trading_value",
    "min_60d_trading_value",
    "missing_price",
}


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip()
    return t.zfill(6) if t.isdigit() else t


def _selection_thresholds(scoring_cfg: dict[str, Any]) -> tuple[dict[str, float], int, float]:
    sel = scoring_cfg.get("selection", {})
    thresholds = sel.get(
        "min_pillar_score",
        {"quality": 60, "valuation": 55, "momentum": 55, "shareholder_return": 55},
    )
    min_pillars = int(sel.get("min_pillars_pass", 3))
    floor = float(sel.get("min_all_pillar_floor", 45))
    return {k: float(v) for k, v in thresholds.items()}, min_pillars, floor


def _pit_pass_for_ticker(
    ticker: str,
    *,
    fundamentals: dict[str, Any],
    pit_excluded: set[str],
    pit_gate_yellow: bool,
) -> bool:
    if ticker in pit_excluded:
        return False
    fund = fundamentals.get(ticker)
    if fund is None:
        return not pit_gate_yellow
    return True


def _value_trap_flag(row: dict[str, Any], scoring_cfg: dict[str, Any]) -> bool:
    reason = str(row.get("key_reason") or "")
    if "가치함정" in reason:
        return True
    trap_penalty = abs(float(scoring_cfg.get("penalties", {}).get("value_trap", 15)))
    return float(row.get("penalty") or 0) >= trap_penalty and "가치함정" in reason


def _build_aux_maps(
    output_dir: Path,
    data_dir: Path,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]], set[str], set[str], dict[str, str]]:
    v2_by: dict[str, dict[str, str]] = {}
    for name in ("alpha_v2_scored.csv", "alpha_v2_top30.csv"):
        for row in _read_csv_rows(output_dir / name):
            t = _normalize_ticker(row.get("ticker", ""))
            if t:
                v2_by[t] = row

    signal_by: dict[str, dict[str, str]] = {}
    for row in _read_csv_rows(output_dir / "alpha_signal_board.csv"):
        t = _normalize_ticker(row.get("ticker", ""))
        if t:
            signal_by[t] = row

    liq_fail: set[str] = set()
    pit_excluded: set[str] = set()
    for row in _read_csv_rows(output_dir / "excluded.csv"):
        t = _normalize_ticker(row.get("ticker", ""))
        rule = str(row.get("failed_rule") or "")
        if rule in _LIQ_RULES:
            liq_fail.add(t)
        if rule in {"point_in_time", "stale_data", "missing_fundamentals"}:
            pit_excluded.add(t)

    universe_market: dict[str, str] = {}
    uni_path = data_dir / "universe.csv"
    if uni_path.exists():
        for row in _read_csv_rows(uni_path):
            t = _normalize_ticker(row.get("ticker", ""))
            if t:
                universe_market[t] = str(row.get("market") or "")

    return v2_by, signal_by, liq_fail, pit_excluded, universe_market


def _flow_fields(
    ticker: str,
    *,
    v2_row: dict[str, str] | None,
    signal_row: dict[str, str] | None,
) -> tuple[float, bool]:
    if v2_row:
        try:
            score = float(v2_row.get("flow_score") or 0)
        except ValueError:
            score = 0.0
        state = str(v2_row.get("flow_signal_state") or "").lower()
        blocker = state in {"distribution", "sell", "stale"}
        return score, score > 0 and not blocker
    if signal_row:
        try:
            score = float(signal_row.get("flow_score") or 0)
        except ValueError:
            score = 0.0
        blocker = str(signal_row.get("flow_blocker") or "").strip()
        return score, score > 0 and not blocker
    return 0.0, True


def _score_fail_reasons(
    row: dict[str, Any],
    *,
    thresholds: dict[str, float],
    min_pillars: int,
    floor: float,
    pit_pass: bool,
    liquidity_pass: bool,
    value_trap: bool,
    pit_gate_yellow: bool,
) -> tuple[list[str], str, int]:
    reasons: list[str] = []
    pillar_pass_flags: dict[str, bool] = {}

    scores = [float(row.get(PILLAR_SCORE_FIELDS[p], 0)) for p in PILLAR_KEYS]
    if scores and min(scores) < floor:
        reasons.append(f"min_pillar_floor_fail(min={min(scores):.1f}<{floor:.0f})")

    for pass_key, score_field, pillar_key, fail_tag in _PILLAR_DIAG:
        thr = float(thresholds.get(pillar_key, 55))
        passed = float(row.get(score_field, 0)) >= thr
        pillar_pass_flags[pass_key] = passed
        if not passed:
            reasons.append(fail_tag)

    actual = _pillars_pass(row, thresholds)
    if actual < min_pillars:
        reasons.append(f"min_pillars_pass(need={min_pillars},have={actual})")

    if row.get("eligible_action") == "NO_NEW" and float(row.get("penalty") or 0) >= 100:
        reasons.append("no_new_high_penalty")

    if not pit_pass:
        if pit_gate_yellow:
            reasons.append("pit_yellow_or_stale_fundamental")
        else:
            reasons.append("pit_fail")

    if not liquidity_pass:
        reasons.append("liquidity_fail")

    if value_trap:
        reasons.append("value_trap_flag")

    if pit_gate_yellow:
        reasons.append("pit_gate_yellow_aux")

    sector = str(row.get("sector") or "").strip().lower()
    if not sector or sector == "unknown":
        reasons.append("sector_unknown_aux")

    primary = reasons[0] if reasons else "eligible"
    if any(r.startswith("min_pillars_pass") for r in reasons):
        primary = next(r for r in reasons if r.startswith("min_pillars_pass"))
    elif any(r.startswith("min_pillar_floor_fail") for r in reasons):
        primary = next(r for r in reasons if r.startswith("min_pillar_floor_fail"))

    return reasons, primary, actual


def _recommended_fix(primary: str, row: dict[str, Any], thresholds: dict[str, float]) -> str:
    if primary == "eligible":
        return "shortlist_eligible — verify export path if missing from gpt_context"
    if primary.startswith("min_pillars_pass"):
        weak = []
        for _pk, score_field, pillar_key, _ft in _PILLAR_DIAG:
            thr = float(thresholds.get(pillar_key, 55))
            gap = thr - float(row.get(score_field, 0))
            if gap > 0:
                weak.append(f"{pillar_key}+{gap:.1f}")
        return f"pass more pillars — closest gaps: {', '.join(weak[:2])}" if weak else "review pillar thresholds"
    if primary.startswith("min_pillar_floor_fail"):
        return "raise weakest pillar above min_all_pillar_floor"
    if "q_pillar_fail" in primary or primary == "q_pillar_fail":
        gap = float(thresholds.get("quality", 60)) - float(row.get("quality_score", 0))
        return f"quality_score needs +{max(gap, 0):.1f} to pass Q pillar"
    if primary == "pit_yellow_or_stale_fundamental":
        return "refresh fundamentals / resolve PIT stale exclusions"
    if primary == "liquidity_fail":
        return "liquidity below universe filter — not shortlist eligible"
    if primary == "value_trap_flag":
        return "value_trap penalty — review valuation trap signals"
    return f"address {primary}"


def build_alpha_shortlist_diagnostics(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    scoring_cfg = load_alpha_scoring_config(data_dir / "alpha_scoring.yaml")
    thresholds, min_pillars, floor = _selection_thresholds(scoring_cfg)

    gpt = read_output_json(output_dir / "gpt_context.json") or {}
    final = read_output_json(output_dir / "final_execution_decision.json") or {}
    acceptance = read_output_json(output_dir / "acceptance_report.json") or {}

    run_id = str(
        final.get("run_id")
        or acceptance.get("run_id")
        or gpt.get("run_id")
        or ""
    )
    execution_scope = str(final.get("execution_scope") or acceptance.get("execution_scope") or "")
    alpha_trade_permission = str(acceptance.get("alpha_trade_permission") or "")
    actual_buy_allowed = int(final.get("actual_buy_allowed") or 0)
    system_permission_blocked = (
        execution_scope in {"ETF_ONLY", "NO_TRADE", "ETF_ONLY_ALPHA_REVIEW"}
        or alpha_trade_permission in {"BLOCK_NEW_BUY", "BLOCK_ALL"}
        or actual_buy_allowed <= 0
    )
    buy_permission_global = actual_buy_allowed > 0 and not system_permission_blocked

    pit_gate = str(gpt.get("alpha_data_gate") or "GREEN")
    pit_gate_yellow = pit_gate in {"YELLOW", "RED"}

    fundamentals_list = load_fundamentals(data_dir / "fundamentals.csv")
    fundamentals = {f.ticker: f for f in fundamentals_list}

    v2_by, signal_by, liq_fail, pit_excluded, universe_market = _build_aux_maps(output_dir, data_dir)

    shortlist_tickers = {
        _normalize_ticker(r.get("ticker", ""))
        for r in _read_csv_rows(output_dir / "alpha_shortlist.csv")
    }

    scored_rows = _read_csv_rows(output_dir / "alpha_scored_universe.csv")
    b_grade = [r for r in scored_rows if str(r.get("grade") or "") == "B"]
    top30 = scored_rows[:30]
    optional_extra = [r for r in top30 if str(r.get("grade") or "") != "B"]
    target_rows = b_grade + [r for r in optional_extra if _normalize_ticker(r.get("ticker", "")) not in {
        _normalize_ticker(x.get("ticker", "")) for x in b_grade
    }]

    diag_rows: list[dict[str, Any]] = []
    for row in target_rows:
        ticker = _normalize_ticker(row.get("ticker", ""))
        v2 = v2_by.get(ticker)
        sig = signal_by.get(ticker)

        liquidity_pass = ticker not in liq_fail
        if v2 is not None:
            liquidity_pass = str(v2.get("liquidity_flag", "true")).lower() != "false"

        pit_pass = _pit_pass_for_ticker(
            ticker,
            fundamentals=fundamentals,
            pit_excluded=pit_excluded,
            pit_gate_yellow=pit_gate_yellow,
        )

        value_trap = False
        if v2 is not None:
            value_trap = str(v2.get("value_trap_flag", "")).lower() == "true"
        else:
            value_trap = _value_trap_flag(row, scoring_cfg)

        flow_score, flow_pass = _flow_fields(ticker, v2_row=v2, signal_row=sig)

        pool_row = dict(row)
        for k, v in pool_row.items():
            try:
                pool_row[k] = float(v) if k.endswith("_score") or k in {"penalty", "total_score", "base_score"} else v
            except (TypeError, ValueError):
                pass

        shortlist_eligible = _in_shortlist_pool(
            pool_row,
            thresholds=thresholds,
            min_pillars=min_pillars,
            floor=floor,
        )
        if pool_row.get("eligible_action") == "NO_NEW" and float(pool_row.get("penalty") or 0) >= 100:
            shortlist_eligible = False

        score_reasons, primary_fail, actual_pillars = _score_fail_reasons(
            pool_row,
            thresholds=thresholds,
            min_pillars=min_pillars,
            floor=floor,
            pit_pass=pit_pass,
            liquidity_pass=liquidity_pass,
            value_trap=value_trap,
            pit_gate_yellow=pit_gate_yellow,
        )

        q_pass = float(pool_row.get("quality_score", 0)) >= float(thresholds.get("quality", 60))
        v_pass = float(pool_row.get("valuation_score", 0)) >= float(thresholds.get("valuation", 55))
        m_pass = float(pool_row.get("momentum_score", 0)) >= float(thresholds.get("momentum", 55))
        sr_pass = float(pool_row.get("shareholder_return_score", 0)) >= float(thresholds.get("shareholder_return", 55))

        sector = str(row.get("sector") or "")
        sector_known = bool(sector.strip()) and sector.strip().lower() != "unknown"

        review_only = (
            system_permission_blocked
            or str(v2.get("review_only", "")).lower() == "true" if v2 else system_permission_blocked
        )

        diag_rows.append({
            "run_id": run_id,
            "ticker": ticker,
            "name": str(row.get("name") or ""),
            "market": str(v2.get("market") if v2 else universe_market.get(ticker, "")),
            "sector": sector,
            "grade": str(row.get("grade") or ""),
            "total_score": float(row.get("total_score") or 0),
            "q_score": float(row.get("quality_score") or 0),
            "v_score": float(row.get("valuation_score") or 0),
            "m_score": float(row.get("momentum_score") or 0),
            "shareholder_return_score": float(row.get("shareholder_return_score") or 0),
            "flow_score": flow_score,
            "q_pillar_pass": q_pass,
            "v_pillar_pass": v_pass,
            "m_pillar_pass": m_pass,
            "shareholder_return_pass": sr_pass,
            "flow_pass": flow_pass,
            "pit_pass": pit_pass,
            "liquidity_pass": liquidity_pass,
            "value_trap_flag": value_trap,
            "sector_known": sector_known,
            "min_pillars_required": min_pillars,
            "actual_pillars_passed": actual_pillars,
            "shortlist_eligible": shortlist_eligible,
            "in_shortlist_csv": ticker in shortlist_tickers,
            "fail_reasons": ";".join(score_reasons) if score_reasons else "none",
            "primary_fail_reason": primary_fail,
            "recommended_fix": _recommended_fix(primary_fail, pool_row, thresholds),
            "buy_permission": buy_permission_global,
            "permission_blocked": system_permission_blocked,
            "review_only": review_only,
            "execution_scope": execution_scope,
            "actual_buy_allowed": actual_buy_allowed,
        })

    b_rows = [r for r in diag_rows if r["grade"] == "B"]
    eligible_count = sum(1 for r in b_rows if r["shortlist_eligible"])
    shortlisted_count = sum(1 for r in b_rows if r["in_shortlist_csv"])

    fail_counter: Counter[str] = Counter()
    pillar_dist: Counter[int] = Counter()
    for r in b_rows:
        pillar_dist[int(r["actual_pillars_passed"])] += 1
        for part in str(r["fail_reasons"]).split(";"):
            if part and part != "none":
                tag = part.split("(", 1)[0]
                fail_counter[tag] += 1

    top_fails = [k for k, _ in fail_counter.most_common(5)]
    most_common = fail_counter.most_common(1)[0][0] if fail_counter else "none"

    recommended_next: list[str] = []
    if eligible_count == 0 and len(b_rows) > 0:
        recommended_next.append(
            f"All {len(b_rows)} B-grade rows fail shortlist pool — top blockers: {', '.join(top_fails[:3])}"
        )
        if fail_counter.get("min_pillars_pass", 0) >= len(b_rows) * 0.5:
            recommended_next.append("Majority blocked by min_pillars_pass — review pillar score distribution (not gate thresholds)")
        if fail_counter.get("q_pillar_fail", 0) >= len(b_rows) * 0.5:
            recommended_next.append("Quality pillar is the most common miss — B-grade total_score does not imply Q>=60")
    elif eligible_count > 0 and shortlisted_count == 0:
        recommended_next.append("shortlist_eligible>0 but shortlist.csv empty — investigate export/pipeline path")
    else:
        recommended_next.append("Monitor shortlist pool; no dominant B-grade blocker pattern")

    summary = {
        "schema_version": "1.0",
        "run_id": run_id,
        "as_of": gpt.get("as_of") or final.get("as_of"),
        "b_grade_count": len(b_rows),
        "optional_top30_non_b_included": len(diag_rows) - len(b_rows),
        "diagnostics_row_count": len(diag_rows),
        "shortlist_eligible_count": eligible_count,
        "shortlisted_count": shortlisted_count,
        "fail_reason_counts": dict(fail_counter),
        "pillar_pass_distribution": {str(k): v for k, v in sorted(pillar_dist.items())},
        "min_pillars_required": min_pillars,
        "min_pillar_thresholds": thresholds,
        "min_all_pillar_floor": floor,
        "most_common_fail_reason": most_common,
        "top_fail_reasons": top_fails,
        "pit_yellow_count": sum(
            1 for r in b_rows if not r["pit_pass"] or pit_gate_yellow
        ),
        "pit_gate": pit_gate,
        "liquidity_fail_count": sum(1 for r in b_rows if not r["liquidity_pass"]),
        "value_trap_count": sum(1 for r in b_rows if r["value_trap_flag"]),
        "sector_unknown_count": sum(1 for r in b_rows if not r["sector_known"]),
        "permission_blocked_count": sum(1 for r in b_rows if r["permission_blocked"]),
        "shortlist_pool_empty": eligible_count == 0 and len(b_rows) > 0,
        "gpt_context_candidate_count": len(gpt.get("top_candidates") or []),
        "recommended_next_action": recommended_next,
        "diagnostics_csv_path": DIAGNOSTICS_CSV,
    }
    return {"rows": diag_rows, "summary": summary}


def write_alpha_shortlist_diagnostics(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    doc = build_alpha_shortlist_diagnostics(data_dir, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "alpha_shortlist_diagnostics.csv"
    rows = doc["rows"]
    if rows:
        fieldnames = list(rows[0].keys())
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
    else:
        csv_path.write_text("run_id,ticker\n", encoding="utf-8-sig")

    summary_path = output_dir / "alpha_shortlist_summary.json"
    summary_path.write_text(
        json.dumps(doc["summary"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return doc["summary"]


def format_alpha_shortlist_report_lines(summary: dict[str, Any]) -> list[str]:
    fixes = summary.get("recommended_next_action") or []
    return [
        "### Alpha Shortlist Diagnostic",
        f"- **B-grade count**: {summary.get('b_grade_count', 0)}",
        f"- **Shortlist eligible count**: {summary.get('shortlist_eligible_count', 0)} "
        f"(shortlisted {summary.get('shortlisted_count', 0)})",
        f"- **Main fail reasons**: {', '.join(summary.get('top_fail_reasons') or []) or '—'}",
        f"- **Most common missing pillar pattern**: `{summary.get('most_common_fail_reason', '—')}` "
        f"(min_pillars_required={summary.get('min_pillars_required', 3)})",
        f"- **Pillar pass distribution**: {summary.get('pillar_pass_distribution', {})}",
        f"- **Recommended fix**: {fixes[0] if fixes else '—'}",
        f"- **Detail**: `{SUMMARY_JSON}` · `{DIAGNOSTICS_CSV}`",
        "",
    ]


def shortlist_summary_for_no_action(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "shortlist_pool_empty": bool(summary.get("shortlist_pool_empty")),
        "b_grade_count": summary.get("b_grade_count", 0),
        "shortlist_eligible_count": summary.get("shortlist_eligible_count", 0),
        "top_fail_reasons": summary.get("top_fail_reasons") or [],
        "most_common_fail_reason": summary.get("most_common_fail_reason"),
        "alpha_shortlist_summary_path": SUMMARY_JSON,
    }
