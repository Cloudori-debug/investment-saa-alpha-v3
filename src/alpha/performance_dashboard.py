from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_loader import load_positions, load_target_portfolio
from src.alpha.benchmark_data import (
    load_combined_prices,
    ticker_cum_return_detail,
    ticker_return_mtd,
    ticker_return_mtd_detail,
)
from src.alpha.gate_forward_enrich import enrich_gate_opportunity_cost_csv
from src.alpha.nav_log import (
    append_portfolio_nav_log,
    build_nav_snapshot,
    nav_return_mtd_detail,
)
from src.decision.shadow_performance import (
    _pct_change,
    _row_on_or_before,
    add_business_days,
    compute_portfolio_log_returns,
    compute_saa_proxy_returns,
)
from src.exposure.core_saa_reference import load_core_saa_reference

ALPHA_DASHBOARD_DISCLAIMER = (
    "Shadow diagnostic only — not a buy/sell recommendation. "
    "v1.0.2 execution authority remains trade_actions / allowed_actions only. "
    "If this system cannot beat the Core SAA benchmark over time, investment justification is weak. "
    "raw_nav_return_mtd may include deposits/asset registration — use adjusted/holdings price returns for judgment."
)

FORWARD_HORIZONS = (5, 20, 60, 120)


def _normalize_ticker(ticker: str | None) -> str | None:
    if ticker is None:
        return None
    t = str(ticker).strip().upper()
    if not t or t == "NULL":
        return None
    return t if t == "CASH" else t.zfill(6) if t.isdigit() else t


def _forward_return(
    prices: pd.DataFrame,
    ticker: str,
    from_date: str,
    business_days: int,
) -> float | None:
    sub = prices[prices["ticker"] == ticker].sort_values("date")
    if sub.empty:
        return None
    start = _row_on_or_before(sub, from_date)  # type: ignore[arg-type]
    if start is None:
        return None
    target = add_business_days(from_date, business_days)
    if not target:
        return None
    end = _row_on_or_before(sub, target)
    if end is None or end["date"] <= start["date"]:
        return None
    return _pct_change(float(end["close"]), float(start["close"]))


def compute_core_saa_benchmark_mtd(data_dir: Path, as_of: str) -> dict[str, Any]:
    ref = load_core_saa_reference(data_dir)
    if not ref:
        return {"core_saa_return_mtd": None, "unresolved_weight_pct": 0.0, "note": "no core reference"}

    prices = load_combined_prices(data_dir)
    weighted_return = 0.0
    weight_used = 0.0
    weight_with_price = 0.0
    unresolved = 0.0
    components: list[dict[str, Any]] = []

    for asset in ref.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        tw = float(asset.get("target_weight_pct") or 0)
        if tw <= 0:
            continue
        ticker = _normalize_ticker(asset.get("ticker"))
        if not ticker:
            unresolved += tw
            components.append({
                "name": asset.get("name", ""),
                "target_weight_pct": tw,
                "mapping_status": "unresolved",
                "return_mtd": None,
            })
            continue
        ret = ticker_return_mtd(prices, ticker, as_of) if not prices.empty else None
        if ret is not None:
            weighted_return += tw / 100 * ret
            weight_used += tw
            weight_with_price += tw
        components.append({
            "ticker": ticker,
            "name": asset.get("name", ""),
            "target_weight_pct": tw,
            "return_mtd": ret,
            "mapping_status": asset.get("mapping_status", "resolved"),
        })

    mtd = round(weighted_return, 4) if weight_with_price > 0 else None
    return {
        "core_saa_return_mtd": mtd,
        "core_weight_coverage_pct": round(weight_used, 2),
        "core_weight_with_price_pct": round(weight_with_price, 2),
        "price_source": "prices_history+prices.csv",
        "unresolved_weight_pct": round(unresolved, 2),
        "components": components,
    }


def _holdings_price_return_mtd(
    positions: list[Any],
    prices: pd.DataFrame,
    as_of: str,
) -> dict[str, Any]:
    """Holdings-weighted MTD from prices — capital-agnostic when coverage is OK."""
    total = sum(float(p.current_value or 0) for p in positions) or 0.0
    if total <= 0 or prices.empty:
        return {
            "holdings_price_return_mtd": None,
            "price_coverage_weight_pct": 0.0,
            "quality": "no_positions_or_prices",
        }
    weighted = 0.0
    covered = 0.0
    for p in positions:
        w = float(p.current_value or 0) / total * 100
        if _normalize_ticker(p.ticker) == "CASH":
            covered += w
            continue
        ret = ticker_return_mtd(prices, p.ticker, as_of)
        if ret is None:
            continue
        weighted += w / 100 * ret
        covered += w
    if covered < 50:
        return {
            "holdings_price_return_mtd": None,
            "price_coverage_weight_pct": round(covered, 2),
            "quality": "insufficient_price_coverage",
        }
    return {
        "holdings_price_return_mtd": round(weighted, 4),
        "price_coverage_weight_pct": round(covered, 2),
        "quality": "ok",
    }


