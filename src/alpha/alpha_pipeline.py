from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.alpha.alpha_report import (
    write_alpha_candidates,
    write_alpha_report,
    write_excluded,
    write_holdings_review,
)
from src.alpha.data_gate import (
    apply_data_gate,
    adjust_gate_for_sector_coverage,
    evaluate_candidate_sector_data_gate,
)
from src.alpha.price_coverage import (
    adjust_gate_for_missing_prices,
    apply_price_coverage_downgrade,
    tickers_missing_prices,
)
from src.alpha.factor_scoring import score_factors
from src.alpha.gpt_context import build_gpt_context, write_gpt_context
from src.alpha.holdings_review import review_holdings
from src.alpha.loaders import (
    load_alpha_scoring_config,
    load_fundamentals,
    load_prices,
    load_universe,
    load_universe_filter_config,
)
from src.alpha.penalty_engine import apply_penalties, assign_grades
from src.alpha.portfolio_selector import (
    SelectionResult,
    build_pillar_leaderboard,
    build_shortlist_and_proposal,
    write_pillar_leaderboard_csv,
    write_proposal_csv,
    write_shortlist_csv,
)
from src.alpha.schemas import AlphaCandidate, AlphaPipelineResult, make_excluded
from src.alpha.universe_filter import filter_universe
from src.data_loader import load_market_indicators, load_positions, load_target_portfolio
from src.models import PositionRow, TargetRow
from src.alpha.sector_mapping import (
    compute_sector_coverage_for_tickers,
    merge_coverage_metrics,
    sector_risk_cap_status,
)


