from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.alpha.loaders import load_alpha_scoring_config, load_fundamentals, load_universe, load_universe_filter_config
from src.alpha.data_gate import apply_data_gate
from src.alpha.factor_scoring import score_factors
from src.alpha.penalty_engine import apply_penalties, assign_grades
from src.alpha.schemas import PriceRecord
from src.alpha.universe_filter import filter_universe
from src.backtest.cost_model import (
    apply_round_trip_cost_fraction,
    load_cost_assumptions,
    round_trip_cost_bps,
    sample_quality_banner,
    sample_quality_label,
)


@dataclass
class QuintileRow:
    quintile: int
    avg_return_3m: float
    avg_total_score: float
    count: int


@dataclass
class AlphaBacktestResult:
    dates: list[str] = field(default_factory=list)  # 가격 이력 커버리지 (품질 라벨 근거 아님)
    scored_dates: list[str] = field(default_factory=list)  # 실제 스코어·quintile 기여 일
    quintiles: list[QuintileRow] = field(default_factory=list)
    top_n_avg_return: float = 0.0
    universe_avg_return: float = 0.0
    top_n_excess: float = 0.0
    top_n_excess_net: float = 0.0
    top_n_avg_return_net: float = 0.0
    monotonic: bool = False
    top_n: int = 5
    lookback_days: int | None = None
    sample_quality: str = "insufficient"
    cost_assumptions: dict[str, Any] = field(default_factory=dict)
    round_trip_cost_bps: float = 0.0
    usable_from_date_kinds: int = 0
    warnings: list[str] = field(default_factory=list)


def _prices_from_frame(hist: pd.DataFrame, as_of: str) -> dict[str, PriceRecord]:
    snap = hist[hist["date"] == as_of]
    rows: dict[str, PriceRecord] = {}
    float_cols = (
        "close", "market_cap", "trading_value_20d", "trading_value_60d",
        "return_1m", "return_3m", "return_6m", "return_12m", "return_12m_ex_1m",
        "high_52w", "distance_from_52w_high", "volatility_60d",
    )
    for r in snap.to_dict(orient="records"):
        for col in float_cols:
            if col in r and str(r[col]).strip():
                r[col] = float(r[col])
            else:
                r[col] = 0.0
        t = str(r["ticker"]).strip()
        if t.isdigit():
            t = t.zfill(6)
        r["ticker"] = t
        rows[t] = PriceRecord.model_validate(r)
    return rows


def _score_on_date(data_dir: Path, as_of: str, prices_by_ticker: dict[str, PriceRecord], scoring_cfg: dict) -> pd.DataFrame:
    filter_cfg = load_universe_filter_config(data_dir / "universe_filter.yaml")
    universe = load_universe(data_dir / "universe.csv")
    fundamentals_raw = load_fundamentals(data_dir / "fundamentals.csv")

    passed, _ = filter_universe(universe, prices_by_ticker, filter_cfg, as_of)
    usable, _, _, _ = apply_data_gate(fundamentals_raw, filter_cfg, as_of)
    scored_universe = [u for u in passed if u.ticker in usable]
    if len(scored_universe) < 5:
        return pd.DataFrame()

    raw = score_factors(scored_universe, usable, prices_by_ticker, scoring_cfg)
    umap = {u.ticker: u for u in scored_universe}
    penalized = apply_penalties(raw, umap, usable, prices_by_ticker, scoring_cfg)
    graded = assign_grades(penalized, scoring_cfg)

    rows = []
    for g in graded:
        px = prices_by_ticker.get(g["ticker"])
        rows.append(
            {
                "ticker": g["ticker"],
                "total_score": g["total_score"],
                "return_3m": px.return_3m if px else 0.0,
            }
        )
    return pd.DataFrame(rows)


