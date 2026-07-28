"""Phase AR-2 — Asset-specific accumulation timing (shadow only, no execution authority)."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.models import GapRow, MarketIndicators, TriggerAlert, TriggerStatus
from src.timing.ar21_input_quality import (
    assess_input_quality,
    build_timing_execution_note,
    score_duration_subcomponents,
    timing_stale_execution_note,
)

AR2_DISCLAIMER = (
    "AR-2 timing score is shadow-only. It does not create buy permission. "
    "Execution remains controlled by gate, dry-run, execution_scope, AR-1 throttle, "
    "and final_execution_decision."
)


@dataclass
class TimingScoreResult:
    timing_score: int | None
    timing_status: str
    positive_signals: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    recommended_note: str = ""


def load_accumulation_timing_config(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "accumulation_timing.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _read_market_history(data_dir: Path, n: int = 5) -> list[dict[str, str]]:
    path = data_dir / "market_indicators.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows[-n:] if rows else []


def _read_macro_tier2(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "macro_tier2.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {}
    last = rows[-1]
    out: dict[str, Any] = {}
    for k, v in last.items():
        if k == "date":
            out[k] = v
            continue
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            out[k] = v
    return out


def _sp500_drawdown(market: MarketIndicators) -> float | None:
    if market.sp500_recent_high <= 0 or market.sp500 <= 0:
        return None
    return round((market.sp500 / market.sp500_recent_high - 1) * 100, 2)


def _vix_change(history: list[dict[str, str]], days: int = 3) -> float | None:
    if len(history) < days + 1:
        return None
    try:
        recent = float(history[-1].get("vix") or 0)
        past = float(history[-1 - days].get("vix") or 0)
    except (TypeError, ValueError):
        return None
    if past <= 0:
        return None
    return round(recent - past, 2)


def _korea_10y_change(history: list[dict[str, str]], days: int = 5) -> float | None:
    if len(history) < days + 1:
        return None
    try:
        recent = float(history[-1].get("korea_10y") or 0)
        past = float(history[-1 - days].get("korea_10y") or 0)
    except (TypeError, ValueError):
        return None
    return round(recent - past, 3)


def _alert_map(alerts: list[TriggerAlert]) -> dict[str, TriggerAlert]:
    return {a.key: a for a in alerts}


def _status_from_score(score: int, blockers: list[str], thresholds: dict[str, int]) -> str:
    if blockers:
        major = any(
            b for b in blockers
            if "panic" in b.lower() or "block" in b.lower() or "crisis" in b.lower()
        )
        if major or score < thresholds.get("wait_min", 30):
            return "Block"
    if score >= thresholds.get("ready_min", 70):
        return "Ready"
    if score >= thresholds.get("watch_min", 50):
        return "Watch"
    if score >= thresholds.get("wait_min", 30):
        return "Wait"
    return "Block"


def score_global_beta(
    market: MarketIndicators,
    alerts: list[TriggerAlert],
    history: list[dict[str, str]],
    macro: dict[str, Any],
    rules: dict[str, Any],
) -> TimingScoreResult:
    score = 42
    positive: list[str] = []
    blockers: list[str] = []
    am = _alert_map(alerts)
    mt = rules.get("market_triggers") or {}
    vix_rules = mt.get("vix") or {}

    sp_dd = _sp500_drawdown(market)
    if sp_dd is not None and -15 <= sp_dd <= -5:
        score += 18
        positive.append(f"S&P500 drawdown {sp_dd:.1f}% (buy zone)")
    elif sp_dd is not None and sp_dd < -15:
        score += 8
        positive.append(f"S&P500 deep drawdown {sp_dd:.1f}% — caution sizing")

    vix = market.vix
    if 20 <= vix <= 35:
        score += 10
        positive.append(f"VIX {vix:.1f} elevated but not panic")
    elif vix < 20:
        score += 4
        positive.append(f"VIX {vix:.1f} calm")

    vix_chg = _vix_change(history, 3)
    if vix_chg is not None and vix_chg <= -1.5:
        score += 12
        positive.append(f"VIX 3D change {vix_chg:+.1f} (fear easing)")
    elif vix_chg is not None and vix_chg <= -0.5:
        score += 6
        positive.append(f"VIX 3D change {vix_chg:+.1f}")

    if vix >= float(vix_rules.get("panic_above", 30)):
        blockers.append(f"VIX panic {vix:.1f}")
        score = min(score, 25)
    elif am.get("vix") and am["vix"].status == TriggerStatus.RISK:
        blockers.append(am["vix"].detail)
        score = min(score, 28)

    usd = am.get("usdkrw")
    if usd and usd.status == TriggerStatus.RISK:
        blockers.append(usd.detail)
        score = min(score, 30)
    elif usd and usd.status == TriggerStatus.INACTIVE:
        score += 6
        positive.append("USD/KRW stable")

    hy = macro.get("hy_oas_bp")
    if isinstance(hy, (int, float)) and hy >= 400:
        blockers.append(f"HY OAS {hy:.0f}bp credit stress")
        score = min(score, 28)

    note = "S&P500 조정 후 VIX 둔화 대기" if score < 70 else "global beta accumulation window"
    return TimingScoreResult(
        timing_score=max(0, min(100, score)),
        timing_status="",
        positive_signals=positive,
        blockers=blockers,
        recommended_note=note,
    )


def score_duration_bond(
    market: MarketIndicators,
    history: list[dict[str, str]],
    macro: dict[str, Any],
    alerts: list[TriggerAlert],
) -> TimingScoreResult:
    score = 38
    positive: list[str] = []
    blockers: list[str] = []
    am = _alert_map(alerts)

    kr_chg = _korea_10y_change(history, 5)
    if kr_chg is not None and kr_chg <= 0:
        score += 14
        positive.append(f"Korea 10Y 5D change {kr_chg:+.2f}pp (easing)")
    elif kr_chg is not None and kr_chg <= 0.15:
        score += 8
        positive.append(f"Korea 10Y rise slowing ({kr_chg:+.2f}pp/5D)")
    elif kr_chg is not None and kr_chg > 0.25:
        blockers.append(f"Korea 10Y rising {kr_chg:+.2f}pp/5D")
        score = min(score, 32)

    cpi_us = macro.get("cpi_us_yoy")
    if isinstance(cpi_us, (int, float)) and cpi_us <= 3.5:
        score += 8
        positive.append(f"US CPI YoY {cpi_us:.1f}% moderating")
    elif isinstance(cpi_us, (int, float)) and cpi_us >= 4.5:
        blockers.append(f"US CPI YoY {cpi_us:.1f}% reinflation risk")
        score = min(score, 35)

    if am.get("oil_shock"):
        blockers.append(am["oil_shock"].detail)
        score = min(score, 30)

    spread = macro.get("yield_spread_2y10y")
    if isinstance(spread, (int, float)) and spread >= 0:
        score += 6
        positive.append(f"2Y-10Y spread {spread:.2f}")

    note = "금리 고점 확인 전" if score < 55 else "duration bond window opening"
    return TimingScoreResult(
        timing_score=max(0, min(100, score)),
        timing_status="",
        positive_signals=positive,
        blockers=blockers,
        recommended_note=note,
    )


def score_hedge_alt(
    market: MarketIndicators,
    macro: dict[str, Any],
    alerts: list[TriggerAlert],
) -> TimingScoreResult:
    score = 45
    positive: list[str] = []
    blockers: list[str] = []
    am = _alert_map(alerts)

    real_kr = macro.get("real_rate_kr")
    if isinstance(real_kr, (int, float)) and real_kr <= 0:
        score += 14
        positive.append(f"KR real rate {real_kr:.1f}% (gold-friendly)")
    elif isinstance(real_kr, (int, float)) and real_kr <= 1:
        score += 6

    usd = am.get("usdkrw")
    if usd and usd.status in {TriggerStatus.INACTIVE, TriggerStatus.WATCH}:
        score += 8
        positive.append("USD/KRW not in spike")
    if usd and usd.status == TriggerStatus.RISK:
        blockers.append(usd.detail)
        score = min(score, 32)

    vix = am.get("vix")
    if vix and vix.status in {TriggerStatus.WATCH, TriggerStatus.RISK}:
        score += 6
        positive.append("Risk-off supports gold hedge")

    if market.gold > 0 and market.gold >= 4200:
        blockers.append(f"Gold price {market.gold:.0f} — short-term overheating watch")
        score = min(score, 45)

    if usd and usd.status == TriggerStatus.RISK and market.korea_10y > 2.5:
        blockers.append("USD spike + rates elevated")
        score = min(score, 28)

    note = "금/실질금리 조건 확인" if score < 60 else "hedge accumulation watch"
    return TimingScoreResult(
        timing_score=max(0, min(100, score)),
        timing_status="",
        positive_signals=positive,
        blockers=blockers,
        recommended_note=note,
    )


def score_income_alt(
    market: MarketIndicators,
    history: list[dict[str, str]],
    macro: dict[str, Any],
    alerts: list[TriggerAlert],
) -> TimingScoreResult:
    score = 35
    positive: list[str] = []
    blockers: list[str] = []
    am = _alert_map(alerts)

    kr_chg = _korea_10y_change(history, 5)
    if kr_chg is not None and kr_chg <= 0.05:
        score += 16
        positive.append("Rate rise paused — REIT/dividend friendly")
    elif kr_chg is not None and kr_chg > 0.2:
        blockers.append(f"Rates still rising ({kr_chg:+.2f}pp/5D)")
        score = min(score, 32)

    sp_dd = _sp500_drawdown(market)
    if sp_dd is not None and -12 <= sp_dd <= -3:
        score += 8
        positive.append(f"Income equity drawdown {sp_dd:.1f}%")

    hy = macro.get("hy_oas_bp")
    if isinstance(hy, (int, float)) and hy < 350:
        score += 8
        positive.append(f"HY OAS {hy:.0f}bp — credit OK")
    elif isinstance(hy, (int, float)) and hy >= 450:
        blockers.append(f"HY OAS {hy:.0f}bp credit stress")
        score = min(score, 28)

    if am.get("vix") and am["vix"].status == TriggerStatus.RISK:
        blockers.append("VIX panic — income/reits blocked")
        score = min(score, 25)

    note = "금리 안정 전" if score < 50 else "income sleeve watch"
    return TimingScoreResult(
        timing_score=max(0, min(100, score)),
        timing_status="",
        positive_signals=positive,
        blockers=blockers,
        recommended_note=note,
    )


def _load_group_gaps(output_dir: Path) -> dict[str, dict[str, float]]:
    gaps: dict[str, dict[str, float]] = {}
    path = output_dir / "portfolio_gap.csv"
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                gaps[row["asset_group"]] = {
                    "current": float(row.get("current") or 0),
                    "target": float(row.get("target") or 0),
                    "gap": float(row.get("gap") or 0),
                }
        return gaps
    final = output_dir / "final_execution_decision.json"
    if final.exists():
        data = json.loads(final.read_text(encoding="utf-8"))
        for g in data.get("group_gaps") or []:
            if isinstance(g, dict):
                gaps[str(g["asset_group"])] = {
                    "current": float(g.get("current") or 0),
                    "target": float(g.get("target") or 0),
                    "gap": float(g.get("gap") or 0),
                }
    return gaps


def _gap_by_timing_sleeve(
    group_gaps: dict[str, dict[str, float]],
    sleeve: str,
    config: dict[str, Any],
    gap_rows: list[GapRow] | None = None,
) -> float:
    """Positive gap = underweight (need to buy)."""
    if sleeve == "duration_bond" and gap_rows:
        tickers = (config.get("representative_assets") or {}).get("duration_bond") or []
        total = sum(
            r.gap for r in gap_rows
            if r.ticker in {str(t).zfill(6) for t in tickers} and r.gap > 0
        )
        return round(total, 2)
    g = group_gaps.get(sleeve, {})
    return max(0.0, float(g.get("gap", 0)))


def _overweight_gap(group_gaps: dict[str, dict[str, float]], group: str) -> float:
    g = group_gaps.get(group, {})
    return max(0.0, -float(g.get("gap", 0)))


def _recommended_ticker(
    sleeve: str,
    gap_rows: list[GapRow],
    config: dict[str, Any],
) -> tuple[str, str]:
    primary = (config.get("recommended_primary") or {}).get(sleeve)
    if sleeve == "duration_bond":
        candidates = (config.get("representative_assets") or {}).get("duration_bond") or []
        by_ticker = {r.ticker: r for r in gap_rows}
        best = None
        for t in candidates:
            row = by_ticker.get(str(t).zfill(6))
            if row and row.gap > 0:
                if best is None or row.gap > best.gap:
                    best = row
        if best:
            return best.ticker, best.name
        if primary:
            return str(primary).zfill(6), primary
        return "148070", "KIWOOM 국고채10년"

    group_map = {
        "global_beta": "global_beta",
        "hedge_alt": "hedge_alt",
        "income_alt": "income_alt",
        "cash_short_bond": "cash_short_bond",
    }
    ag = group_map.get(sleeve, sleeve)
    candidates = [r for r in gap_rows if r.asset_group == ag and r.gap > 0 and r.ticker != "CASH"]
    if candidates:
        top = max(candidates, key=lambda r: r.gap)
        return top.ticker, top.name
    if primary:
        tickers = (config.get("representative_assets") or {}).get(sleeve) or []
        name = primary
        for r in gap_rows:
            if r.ticker == str(primary).zfill(6):
                name = r.name
                break
        return str(primary).zfill(6), name
    return "", ""


def _enrich_timing_row(
    row: dict[str, Any],
    *,
    data_dir: Path,
    config: dict[str, Any],
    macro: dict[str, Any],
    data_gate: str,
    execution_scope: str,
    dry_run_days: int,
    dry_run_required: int,
    timing_blockers: list[str],
    execution_blockers: list[str],
) -> dict[str, Any]:
    sleeve = str(row.get("asset_group", ""))
    iq = assess_input_quality(data_dir, sleeve, config, macro=macro)
    row.update(iq)
    row["execution_prohibited_stale"] = bool(iq.get("execution_prohibited_stale"))
    if row["execution_prohibited_stale"]:
        row["executable"] = False
        row["execution_status"] = "prohibited_stale_input"
        row["timing_execution_note"] = timing_stale_execution_note(iq.get("stale_inputs"))
    else:
        row["timing_execution_note"] = build_timing_execution_note(
            timing_status=str(row.get("timing_status", "")),
            execution_status=str(row.get("execution_status", "")),
            executable=bool(row.get("executable")),
            data_gate=data_gate,
            dry_run_days=dry_run_days,
            dry_run_required=dry_run_required,
            execution_scope=execution_scope,
        )
    row["timing_blockers"] = timing_blockers
    row["execution_blockers"] = execution_blockers
    if iq.get("execution_prohibited_stale"):
        blockers = list(row.get("execution_blockers") or [])
        blockers.append("stale_critical_input")
        row["execution_blockers"] = blockers
    if row.get("timing_status") in {"Ready", "Watch"} and not row.get("executable"):
        row["ready_or_watch_but_blocked"] = True
    else:
        row["ready_or_watch_but_blocked"] = False
    if row.get("timing_status") == "Watch":
        row["watch_not_buy_reminder"] = (config.get("readiness_notes") or {}).get(
            "watch_not_buy",
            "Timing Watch ≠ Buy.",
        )
    return row


def _duration_subcomponents(
    market: MarketIndicators,
    history: list[dict[str, str]],
    macro: dict[str, Any],
    alerts: list[TriggerAlert],
    config: dict[str, Any],
    data_dir: Path,
) -> dict[str, Any]:
    base = score_duration_bond(market, history, macro, alerts)
    kr_chg = _korea_10y_change(history, 5)
    kr_score = min(100, max(0, (base.timing_score or 40) + (8 if kr_chg is not None and kr_chg <= 0 else 0)))
    us_score = min(100, max(0, (base.timing_score or 40) - 6))
    spread = macro.get("yield_spread_2y10y")
    if isinstance(spread, (int, float)) and spread >= 0.2:
        us_score += 6
    kr_iq = assess_input_quality(data_dir, "duration_kr", config, macro=macro)
    us_iq = assess_input_quality(data_dir, "duration_us", config, macro=macro)
    return score_duration_subcomponents(
        kr_score=kr_score,
        us_score=us_score,
        kr_signals=[s for s in base.positive_signals if "Korea" in s or "korea" in s.lower()],
        us_signals=[f"2Y-10Y spread {spread}" if spread else "US duration proxy"],
        kr_stale=kr_iq["stale_inputs"],
        us_stale=us_iq["stale_inputs"],
    )


def build_execution_status(
    *,
    data_gate: str,
    execution_scope: str,
    dry_run_days: int,
    dry_run_required: int,
    throttle_meta: dict[str, Any],
    timing_status: str,
    underweight_gap: float,
) -> dict[str, Any]:
    blockers: list[str] = []
    blocked_by_gate = data_gate != "GREEN"
    blocked_by_dry_run = dry_run_days < dry_run_required
    blocked_by_scope = execution_scope in {"NO_TRADE", ""} or (
        data_gate == "RED"
    )
    blocked_by_throttle = throttle_meta.get("gate_allowed") is False

    if blocked_by_gate:
        blockers.append(f"data_gate {data_gate}")
    if blocked_by_dry_run:
        blockers.append(f"dry-run {dry_run_days}/{dry_run_required}")
    if blocked_by_scope:
        blockers.append(f"execution_scope {execution_scope}")
    if blocked_by_throttle:
        blockers.append(throttle_meta.get("block_reason") or "core throttle blocked")

    if timing_status in {"Block", "Wait", "ReduceOnly", "Park", "FundingSource"}:
        blockers.append(f"timing_status {timing_status}")
    if underweight_gap <= 0 and timing_status not in {"FundingSource", "Park", "ReduceOnly"}:
        blockers.append("not underweight")

    executable = (
        not blocked_by_gate
        and not blocked_by_dry_run
        and not blocked_by_scope
        and not blocked_by_throttle
        and timing_status == "Ready"
        and underweight_gap > 0
    )

    return {
        "blocked_by_gate": blocked_by_gate,
        "blocked_by_dry_run": blocked_by_dry_run,
        "blocked_by_scope": blocked_by_scope,
        "blocked_by_throttle": blocked_by_throttle,
        "executable": executable,
        "execution_status": "executable" if executable else "blocked",
        "blockers": blockers,
    }


def build_asset_accumulation_timing(
    *,
    data_dir: Path,
    output_dir: Path,
    market: MarketIndicators,
    alerts: list[TriggerAlert],
    rules: dict[str, Any],
    gap_rows: list[GapRow],
    data_gate: str,
    execution_scope: str,
    dry_run_days: int,
    dry_run_required: int = 10,
    throttle_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = load_accumulation_timing_config(data_dir)
    thresholds = config.get("timing_status_thresholds") or {}
    history = _read_market_history(data_dir)
    macro = _read_macro_tier2(data_dir)
    group_gaps = _load_group_gaps(output_dir)
    throttle = throttle_meta or {}
    if not throttle and (output_dir / "core_deployment_throttle_status.json").exists():
        throttle = json.loads(
            (output_dir / "core_deployment_throttle_status.json").read_text(encoding="utf-8")
        )

    per_trade = float((throttle.get("limits") or {}).get("per_trade_max_pct") or 3.0)
    weekly_remain = float((throttle.get("usage") or {}).get("weekly_remaining_pct") or 5.0)

    scorers = {
        "global_beta": lambda: score_global_beta(market, alerts, history, macro, rules),
        "duration_bond": lambda: score_duration_bond(market, history, macro, alerts),
        "hedge_alt": lambda: score_hedge_alt(market, macro, alerts),
        "income_alt": lambda: score_income_alt(market, history, macro, alerts),
    }

    rows: list[dict[str, Any]] = []

    for sleeve, scorer in scorers.items():
        result = scorer()
        uw_gap = _gap_by_timing_sleeve(group_gaps, sleeve, config, gap_rows)
        result.timing_status = _status_from_score(
            result.timing_score or 0, result.blockers, thresholds,
        )
        if uw_gap <= 0.5:
            result.timing_status = "Wait"
            result.blockers.append("no meaningful underweight")

        ticker, name = _recommended_ticker(sleeve, gap_rows, config)
        exec_info = build_execution_status(
            data_gate=data_gate,
            execution_scope=execution_scope,
            dry_run_days=dry_run_days,
            dry_run_required=dry_run_required,
            throttle_meta=throttle,
            timing_status=result.timing_status,
            underweight_gap=uw_gap,
        )
        max_buy = 0.0
        if exec_info["executable"]:
            max_buy = round(min(per_trade, weekly_remain, uw_gap), 2)

        rep = (config.get("representative_assets") or {}).get(sleeve) or []
        row = {
            "asset_group": sleeve,
            "representative_assets": rep,
            "underweight_gap_pct": round(uw_gap, 2),
            "timing_score": result.timing_score,
            "timing_status": result.timing_status,
            "execution_status": exec_info["execution_status"],
            "blocked_by_gate": exec_info["blocked_by_gate"],
            "blocked_by_dry_run": exec_info["blocked_by_dry_run"],
            "blocked_by_scope": exec_info["blocked_by_scope"],
            "blocked_by_throttle": exec_info["blocked_by_throttle"],
            "executable": exec_info["executable"],
            "blockers": exec_info["blockers"] + result.blockers,
            "positive_signals": result.positive_signals,
            "recommended_asset": ticker,
            "recommended_asset_name": name,
            "recommended_note": result.recommended_note,
            "max_buy_pct_after_throttle": max_buy,
            "shadow_only": True,
            "execution_authority": "none",
        }
        if sleeve == "duration_bond":
            row["duration_components"] = _duration_subcomponents(
                market, history, macro, alerts, config, data_dir,
            )
        rows.append(_enrich_timing_row(
            row,
            data_dir=data_dir,
            config=config,
            macro=macro,
            data_gate=data_gate,
            execution_scope=execution_scope,
            dry_run_days=dry_run_days,
            dry_run_required=dry_run_required,
            timing_blockers=list(result.blockers),
            execution_blockers=list(exec_info["blockers"]),
        ))

    cash_gap = group_gaps.get("cash_short_bond", {})
    cash_uw = float(cash_gap.get("gap", 0))
    cash_status = "FundingSource" if cash_uw < -5 else "Park"
    cash_exec = build_execution_status(
        data_gate=data_gate,
        execution_scope=execution_scope,
        dry_run_days=dry_run_days,
        dry_run_required=dry_run_required,
        throttle_meta=throttle,
        timing_status=cash_status,
        underweight_gap=0,
    )
    rows.append(_enrich_timing_row(
        {
            "asset_group": "cash_short_bond",
            "representative_assets": (config.get("representative_assets") or {}).get("cash_short_bond") or [],
            "underweight_gap_pct": round(max(0.0, cash_uw), 2),
            "overweight_gap_pct": round(_overweight_gap(group_gaps, "cash_short_bond"), 2),
            "timing_score": None,
            "timing_status": cash_status,
            "execution_status": "blocked",
            "blocked_by_gate": cash_exec["blocked_by_gate"],
            "blocked_by_dry_run": cash_exec["blocked_by_dry_run"],
            "blocked_by_scope": cash_exec["blocked_by_scope"],
            "blocked_by_throttle": cash_exec["blocked_by_throttle"],
            "executable": False,
            "blockers": cash_exec["blockers"] + ["cash is park/funding — not accumulation target"],
            "positive_signals": ["Excess cash deployable when Core Ready + executable"],
            "recommended_asset": "157450",
            "recommended_asset_name": "TIGER 단기통안채",
            "recommended_note": "Gate YELLOW/RED → hold cash buffer",
            "max_buy_pct_after_throttle": 0.0,
            "shadow_only": True,
            "execution_authority": "none",
        },
        data_dir=data_dir,
        config=config,
        macro=macro,
        data_gate=data_gate,
        execution_scope=execution_scope,
        dry_run_days=dry_run_days,
        dry_run_required=dry_run_required,
        timing_blockers=["cash park/funding role"],
        execution_blockers=list(cash_exec["blockers"]),
    ))

    alpha_gap = group_gaps.get("kr_alpha", {})
    alpha_ow = _overweight_gap(group_gaps, "kr_alpha")
    rows.append(_enrich_timing_row(
        {
            "asset_group": "kr_alpha",
            "representative_assets": [],
            "underweight_gap_pct": round(max(0.0, float(alpha_gap.get("gap", 0))), 2),
            "overweight_gap_pct": round(alpha_ow, 2),
            "timing_score": None,
            "timing_status": "ReduceOnly",
            "execution_status": "blocked",
            "blocked_by_gate": data_gate != "GREEN",
            "blocked_by_dry_run": dry_run_days < dry_run_required,
            "blocked_by_scope": True,
            "blocked_by_throttle": True,
            "executable": False,
            "blockers": ["kr_alpha new buy forbidden", "trim → Core underweight only"],
            "positive_signals": [],
            "recommended_asset": "",
            "recommended_asset_name": "",
            "recommended_note": "신규매수 금지 — trim 후 Core ETF 재배치",
            "max_buy_pct_after_throttle": 0.0,
            "shadow_only": True,
            "execution_authority": "none",
        },
        data_dir=data_dir,
        config=config,
        macro=macro,
        data_gate=data_gate,
        execution_scope=execution_scope,
        dry_run_days=dry_run_days,
        dry_run_required=dry_run_required,
        timing_blockers=["kr_alpha reduce-only policy"],
        execution_blockers=["kr_alpha new buy forbidden"],
    ))

    ranked = sorted(
        [r for r in rows if r["timing_score"] is not None and r["underweight_gap_pct"] > 0],
        key=lambda x: (-int(x["timing_score"] or 0), -float(x["underweight_gap_pct"])),
    )

    return {
        "phase": "AR-2.1",
        "mode": "shadow_timing_only",
        "execution_authority": "none",
        "disclaimer": AR2_DISCLAIMER,
        "readiness_disclaimer": (
            "Timing Watch/Ready ≠ Buy permission. "
            "Execution blocked unless executable=true in final_execution_decision."
        ),
        "as_of": market.date,
        "data_gate": data_gate,
        "execution_scope": execution_scope,
        "dry_run_days": dry_run_days,
        "dry_run_required": dry_run_required,
        "rows": rows,
        "priority_ranking": [
            {
                "asset_group": r["asset_group"],
                "timing_score": r["timing_score"],
                "underweight_gap_pct": r["underweight_gap_pct"],
                "timing_status": r["timing_status"],
                "input_quality": r.get("input_quality"),
            }
            for r in ranked
        ],
        "executable_count": sum(1 for r in rows if r.get("executable")),
        "ar21_qa": {
            "ready_but_blocked_count": sum(
                1 for r in rows
                if r.get("timing_status") == "Ready" and not r.get("executable")
            ),
            "watch_but_blocked_count": sum(
                1 for r in rows
                if r.get("timing_status") == "Watch" and not r.get("executable")
            ),
            "all_execution_blocked": all(not r.get("executable") for r in rows),
            "rows_with_stale_inputs": sum(
                1 for r in rows if r.get("stale_inputs")
            ),
        },
    }


def write_asset_accumulation_timing(
    *,
    data_dir: Path,
    output_dir: Path,
    market: MarketIndicators,
    alerts: list[TriggerAlert],
    rules: dict[str, Any],
    gap_rows: list[GapRow],
    data_gate: str,
    execution_scope: str,
    dry_run_days: int,
    dry_run_required: int = 10,
    throttle_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = build_asset_accumulation_timing(
        data_dir=data_dir,
        output_dir=output_dir,
        market=market,
        alerts=alerts,
        rules=rules,
        gap_rows=gap_rows,
        data_gate=data_gate,
        execution_scope=execution_scope,
        dry_run_days=dry_run_days,
        dry_run_required=dry_run_required,
        throttle_meta=throttle_meta,
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "asset_accumulation_timing.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ar2_path = output_dir / "ar2_accumulation_timing_report.json"
    ar2_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    csv_path = output_dir / "asset_accumulation_timing.csv"
    fieldnames = [
        "asset_group", "underweight_gap_pct", "timing_score", "timing_status",
        "execution_status", "input_quality", "stale_inputs",
        "recommended_asset", "recommended_asset_name",
        "max_buy_pct_after_throttle", "timing_execution_note",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in report["rows"]:
            out = dict(row)
            if isinstance(out.get("stale_inputs"), list):
                out["stale_inputs"] = ";".join(out["stale_inputs"])
            writer.writerow(out)

    return report