def _score_distribution(graded: list[dict[str, Any]]) -> dict[str, Any]:
    """Read-only score stats — no scoring logic change."""
    if not graded:
        return {"scored_count": 0, "grade_counts": {}, "total_score": {}}
    scores = [float(g.get("total_score") or 0) for g in graded]
    scores_sorted = sorted(scores)
    n = len(scores_sorted)
    mid = scores_sorted[n // 2]
    grade_counts: dict[str, int] = {}
    for g in graded:
        gr = str(g.get("grade") or "—")
        grade_counts[gr] = grade_counts.get(gr, 0) + 1
    return {
        "scored_count": n,
        "grade_counts": grade_counts,
        "total_score": {
            "min": round(min(scores), 1),
            "max": round(max(scores), 1),
            "median": round(mid, 1),
        },
    }


def _build_constraint_warnings(
    data_dir: Path,
    output_dir: Path,
    targets: list[TargetRow] | None,
    candidates: list[AlphaCandidate],
    holdings: list,
) -> tuple[list[str], dict]:
    from src.alpha.constraints import check_kr_alpha_constraints

    if targets is None:
        targets = load_target_portfolio(data_dir / "target_portfolio.csv")
    cand_dicts = [c.model_dump() for c in candidates]
    hold_dicts = [h.model_dump() for h in holdings]
    warnings, meta = check_kr_alpha_constraints(
        targets,
        output_dir,
        candidates=cand_dicts,
        holdings_review=hold_dicts,
    )
    return warnings, meta


@dataclass
class AlphaPipelineOutput:
    result: AlphaPipelineResult
    gpt_context: dict[str, Any]


def _resolve_as_of(data_dir: Path, as_of: str | None) -> str:
    if as_of:
        return as_of
    market_path = data_dir / "market_indicators.csv"
    if market_path.exists():
        market = load_market_indicators(market_path)
        if market.date:
            return market.date
    prices = load_prices(data_dir / "prices.csv")
    if prices:
        return prices[0].date
    return "2026-01-01"


def run_alpha_pipeline(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
    positions: list[PositionRow] | None = None,
    targets: list[TargetRow] | None = None,
    regime: dict[str, Any] | None = None,
    asset_group_targets: dict[str, Any] | None = None,
    write_outputs: bool = True,
    run_mode_config: object | None = None,
) -> AlphaPipelineOutput:
    from src.hakedaka_gate import (
        apply_hakedaka_alpha_bonus,
        build_liquidity_pass_map,
        hakedaka_alpha_limitations,
        merge_hakedaka_into_universe,
    )

    as_of_date = _resolve_as_of(data_dir, as_of)
    filter_cfg = load_universe_filter_config(data_dir / "universe_filter.yaml")
    scoring_cfg = load_alpha_scoring_config(data_dir / "alpha_scoring.yaml")

    from src.data_refresh.prices_refresh import ensure_tier_a_prices

    import os

    from src.alpha_v2_gate import evaluate_standard_price_fetch

    skip_tier_prices = False
    if run_mode_config is not None:
        skip_tier_prices, _ = evaluate_standard_price_fetch(
            data_dir,
            output_dir,
            as_of=as_of_date,
            run_mode=run_mode_config.run_mode,
        )
    fetch_tier_a = os.environ.get("PYTEST_CURRENT_TEST") is None and not skip_tier_prices

    tier_notes: list[str] = []
    if fetch_tier_a:
        tier_a = ensure_tier_a_prices(
            data_dir, as_of_date, output_dir=output_dir, top_n=50, fetch_missing=True,
        )
    else:
        tier_a = ensure_tier_a_prices(
            data_dir, as_of_date, output_dir=output_dir, top_n=50, fetch_missing=False,
        )
    if tier_a.added:
        preview = ", ".join(tier_a.added[:12])
        suffix = " …" if len(tier_a.added) > 12 else ""
        tier_notes.append(f"Tier A 시세 추가 ({len(tier_a.added)}): {preview}{suffix}")
    if tier_a.failed:
        preview = ", ".join(tier_a.failed[:12])
        suffix = " …" if len(tier_a.failed) > 12 else ""
        tier_notes.append(f"Tier A 시세 미확보 ({len(tier_a.failed)}): {preview}{suffix}")
    tier_notes.extend(tier_a.warnings)

    universe = load_universe(data_dir / "universe.csv")
    universe = merge_hakedaka_into_universe(universe, data_dir)
    fundamentals_raw = load_fundamentals(data_dir / "fundamentals.csv")
    prices_list = load_prices(data_dir / "prices.csv", as_of=as_of_date)
    prices_by_ticker = {p.ticker: p for p in prices_list}

    all_excluded = []

    passed_universe, excluded_universe = filter_universe(
        universe, prices_by_ticker, filter_cfg, as_of_date
    )
    liquidity_pass_map = build_liquidity_pass_map(passed_universe, excluded_universe, data_dir)
    all_excluded.extend(excluded_universe)

    usable_fund, excluded_gate, gate_status, limitations = apply_data_gate(
        fundamentals_raw, filter_cfg, as_of_date
    )
    all_excluded.extend(excluded_gate)

    prefetch = ensure_tier_a_prices(
        data_dir,
        as_of_date,
        output_dir=output_dir,
        top_n=50,
        prefetch_fundamental=True,
        usable_fund=usable_fund,
        prices_by_ticker=prices_by_ticker,
        fetch_missing=fetch_tier_a,
    )
    if prefetch.added:
        preview = ", ".join(prefetch.added[:12])
        suffix = " …" if len(prefetch.added) > 12 else ""
        tier_notes.append(f"Tier C prefetch 시세 ({len(prefetch.added)}): {preview}{suffix}")
        prices_list = load_prices(data_dir / "prices.csv", as_of=as_of_date)
        prices_by_ticker = {p.ticker: p for p in prices_list}
        passed_universe, excluded_universe = filter_universe(
            universe, prices_by_ticker, filter_cfg, as_of_date
        )
        liquidity_pass_map = build_liquidity_pass_map(passed_universe, excluded_universe, data_dir)
        all_excluded = list(excluded_universe) + list(excluded_gate)
    tier_notes.extend(prefetch.warnings)

    passed_tickers = {u.ticker for u in passed_universe}
    excluded_tickers = {e.ticker for e in all_excluded}
    scored_universe = [u for u in passed_universe if u.ticker in usable_fund]

    for u in passed_universe:
        if u.ticker in usable_fund or u.ticker in excluded_tickers:
            continue
        all_excluded.append(
            make_excluded(u.ticker, u.name, "재무 데이터 없음", "missing_fundamentals")
        )

    if not scored_universe:
        all_limitations = list(limitations) + tier_notes
        result = AlphaPipelineResult(
            as_of=as_of_date,
            candidates=[],
            excluded=all_excluded,
            holdings_review=[],
            data_gate=gate_status,
            limitations=all_limitations,
        )
        gpt = build_gpt_context(
            result, regime, asset_group_targets, kr_alpha_meta={}, constraint_warnings=[]
        )
        if write_outputs:
            _write_all(output_dir, result, gpt, None)
        return AlphaPipelineOutput(result=result, gpt_context=gpt)

    raw_scored = score_factors(scored_universe, usable_fund, prices_by_ticker, scoring_cfg)
    universe_map = {u.ticker: u for u in scored_universe}
    penalized = apply_penalties(raw_scored, universe_map, usable_fund, prices_by_ticker, scoring_cfg)
    graded = assign_grades(penalized, scoring_cfg)
    graded, price_warnings = apply_price_coverage_downgrade(graded, prices_by_ticker)
    graded = apply_hakedaka_alpha_bonus(
        graded, data_dir, liquidity_pass_by_ticker=liquidity_pass_map,
    )

    if positions is None:
        positions = load_positions(data_dir / "positions.csv")
    if targets is None:
        targets = load_target_portfolio(data_dir / "target_portfolio.csv")

    incumbent = {
        p.ticker
        for p in positions
        if p.asset_group == "kr_alpha" and p.ticker.upper() != "CASH"
    }
    from src.alpha.target_bridge import load_kr_alpha_budget

    kr_budget = load_kr_alpha_budget(output_dir) if output_dir.exists() else None
    from src.hakedaka_gate import load_integration_config

    integration_cfg = load_integration_config(data_dir)
    selection = build_shortlist_and_proposal(
        graded,
        scoring_cfg,
        incumbent_tickers=incumbent,
        kr_alpha_budget=kr_budget,
        integration_cfg=integration_cfg,
    )
    pillar_board = build_pillar_leaderboard(graded, scoring_cfg, selection, top_n=10)

    graded_map = {g["ticker"]: g for g in graded}
    candidates = [
        AlphaCandidate.model_validate({**graded_map[s.ticker], "rank": s.pool_rank})
        for s in selection.shortlist
        if s.ticker in graded_map
    ]
    candidates_by_ticker = {
        t: AlphaCandidate.model_validate(row) for t, row in graded_map.items()
    }

    target_kr = {
        t.ticker
        for t in (targets or [])
        if t.asset_group == "kr_alpha" and t.target_weight > 0
    }
    missing_price_targets = sorted(tickers_missing_prices(target_kr, prices_by_ticker))

    holdings = review_holdings(
        positions,
        targets,
        candidates_by_ticker,
        scoring_cfg,
        missing_price_tickers=missing_price_targets,
    )

    constraint_warnings, kr_meta = _build_constraint_warnings(
        data_dir, output_dir, targets, candidates, holdings
    )
    gate_status, sector_gate_notes = adjust_gate_for_sector_coverage(gate_status, kr_meta)
    if sector_gate_notes:
        limitations = list(limitations) + sector_gate_notes

    cand_rows = [c.model_dump() for c in candidates]
    shortlist_cov = compute_sector_coverage_for_tickers(cand_rows, data_dir)
    top10_graded = sorted(graded, key=lambda x: float(x.get("total_score") or 0), reverse=True)[:10]
    top10_cov = compute_sector_coverage_for_tickers(top10_graded, data_dir)
    holdings_items = [{"ticker": h.ticker, "name": h.name, "sector": ""} for h in holdings]
    holdings_cov = compute_sector_coverage_for_tickers(holdings_items, data_dir)
    sector_coverage = merge_coverage_metrics(shortlist_cov, top10_cov, holdings_cov)
    sector_coverage["sector_risk_cap_status"] = sector_risk_cap_status(sector_coverage)

    from src.alpha.top10_sector_candidate import write_top10_sector_candidate_artifacts

    top10_candidate_meta: dict[str, Any] = {}
    if write_outputs:
        top10_candidate_meta = write_top10_sector_candidate_artifacts(
            top10_graded,
            data_dir,
            output_dir,
            as_of=as_of_date,
            sector_coverage_before=top10_cov,
        )
    kr_meta["top10_sector_candidate"] = top10_candidate_meta
    alpha_sector_data_gate, candidate_sector_notes = evaluate_candidate_sector_data_gate(
        float(sector_coverage.get("shortlist_unknown_rate") or 0),
        float(sector_coverage.get("top10_unknown_rate") or 0),
    )
    if candidate_sector_notes:
        limitations = list(limitations) + candidate_sector_notes
    kr_meta["sector_coverage"] = sector_coverage
    kr_meta["alpha_sector_data_gate"] = alpha_sector_data_gate
    score_dist = _score_distribution(graded)
    gate_status, price_gate_notes = adjust_gate_for_missing_prices(
        gate_status, missing_target_tickers=missing_price_targets,
    )
    if price_gate_notes:
        limitations = list(limitations) + price_gate_notes
    if price_warnings:
        limitations = list(limitations) + price_warnings
    if constraint_warnings:
        limitations = list(limitations) + constraint_warnings
    if tier_notes:
        limitations = list(limitations) + tier_notes
    if selection.warnings:
        limitations = list(limitations) + selection.warnings

    hk_in_shortlist = sum(1 for s in selection.shortlist if s.in_hakedaka)
    hk_priority = sum(1 for s in selection.shortlist if getattr(s, "hakedaka_priority", False))
    hk_notes = hakedaka_alpha_limitations(data_dir, graded, overlap_count=hk_in_shortlist)
    if hk_notes:
        limitations = list(limitations) + hk_notes

    if write_outputs:
        from src.hakedaka_gate import write_hakedaka_overlap_diagnostics

        write_hakedaka_overlap_diagnostics(
            data_dir,
            output_dir,
            universe=universe,
            excluded=all_excluded,
            graded=graded,
            shortlist_tickers={s.ticker for s in selection.shortlist},
            proposal_tickers={p.ticker for p in selection.proposal},
            prices_by_ticker=prices_by_ticker,
            filter_cfg=filter_cfg,
            as_of=as_of_date,
            usable_fund_tickers=set(usable_fund),
            scoring_cfg=scoring_cfg,
        )

    result = AlphaPipelineResult(
        as_of=as_of_date,
        candidates=candidates,
        excluded=all_excluded,
        holdings_review=holdings,
        data_gate=gate_status,
        limitations=limitations,
    )
    gpt = build_gpt_context(
        result,
        regime,
        asset_group_targets,
        kr_alpha_meta=kr_meta,
        constraint_warnings=constraint_warnings,
        portfolio_proposal=[p.__dict__ for p in selection.proposal],
        shortlist_meta={
            "pool_size": len(selection.shortlist),
            "proposal_size": len(selection.proposal),
            "scored_count": len(graded),
            "hakedaka_in_shortlist": hk_in_shortlist,
            "hakedaka_priority_in_shortlist": hk_priority,
            "score_distribution": score_dist,
            **sector_coverage,
            "alpha_sector_data_gate": alpha_sector_data_gate,
            "qvm_hakedaka_overlap_count": hk_in_shortlist,
        },
    )

    if write_outputs:
        from src.alpha.flow_refresh import run_flow_refresh
        from src.alpha.investor_flows import write_investor_flows_template
        from src.alpha.sector_mapping import write_sector_mapping_template
        from src.alpha.top10_sector_candidate import format_top10_sector_candidate_report_lines
        import csv

        top10_path = output_dir / "alpha_top10_scored.csv"
        with top10_path.open("w", encoding="utf-8", newline="") as f:
            fieldnames = ["rank", "ticker", "name", "total_score", "grade", "sector"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for i, g in enumerate(top10_graded, start=1):
                writer.writerow({
                    "rank": i,
                    "ticker": g.get("ticker", ""),
                    "name": g.get("name", ""),
                    "total_score": g.get("total_score", ""),
                    "grade": g.get("grade", ""),
                    "sector": g.get("sector", ""),
                })

        from src.alpha.alpha_report import write_alpha_scored_universe

        write_alpha_scored_universe(output_dir / "alpha_scored_universe.csv", graded)

        map_tickers = [{"ticker": g["ticker"], "name": g["name"], "sector": g.get("sector", "")} for g in graded]
        write_sector_mapping_template(data_dir, map_tickers)

        from src.alpha.flow_refresh import resolve_flow_target_tickers

        flow_tickers = resolve_flow_target_tickers(
            holdings=holdings,
            candidates=candidates,
            data_dir=data_dir,
            output_dir=output_dir,
        )
        write_investor_flows_template(data_dir, flow_tickers, as_of=as_of_date)
        flow_mode = "cache_first"
        if run_mode_config is not None:
            flow_mode = str(getattr(run_mode_config, "flow_refresh_mode", flow_mode))
        from src.runtime.run_mode_contract import investor_flows_covers_as_of

        skip_flow = flow_mode == "cache_first" and investor_flows_covers_as_of(data_dir, as_of_date)
        if skip_flow:
            flow_refresh_meta = {
                "skipped": True,
                "reason": "investor_flows_unchanged",
                "mode": flow_mode,
                "as_of": as_of_date,
            }
        else:
            flow_refresh_meta = run_flow_refresh(
                data_dir,
                output_dir,
                as_of=as_of_date,
                tickers=flow_tickers,
                use_cache=flow_mode != "full",
            ).to_meta()
        kr_meta["flow_refresh"] = flow_refresh_meta
        gpt.setdefault("kr_alpha_meta", {})["flow_refresh"] = flow_refresh_meta

        signal_rows = _build_signal_board_rows(
            candidates=candidates,
            holdings=holdings,
            graded_map=graded_map,
            usable_fund=usable_fund,
            prices_by_ticker=prices_by_ticker,
            data_dir=data_dir,
            sector_coverage=sector_coverage,
            data_gate=gate_status,
            alpha_sector_data_gate=alpha_sector_data_gate,
        )
        from src.alpha.alpha_signal_board import summarize_signal_board

        signal_summary = summarize_signal_board(signal_rows)
        kr_meta["alpha_signal_summary"] = signal_summary

        _write_all(
            output_dir,
            result,
            gpt,
            selection,
            pillar_board,
            signal_rows=signal_rows,
            signal_summary=signal_summary,
            alpha_sector_data_gate=alpha_sector_data_gate,
            top10_candidate_meta=top10_candidate_meta,
            flow_refresh_meta=flow_refresh_meta,
        )

    return AlphaPipelineOutput(result=result, gpt_context=gpt)


def _build_signal_board_rows(
    *,
    candidates: list,
    holdings: list,
    graded_map: dict,
    usable_fund: dict,
    prices_by_ticker: dict,
    data_dir: Path,
    sector_coverage: dict,
    data_gate: str,
    alpha_sector_data_gate: str,
    alpha_auto_buy_permission: str = "BLOCKED",
) -> list:
    from src.alpha.alpha_signal_board import SignalBoardRow, build_alpha_signal_board

    return build_alpha_signal_board(
        candidates=candidates,
        holdings_review=holdings,
        graded_by_ticker=graded_map,
        fundamentals=usable_fund,
        prices=prices_by_ticker,
        data_dir=data_dir,
        sector_coverage=sector_coverage,
        alpha_auto_buy_permission=alpha_auto_buy_permission,
        data_gate=data_gate,
        alpha_sector_data_gate=alpha_sector_data_gate,
    )


def refresh_alpha_signal_board_from_outputs(
    data_dir: Path,
    output_dir: Path,
    *,
    alpha_auto_buy_permission: str = "BLOCKED",
) -> list:
    """Re-build signal board after execution permissions are known."""
    import json

    import pandas as pd

    from src.alpha.alpha_signal_board import (
        build_alpha_signal_board,
        summarize_signal_board,
        write_alpha_signal_board,
    )
    from src.alpha.schemas import AlphaCandidate, HoldingReview

    cand_path = output_dir / "alpha_candidates.csv"
    hold_path = output_dir / "holdings_review.csv"
    if not cand_path.exists():
        return []

    cand_df = pd.read_csv(cand_path, dtype=str)
    candidates = [AlphaCandidate.model_validate(r) for r in cand_df.to_dict("records")]

    holdings = []
    if hold_path.exists():
        hold_df = pd.read_csv(hold_path, dtype=str)
        for r in hold_df.to_dict("records"):
            holdings.append(HoldingReview.model_validate({
                **r,
                "current_weight": float(r.get("current_weight") or 0),
                "target_weight": float(r.get("target_weight") or 0),
                "alpha_score": float(r.get("alpha_score") or 0),
            }))

    graded_map = {c.ticker: c.model_dump() for c in candidates}
    gpt = {}
    gpt_path = output_dir / "gpt_context.json"
    if gpt_path.exists():
        gpt = json.loads(gpt_path.read_text(encoding="utf-8"))

    sector_coverage = (gpt.get("shortlist_meta") or {}) or (gpt.get("kr_alpha_meta") or {}).get("sector_coverage", {})
    alpha_sector_data_gate = (gpt.get("shortlist_meta") or {}).get("alpha_sector_data_gate", "GREEN")

    from src.alpha.loaders import load_fundamentals, load_prices

    as_of = str(gpt.get("as_of") or "")[:10]
    fundamentals = {f.ticker: f for f in load_fundamentals(data_dir / "fundamentals.csv")}
    prices = {p.ticker: p for p in load_prices(data_dir / "prices.csv", as_of=as_of or None)}

    rows = build_alpha_signal_board(
        candidates=candidates,
        holdings_review=holdings,
        graded_by_ticker=graded_map,
        fundamentals=fundamentals,
        prices=prices,
        data_dir=data_dir,
        sector_coverage=sector_coverage,
        alpha_auto_buy_permission=alpha_auto_buy_permission,
        data_gate=str(gpt.get("alpha_data_gate") or "GREEN"),
        alpha_sector_data_gate=str(alpha_sector_data_gate),
    )
    write_alpha_signal_board(output_dir / "alpha_signal_board.csv", rows)
    summary = summarize_signal_board(rows)
    if gpt_path.exists():
        gpt.setdefault("kr_alpha_meta", {})["alpha_signal_summary"] = summary
        gpt_path.write_text(json.dumps(gpt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rows


def _write_all(
    output_dir: Path,
    result: AlphaPipelineResult,
    gpt: dict[str, Any],
    selection: SelectionResult | None = None,
    pillar_board: list | None = None,
    *,
    signal_rows: list | None = None,
    signal_summary: dict[str, Any] | None = None,
    alpha_sector_data_gate: str | None = None,
    top10_candidate_meta: dict[str, Any] | None = None,
    flow_refresh_meta: dict[str, Any] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_alpha_candidates(output_dir / "alpha_candidates.csv", result.candidates)
    if selection is not None:
        write_shortlist_csv(output_dir / "alpha_shortlist.csv", selection.shortlist)
        write_proposal_csv(output_dir / "alpha_portfolio_proposal.csv", selection.proposal)
    if pillar_board is not None:
        write_pillar_leaderboard_csv(output_dir / "alpha_pillar_leaderboard.csv", pillar_board)
    write_excluded(output_dir / "excluded.csv", result.excluded)
    write_holdings_review(output_dir / "holdings_review.csv", result.holdings_review)
    if signal_rows is not None:
        from src.alpha.alpha_signal_board import write_alpha_signal_board

        write_alpha_signal_board(output_dir / "alpha_signal_board.csv", signal_rows)
        write_alpha_report(
            output_dir / "alpha_report.md",
            result,
            selection=selection,
            signal_rows=signal_rows,
            signal_summary=signal_summary,
            alpha_sector_data_gate=alpha_sector_data_gate,
            top10_candidate_meta=top10_candidate_meta,
            flow_refresh_meta=flow_refresh_meta,
        )
    else:
        write_alpha_report(
            output_dir / "alpha_report.md",
            result,
            selection=selection,
            alpha_sector_data_gate=alpha_sector_data_gate,
            top10_candidate_meta=top10_candidate_meta,
            flow_refresh_meta=flow_refresh_meta,
        )
    write_gpt_context(output_dir / "gpt_context.json", gpt)


def load_regime_from_output(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "compass_regime.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_asset_targets_from_output(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "target_asset_allocation.csv"
    if not path.exists():
        return {}
    import pandas as pd

    df = pd.read_csv(path)
    return {str(r["asset_group"]): float(r["final_target"]) for _, r in df.iterrows() if "asset_group" in r}
