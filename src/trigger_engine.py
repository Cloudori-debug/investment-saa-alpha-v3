from __future__ import annotations

from pathlib import Path

from src.data_provenance import field_stale_days
from src.models import MarketIndicators, TriggerAlert, TriggerStatus
from src.trigger_conditions import build_trigger_context, evaluate_asset_triggers


def _pct_drawdown(current: float, recent_high: float) -> float | None:
    if recent_high <= 0 or current <= 0:
        return None
    return round((current / recent_high - 1) * 100, 2)


def _kospi_pullback_level(drawdown: float, rules: dict) -> str | None:
    kospi = rules.get("market_triggers", {}).get("kospi", {})
    if drawdown <= float(kospi.get("crisis_zone", -20)):
        return "crisis"
    if drawdown <= float(kospi.get("pullback_buy_3", -15)):
        return "buy_3"
    if drawdown <= float(kospi.get("pullback_buy_2", -10)):
        return "buy_2"
    if drawdown <= float(kospi.get("pullback_buy_1", -5)):
        return "buy_1"
    return None


def _evaluate_market_triggers(
    market: MarketIndicators,
    rules: dict,
    asset_group_gaps: dict[str, dict[str, float]] | None,
    data_dir: Path | None = None,
) -> list[TriggerAlert]:
    alerts: list[TriggerAlert] = []
    mt = rules.get("market_triggers", {})

    kospi_dd = _pct_drawdown(market.kospi, market.kospi_recent_high)
    if kospi_dd is not None:
        level = _kospi_pullback_level(kospi_dd, rules)
        if level:
            alerts.append(
                TriggerAlert(
                    key="kospi_pullback",
                    label="KOSPI Pullback",
                    status=TriggerStatus.ACTIVE,
                    detail=f"drawdown {kospi_dd:.1f}% → {level}",
                )
            )
        else:
            alerts.append(
                TriggerAlert(
                    key="kospi_pullback",
                    label="KOSPI Pullback",
                    status=TriggerStatus.INACTIVE,
                    detail=f"drawdown {kospi_dd:.1f}% — no buy trigger",
                )
            )

    sp500_dd = _pct_drawdown(market.sp500, market.sp500_recent_high)
    sp_stale, sp_stale_d = field_stale_days(data_dir, "sp500")
    if sp_stale:
        alerts.append(
            TriggerAlert(
                key="sp500_pullback",
                label="S&P500 Pullback",
                status=TriggerStatus.INACTIVE,
                detail=f"provenance stale ({sp_stale_d}d) — trigger 비활성",
            )
        )
    elif sp500_dd is not None and market.sp500 > 0:
        sp_rules = mt.get("sp500", {})
        active = sp500_dd <= float(sp_rules.get("pullback_buy_1", -5))
        alerts.append(
            TriggerAlert(
                key="sp500_pullback",
                label="S&P500 Pullback",
                status=TriggerStatus.ACTIVE if active else TriggerStatus.INACTIVE,
                detail=f"drawdown {sp500_dd:.1f}%",
            )
        )
    elif market.sp500 <= 0:
        alerts.append(
            TriggerAlert(
                key="sp500_pullback",
                label="S&P500 Pullback",
                status=TriggerStatus.INACTIVE,
                detail="S&P500 data missing — trigger inactive",
            )
        )

    vix_rules = mt.get("vix", {})
    vix = market.vix
    vix_stale, vix_stale_d = field_stale_days(data_dir, "vix")
    if vix_stale and vix > 0:
        vix_status, vix_detail = TriggerStatus.INACTIVE, f"provenance stale ({vix_stale_d}d) — trigger 비활성"
    elif vix >= float(vix_rules.get("panic_above", 30)):
        vix_status, vix_detail = TriggerStatus.RISK, f"VIX {vix:.1f} panic (stop-buy)"
    elif vix >= float(vix_rules.get("risk_off_above", 25)):
        vix_status, vix_detail = TriggerStatus.RISK, f"VIX {vix:.1f} risk-off"
    elif vix >= float(vix_rules.get("caution_above", 20)):
        vix_status, vix_detail = TriggerStatus.WATCH, f"VIX {vix:.1f} caution"
    else:
        vix_status, vix_detail = TriggerStatus.INACTIVE, f"VIX {vix:.1f} normal"
    alerts.append(TriggerAlert(key="vix", label="VIX", status=vix_status, detail=vix_detail))

    fx_rules = mt.get("usdkrw", {})
    fx_risk = float(fx_rules.get("risk_level", 1550))
    fx_stable = float(fx_rules.get("stable_level", 1500))
    if market.usdkrw >= fx_risk:
        fx_status, fx_detail = TriggerStatus.RISK, f"USD/KRW {market.usdkrw:.1f} above risk {fx_risk}"
    elif market.usdkrw >= fx_stable:
        fx_status, fx_detail = TriggerStatus.WATCH, f"USD/KRW {market.usdkrw:.1f} watch"
    else:
        fx_status, fx_detail = TriggerStatus.INACTIVE, f"USD/KRW {market.usdkrw:.1f} stable"
    alerts.append(TriggerAlert(key="usdkrw", label="USD/KRW", status=fx_status, detail=fx_detail))

    oil_shock = float(mt.get("oil_shock_above", 90))
    if market.oil_brent >= oil_shock:
        alerts.append(TriggerAlert(
            key="oil_shock",
            label="Oil shock",
            status=TriggerStatus.WATCH,
            detail=f"Brent ${market.oil_brent:.1f} ≥ {oil_shock}",
        ))

    flow = market.foreign_flow_3d.lower()
    if flow in {"heavy_selling", "sell", "negative", "outflow"}:
        flow_status = TriggerStatus.RISK
    elif flow in {"recovery", "buying", "positive", "inflow"}:
        flow_status = TriggerStatus.ACTIVE
    else:
        flow_status = TriggerStatus.INACTIVE
    alerts.append(
        TriggerAlert(
            key="foreign_flow",
            label="Foreign Flow (3d)",
            status=flow_status,
            detail=market.foreign_flow_3d,
        )
    )

    if asset_group_gaps:
        trim_ppt = float(rules.get("position_triggers", {}).get("trim_if_target_overweight_ppt", 5))
        for group, vals in asset_group_gaps.items():
            if vals.get("gap", 0) <= -trim_ppt:
                if group == "cash_short_bond":
                    alerts.append(
                        TriggerAlert(
                            key=f"overweight_{group}",
                            label=f"{group} overweight",
                            status=TriggerStatus.WATCH,
                            detail=(
                                f"gap {vals['gap']:.1f}%p — funding source / Park "
                                "(매수 탄약·trim zone 아님)"
                            ),
                        )
                    )
                else:
                    alerts.append(
                        TriggerAlert(
                            key=f"overweight_{group}",
                            label=f"{group} overweight",
                            status=TriggerStatus.ACTIVE,
                            detail=f"gap {vals['gap']:.1f}%p — trim zone",
                        )
                    )

    return alerts


