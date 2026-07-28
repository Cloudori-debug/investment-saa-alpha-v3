"""Alpha candidate review lists for AI export bundle — no scoring or buy logic changes."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.field_normalize import normalize_sector, sanitize_json_value
from src.report.io_utils import read_output_json

CANDIDATE_ONLY_NOTE = "candidate only, not buy approval"
TOP_LIST_POLICY = "B universe + Top 30 only, full scored universe excluded from bundle"
MAX_B_UNIVERSE = 30
MAX_TOP30 = 30
MAX_REPLACE_ALTS = 5


def _blocked_tickers(data_dir: Path) -> set[str]:
    from src.alpha.target_portfolio_guard import get_blocked_reintroductions

    return set(get_blocked_reintroductions(data_dir).keys())


def _load_scored_universe(output_dir: Path) -> list[dict[str, Any]]:
    path = output_dir / "alpha_scored_universe.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    rows: list[dict[str, Any]] = []
    for rec in df.to_dict(orient="records"):
        row = dict(rec)
        for key in (
            "rank",
            "quality_score",
            "valuation_score",
            "momentum_score",
            "shareholder_return_score",
            "base_score",
            "penalty",
            "total_score",
        ):
            if key in row and row[key] not in ("", None):
                try:
                    row[key] = float(row[key])
                except (TypeError, ValueError):
                    pass
        if row.get("sector"):
            row["sector"] = normalize_sector(str(row["sector"]))
        rows.append(row)
    return rows


def _signal_map(output_dir: Path) -> dict[str, dict[str, Any]]:
    path = output_dir / "alpha_signal_board.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype={"ticker": str}, keep_default_na=False)
    return {str(r.get("ticker", "")): dict(r) for r in df.to_dict(orient="records")}


def _weight_map(output_dir: Path) -> dict[str, dict[str, float]]:
    path = output_dir / "current_vs_target.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype={"ticker": str}, keep_default_na=False)
    out: dict[str, dict[str, float]] = {}
    for rec in df.to_dict(orient="records"):
        ticker = str(rec.get("ticker", ""))
        try:
            out[ticker] = {
                "current_weight": float(rec.get("current_weight") or 0),
                "target_weight": float(rec.get("target_weight") or 0),
            }
        except (TypeError, ValueError):
            out[ticker] = {"current_weight": 0.0, "target_weight": 0.0}
    return out


def _price_map(data_dir: Path, as_of: str | None) -> dict[str, dict[str, float]]:
    from src.alpha.loaders import load_prices

    path = data_dir / "prices.csv"
    if not path.exists():
        return {}
    prices = load_prices(path, as_of=as_of or None)
    return {
        p.ticker: {
            "market_cap": float(p.market_cap or 0),
            "avg_trading_value_20d": float(p.trading_value_20d or 0),
        }
        for p in prices
    }


def _actual_buy_allowed(output_dir: Path) -> int:
    final = read_output_json(output_dir / "final_execution_decision.json") or {}
    from src.report.execution_metrics import count_executable_actions

    metrics = count_executable_actions(final)
    if final.get("target_guard_conflict_detected"):
        return 0
    return int(metrics.get("actual_buy_allowed_count") or 0)


def _buy_permission(actual_buy_allowed: int) -> bool:
    return actual_buy_allowed > 0


def _enrich_row(
    row: dict[str, Any],
    *,
    signal_map: dict[str, dict[str, Any]],
    weight_map: dict[str, dict[str, float]],
    price_map: dict[str, dict[str, float]],
    actual_buy_allowed: int,
    rank: int | None = None,
) -> dict[str, Any]:
    ticker = str(row.get("ticker", ""))
    sig = signal_map.get(ticker, {})
    weights = weight_map.get(ticker, {})
    px = price_map.get(ticker, {})
    flags: list[str] = []
    if sig.get("risk_blocker"):
        flags.append(str(sig["risk_blocker"]))
    if sig.get("missing_for_buy"):
        flags.append(str(sig["missing_for_buy"]))

    out: dict[str, Any] = {
        "rank": rank if rank is not None else row.get("rank"),
        "ticker": ticker,
        "name": row.get("name", sig.get("name", "")),
        "sector": normalize_sector(str(row.get("sector") or sig.get("sector") or "")),
        "grade": row.get("grade", sig.get("grade", "")),
        "total_score": row.get("total_score", sig.get("total_score")),
        "quality_score": row.get("quality_score"),
        "value_score": row.get("valuation_score"),
        "momentum_score": row.get("momentum_score"),
        "shareholder_return_score": row.get("shareholder_return_score"),
        "market_cap": px.get("market_cap"),
        "avg_trading_value_20d": px.get("avg_trading_value_20d"),
        "current_weight": weights.get("current_weight", sig.get("current_weight_pct")),
        "target_weight": weights.get("target_weight", sig.get("target_weight_pct")),
        "action_state": sig.get("action_state"),
        "eligible_action": row.get("eligible_action", sig.get("eligible_action")),
        "exclusion_flag": bool(str(row.get("grade", "")) == "Reject"),
        "risk_flag": "; ".join(flags) if flags else None,
        "buy_permission": _buy_permission(actual_buy_allowed),
        "note": CANDIDATE_ONLY_NOTE,
    }
    return sanitize_json_value(out)


def _filter_blocked(rows: list[dict[str, Any]], blocked: set[str]) -> list[dict[str, Any]]:
    return [r for r in rows if str(r.get("ticker", "")) not in blocked]


def build_alpha_grade_b_universe(
    scored: list[dict[str, Any]],
    *,
    signal_map: dict[str, dict[str, Any]],
    weight_map: dict[str, dict[str, float]],
    price_map: dict[str, dict[str, float]],
    actual_buy_allowed: int,
    blocked: set[str],
) -> list[dict[str, Any]]:
    b_rows = [
        r for r in scored
        if str(r.get("grade", "")).upper() == "B" and float(r.get("total_score") or 0) > 0
    ]
    b_rows = sorted(b_rows, key=lambda x: float(x.get("total_score") or 0), reverse=True)
    b_rows = _filter_blocked(b_rows, blocked)[:MAX_B_UNIVERSE]
    return [
        _enrich_row(
            row,
            signal_map=signal_map,
            weight_map=weight_map,
            price_map=price_map,
            actual_buy_allowed=actual_buy_allowed,
            rank=i,
        )
        for i, row in enumerate(b_rows, start=1)
    ]


def build_alpha_top30_scored(
    scored: list[dict[str, Any]],
    *,
    signal_map: dict[str, dict[str, Any]],
    weight_map: dict[str, dict[str, float]],
    price_map: dict[str, dict[str, float]],
    actual_buy_allowed: int,
    blocked: set[str],
) -> list[dict[str, Any]]:
    ranked = sorted(
        _filter_blocked(scored, blocked),
        key=lambda x: float(x.get("total_score") or 0),
        reverse=True,
    )[:MAX_TOP30]
    return [
        _enrich_row(
            row,
            signal_map=signal_map,
            weight_map=weight_map,
            price_map=price_map,
            actual_buy_allowed=actual_buy_allowed,
            rank=i,
        )
        for i, row in enumerate(ranked, start=1)
    ]


def _sector_match(a: str, b: str) -> bool:
    sa = normalize_sector(a).lower()
    sb = normalize_sector(b).lower()
    if not sa or not sb or sa in {"unknown", "—"} or sb in {"unknown", "—"}:
        return False
    return sa == sb or sa in sb or sb in sa


def build_alpha_replace_candidates(
    *,
    signal_map: dict[str, dict[str, Any]],
    b_universe: list[dict[str, Any]],
    actual_buy_allowed: int,
    blocked: set[str],
) -> list[dict[str, Any]]:
    replace_states = {"Replace-review", "Exclude"}
    b_pool = [
        r for r in b_universe
        if str(r.get("ticker", "")) not in blocked
    ]
    matches: list[dict[str, Any]] = []

    for ticker, sig in signal_map.items():
        if ticker in blocked:
            continue
        action_state = str(sig.get("action_state") or "")
        review_action = str(sig.get("review_action") or "")
        if action_state not in replace_states and review_action != "REPLACE_CANDIDATE":
            continue
        replace_reason = review_action or action_state or "replace_review"
        from_sector = normalize_sector(str(sig.get("sector") or ""))
        used: set[str] = {ticker}

        same_sector = [
            c for c in b_pool
            if c["ticker"] not in used and _sector_match(from_sector, str(c.get("sector") or ""))
        ]
        cross_sector = [
            c for c in b_pool
            if c["ticker"] not in used and not _sector_match(from_sector, str(c.get("sector") or ""))
        ]
        fallback = [c for c in b_pool if c["ticker"] not in used]

        picked: list[tuple[dict[str, Any], str]] = []
        for candidate, match_type in (
            [(c, "same_sector") for c in same_sector]
            + [(c, "cross_sector") for c in cross_sector]
            + [(c, "fallback") for c in fallback]
        ):
            if len(picked) >= MAX_REPLACE_ALTS:
                break
            if candidate["ticker"] in used:
                continue
            used.add(candidate["ticker"])
            picked.append((candidate, match_type))

        for candidate, match_type in picked:
            matches.append(sanitize_json_value({
                "replace_from_ticker": ticker,
                "replace_from_name": sig.get("name", ""),
                "replace_reason": replace_reason,
                "candidate_ticker": candidate.get("ticker"),
                "candidate_name": candidate.get("name"),
                "candidate_sector": candidate.get("sector"),
                "candidate_grade": candidate.get("grade"),
                "candidate_score": candidate.get("total_score"),
                "match_type": match_type,
                "buy_permission": _buy_permission(actual_buy_allowed),
                "note": CANDIDATE_ONLY_NOTE,
            }))
    return matches


def build_alpha_screening_meta(
    data_dir: Path,
    output_dir: Path,
    *,
    gpt_context: dict[str, Any] | None = None,
    b_count: int,
    top30_count: int,
    replace_count: int,
) -> dict[str, Any]:
    gpt = gpt_context or read_output_json(output_dir / "gpt_context.json") or {}
    shortlist = gpt.get("shortlist_meta") or {}
    score_dist = shortlist.get("score_distribution") or {}
    grade_counts = score_dist.get("grade_counts") or {}

    universe_count = 945
    uni_path = data_dir / "universe.csv"
    if uni_path.exists():
        universe_count = len(pd.read_csv(uni_path, dtype=str))

    actual_buy = _actual_buy_allowed(output_dir)
    buy_status = "ALLOWED" if actual_buy > 0 else "BLOCKED"

    kr_alpha_readiness = "NOT_READY"
    saa = read_output_json(output_dir / "saa_restart_readiness_report.json") or {}
    kr_alpha_readiness = (
        saa.get("kr_alpha_restart_readiness")
        or saa.get("saa_restart_readiness")
        or "NOT_READY"
    )

    green = read_output_json(output_dir / "acceptance_report.json") or {}
    gl = green.get("green_layers") or {}

    return sanitize_json_value({
        "universe_count": universe_count,
        "scored_count": shortlist.get("scored_count") or score_dist.get("scored_count"),
        "grade_distribution": grade_counts,
        "excluded_summary": gpt.get("excluded_summary") or {},
        "top_list_policy": TOP_LIST_POLICY,
        "alpha_grade_b_universe_count": b_count,
        "alpha_top30_scored_count": top30_count,
        "alpha_replace_candidates_count": replace_count,
        "actual_buy_allowed": actual_buy,
        "buy_permission_status": buy_status,
        "kr_alpha_restart_readiness": kr_alpha_readiness,
        "technical_status": gl.get("technical_status"),
        "operational_status": gl.get("operational_status"),
        "market_status": gl.get("market_status"),
        "note": CANDIDATE_ONLY_NOTE,
    })


def build_alpha_export_sections(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Build alpha review lists for ai_export_bundle."""
    gpt = read_output_json(output_dir / "gpt_context.json") or {}
    as_of = str(gpt.get("as_of") or "")[:10]
    blocked = _blocked_tickers(data_dir)
    scored = _load_scored_universe(output_dir)
    signal_map = _signal_map(output_dir)
    weight_map = _weight_map(output_dir)
    price_map = _price_map(data_dir, as_of)
    actual_buy = _actual_buy_allowed(output_dir)

    b_universe = build_alpha_grade_b_universe(
        scored,
        signal_map=signal_map,
        weight_map=weight_map,
        price_map=price_map,
        actual_buy_allowed=actual_buy,
        blocked=blocked,
    )
    top30 = build_alpha_top30_scored(
        scored,
        signal_map=signal_map,
        weight_map=weight_map,
        price_map=price_map,
        actual_buy_allowed=actual_buy,
        blocked=blocked,
    )
    replace_rows = build_alpha_replace_candidates(
        signal_map=signal_map,
        b_universe=b_universe,
        actual_buy_allowed=actual_buy,
        blocked=blocked,
    )
    meta = build_alpha_screening_meta(
        data_dir,
        output_dir,
        gpt_context=gpt,
        b_count=len(b_universe),
        top30_count=len(top30),
        replace_count=len(replace_rows),
    )

    return {
        "alpha_screening_meta": meta,
        "alpha_grade_b_universe": b_universe,
        "alpha_top30_scored": top30,
        "alpha_replace_candidates": replace_rows,
    }


