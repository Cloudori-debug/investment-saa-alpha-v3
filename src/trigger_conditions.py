from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from src.models import MarketIndicators, TriggerAlert, TriggerStatus


@dataclass
class TriggerContext:
    market: MarketIndicators
    rules: dict[str, Any]
    alert_by_key: dict[str, TriggerAlert]
    asset_group_gaps: dict[str, dict[str, float]]
    position_weights: dict[str, float]
    ticker_gaps: dict[str, float]
    growth_score: float | None = None
    market_history: list[MarketIndicators] = field(default_factory=list)


def _alert_active(ctx: TriggerContext, key: str) -> bool:
    a = ctx.alert_by_key.get(key)
    return a is not None and a.status == TriggerStatus.ACTIVE


def _alert_not_risk(ctx: TriggerContext, key: str) -> bool:
    a = ctx.alert_by_key.get(key)
    return a is None or a.status != TriggerStatus.RISK


def _vix_below(ctx: TriggerContext, threshold: float) -> bool:
    return ctx.market.vix > 0 and ctx.market.vix < threshold


def _vix_above(ctx: TriggerContext, threshold: float) -> bool:
    return ctx.market.vix >= threshold


def _overweight(ctx: TriggerContext, group: str, ppt: float) -> bool:
    gap = ctx.asset_group_gaps.get(group, {}).get("gap", 0)
    return gap <= -ppt


def _underweight(ctx: TriggerContext, group: str) -> bool:
    return ctx.asset_group_gaps.get(group, {}).get("gap", 0) >= 1.0


def _oil_shock(ctx: TriggerContext) -> bool:
    mt = ctx.rules.get("market_triggers", {})
    shock = float(mt.get("oil_shock_above", 90))
    if ctx.market.oil_brent >= shock:
        return True
    compass = ctx.rules.get("compass_oil_shock_above")
    if compass and ctx.market.oil_brent >= float(compass):
        return True
    return ctx.market.oil_brent >= 90


def _geopolitical_risk(ctx: TriggerContext) -> bool:
    return _vix_above(ctx, 25) and (_oil_shock(ctx) or ctx.market.vix >= 30)


def _real_yield_falling(ctx: TriggerContext) -> bool:
    if len(ctx.market_history) < 2:
        return False
    prev = ctx.market_history[-2].korea_10y
    cur = ctx.market.korea_10y
    return prev > 0 and cur > 0 and cur < prev - 0.05


def _usdkrw_spike(ctx: TriggerContext) -> bool:
    a = ctx.alert_by_key.get("usdkrw")
    return a is not None and a.status in {TriggerStatus.RISK, TriggerStatus.WATCH}


def _usdkrw_stabilizing(ctx: TriggerContext) -> bool:
    if len(ctx.market_history) < 2:
        return not _usdkrw_spike(ctx)
    prev = ctx.market_history[-2].usdkrw
    cur = ctx.market.usdkrw
    if prev <= 0 or cur <= 0:
        return not _usdkrw_spike(ctx)
    return cur <= prev and not _usdkrw_spike(ctx)


def _fomc_passed(ctx: TriggerContext) -> bool:
    events = ctx.rules.get("events", {})
    dates = events.get("fomc_dates") or []
    window = int(events.get("fomc_pass_window_days", 14))
    as_of = _parse_date(ctx.market.date)
    if not as_of:
        return True
    for d in dates:
        fomc = _parse_date(str(d))
        if fomc and 0 <= (as_of - fomc).days <= window:
            return True
    return not dates


def _semiconductor_thesis_intact(ctx: TriggerContext) -> bool:
    if ctx.growth_score is not None:
        return ctx.growth_score >= 0.0
    return ctx.market.regime.upper() not in {"RISK_OFF", "CRISIS", "RED"}


def _stock_pullback(ctx: TriggerContext, ticker: str, pct: float) -> bool:
    if ticker not in ctx.ticker_gaps:
        return False
    path_guess = ctx.rules.get("_prices_path")
    if not path_guess:
        return False
    return _price_pullback_from_csv(path_guess, ticker, pct)


def _price_pullback_from_csv(prices_path: Path, ticker: str, pct: float) -> bool:
    if not prices_path.exists():
        return False
    df = pd.read_csv(prices_path, dtype=str, keep_default_na=False)
    row = df[df["ticker"].astype(str).str.strip() == ticker]
    if row.empty:
        return False
    r = row.iloc[0]
    try:
        close = float(r.get("close", 0))
        high = float(r.get("high_52w", 0))
        if high <= 0 or close <= 0:
            dist = float(r.get("distance_from_52w_high", 0))
            if dist > 0:
                return (dist - 1) * 100 <= -pct
            return False
        drawdown = (close / high - 1) * 100
        return drawdown <= -pct
    except ValueError:
        return False


def _parse_date(s: str) -> datetime | None:
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        return None


CONDITIONS: dict[str, Any] = {
    "kospi_pullback_triggered": lambda ctx: _alert_active(ctx, "kospi_pullback"),
    "sp500_pullback_triggered": lambda ctx: _alert_active(ctx, "sp500_pullback"),
    "vix_below_25": lambda ctx: _vix_below(ctx, 25),
    "vix_above_30": lambda ctx: _vix_above(ctx, 30),
    "usdkrw_not_spiking": lambda ctx: _alert_not_risk(ctx, "usdkrw"),
    "target_overweight_5ppt": lambda ctx: any(
        _overweight(ctx, g, 5) for g in ctx.asset_group_gaps
    ),
    "target_overweight_3ppt": lambda ctx: any(
        _overweight(ctx, g, 3) for g in ctx.asset_group_gaps
    ),
    "fomc_event_passed": _fomc_passed,
    "oil_shock": _oil_shock,
    "geopolitical_risk": _geopolitical_risk,
    "real_yield_falling": _real_yield_falling,
    "usdkrw_stabilizing_after_drop": _usdkrw_stabilizing,
    "fx_hedge_needed": lambda ctx: _usdkrw_spike(ctx) and _underweight(ctx, "fx_dollar"),
    "geopolitical_risk_eases": lambda ctx: not _geopolitical_risk(ctx),
}


