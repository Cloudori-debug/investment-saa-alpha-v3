from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.alpha.loaders import load_fundamentals, load_prices
from src.alpha.schemas import FundamentalRecord, PriceRecord, UniverseRecord
from src.models import PositionRow, TargetRow

from src.alpha_v0_2.catalyst_score import score_catalyst
from src.alpha_v0_2.classifier import classify_row, legacy_classification_label
from src.alpha_v0_2.config_loader import clamp_score, load_alpha_v02_config
from src.alpha_v0_2.exclusion_gate import run_exclusion_gate
from src.alpha_v0_2.momentum_score import score_momentum
from src.alpha_v0_2.quality_score import score_quality
from src.alpha_v0_2.risk_budget import compute_alpha_weights, portfolio_risk_budget, score_risk_control
from src.alpha_v0_2.schemas import ALPHA_V02_SCHEMA, AlphaV02ShadowResult, ScoredRow
from src.alpha_v0_2.universe import build_evaluation_universe
from src.alpha_v0_2.value_score import score_value


def _fund_map(rows: list[FundamentalRecord]) -> dict[str, FundamentalRecord]:
    out: dict[str, FundamentalRecord] = {}
    for r in rows:
        out[r.ticker] = r
    return out


def _price_map(rows: list[PriceRecord]) -> dict[str, PriceRecord]:
    return {r.ticker: r for r in rows}


def _legacy_screener_map(output_dir: Path) -> dict[str, dict[str, Any]]:
    path = output_dir / "alpha_candidates.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    out: dict[str, dict[str, Any]] = {}
    for _, r in df.iterrows():
        ticker = str(r.get("ticker", "")).zfill(6)
        out[ticker] = {
            "grade": str(r.get("grade", "")),
            "rank": int(r["rank"]) if str(r.get("rank", "")).isdigit() else None,
            "total_score": r.get("total_score", ""),
            "eligible_action": r.get("eligible_action", ""),
        }
    return out


def score_universe_row(
    rec: UniverseRecord,
    *,
    fund: FundamentalRecord | None,
    price: PriceRecord | None,
    prices_by_ticker: dict[str, PriceRecord],
    weight_pct: float,
    sector_weights: dict[str, float],
    in_portfolio: bool,
    in_target: bool,
    legacy: dict[str, Any] | None,
    cfg: dict[str, Any],
    portfolio_new_buy_allowed: bool,
) -> ScoredRow:
    weights = cfg.get("weights", {})
    ex = run_exclusion_gate(rec, fund, price, cfg)
    q = score_quality(fund, price, cfg)
    v = score_value(fund, cfg)
    m = score_momentum(price, prices_by_ticker, cfg)
    c = score_catalyst(fund, cfg)
    risk_pts, _ = score_risk_control(
        ticker=rec.ticker,
        sector=rec.sector,
        weight_pct=weight_pct,
        sector_weights=sector_weights,
        cfg=cfg,
    )

    total = clamp_score(
        q.score * float(weights.get("quality", 30)) / 100
        + v.score * float(weights.get("value", 25)) / 100
        + m.score * float(weights.get("momentum", 20)) / 100
        + c.score * float(weights.get("catalyst", 15)) / 100
        + risk_pts * float(weights.get("risk_control", 10)) / 10
    )

    leg = legacy or {}
    row = ScoredRow(
        ticker=rec.ticker,
        name=rec.name,
        sector=rec.sector,
        current_weight_pct=weight_pct,
        in_portfolio=in_portfolio,
        in_legacy_target=in_target,
        legacy_screener_grade=str(leg.get("grade", "")),
        legacy_screener_rank=leg.get("rank"),
        exclusion_pass=ex.passed,
        quality_pass=q.passed,
        momentum_pass=m.passed,
        quality_score=q.score,
        value_score=v.score,
        momentum_score=m.score,
        catalyst_score=c.score,
        risk_control_score=risk_pts,
        total_score=total,
        rel_return_90d=m.rel_return_90d,
        rel_return_120d=m.rel_return_120d,
    )
    return classify_row(row, portfolio_new_buy_allowed=portfolio_new_buy_allowed, cfg=cfg)