def build_alpha_screening_summary_lines(output_dir: Path) -> list[str]:
    """Daily report alpha screening summary — review only, not buy approval."""
    sections = build_alpha_export_sections(output_dir.parent / "data", output_dir)
    meta = sections.get("alpha_screening_meta") or {}
    scored = meta.get("scored_count", "—")
    b_count = meta.get("alpha_grade_b_universe_count", "—")
    actual_buy = meta.get("actual_buy_allowed", 0)
    buy_status = meta.get("buy_permission_status", "BLOCKED")
    kr_ready = meta.get("kr_alpha_restart_readiness", "NOT_READY")

    lines = [
        "",
        "### Alpha screener (AI bundle review lists)",
        f"- Alpha screener scored **{scored}** names; **B-grade universe {b_count}** names included in AI bundle.",
        f"- Top 30 is for review only. **Actual Buy Allowed={actual_buy}** overrides all alpha candidates.",
        f"- **buy_permission_status**: `{buy_status}` · **kr_alpha_restart_readiness**: `{kr_ready}`",
        f"- {CANDIDATE_ONLY_NOTE}. Full scored universe is **not** included in export bundle.",
    ]
    if actual_buy <= 0:
        lines.append("- No alpha new buy while Actual Buy Allowed=0 or kr_alpha hard stop / NO_TRADE applies.")
    return lines