def compute_actual_and_kr_alpha_mtd(
    data_dir: Path,
    output_dir: Path,
    as_of: str,
) -> dict[str, Any]:
    positions = load_positions(data_dir / "positions.csv")
    total = sum(float(p.current_value or 0) for p in positions) or 0.0
    prices = load_combined_prices(data_dir)

    port_log = compute_portfolio_log_returns(
        output_dir / "ops_shadow_log.csv",
        as_of,
        total,
    )
    nav_detail = nav_return_mtd_detail(output_dir / "portfolio_nav_log.csv", as_of)
    holdings = _holdings_price_return_mtd(positions, prices, as_of)

    # Prefer capital-agnostic holdings price return; then adjusted NAV; then shadow log.
    # Raw NAV ratio is NEVER primary — capital registration can inflate it (2026-07-03).
    actual_mtd = None
    actual_source = None
    if holdings.get("holdings_price_return_mtd") is not None:
        actual_mtd = holdings["holdings_price_return_mtd"]
        actual_source = "holdings_price_return"
    elif nav_detail.get("adjusted_nav_return_mtd") is not None:
        actual_mtd = nav_detail["adjusted_nav_return_mtd"]
        actual_source = "portfolio_nav_log_adjusted"
    elif port_log.get("portfolio_return_mtd") is not None:
        actual_mtd = port_log.get("portfolio_return_mtd")
        actual_source = "ops_shadow_log"
    elif nav_detail.get("raw_nav_return_mtd") is not None:
        actual_mtd = nav_detail["raw_nav_return_mtd"]
        actual_source = "portfolio_nav_log_raw_fallback"

    kr_alpha_weight = 0.0
    kr_alpha_return = 0.0
    kr_alpha_cov = 0.0
    for p in positions:
        if p.asset_group != "kr_alpha":
            continue
        w = float(p.current_value or 0) / total * 100 if total else 0
        ret = ticker_return_mtd(prices, p.ticker, as_of) if not prices.empty else None
        if ret is not None:
            kr_alpha_return += w / 100 * ret
            kr_alpha_cov += w
        kr_alpha_weight += w

    kospi_detail = (
        ticker_return_mtd_detail(prices, "069500", as_of)
        if not prices.empty
        else {"return_mtd": None, "quality": "no_prices"}
    )
    kospi200_mtd = kospi_detail.get("return_mtd")
    kr_alpha_mtd = round(kr_alpha_return, 4) if kr_alpha_cov > 0 else None
    excess_kospi = None
    if kr_alpha_mtd is not None and kospi200_mtd is not None:
        excess_kospi = round(kr_alpha_mtd - kospi200_mtd, 4)

    return {
        "actual_portfolio_return_mtd": actual_mtd,
        "actual_return_source": actual_source,
        "raw_nav_return_mtd": nav_detail.get("raw_nav_return_mtd"),
        "adjusted_nav_return_mtd": nav_detail.get("adjusted_nav_return_mtd"),
        "estimated_external_flow_mtd_krw": nav_detail.get("estimated_external_flow_mtd_krw"),
        "nav_capital_like_events": nav_detail.get("capital_like_events") or [],
        "nav_return_quality": nav_detail.get("quality"),
        "holdings_price_return_mtd": holdings.get("holdings_price_return_mtd"),
        "holdings_price_coverage_weight_pct": holdings.get("price_coverage_weight_pct"),
        "portfolio_value_krw": round(total),
        "kr_alpha_weight_pct": round(kr_alpha_weight, 2),
        "kr_alpha_return_mtd": kr_alpha_mtd,
        "kospi200_return_mtd": kospi200_mtd,
        "kospi200_return_quality": kospi_detail.get("quality"),
        "kospi200_detail": kospi_detail,
        "kr_alpha_excess_vs_kospi200": excess_kospi,
        "judgment_note": (
            "Do not treat raw_nav_return_mtd as trading alpha. "
            "Prefer holdings_price_return_mtd or adjusted_nav_return_mtd. "
            "No cashflow ledger exists — capital events are heuristic."
        ),
    }