def run_alpha_v0_2_shadow(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    positions: list[PositionRow],
    targets: list[TargetRow],
    legacy_output_dir: Path | None = None,
    run_id: str | None = None,
) -> AlphaV02ShadowResult:
    """Alpha v0.2 shadow — v1.0.2 trade_actions·target 변경 없음."""
    cfg = load_alpha_v02_config(data_dir)
    fundamentals = _fund_map(load_fundamentals(data_dir / "fundamentals.csv"))
    prices = load_prices(data_dir / "prices.csv", as_of=as_of)
    prices_by_ticker = _price_map(prices)

    eval_universe, _ = build_evaluation_universe(
        data_dir,
        positions=positions,
        targets=targets,
        prices_by_ticker=prices_by_ticker,
        as_of=as_of,
    )

    total_port = sum(p.current_value for p in positions if p.ticker.upper() != "CASH")
    alpha_w, weights_by_ticker = compute_alpha_weights(positions)
    sector_weights: dict[str, float] = {}
    for p in positions:
        if p.asset_group != "kr_alpha":
            continue
        sector_weights[p.sector] = sector_weights.get(p.sector, 0.0) + (
            p.current_value / total_port * 100 if total_port else 0
        )

    budget = portfolio_risk_budget(positions, cfg)
    legacy_map = _legacy_screener_map(legacy_output_dir or output_dir)
    target_tickers = {t.ticker for t in targets if t.asset_group == "kr_alpha" and t.target_weight > 0}
    held_tickers = {p.ticker for p in positions if p.asset_group == "kr_alpha"}

    rows: list[ScoredRow] = []
    for rec in eval_universe:
        fund = fundamentals.get(rec.ticker)
        price = prices_by_ticker.get(rec.ticker)
        w = weights_by_ticker.get(rec.ticker, 0.0)
        row = score_universe_row(
            rec,
            fund=fund,
            price=price,
            prices_by_ticker=prices_by_ticker,
            weight_pct=w,
            sector_weights=sector_weights,
            in_portfolio=rec.ticker in held_tickers,
            in_target=rec.ticker in target_tickers,
            legacy=legacy_map.get(rec.ticker),
            cfg=cfg,
            portfolio_new_buy_allowed=bool(budget["new_alpha_buy_allowed"]),
        )
        rows.append(row)

    rows.sort(key=lambda r: (-r.total_score, r.ticker))

    diff = 0
    for row in rows:
        if not row.legacy_screener_grade:
            continue
        leg_label = legacy_classification_label(row.legacy_screener_grade)
        if row.classification not in {"Core", "Active"} and leg_label in {"Hold/Core"}:
            diff += 1
        if row.classification in {"Exit", "Legacy"} and leg_label == "Hold/Core":
            diff += 1

    result = AlphaV02ShadowResult(
        as_of=as_of,
        alpha_budget_status=budget["alpha_budget_status"],
        current_alpha_weight_pct=alpha_w,
        new_alpha_buy_allowed=bool(budget["new_alpha_buy_allowed"]),
        allowed_action=str(budget["allowed_action"]),
        rows=rows,
        legacy_diff_count=diff,
        benchmark_notes=[
            f"KOSPI200 proxy {cfg.get('momentum', {}).get('benchmark_ticker', '069500')}",
            "90d/120d = return_3m/6m vs benchmark",
        ],
    )

    write_alpha_v0_2_outputs(result, output_dir, legacy_map=legacy_map, run_id=run_id)
    return result