def run_alpha_lite_backtest(
    data_dir: Path,
    *,
    history_file: str = "prices_history.csv",
    top_n: int = 5,
    lookback_days: int | None = None,
) -> AlphaBacktestResult:
    """Cross-sectional Alpha 검증: quintile spread + top-N vs universe (return_3m proxy)."""
    history_path = data_dir / history_file
    cost_assumptions = load_cost_assumptions(data_dir / "cost_assumptions.yaml")
    holding_days = int(cost_assumptions.get("typical_holding_days") or 63)
    result = AlphaBacktestResult(
        top_n=top_n,
        lookback_days=lookback_days,
        cost_assumptions=cost_assumptions,
        round_trip_cost_bps=round_trip_cost_bps(cost_assumptions),
    )
    scoring_cfg = load_alpha_scoring_config(data_dir / "alpha_scoring.yaml")

    if history_path.exists():
        hist = pd.read_csv(history_path, dtype=str, keep_default_na=False)
    elif (data_dir / "prices.csv").exists():
        hist = pd.read_csv(data_dir / "prices.csv", dtype=str, keep_default_na=False)
    else:
        result.warnings.append("prices_history.csv / prices.csv 없음")
        result.sample_quality = sample_quality_label(0)
        return result

    dates = sorted(hist["date"].unique().tolist())
    if lookback_days is not None and lookback_days > 0 and dates:
        dates = dates[-int(lookback_days) :]
    result.dates = dates
    result.usable_from_date_kinds = _count_usable_from_date_kinds(data_dir)
    all_quintile_returns: list[list[float]] = [[] for _ in range(5)]
    top_returns: list[float] = []
    uni_returns: list[float] = []
    scored_dates: list[str] = []

    for as_of in dates:
        prices_by_ticker = _prices_from_frame(hist, as_of)
        scored = _score_on_date(data_dir, as_of, prices_by_ticker, scoring_cfg)
        if scored.empty or len(scored) < 5:
            continue

        scored = scored.sort_values("total_score", ascending=False)
        uni_returns.extend(scored["return_3m"].astype(float).tolist())
        top_returns.extend(scored.head(top_n)["return_3m"].astype(float).tolist())

        try:
            scored["quintile"] = pd.qcut(scored["total_score"], 5, labels=False, duplicates="drop")
        except ValueError:
            continue
        scored_dates.append(as_of)
        for q in range(5):
            bucket = scored[scored["quintile"] == q]
            if not bucket.empty:
                all_quintile_returns[q].append(float(bucket["return_3m"].mean()))

    result.scored_dates = scored_dates

    if uni_returns:
        result.universe_avg_return = round(float(np.mean(uni_returns)), 4)
    if top_returns:
        result.top_n_avg_return = round(float(np.mean(top_returns)), 4)
        result.top_n_excess = round(result.top_n_avg_return - result.universe_avg_return, 4)
        result.top_n_avg_return_net = round(
            apply_round_trip_cost_fraction(
                result.top_n_avg_return, holding_days, cost_assumptions
            ),
            4,
        )
        # Excess net: only portfolio leg pays round-trip vs universe (proxy)
        result.top_n_excess_net = round(
            apply_round_trip_cost_fraction(
                result.top_n_excess, holding_days, cost_assumptions
            ),
            4,
        )

    quintile_avgs = []
    for q, vals in enumerate(all_quintile_returns):
        if vals:
            avg_r = float(np.mean(vals))
            quintile_avgs.append(avg_r)
            result.quintiles.append(
                QuintileRow(quintile=q + 1, avg_return_3m=round(avg_r, 4), avg_total_score=0.0, count=len(vals))
            )

    if len(quintile_avgs) >= 2:
        result.monotonic = quintile_avgs[-1] >= quintile_avgs[0]

    # 품질 라벨은 실제 기여 일수(scored_dates) 기준 — 가격 커버리지(dates)와 혼동 금지
    result.sample_quality = sample_quality_label(len(result.scored_dates))
    if result.sample_quality == "insufficient":
        result.warnings.append("예측력 판단 불가 — 참고용 (유효 표본 < 60일)")
    elif result.sample_quality == "preliminary":
        result.warnings.append("예비 검증 — 확정 아님 (유효 표본 60~180일)")

    if not result.quintiles:
        result.warnings.append("스코어 가능 일수 부족 — prices_history 확장 권장")

    pit_warning = _pit_coverage_warning(
        price_history_days=len(result.dates),
        scored_days=len(result.scored_dates),
        usable_from_date_kinds=result.usable_from_date_kinds,
    )
    if pit_warning:
        result.warnings.append(pit_warning)

    return result


def _count_usable_from_date_kinds(data_dir: Path) -> int:
    path = data_dir / "fundamentals.csv"
    if not path.exists():
        return 0
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, usecols=["usable_from_date"])
    except (ValueError, KeyError):
        return 0
    values = {str(v).strip()[:10] for v in df["usable_from_date"] if str(v).strip()}
    return len(values)


def _pit_coverage_warning(
    *,
    price_history_days: int,
    scored_days: int,
    usable_from_date_kinds: int,
) -> str | None:
    if price_history_days <= 0:
        return None
    if scored_days / price_history_days >= 0.3:
        return None
    kinds = usable_from_date_kinds if usable_from_date_kinds > 0 else "?"
    return (
        f"PIT 재무 데이터가 단일 스냅샷(usable_from_date 종류 {kinds}개)이라 "
        "유효 표본이 가격 데이터 범위 대비 크게 작음 — 결과를 전략 판단 근거로 사용하지 말 것"
    )


