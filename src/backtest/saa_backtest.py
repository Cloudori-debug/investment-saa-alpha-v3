from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.compass.profile_aliases import resolve_profile_name
from src.compass.saa_engine import get_group_bounds, get_saa_weights, load_saa_profiles
from src.data_loader import load_market_indicators_history
from src.models import VALID_ASSET_GROUPS


@dataclass
class SaaBacktestRow:
    date: str
    profile: str
    weights: dict[str, float] = field(default_factory=dict)


@dataclass
class SaaBacktestResult:
    profile: str
    rows: list[SaaBacktestRow] = field(default_factory=list)
    bounds: dict[str, dict[str, float]] = field(default_factory=dict)


def run_saa_backtest(
    data_dir: Path,
    *,
    profile: str | None = None,
    history_file: str = "market_indicators_history.csv",
) -> SaaBacktestResult:
    """정적 SAA 프로필 검증 — 레짐·TAA 무관, 기준 비중 안정성 확인용."""
    profiles = load_saa_profiles(data_dir / "saa_profiles.yaml")
    name = resolve_profile_name(profiles, profile)
    saa = get_saa_weights(profiles, name)
    bounds = get_group_bounds(profiles, name)

    history_path = data_dir / history_file
    if history_path.exists():
        dates = [m.date for m in load_market_indicators_history(history_path)]
    else:
        dates = ["static"]

    rows = [
        SaaBacktestRow(date=d, profile=name, weights=dict(saa))
        for d in dates
    ]
    return SaaBacktestResult(profile=name, rows=rows, bounds=bounds)


def write_saa_backtest_outputs(result: SaaBacktestResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    for row in result.rows:
        rec: dict = {"date": row.date, "profile": row.profile}
        for group in sorted(VALID_ASSET_GROUPS):
            rec[f"{group}_target"] = row.weights.get(group, 0.0)
        records.append(rec)
    pd.DataFrame(records).to_csv(output_dir / "saa_backtest_results.csv", index=False, encoding="utf-8-sig")

    if not result.rows:
        return
    w = result.rows[0].weights
    lines = [
        "# SAA 정적 백테스트",
        "",
        f"- 프로필: **{result.profile}**",
        f"- 관측 일수: {len(result.rows)} (TAA 미적용 — 비중 변동 없음)",
        "",
        "## 기준 자산군 비중 (%)",
        "",
        "| 자산군 | SAA | min | max |",
        "|--------|----:|----:|----:|",
    ]
    for group in sorted(VALID_ASSET_GROUPS):
        b = result.bounds.get(group, {"min": 0, "max": 100})
        lines.append(f"| {group} | {w.get(group, 0):.1f} | {b['min']:.0f} | {b['max']:.0f} |")
    lines.extend([
        "",
        "> SAA 백테스트는 **전략적 기준 비중** 검증용입니다. 수익률·레짐 반응은 TAA 탭을 참고하세요.",
    ])
    (output_dir / "saa_backtest_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