def _evaluate_kospi_review_triggers(
    market: MarketIndicators,
    rules: dict,
    kospi_dd: float | None,
    *,
    core_price_gate: str = "pass",
    data_gate: str = "GREEN",
    health_gate: str = "GREEN",
    dry_run_days: int = 0,
) -> list[TriggerAlert]:
    """조정 구간 분할매수 검토 알림 — gates 충족 시에만 WATCH."""
    cfg = rules.get("kospi_drawdown_triggers") or {}
    if not cfg or kospi_dd is None:
        return []

    req = cfg.get("require") or {}
    blocked_regimes = [r.upper() for r in (req.get("manual_regime_block") or [])]
    regime_upper = (market.regime or "").upper()
    gates_ok = (
        core_price_gate == str(req.get("core_price_gate", "pass"))
        and data_gate != str(req.get("data_gate_not", "RED"))
        and health_gate != str(req.get("health_gate_not", "RED"))
        and dry_run_days >= int(req.get("dry_run_days_min", 10))
        and not any(b in regime_upper for b in blocked_regimes)
    )

    alerts: list[TriggerAlert] = []
    levels = sorted(cfg.get("levels") or [], key=lambda x: float(x.get("threshold_pct", 0)))

    deepest: dict | None = None
    for level in levels:
        threshold = float(level.get("threshold_pct", 0))
        if kospi_dd <= threshold:
            deepest = level

    if deepest and gates_ok:
        alerts.append(
            TriggerAlert(
                key=f"kospi_review_{deepest['name']}",
                label=f"KOSPI Review — {deepest['name']}",
                status=TriggerStatus.WATCH,
                detail=(
                    f"drawdown {kospi_dd:.1f}% ≤ {deepest['threshold_pct']}% · "
                    f"action={deepest.get('action')} · {deepest.get('execution', 'manual_review_only')}"
                ),
            )
        )
    elif deepest and not gates_ok:
        missing: list[str] = []
        if core_price_gate != str(req.get("core_price_gate", "pass")):
            missing.append("core_price_gate")
        if data_gate == "RED":
            missing.append("data_gate=RED")
        if health_gate == "RED":
            missing.append("health_gate=RED")
        if dry_run_days < int(req.get("dry_run_days_min", 10)):
            missing.append(f"dry_run {dry_run_days}/{req.get('dry_run_days_min', 10)}")
        if any(b in regime_upper for b in blocked_regimes):
            missing.append("manual_regime blocked")
        alerts.append(
            TriggerAlert(
                key="kospi_review_gated",
                label="KOSPI Review (gated)",
                status=TriggerStatus.INACTIVE,
                detail=(
                    f"drawdown {kospi_dd:.1f}% — {deepest['name']} 조건 충족하나 "
                    f"검토 게이트 미충족: {', '.join(missing)}"
                ),
            )
        )
    return alerts


