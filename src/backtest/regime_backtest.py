from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.compass.portfolio_builder import build_portfolio_allocation
from src.compass.regime_engine import compute_compass
from src.compass.saa_engine import load_saa_profiles
from src.config import load_yaml
from src.data_loader import load_market_indicators_history, load_market_row
from src.compass.tier2_macro import load_macro_tier2


from src.models import VALID_ASSET_GROUPS


@dataclass
class BacktestRow:
    date: str
    market_phase: str
    computed_regime: str
    applied_regime: str
    cash_target: float
    kr_alpha_target: float
    compass_direction: str
    group_targets: dict[str, float] = field(default_factory=dict)


@dataclass
class BacktestResult:
    rows: list[BacktestRow] = field(default_factory=list)
    regime_changes: int = 0
    phase_changes: int = 0


def run_regime_backtest(
    data_dir: Path,
    *,
    profile: str | None = None,
    history_file: str = "market_indicators_history.csv",
) -> BacktestResult:
    history_path = data_dir / history_file
    if not history_path.exists():
        raise FileNotFoundError(f"history not found: {history_path}")

    rules = load_yaml(data_dir / "compass_rules.yaml")
    profiles = load_saa_profiles(data_dir / "saa_profiles.yaml")
    tier2_path = data_dir / "macro_tier2.csv"
    history = load_market_indicators_history(history_path)

    result = BacktestResult()
    prev_regime: str | None = None
    prev_phase: str | None = None

    for market in history:
        tier2 = load_macro_tier2(tier2_path, as_of=market.date)
        compass = compute_compass(market, rules, tier2=tier2, use_manual_regime=True)
        allocation = build_portfolio_allocation(compass, profiles, profile_name=profile)
        cash = next(g for g in allocation.groups if g.asset_group == "cash_short_bond")
        alpha = next(g for g in allocation.groups if g.asset_group == "kr_alpha")
        group_targets = {g.asset_group: g.final_target for g in allocation.groups}

        if prev_regime and prev_regime != compass.applied_regime.value:
            result.regime_changes += 1
        if prev_phase and prev_phase != compass.market_phase.value:
            result.phase_changes += 1
        prev_regime = compass.applied_regime.value
        prev_phase = compass.market_phase.value

        result.rows.append(
            BacktestRow(
                date=market.date,
                market_phase=compass.market_phase.value,
                computed_regime=compass.computed_regime.value,
                applied_regime=compass.applied_regime.value,
                cash_target=cash.final_target,
                kr_alpha_target=alpha.final_target,
                compass_direction=compass.compass_direction,
                group_targets=group_targets,
            )
        )

    return result


def write_backtest_outputs(result: BacktestResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    legacy_rows = []
    for r in result.rows:
        legacy_rows.append(
            {
                "date": r.date,
                "market_phase": r.market_phase,
                "computed_regime": r.computed_regime,
                "applied_regime": r.applied_regime,
                "cash_target": r.cash_target,
                "kr_alpha_target": r.kr_alpha_target,
                "compass_direction": r.compass_direction,
            }
        )
    pd.DataFrame(legacy_rows).to_csv(output_dir / "backtest_results.csv", index=False)

    taa_records: list[dict] = []
    for r in result.rows:
        rec: dict = {
            "date": r.date,
            "market_phase": r.market_phase,
            "applied_regime": r.applied_regime,
            "compass_direction": r.compass_direction,
        }
        for group in sorted(VALID_ASSET_GROUPS):
            rec[f"{group}_target"] = r.group_targets.get(group, 0.0)
        taa_records.append(rec)
    pd.DataFrame(taa_records).to_csv(output_dir / "taa_backtest_results.csv", index=False, encoding="utf-8-sig")

    lines = [
        "# TAA·레짐 백테스트 리포트",
        "",
        f"- 기간: {result.rows[0].date} ~ {result.rows[-1].date}" if result.rows else "- 기간: —",
        f"- 관측 수: {len(result.rows)}",
        f"- 레짐 전환: {result.regime_changes}회",
        f"- 시장국면 전환: {result.phase_changes}회",
        "",
        "## 일별 요약",
        "",
        "| date | phase | applied_regime | cash% | kr_alpha% | direction |",
        "|------|-------|----------------|------:|----------:|-----------|",
    ]
    for r in result.rows:
        lines.append(
            f"| {r.date} | {r.market_phase} | {r.applied_regime} | "
            f"{r.cash_target:.1f} | {r.kr_alpha_target:.1f} | {r.compass_direction} |"
        )
    lines.extend([
        "",
        "> TAA 백테스트 — SAA + 레짐/국면 tilt 반영 비중 경로 검증. **수익률 예측 아님.**",
    ])
    (output_dir / "backtest_report.md").write_text("\n".join(lines), encoding="utf-8")
    (output_dir / "taa_backtest_report.md").write_text("\n".join(lines), encoding="utf-8")