def write_alpha_v0_2_outputs(
    result: AlphaV02ShadowResult,
    output_dir: Path,
    *,
    legacy_map: dict[str, dict[str, Any]] | None = None,
    run_id: str | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "alpha_v0_2_classification.csv"
    fieldnames = [
        "ticker",
        "name",
        "current_weight_pct",
        "in_portfolio",
        "legacy_screener_grade",
        "legacy_screener_label",
        "alpha_v0_2_classification",
        "total_score",
        "new_buy_status",
        "quality_pass",
        "momentum_pass",
        "rel_return_90d",
        "rel_return_120d",
        "reason",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in result.rows:
            writer.writerow({
                "ticker": row.ticker,
                "name": row.name,
                "current_weight_pct": row.current_weight_pct,
                "in_portfolio": row.in_portfolio,
                "legacy_screener_grade": row.legacy_screener_grade,
                "legacy_screener_label": legacy_classification_label(row.legacy_screener_grade),
                "alpha_v0_2_classification": row.classification,
                "total_score": row.total_score,
                "new_buy_status": row.new_buy_status,
                "quality_pass": row.quality_pass,
                "momentum_pass": row.momentum_pass,
                "rel_return_90d": row.rel_return_90d if row.rel_return_90d is not None else "",
                "rel_return_120d": row.rel_return_120d if row.rel_return_120d is not None else "",
                "reason": row.reason,
            })

    shadow_json = output_dir / "alpha_v0_2_shadow.json"
    payload = result.model_dump()
    if run_id:
        from src.alpha_shadow_policy import stamp_alpha_v02_shadow_metadata

        payload = stamp_alpha_v02_shadow_metadata(payload, run_id=run_id)
    shadow_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    log_path = output_dir / "alpha_v0_2_shadow_log.csv"
    log_fields = [
        "date",
        "alpha_budget_status",
        "current_alpha_weight_pct",
        "new_alpha_buy_allowed",
        "legacy_diff_count",
        "core_count",
        "legacy_count",
        "exit_count",
        "mismatch_vs_legacy",
    ]
    core_c = sum(1 for r in result.rows if r.classification == "Core")
    legacy_c = sum(1 for r in result.rows if r.classification == "Legacy")
    exit_c = sum(1 for r in result.rows if r.classification == "Exit")
    log_row = {
        "date": result.as_of,
        "alpha_budget_status": result.alpha_budget_status,
        "current_alpha_weight_pct": result.current_alpha_weight_pct,
        "new_alpha_buy_allowed": result.new_alpha_buy_allowed,
        "legacy_diff_count": result.legacy_diff_count,
        "core_count": core_c,
        "legacy_count": legacy_c,
        "exit_count": exit_c,
        "mismatch_vs_legacy": result.legacy_diff_count,
    }
    write_header = not log_path.exists()
    with log_path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=log_fields)
        if write_header:
            writer.writeheader()
        writer.writerow(log_row)

    if legacy_map is not None:
        diff_path = output_dir / "alpha_v0_2_legacy_diff.json"
        diff_path.write_text(
            json.dumps({
                "schema_version": ALPHA_V02_SCHEMA,
                "as_of": result.as_of,
                "legacy_diff_count": result.legacy_diff_count,
                "rows": [
                    {
                        "ticker": r.ticker,
                        "legacy_grade": r.legacy_screener_grade,
                        "v0_2": r.classification,
                        "new_buy_status": r.new_buy_status,
                    }
                    for r in result.rows
                    if r.legacy_screener_grade or r.in_portfolio
                ],
            }, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )


def build_daily_report_alpha_v02_section(
    output_dir: Path | None,
    *,
    data_dir: Path | None = None,
    run_id: str | None = None,
) -> list[str]:
    if output_dir is None:
        return []
    from src.alpha_shadow_policy import resolve_alpha_v02_shadow_doc

    doc, status, enabled = resolve_alpha_v02_shadow_doc(
        output_dir,
        data_dir=data_dir,
        run_id=run_id,
    )
    if not enabled or status == "disabled":
        return [
            "## Alpha v0.2 Shadow (research only)",
            "- **Alpha v0.2 shadow**: disabled",
            "",
        ]
    if doc is None:
        return []
    if doc.get("mode") != "shadow":
        return []

    held = [r for r in doc.get("rows", []) if r.get("in_portfolio")]
    summary = (
        f"budget `{doc.get('alpha_budget_status')}` · "
        f"alpha {doc.get('current_alpha_weight_pct')}% · "
        f"new_buy `{doc.get('new_alpha_buy_allowed')}` · "
        f"legacy_diff {doc.get('legacy_diff_count')}"
    )
    lines = [
        "## Alpha v0.2 Shadow (research only)",
        f"- **Portfolio:** {summary}",
        f"- **authority:** `{doc.get('execution_authority', 'v1.0.2')}` — trade_actions 변경 없음",
        "",
        "| ticker | weight% | v0.2 | new_buy | reason |",
        "|--------|--------:|------|---------|--------|",
    ]
    for r in held[:12]:
        lines.append(
            f"| {r.get('ticker')} | {r.get('current_weight_pct', 0)} | "
            f"{r.get('classification')} | {r.get('new_buy_status')} | {r.get('reason', '')[:40]} |"
        )
    if len(held) > 12:
        lines.append(f"| … | | | | +{len(held) - 12} holdings |")
    lines.append("")
    return lines
