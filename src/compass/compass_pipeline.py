from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.compass.action_labels import COMPASS_ACTION_FOOTNOTE, group_action_display_label

from src.compass.compass_report import write_compass_json, write_compass_report
from src.compass.group_gap import compute_group_gaps
from src.compass.mismatch_check import check_target_mismatch
from src.compass.models import (
    CompassResult,
    GroupGapRow,
    PortfolioAllocation,
    TargetMismatchWarning,
)
from src.compass.portfolio_builder import build_portfolio_allocation
from src.compass.regime_auto import load_tier2_sources, use_manual_regime_flag
from src.compass.regime_engine import compute_compass
from src.compass.saa_engine import load_saa_profiles
from src.compass.target_decomposer import decompose_target_portfolio
from src.compass.tier2_macro import load_macro_tier2
from src.config import load_yaml
from src.data_loader import load_market_indicators, load_target_portfolio, write_target_portfolio
from src.models import PositionRow, TargetRow
from src.regime_classifier import classify_data_gate_from_regime, execution_level_hint, parse_regime


@dataclass
class CompassPipelineResult:
    compass: CompassResult
    allocation: PortfolioAllocation
    group_gaps: list[GroupGapRow] = field(default_factory=list)
    mismatch_warnings: list[TargetMismatchWarning] = field(default_factory=list)
    generated_targets: list[TargetRow] = field(default_factory=list)
    tier2_used: bool = False


def run_compass_pipeline(
    data_dir: Path,
    output_dir: Path,
    *,
    profile: str | None = None,
    positions: list[PositionRow] | None = None,
    ticker_targets: list[TargetRow] | None = None,
    template_targets: list[TargetRow] | None = None,
    generated_at: str | None = None,
    auto_decompose: bool = True,
    run_id: str = "",
) -> CompassPipelineResult:
    market = load_market_indicators(data_dir / "market_indicators.csv")
    rules = load_yaml(data_dir / "compass_rules.yaml")
    profiles = load_saa_profiles(data_dir / "saa_profiles.yaml")
    tier2 = load_macro_tier2(data_dir / "macro_tier2.csv", as_of=market.date)

    data_gate = "GREEN"
    execution_level = 1
    if positions is not None:
        from src.config import load_portfolio_policy
        from src.portfolio_gap import compute_gaps
        from src.validators import validate_inputs

        if ticker_targets is None and (data_dir / "target_portfolio.csv").exists():
            ticker_targets = load_target_portfolio(data_dir / "target_portfolio.csv")
        if ticker_targets:
            policy = load_portfolio_policy(data_dir / "portfolio_policy.yaml")
            validation = validate_inputs(positions, ticker_targets, policy)
            data_gate = classify_data_gate_from_regime(market.regime, validation.data_gate)
            gap_rows = compute_gaps(positions, ticker_targets)
            max_gap = max((abs(r.gap) for r in gap_rows), default=0)
            execution_level = execution_level_hint(data_gate, parse_regime(market), max_gap)

    sources = load_tier2_sources(data_dir)
    compass = compute_compass(
        market,
        rules,
        data_gate=data_gate,
        execution_level=execution_level,
        tier2=tier2,
        output_dir=output_dir,
        use_manual_regime=use_manual_regime_flag(sources),
    )
    tilt_meta: dict = {}
    allocation = build_portfolio_allocation(
        compass, profiles, profile_name=profile, rules=rules, tilt_meta=tilt_meta,
    )

    generated_targets: list[TargetRow] = []
    if auto_decompose:
        template = template_targets
        if template is None and (data_dir / "target_portfolio_template.csv").exists():
            template = load_target_portfolio(data_dir / "target_portfolio_template.csv")
        elif template is None and (data_dir / "target_portfolio.csv").exists():
            template = load_target_portfolio(data_dir / "target_portfolio.csv")
        if template:
            generated_targets = decompose_target_portfolio(allocation, template)
            write_target_portfolio(generated_targets, output_dir / "generated_target_portfolio.csv")

    group_gaps: list[GroupGapRow] = []
    mismatch_warnings: list[TargetMismatchWarning] = []

    if positions is not None:
        group_gaps = compute_group_gaps(positions, allocation)
        manual_targets = ticker_targets
        if manual_targets is None and (data_dir / "target_portfolio.csv").exists():
            manual_targets = load_target_portfolio(data_dir / "target_portfolio.csv")
        if manual_targets:
            mismatch_warnings = check_target_mismatch(allocation, manual_targets)

    ts = generated_at or datetime.now(timezone.utc).isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)

    write_target_asset_allocation_csv(allocation, output_dir / "target_asset_allocation.csv")
    if group_gaps:
        write_portfolio_gap_csv(group_gaps, output_dir / "portfolio_gap.csv")
        write_portfolio_actions_md(group_gaps, output_dir / "portfolio_actions.md")

    write_compass_json(
        output_dir / "compass_regime.json",
        compass,
        allocation,
        mismatch_warnings=mismatch_warnings,
        generated_at=ts,
        tier2_used=tier2 is not None,
    )
    write_compass_report(
        output_dir / "compass_report.md",
        compass,
        allocation,
        group_gaps=group_gaps,
        mismatch_warnings=mismatch_warnings,
        generated_targets=generated_targets,
        tier2_used=tier2 is not None,
        generated_at=ts,
    )

    from src.compass.judgment_log import write_compass_judgment_log

    write_compass_judgment_log(
        output_dir,
        compass,
        market,
        tilt_meta=tilt_meta,
        run_id=run_id or ts,
    )

    return CompassPipelineResult(
        compass=compass,
        allocation=allocation,
        group_gaps=group_gaps,
        mismatch_warnings=mismatch_warnings,
        generated_targets=generated_targets,
        tier2_used=tier2 is not None,
    )


def write_target_asset_allocation_csv(allocation: PortfolioAllocation, path: Path) -> None:
    df = pd.DataFrame(
        [
            {
                "asset_group": g.asset_group,
                "saa_weight": g.saa_weight,
                "phase_tilt": g.phase_tilt,
                "regime_tilt": g.regime_tilt,
                "raw_target": g.raw_target,
                "final_target": g.final_target,
                "min_weight": g.min_weight,
                "max_weight": g.max_weight,
            }
            for g in allocation.groups
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def write_portfolio_gap_csv(gaps: list[GroupGapRow], path: Path) -> None:
    df = pd.DataFrame([g.model_dump() for g in gaps])
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def write_portfolio_actions_md(gaps: list[GroupGapRow], path: Path) -> None:
    lines = [
        "# 자산군 실행 판단",
        "",
        "| 자산군 | 현재 | 목표 | Gap | Action | 사유 |",
        "|--------|-----:|-----:|----:|--------|------|",
    ]
    for g in gaps:
        lines.append(
            f"| {g.asset_group} | {g.current:.1f}% | {g.target:.1f}% | {g.gap:+.1f}%p | "
            f"**{group_action_display_label(g.action, gap=g.gap)}** | {g.reason} |"
        )
    lines.extend([
        "",
        COMPASS_ACTION_FOOTNOTE,
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