def evaluate_triggers(
    market: MarketIndicators,
    rules: dict,
    *,
    asset_group_gaps: dict[str, dict[str, float]] | None = None,
    gap_rows: list | None = None,
    growth_score: float | None = None,
    data_dir: Path | None = None,
    core_price_gate: str = "pass",
    data_gate: str = "GREEN",
    health_gate: str = "GREEN",
    dry_run_days: int = 0,
) -> list[TriggerAlert]:
    market_alerts = _evaluate_market_triggers(market, rules, asset_group_gaps, data_dir)
    kospi_dd = _pct_drawdown(market.kospi, market.kospi_recent_high)
    review_alerts = _evaluate_kospi_review_triggers(
        market,
        rules,
        kospi_dd,
        core_price_gate=core_price_gate,
        data_gate=data_gate,
        health_gate=health_gate,
        dry_run_days=dry_run_days,
    )
    ctx = build_trigger_context(
        market,
        rules,
        market_alerts,
        asset_group_gaps=asset_group_gaps,
        gap_rows=gap_rows,
        growth_score=growth_score,
        data_dir=data_dir,
    )
    asset_alerts = evaluate_asset_triggers(ctx)
    return market_alerts + review_alerts + asset_alerts


def is_buy_trigger_active(alerts: list[TriggerAlert], asset_group: str) -> bool:
    """자산군별 buy — market pullback 또는 asset_triggers buy 신호."""
    if any(a.key == "vix" and a.status == TriggerStatus.RISK for a in alerts):
        return False

    group_asset_keys = {
        "domestic_beta": "domestic_beta",
        "global_beta": "global_beta",
        "kr_alpha": "sk_hynix",
        "hedge_alt": "gold",
        "fx_dollar": "dollar",
    }
    asset_key = group_asset_keys.get(asset_group)
    if asset_key:
        buy_key = f"asset_buy_{asset_key}"
        if any(
            a.key == buy_key and a.status == TriggerStatus.ACTIVE
            for a in alerts
        ):
            return True

    active_keys = {a.key for a in alerts if a.status == TriggerStatus.ACTIVE}
    if asset_group == "domestic_beta":
        if any(a.key == "asset_buy_domestic_beta" and a.status == TriggerStatus.ACTIVE for a in alerts):
            return True
        return "kospi_pullback" in active_keys
    if asset_group == "global_beta":
        return "sp500_pullback" in active_keys
    if asset_group == "kr_alpha":
        return "kospi_pullback" in active_keys or f"asset_buy_sk_hynix" in active_keys
    if asset_group == "hedge_alt":
        return f"asset_buy_gold" in active_keys
    if asset_group == "fx_dollar":
        return f"asset_buy_dollar" in active_keys
    return False


def is_stop_buy(alerts: list[TriggerAlert]) -> bool:
    return any(a.key == "vix" and a.status == TriggerStatus.RISK for a in alerts)