def _read_trade_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_gate_opportunity_cost(
    output_dir: Path,
    data_dir: Path,
    as_of: str,
) -> list[dict[str, Any]]:
    """Trigger/theoretical buy vs executable — forward return shadow tracking."""
    theoretical = {r["ticker"]: r for r in _read_trade_csv(output_dir / "theoretical_trade_actions.csv")}
    executable = {r["ticker"]: r for r in _read_trade_csv(output_dir / "trade_actions.csv")}
    prices = load_combined_prices(data_dir)
    rows: list[dict[str, Any]] = []

    buy_like = {"Buy", "Buy-allowed", "buy", "buy-allowed"}
    for ticker, theo in theoretical.items():
        theo_action = theo.get("action", "")
        exec_row = executable.get(ticker, {})
        exec_action = exec_row.get("action", "")
        if theo_action not in buy_like:
            continue
        if exec_action in buy_like or exec_action == "Trim":
            continue

        norm = _normalize_ticker(ticker) or ticker
        row: dict[str, Any] = {
            "date": as_of[:10],
            "ticker": norm,
            "name": theo.get("name", ""),
            "theoretical_action": theo_action,
            "executable_action": exec_action,
            "blocked_by_gate": True,
        }
        for h in FORWARD_HORIZONS:
            row[f"forward_return_{h}d"] = (
                _forward_return(prices, norm, as_of, h) if not prices.empty else None
            )
        fr20 = row.get("forward_return_20d")
        if fr20 is not None:
            if fr20 > 0:
                row["gate_effect"] = "missed_upside"
            elif fr20 < 0:
                row["gate_effect"] = "avoided_loss"
            else:
                row["gate_effect"] = "neutral"
        else:
            row["gate_effect"] = "pending"
        rows.append(row)

    return rows


def build_grade_forward_returns(
    output_dir: Path,
    data_dir: Path,
    as_of: str,
) -> list[dict[str, Any]]:
    path = output_dir / "alpha_candidates.csv"
    if not path.exists():
        return []
    prices = load_combined_prices(data_dir)
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for cand in csv.DictReader(handle):
            ticker = _normalize_ticker(cand.get("ticker", "")) or ""
            grade = cand.get("grade", "")
            row: dict[str, Any] = {
                "date": as_of[:10],
                "ticker": ticker,
                "name": cand.get("name", ""),
                "grade": grade,
                "total_score": cand.get("total_score", ""),
            }
            for h in FORWARD_HORIZONS:
                row[f"forward_return_{h}d"] = (
                    _forward_return(prices, ticker, as_of, h) if ticker and not prices.empty else None
                )
            rows.append(row)

    return rows