def _eval_conditions(ctx: TriggerContext, names: list[str], extra: dict[str, Any] | None = None) -> tuple[bool, list[str]]:
    matched: list[str] = []
    for name in names:
        if name == "stock_pullback_7pct":
            ticker = (extra or {}).get("ticker", "000660")
            ok = _stock_pullback(ctx, ticker, 7.0)
        elif name == "semiconductor_thesis_intact":
            ok = _semiconductor_thesis_intact(ctx)
        elif name == "total_weight_below_target":
            ticker = (extra or {}).get("ticker", "000660")
            ok = ctx.ticker_gaps.get(ticker, 0) >= 0.5
        elif name in CONDITIONS:
            ok = CONDITIONS[name](ctx)
        else:
            ok = False
        if ok:
            matched.append(name)
    all_required = len(matched) == len(names)
    return all_required, matched


def evaluate_asset_triggers(
    ctx: TriggerContext,
) -> list[TriggerAlert]:
    """trigger_rules.yaml asset_triggers → 자산군별 buy/sell/trim 신호."""
    asset_rules = ctx.rules.get("asset_triggers", {})
    alerts: list[TriggerAlert] = []

    group_map = {
        "domestic_beta": "domestic_beta",
        "global_beta": "global_beta",
        "sk_hynix": "kr_alpha",
        "gold": "hedge_alt",
        "dollar": "fx_dollar",
    }

    def _watch_label(asset_key: str, *, suppressed: bool = False) -> str:
        if suppressed:
            return f"{asset_key} watch signal suppressed"
        return f"{asset_key} watch signal"

    for asset_key, cfg in asset_rules.items():
        if not isinstance(cfg, dict):
            continue
        extra = {"ticker": cfg.get("ticker", "000660")} if asset_key == "sk_hynix" else {}
        group = group_map.get(asset_key, asset_key)

        buy_when = cfg.get("buy_when") or []
        sell_when = cfg.get("sell_when") or []
        trim_when = cfg.get("trim_when") or []

        buy_ok, buy_matched = _eval_conditions(ctx, buy_when, extra) if buy_when else (False, [])
        sell_ok, sell_matched = _eval_conditions(ctx, sell_when, extra) if sell_when else (False, [])
        trim_ok, trim_matched = _eval_conditions(ctx, trim_when, extra) if trim_when else (False, [])

        group_target = float(ctx.asset_group_gaps.get(group, {}).get("target", 1.0) or 0)
        zero_target = group_target <= 0.01

        if buy_ok and zero_target:
            alerts.append(TriggerAlert(
                key=f"asset_buy_{asset_key}",
                label=_watch_label(asset_key, suppressed=True),
                status=TriggerStatus.WATCH,
                detail="suppressed — target weight 0% (watch only)",
            ))
        elif buy_ok:
            alerts.append(TriggerAlert(
                key=f"asset_buy_{asset_key}",
                label=_watch_label(asset_key),
                status=TriggerStatus.ACTIVE,
                detail=f"watch_condition: {', '.join(buy_matched)}",
            ))
        elif sell_ok:
            alerts.append(TriggerAlert(
                key=f"asset_sell_{asset_key}",
                label=f"{asset_key} sell/trim signal",
                status=TriggerStatus.RISK,
                detail=f"sell_when: {', '.join(sell_matched)}",
            ))
        elif trim_ok:
            alerts.append(TriggerAlert(
                key=f"asset_trim_{asset_key}",
                label=f"{asset_key} trim signal",
                status=TriggerStatus.WATCH,
                detail=f"trim_when: {', '.join(trim_matched)}",
            ))
        else:
            pending = buy_when[:2] if buy_when else []
            alerts.append(TriggerAlert(
                key=f"asset_{asset_key}",
                label=f"{asset_key} ({group})",
                status=TriggerStatus.INACTIVE,
                detail=f"대기 — {', '.join(pending) if pending else 'no rules'}",
            ))

    return alerts


def build_trigger_context(
    market: MarketIndicators,
    rules: dict,
    market_alerts: list[TriggerAlert],
    *,
    asset_group_gaps: dict[str, dict[str, float]] | None = None,
    gap_rows: list | None = None,
    growth_score: float | None = None,
    data_dir: Path | None = None,
) -> TriggerContext:
    alert_by_key = {a.key: a for a in market_alerts}
    position_weights: dict[str, float] = {}
    ticker_gaps: dict[str, float] = {}
    if gap_rows:
        total = sum(getattr(r, "current_weight", 0) for r in gap_rows) or 100
        for r in gap_rows:
            ticker_gaps[r.ticker] = getattr(r, "gap", 0)
            position_weights[r.ticker] = getattr(r, "current_weight", 0)

    history: list[MarketIndicators] = []
    if data_dir:
        hist_path = data_dir / "market_indicators_history.csv"
        if hist_path.exists():
            from src.data_loader import load_market_indicators_history
            history = load_market_indicators_history(hist_path)

    rules_copy = dict(rules)
    if data_dir:
        rules_copy["_prices_path"] = data_dir / "prices.csv"

    return TriggerContext(
        market=market,
        rules=rules_copy,
        alert_by_key=alert_by_key,
        asset_group_gaps=asset_group_gaps or {},
        position_weights=position_weights,
        ticker_gaps=ticker_gaps,
        growth_score=growth_score,
        market_history=history,
    )