def write_alpha_backtest_outputs(result: AlphaBacktestResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        {"quintile": q.quintile, "avg_return_3m": q.avg_return_3m, "observations": q.count}
        for q in result.quintiles
    ]
    pd.DataFrame(rows).to_csv(output_dir / "alpha_backtest_quintiles.csv", index=False, encoding="utf-8-sig")

    a = result.cost_assumptions or {}
    price_history_days = len(result.dates)
    scored_days_used = len(result.scored_dates)
    quality = result.sample_quality or sample_quality_label(scored_days_used)
    summary = pd.DataFrame(
        [
            {
                "top_n": result.top_n,
                "top_n_avg_return_3m": result.top_n_avg_return,
                "top_n_avg_return_3m_net": result.top_n_avg_return_net,
                "universe_avg_return_3m": result.universe_avg_return,
                "top_n_excess": result.top_n_excess,
                "top_n_excess_net": result.top_n_excess_net,
                "round_trip_cost_bps": result.round_trip_cost_bps,
                "sample_quality": result.sample_quality,
                "lookback_days": result.lookback_days if result.lookback_days is not None else "",
                "monotonic_quintiles": result.monotonic,
                "price_history_days": price_history_days,
                "scored_days_used": scored_days_used,
                # legacy alias — 품질 라벨 근거인 유효 기여 일수
                "dates_used": scored_days_used,
            }
        ]
    )
    summary.to_csv(output_dir / "alpha_backtest_summary.csv", index=False, encoding="utf-8-sig")

    banner = sample_quality_banner(quality)
    commission = a.get("commission_bps", 15)
    slippage = a.get("slippage_bps", 20)
    tax = a.get("securities_tx_tax_bps", 18)

    lines = [
        "# Alpha Lite Backtest (cost-adjusted)",
        "",
    ]
    if quality == "insufficient":
        lines.extend([
            f"> **{banner}** — 유효 표본 {scored_days_used}일 (< 60). "
            "Gross/Net 수치는 팩터 정렬 참고용이며 운용 근거로 쓰지 말 것.",
            "",
        ])
    else:
        lines.extend([f"> 품질 라벨: **{quality}** — {banner}", ""])

    lines.extend([
        (
            f"- 유효 기여 일수 (`scored_days_used`): **{scored_days_used}일** "
            f"· 품질 라벨 근거: `{quality}`"
        ),
        (
            f"- 가격 이력 커버리지 (`price_history_days`): {price_history_days}일 "
            "— 참고용, 품질 라벨 근거 아님"
        ),
        f"- Top-{result.top_n} 평균 3M 수익률 (Gross): **{result.top_n_avg_return:.2%}**",
        f"- Universe 평균: **{result.universe_avg_return:.2%}**",
        f"- Gross Top-{result.top_n} 초과수익: **{result.top_n_excess:.2%}**",
        (
            f"- Cost 가정: 수수료 {commission}bp + 슬리피지 {slippage}bp + "
            f"거래세 {tax}bp (왕복 {result.round_trip_cost_bps:g}bp) "
            "— `data/cost_assumptions.yaml` 가정치, 원장님 확인 후 조정"
        ),
        f"- **Net Top-{result.top_n} 초과수익 (비용 차감 후)**: **{result.top_n_excess_net:.2%}**",
        f"- Quintile monotonic (Q1→Q5): **{'Yes' if result.monotonic else 'No'}**",
        "",
        "## Quintile Spread",
        "",
        "| Quintile | Avg return_3m |",
        "|----------|---------------|",
    ])
    for q in result.quintiles:
        lines.append(f"| Q{q.quintile} | {q.avg_return_3m:.2%} |")

    if result.warnings:
        lines.extend(["", "## Warnings", ""])
        for w in result.warnings:
            lines.append(f"- {w}")

    lines.extend([
        "",
        "## 한계 (투자 전략 미반영)",
        "",
        "- **Lite 검증만 제공**: 횡단면 QVM-SR 스코어 → `return_3m` proxy 상관만 확인",
        "- **6~8종 집중·role(core/satellite)·익절/손절·사람 승인** 규칙 미포함",
        "- PIT 재무·생존편향·리밸런스 타이밍·승인 지연 미반영 (왕복 비용만 placeholder 차감)",
        "- 실제 알파 운용 **성과 예측 불가** — 팩터 정렬(monotonicity) 검증용",
        "- gate / policy_cap / Actual Buy Allowed / approval_bridge **미변경**",
        "",
        "_return_3m은 forward 수익률 proxy. Net은 왕복 비용 차감 참고치._",
    ])
    (output_dir / "alpha_backtest_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
