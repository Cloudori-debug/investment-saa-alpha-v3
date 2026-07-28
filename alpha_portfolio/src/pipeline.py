from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from src.config_loader import load_yaml
from src.exit_engine import run_exit_review
from src.loaders import (
    load_all_positions,
    load_fundamentals,
    load_park_state,
    load_positions,
    load_price_snapshot,
    load_shareholder,
    load_stock_flags,
    load_target_portfolio,
)
from src.paths import get_paths
from src.screener import build_merged_frame, run_screener
from src.target_matrix import build_target_draft


@dataclass
class PipelineResult:
    scores: pd.DataFrame
    candidates: pd.DataFrame
    exit_review: pd.DataFrame
    screening_universe: pd.DataFrame
    target_draft: pd.DataFrame | None = None
    target_changes: pd.DataFrame | None = None
    replace_pairs: pd.DataFrame | None = None
    matrix_warnings: list[str] | None = None
    tier_allocation: dict | None = None


def _ensure_dirs(paths: dict[str, Path]) -> None:
    for key in ("raw", "input", "output", "state"):
        paths[key].mkdir(parents=True, exist_ok=True)


def _load_blocked_reintroduction_tickers(project_root: Path) -> set[str]:
    """Read multi_asset guard registry — blocked tickers must not re-enter target_draft."""
    guard_path = project_root.parent / "data" / "target_portfolio_write_guard.json"
    if not guard_path.exists():
        return set()
    try:
        import json

        payload = json.loads(guard_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    blocked = payload.get("blocked_reintroductions") or {}
    return {str(t).zfill(6) for t in blocked.keys()}


def _attach_flags(merged: pd.DataFrame, flags: pd.DataFrame) -> pd.DataFrame:
    if flags.empty:
        merged = merged.copy()
        merged["governance_red"] = False
        return merged
    out = merged.merge(flags[["ticker", "governance_red"]], on="ticker", how="left")
    out["governance_red"] = out["governance_red"].fillna(False)
    return out


def _attach_park(merged: pd.DataFrame, park: pd.DataFrame) -> pd.DataFrame:
    if park.empty:
        return merged
    return merged.merge(
        park[["ticker", "park_start_date", "park_reason"]],
        on="ticker",
        how="left",
    )


def run_pipeline(
    root: Path | None = None,
    *,
    kr_alpha_weight: float | None = None,
    as_of: date | None = None,
    collect_first: bool = False,
    collect_scope: str | None = None,
) -> PipelineResult:
    paths = get_paths(root)
    _ensure_dirs(paths)

    if collect_first:
        from src.collect.pykrx_collector import run_collect

        as_of_str = as_of.isoformat() if as_of else None
        run_collect(root, as_of=as_of_str, scope=collect_scope)  # type: ignore[arg-type]

    gate_cfg = load_yaml(paths["config"] / "universe_gate.yaml").get("gate", {})
    scoring_cfg = load_yaml(paths["config"] / "alpha_scoring.yaml")
    exit_cfg = load_yaml(paths["config"] / "alpha_exit_rules.yaml")

    positions_path = paths["raw"] / "positions.csv"
    if not positions_path.exists():
        alt = Path(root or paths["project"]).parent / "data" / "positions.csv"
        if alt.exists():
            positions_path = alt

    positions = load_positions(positions_path)
    all_positions = load_all_positions(positions_path)
    held_tickers = set(positions["ticker"].tolist()) if not positions.empty else set()

    fundamentals = load_fundamentals(paths["raw"] / "fundamentals.csv")
    price_snapshot = load_price_snapshot(paths["raw"] / "price_snapshot.csv")
    shareholder = load_shareholder(paths["raw"] / "shareholder.csv")
    target = load_target_portfolio(paths["raw"] / "target_portfolio.csv")
    if target.empty:
        alt = Path(root or paths["project"]).parent / "data" / "target_portfolio.csv"
        if alt.exists():
            target = load_target_portfolio(alt)

    merged = build_merged_frame(fundamentals, price_snapshot, shareholder, held_tickers)
    from src.sector_enrich import enrich_sectors

    merged = enrich_sectors(merged)
    merged = _attach_flags(merged, load_stock_flags(paths["raw"] / "stock_flags.csv"))
    merged = _attach_park(merged, load_park_state(paths["state"] / "park_state.csv"))

    if as_of:
        merged["as_of"] = as_of.isoformat()

    from src.gate import run_gate

    screening_universe = run_gate(merged, gate_cfg)
    paths["input"].mkdir(parents=True, exist_ok=True)
    screening_universe.to_csv(paths["input"] / "screening_universe.csv", index=False, encoding="utf-8-sig")

    scores, candidates = run_screener(screening_universe, gate_cfg, scoring_cfg, kr_alpha_weight=kr_alpha_weight)

    exit_review = run_exit_review(
        merged,
        scores,
        positions,
        exit_cfg,
        scoring_cfg,
        target,
        all_positions=all_positions,
        as_of=as_of,
    )

    target_draft = None
    target_changes = None
    replace_pairs = None
    matrix_warnings: list[str] = []
    if kr_alpha_weight is not None and kr_alpha_weight > 0:
        matrix_cfg = load_yaml(paths["config"] / "target_matrix.yaml")
        tm = build_target_draft(
            target,
            scores,
            candidates,
            exit_review,
            matrix_cfg,
            kr_alpha_weight=float(kr_alpha_weight),
        )
        target_draft = tm.draft
        target_changes = tm.changes
        replace_pairs = tm.replace_pairs
        matrix_warnings = tm.warnings

    paths["output"].mkdir(parents=True, exist_ok=True)
    scores.to_csv(paths["output"] / "alpha_scores.csv", index=False, encoding="utf-8-sig")
    candidates.to_csv(paths["output"] / "alpha_candidates.csv", index=False, encoding="utf-8-sig")
    exit_review.to_csv(paths["output"] / "alpha_exit_review.csv", index=False, encoding="utf-8-sig")

    blocked = _load_blocked_reintroduction_tickers(paths["project"])
    if blocked:
        if target_draft is not None and not target_draft.empty:
            target_draft = target_draft[
                ~target_draft["ticker"].astype(str).str.zfill(6).isin(blocked)
            ].copy()
        if target_changes is not None and not target_changes.empty:
            target_changes = target_changes[
                ~target_changes["ticker"].astype(str).str.zfill(6).isin(blocked)
            ].copy()

    if target_draft is not None and not target_draft.empty:
        target_draft.to_csv(paths["output"] / "target_draft.csv", index=False, encoding="utf-8-sig")
    if target_changes is not None and not target_changes.empty:
        target_changes.to_csv(paths["output"] / "target_changes.csv", index=False, encoding="utf-8-sig")
    if replace_pairs is not None and not replace_pairs.empty:
        replace_pairs.to_csv(paths["output"] / "replace_pairs.csv", index=False, encoding="utf-8-sig")

    tier_allocation = None
    tw_path = paths["config"] / "tier_weighting.yaml"
    if tw_path.exists() and not candidates.empty:
        from src.tier_allocator import build_tiered_portfolio_from_candidates

        tw_cfg = load_yaml(tw_path)
        tier_allocation = build_tiered_portfolio_from_candidates(
            candidates,
            fundamentals,
            tw_cfg=tw_cfg,
            max_names=7,
        )
        if tier_allocation:
            (paths["output"] / "tier_allocation.json").write_text(
                json.dumps(tier_allocation, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    return PipelineResult(
        scores=scores,
        candidates=candidates,
        exit_review=exit_review,
        screening_universe=screening_universe,
        target_draft=target_draft,
        target_changes=target_changes,
        replace_pairs=replace_pairs,
        matrix_warnings=matrix_warnings,
        tier_allocation=tier_allocation,
    )