def _grade_summary(forward_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_grade: dict[str, list[float]] = {}
    for row in forward_rows:
        g = str(row.get("grade") or "?")
        fr = row.get("forward_return_20d")
        if fr is not None:
            by_grade.setdefault(g, []).append(float(fr))
    summary = {
        g: round(sum(v) / len(v), 4) if v else None
        for g, v in sorted(by_grade.items())
    }
    top_grades = {r.get("grade") for r in forward_rows[:5]} if forward_rows else set()
    weak = bool(top_grades) and top_grades <= {"B", "C", "D", "F"}
    return {"grade_forward_return_20d_avg": summary, "weak_alpha_regime": weak}


def _satellite_proxy_returns(
    actual_mtd: float | None,
    gate_rows: list[dict[str, Any]],
    theoretical_buy_weight: float,
) -> dict[str, float | None]:
    """Shadow proxy — full curve requires 90-day CSV accumulation."""
    missed = 0.0
    avoided = 0.0
    for row in gate_rows:
        fr = row.get("forward_return_20d")
        if fr is None:
            continue
        w = theoretical_buy_weight / max(len(gate_rows), 1)
        if row.get("gate_effect") == "missed_upside":
            missed += w * float(fr)
        elif row.get("gate_effect") == "avoided_loss":
            avoided += abs(w * float(fr))

    executable = actual_mtd
    theoretical = None
    if actual_mtd is not None:
        theoretical = round(actual_mtd + missed - avoided, 4)

    return {
        "satellite_executable_return_mtd": executable,
        "satellite_theoretical_return_mtd": theoretical,
        "theoretical_minus_executable_return_mtd": (
            round(theoretical - executable, 4)
            if theoretical is not None and executable is not None else None
        ),
        "missed_upside_from_gate_mtd_proxy": round(missed, 4),
        "avoided_drawdown_from_gate_mtd_proxy": round(avoided, 4),
    }


_GAP_THRESHOLD_PCT = 0.5  # %p — ignore microscopic gaps
_CORE_SAA_EXCLUDED_GROUPS = frozenset({"kr_alpha"})


def compute_core_saa_gap_opportunity_cost(
    data_dir: Path,
    output_dir: Path,
    as_of: str,
    *,
    gap_threshold_pct: float = _GAP_THRESHOLD_PCT,
) -> dict[str, Any]:
    """target vs holdings gap × ticker MTD return — portfolio-level opportunity cost (shadow).

    Does NOT change Actual Buy Allowed, target_write, or any execution gate.
    """
    del output_dir  # reserved for future decision_log join; keep signature per spec
    target_path = data_dir / "target_portfolio.csv"
    pos_path = data_dir / "positions.csv"
    if not target_path.exists() or not pos_path.exists():
        return {
            "method": "target_weight_gap_x_ticker_price_return",
            "as_of": as_of[:10],
            "total_gap_pct": None,
            "opportunity_cost_mtd_pct": None,
            "by_bucket": [],
            "quality": "missing_inputs",
            "limitation": "target_portfolio.csv or positions.csv missing",
            "disclaimer": (
                "This does NOT change Actual Buy Allowed, target_write, or any execution gate. "
                "Diagnostic only."
            ),
        }

    targets = load_target_portfolio(target_path)
    positions = load_positions(pos_path)
    total_nav = sum(float(p.current_value or 0) for p in positions) or 0.0
    actual_w: dict[str, float] = {}
    for p in positions:
        t = _normalize_ticker(p.ticker) or p.ticker
        if total_nav > 0:
            actual_w[t] = actual_w.get(t, 0.0) + float(p.current_value or 0) / total_nav * 100.0

    prices = load_combined_prices(data_dir)
    bucket: dict[str, dict[str, Any]] = {}
    missing_price = False
    included_abs_gap = 0.0
    contrib_sum = 0.0
    contrib_ok = True
    details: list[dict[str, Any]] = []

    for row in targets:
        group = str(row.asset_group or "")
        if group in _CORE_SAA_EXCLUDED_GROUPS:
            continue
        ticker = _normalize_ticker(row.ticker) or row.ticker
        tw = float(row.target_weight or 0)
        aw = float(actual_w.get(ticker, 0.0))
        gap = round(tw - aw, 4)
        if abs(gap) < gap_threshold_pct:
            continue
        included_abs_gap += abs(gap)
        if str(ticker).upper() == "CASH":
            ret = 0.0
        else:
            ret = ticker_return_mtd(prices, ticker, as_of) if not prices.empty else None
        contrib: float | None
        if ret is None:
            contrib = None
            missing_price = True
            contrib_ok = False
        else:
            # gap %p × return % → portfolio %p contribution
            contrib = round((gap / 100.0) * float(ret), 6)
            contrib_sum += contrib

        details.append({
            "ticker": ticker,
            "name": row.name,
            "asset_group": group,
            "target_weight_pct": round(tw, 4),
            "actual_weight_pct": round(aw, 4),
            "gap_pct": gap,
            "ticker_return_mtd": ret,
            "contrib_pct": contrib,
        })

        b = bucket.setdefault(group, {
            "asset_group": group,
            "gap_pct": 0.0,
            "ticker_return_mtd": None,
            "contrib_pct": None,
            "members": 0,
            "priced_members": 0,
            "reason": None,
        })
        b["gap_pct"] = round(float(b["gap_pct"]) + gap, 4)
        b["members"] = int(b["members"]) + 1
        if ret is not None and contrib is not None:
            b["priced_members"] = int(b["priced_members"]) + 1
            prev_c = b["contrib_pct"]
            b["contrib_pct"] = round((0.0 if prev_c is None else float(prev_c)) + contrib, 6)
            # weight returns by |gap| for bucket display
            prev_r = b.get("_ret_gap_sum", 0.0)
            prev_g = b.get("_ret_gap_abs", 0.0)
            b["_ret_gap_sum"] = float(prev_r) + float(ret) * abs(gap)
            b["_ret_gap_abs"] = float(prev_g) + abs(gap)
        else:
            b["reason"] = "insufficient_price_history_or_missing"

    by_bucket: list[dict[str, Any]] = []
    for group, b in sorted(bucket.items(), key=lambda kv: -abs(float(kv[1]["gap_pct"]))):
        ret_abs = float(b.pop("_ret_gap_abs", 0.0) or 0.0)
        ret_sum = float(b.pop("_ret_gap_sum", 0.0) or 0.0)
        if ret_abs > 0:
            b["ticker_return_mtd"] = round(ret_sum / ret_abs, 4)
        elif b.get("reason") is None and int(b.get("priced_members") or 0) == 0:
            b["reason"] = "insufficient_price_history_or_missing"
            b["contrib_pct"] = None
        by_bucket.append({
            "asset_group": b["asset_group"],
            "gap_pct": b["gap_pct"],
            "ticker_return_mtd": b["ticker_return_mtd"],
            "contrib_pct": b["contrib_pct"],
            "reason": b.get("reason"),
        })

    opportunity = round(contrib_sum, 4) if contrib_ok and details else None
    if details and not contrib_ok:
        opportunity = None  # conservative: any missing price → total null

    quality = "shadow_diagnostic_only"
    if not details:
        quality = "no_material_gaps"
    elif missing_price:
        quality = "partial_price_coverage"

    return {
        "method": "target_weight_gap_x_ticker_price_return",
        "as_of": as_of[:10],
        "total_gap_pct": round(included_abs_gap, 4) if details else 0.0,
        "opportunity_cost_mtd_pct": opportunity,
        "by_bucket": by_bucket,
        "by_ticker": details,
        "gap_threshold_pct": gap_threshold_pct,
        "excluded_asset_groups": sorted(_CORE_SAA_EXCLUDED_GROUPS),
        "quality": quality,
        "limitation": (
            "짧은 표본·가격 결측 시 개별 항목 null. "
            "전체 합계도 결측 항목이 있으면 보수적으로 null 처리. "
            "사후 shadow upper-bound — 슬리피지·타이밍 미반영."
        ),
        "disclaimer": (
            "This does NOT change Actual Buy Allowed, target_write, or any execution gate. "
            "Diagnostic only."
        ),
    }


INCEPTION_DATE_DEFAULT = "2026-06-17"  # decision_log.jsonl first entry


def compute_core_saa_gap_opportunity_cost_since_inception(
    data_dir: Path,
    output_dir: Path,
    as_of: str,
    *,
    inception_date: str = INCEPTION_DATE_DEFAULT,
    gap_threshold_pct: float = _GAP_THRESHOLD_PCT,
) -> dict[str, Any]:
    """Today's target vs holdings gap × cumulative return since inception (approximation).

    Assumes today's gap snapshot persisted since inception — upper-bound shadow estimate.
    Does NOT change Actual Buy Allowed / target_write / any execution gate.
    """
    del output_dir
    inception = inception_date[:10]
    as_of_day = as_of[:10]
    target_path = data_dir / "target_portfolio.csv"
    pos_path = data_dir / "positions.csv"
    empty = {
        "method": "target_weight_gap_x_ticker_cumulative_return_since_inception",
        "inception_date": inception,
        "as_of": as_of_day,
        "total_gap_pct": None,
        "opportunity_cost_since_inception_pct": None,
        "by_bucket": [],
        "by_ticker": [],
        "quality": "missing_inputs",
        "limitation": (
            "오늘 스냅샷 갭이 inception 이후 계속 유지됐다고 가정한 근사치(상한선 성격). "
            "실제 일별 갭 변화·슬리피지·매매 타이밍 미반영."
        ),
        "disclaimer": (
            "This does NOT change Actual Buy Allowed, target_write, or any execution gate. "
            "Diagnostic only — approximation."
        ),
    }
    if not target_path.exists() or not pos_path.exists():
        return empty

    targets = load_target_portfolio(target_path)
    positions = load_positions(pos_path)
    total_nav = sum(float(p.current_value or 0) for p in positions) or 0.0
    actual_w: dict[str, float] = {}
    for p in positions:
        t = _normalize_ticker(p.ticker) or p.ticker
        if total_nav > 0:
            actual_w[t] = actual_w.get(t, 0.0) + float(p.current_value or 0) / total_nav * 100.0

    prices = load_combined_prices(data_dir)
    bucket: dict[str, dict[str, Any]] = {}
    missing_price = False
    missing_inception = False
    included_abs_gap = 0.0
    contrib_sum = 0.0
    contrib_ok = True
    details: list[dict[str, Any]] = []

    for row in targets:
        group = str(row.asset_group or "")
        if group in _CORE_SAA_EXCLUDED_GROUPS:
            continue
        ticker = _normalize_ticker(row.ticker) or row.ticker
        tw = float(row.target_weight or 0)
        aw = float(actual_w.get(ticker, 0.0))
        gap = round(tw - aw, 4)
        if abs(gap) < gap_threshold_pct:
            continue
        included_abs_gap += abs(gap)

        if str(ticker).upper() == "CASH":
            ret = 0.0
            ret_quality = "cash_fixed_zero"
        else:
            detail = (
                ticker_cum_return_detail(prices, ticker, inception, as_of_day)
                if not prices.empty
                else {"return_pct": None, "quality": "no_prices"}
            )
            ret = detail.get("return_pct")
            ret_quality = str(detail.get("quality") or "unknown")
            if ret_quality == "missing_inception_price":
                missing_inception = True

        contrib: float | None
        if ret is None:
            contrib = None
            missing_price = True
            contrib_ok = False
        else:
            contrib = round((gap / 100.0) * float(ret), 6)
            contrib_sum += float(contrib)

        details.append({
            "ticker": ticker,
            "name": row.name,
            "asset_group": group,
            "target_weight_pct": round(tw, 4),
            "actual_weight_pct": round(aw, 4),
            "gap_pct": gap,
            "ticker_cum_return_since_inception": ret,
            "return_quality": ret_quality,
            "contrib_pct": contrib,
        })

        b = bucket.setdefault(group, {
            "asset_group": group,
            "gap_pct": 0.0,
            "ticker_cum_return_since_inception": None,
            "contrib_pct": None,
            "members": 0,
            "priced_members": 0,
            "reason": None,
        })
        b["gap_pct"] = round(float(b["gap_pct"]) + gap, 4)
        b["members"] = int(b["members"]) + 1
        if ret is not None and contrib is not None:
            b["priced_members"] = int(b["priced_members"]) + 1
            prev_c = b["contrib_pct"]
            b["contrib_pct"] = round((0.0 if prev_c is None else float(prev_c)) + float(contrib), 6)
            prev_r = b.get("_ret_gap_sum", 0.0)
            prev_g = b.get("_ret_gap_abs", 0.0)
            b["_ret_gap_sum"] = float(prev_r) + float(ret) * abs(gap)
            b["_ret_gap_abs"] = float(prev_g) + abs(gap)
        else:
            b["reason"] = "insufficient_price_history_or_missing"

    by_bucket: list[dict[str, Any]] = []
    for group, b in sorted(bucket.items(), key=lambda kv: -abs(float(kv[1]["gap_pct"]))):
        ret_abs = float(b.pop("_ret_gap_abs", 0.0) or 0.0)
        ret_sum = float(b.pop("_ret_gap_sum", 0.0) or 0.0)
        if ret_abs > 0:
            b["ticker_cum_return_since_inception"] = round(ret_sum / ret_abs, 4)
        elif b.get("reason") is None and int(b.get("priced_members") or 0) == 0:
            b["reason"] = "insufficient_price_history_or_missing"
            b["contrib_pct"] = None
        by_bucket.append({
            "asset_group": b["asset_group"],
            "gap_pct": b["gap_pct"],
            "ticker_cum_return_since_inception": b["ticker_cum_return_since_inception"],
            "contrib_pct": b["contrib_pct"],
            "reason": b.get("reason"),
        })

    opportunity = round(contrib_sum, 4) if contrib_ok and details else None
    if details and not contrib_ok:
        opportunity = None

    quality = "shadow_diagnostic_only"
    if not details:
        quality = "no_material_gaps"
    elif missing_inception:
        quality = "missing_inception_price"
    elif missing_price:
        quality = "partial_price_coverage"

    return {
        "method": "target_weight_gap_x_ticker_cumulative_return_since_inception",
        "inception_date": inception,
        "as_of": as_of_day,
        "total_gap_pct": round(included_abs_gap, 4) if details else 0.0,
        "opportunity_cost_since_inception_pct": opportunity,
        "by_bucket": by_bucket,
        "by_ticker": details,
        "gap_threshold_pct": gap_threshold_pct,
        "excluded_asset_groups": sorted(_CORE_SAA_EXCLUDED_GROUPS),
        "quality": quality,
        "limitation": (
            "오늘 스냅샷 갭이 inception 이후 계속 유지됐다고 가정한 근사치(상한선 성격). "
            "실제 일별 갭 변화·슬리피지·매매 타이밍 미반영."
        ),
        "disclaimer": (
            "This does NOT change Actual Buy Allowed, target_write, or any execution gate. "
            "Diagnostic only — approximation."
        ),
    }


def build_alpha_performance_dashboard(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    run_id: str = "",
) -> dict[str, Any]:
    core = compute_core_saa_benchmark_mtd(data_dir, as_of)
    actual = compute_actual_and_kr_alpha_mtd(data_dir, output_dir, as_of)
    legacy_saa = compute_saa_proxy_returns(data_dir, as_of)
    gap_oc = compute_core_saa_gap_opportunity_cost(data_dir, output_dir, as_of)
    gap_si = compute_core_saa_gap_opportunity_cost_since_inception(data_dir, output_dir, as_of)

    gate_rows = build_gate_opportunity_cost(output_dir, data_dir, as_of)
    grade_rows = build_grade_forward_returns(output_dir, data_dir, as_of)
    grade_stats = _grade_summary(grade_rows)

    actual_mtd = actual.get("actual_portfolio_return_mtd")
    core_mtd = core.get("core_saa_return_mtd")
    excess_core = None
    if actual_mtd is not None and core_mtd is not None:
        excess_core = round(float(actual_mtd) - float(core_mtd), 4)

    theo_buys = _read_trade_csv(output_dir / "theoretical_trade_actions.csv")
    buy_weight = sum(
        float(r.get("allowed_size_pct") or 0)
        for r in theo_buys
        if r.get("action") in {"Buy-allowed", "Buy"}
    )
    satellite = _satellite_proxy_returns(actual_mtd, gate_rows, buy_weight)

    executable_buy_count = sum(
        1 for r in _read_trade_csv(output_dir / "trade_actions.csv")
        if r.get("action") in {"Buy", "Buy-allowed"}
    )

    return {
        "mode": "shadow_diagnostic_only",
        "authority": "none",
        "diagnostic_only": True,
        "execution_authority": "v1.0.2",
        "as_of": as_of[:10],
        "run_id": run_id,
        "disclaimer": ALPHA_DASHBOARD_DISCLAIMER,
        "metrics": {
            "core_saa_return_mtd": core_mtd,
            "legacy_defensive_balanced_saa_mtd": legacy_saa.get("benchmark_saa_return_mtd"),
            "actual_portfolio_return_mtd": actual_mtd,
            "actual_return_source": actual.get("actual_return_source"),
            "raw_nav_return_mtd": actual.get("raw_nav_return_mtd"),
            "adjusted_nav_return_mtd": actual.get("adjusted_nav_return_mtd"),
            "holdings_price_return_mtd": actual.get("holdings_price_return_mtd"),
            "estimated_external_flow_mtd_krw": actual.get("estimated_external_flow_mtd_krw"),
            "nav_return_quality": actual.get("nav_return_quality"),
            "kospi200_return_quality": actual.get("kospi200_return_quality"),
            **satellite,
            "excess_return_vs_core_mtd": excess_core,
            "kr_alpha_return_mtd": actual.get("kr_alpha_return_mtd"),
            "kr_alpha_excess_vs_kospi200_mtd": actual.get("kr_alpha_excess_vs_kospi200"),
            "kospi200_return_mtd": actual.get("kospi200_return_mtd"),
            "core_saa_gap_opportunity_cost_mtd": gap_oc.get("opportunity_cost_mtd_pct"),
            "core_saa_total_gap_pct": gap_oc.get("total_gap_pct"),
            "core_saa_gap_opportunity_cost_since_inception": gap_si.get(
                "opportunity_cost_since_inception_pct"
            ),
            "core_saa_gap_inception_date": gap_si.get("inception_date"),
            "executable_buy_count": executable_buy_count,
            "theoretical_buy_count": sum(
                1 for r in theo_buys if r.get("action") in {"Buy-allowed", "Buy"}
            ),
            **grade_stats,
        },
        "core_saa_gap_opportunity_cost": gap_oc,
        "core_saa_gap_opportunity_cost_since_inception": gap_si,
        "nav_capital_like_events": actual.get("nav_capital_like_events") or [],
        "judgment_note": actual.get("judgment_note"),
        "core_benchmark_detail": core,
        "actual_detail": actual,
        "gate_opportunity_cost_count": len(gate_rows),
        "grade_forward_count": len(grade_rows),
        "report_lines": [
            (
                f"Core SAA MTD {core_mtd}% vs Actual {actual_mtd}% "
                f"(source={actual.get('actual_return_source')}) · excess {excess_core}%p"
            ),
            (
                f"raw NAV MTD {actual.get('raw_nav_return_mtd')}% · "
                f"adjusted NAV MTD {actual.get('adjusted_nav_return_mtd')}% · "
                f"external_flow≈{actual.get('estimated_external_flow_mtd_krw')} KRW"
            ),
            (
                f"kr_alpha MTD {actual.get('kr_alpha_return_mtd')}% vs KOSPI200 "
                f"{actual.get('kospi200_return_mtd')} "
                f"(quality={actual.get('kospi200_return_quality')}) · "
                f"excess {actual.get('kr_alpha_excess_vs_kospi200')}%p"
            ),
            (
                f"Core SAA gap opportunity cost MTD "
                f"{gap_oc.get('opportunity_cost_mtd_pct')}%p "
                f"(total gap {gap_oc.get('total_gap_pct')}%p) — shadow only"
            ),
            (
                f"Core SAA gap opportunity cost since {gap_si.get('inception_date')} "
                f"{gap_si.get('opportunity_cost_since_inception_pct')}%p "
                f"(approx; quality={gap_si.get('quality')}) — shadow only"
            ),
            f"Gate blocked buys: {len(gate_rows)} · executable buys: {executable_buy_count}",
            "shadow only — not investment advice; raw NAV ≠ trading alpha",
        ],
    }


def write_alpha_performance_dashboard(doc: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _append_csv(path: Path, row: dict[str, Any], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in fieldnames})


DASHBOARD_CSV_FIELDS = [
    "date", "run_id",
    "core_saa_return_mtd", "actual_portfolio_return_mtd",
    "satellite_executable_return_mtd", "satellite_theoretical_return_mtd",
    "excess_return_vs_core_mtd", "kr_alpha_excess_vs_kospi200_mtd",
    "executable_buy_count", "theoretical_buy_count", "weak_alpha_regime",
]

GATE_CSV_FIELDS = [
    "date", "ticker", "name", "theoretical_action", "executable_action",
    "forward_return_5d", "forward_return_20d", "forward_return_60d", "forward_return_120d",
    "gate_effect",
]

GRADE_CSV_FIELDS = [
    "date", "ticker", "name", "grade", "total_score",
    "forward_return_5d", "forward_return_20d", "forward_return_60d", "forward_return_120d",
]


_GAP_DATA_TRUST = {
    "data_trust": "untrusted_prices_history_incident",
    "data_trust_note": (
        "Do not use for ops judgment until prices_history.csv is restored/revalidated. "
        "D1 write corruption incident 2026-07-09."
    ),
}


def _mark_gap_data_untrusted(doc: dict[str, Any]) -> dict[str, Any]:
    """Tag gap OC artifacts — not for ops judgment after D1 incident."""
    from datetime import datetime, timezone

    out = dict(doc)
    out.update(_GAP_DATA_TRUST)
    out["data_trust_marked_at"] = datetime.now(timezone.utc).isoformat()
    return out


def write_alpha_performance_outputs(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    run_id: str = "",
) -> dict[str, Any]:
    nav_snapshot = build_nav_snapshot(data_dir, as_of=as_of, run_id=run_id)
    append_portfolio_nav_log(output_dir / "portfolio_nav_log.csv", nav_snapshot)

    enrich_gate_opportunity_cost_csv(output_dir / "alpha_gate_opportunity_cost.csv", data_dir)

    doc = build_alpha_performance_dashboard(data_dir, output_dir, as_of=as_of, run_id=run_id)
    doc["nav_snapshot"] = nav_snapshot
    write_alpha_performance_dashboard(doc, output_dir / "alpha_performance_dashboard.json")

    gap_oc = _mark_gap_data_untrusted(doc.get("core_saa_gap_opportunity_cost") or {})
    gap_si = _mark_gap_data_untrusted(doc.get("core_saa_gap_opportunity_cost_since_inception") or {})
    (output_dir / "core_saa_gap_opportunity_cost.json").write_text(
        json.dumps(gap_oc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    (output_dir / "core_saa_gap_opportunity_cost_since_inception.json").write_text(
        json.dumps(gap_si, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    m = doc.get("metrics") or {}
    _append_csv(output_dir / "alpha_performance_dashboard.csv", {
        "date": as_of[:10],
        "run_id": run_id,
        **{k: m.get(k, "") for k in DASHBOARD_CSV_FIELDS if k not in {"date", "run_id"}},
    }, DASHBOARD_CSV_FIELDS)

    for row in build_gate_opportunity_cost(output_dir, data_dir, as_of):
        _append_csv(output_dir / "alpha_gate_opportunity_cost.csv", row, GATE_CSV_FIELDS)

    for row in build_grade_forward_returns(output_dir, data_dir, as_of):
        _append_csv(output_dir / "alpha_grade_forward_return.csv", row, GRADE_CSV_FIELDS)

    return doc
