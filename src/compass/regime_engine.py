from __future__ import annotations

from pathlib import Path
from typing import Any

from src.compass.economic_phase import (
    _kospi_drawdown_pct,
    _kospi_vs_ma200_pct,
    classify_market_phase,
    score_growth,
    score_inflation,
    score_liquidity,
    score_risk_appetite,
)
from src.compass.hysteresis import apply_phase_hysteresis, apply_regime_hysteresis
from src.compass.judgment_log import judgment_log_path, read_judgment_log_tail
from src.compass.models import (
    CompassDirection,
    CompassResult,
    CompassSignal,
    OverrideInfo,
    RiskRegime,
    ScoreBreakdownItem,
)
from src.compass.tier2_macro import MacroTier2, blend_axis_scores, score_tier2_axes
from src.models import MarketIndicators


_DIRECTION_LABELS: dict[CompassDirection, str] = {
    "N": "북 — 시장 회복, 리스크 중립 (베타 점진 확대)",
    "NE": "북동 — Risk-On 확장 (시장·리스크 동반 상승)",
    "E": "동 — 인플레·금리 압력 (실물·헤지 강화)",
    "SE": "남동 — 둔화·방어 (현금·채권 비중 확대)",
    "S": "남 — 시장 수축 (리스크 자산 축소)",
    "SW": "남서 — 유동성 경색 (방어 최우선)",
    "W": "서 — 시장 둔화 (알파·베타 축소)",
    "NW": "북서 — 관망·중립 (SAA 유지)",
}


def _resolve_compass_direction(growth: float, risk: float, rules: dict[str, Any]) -> CompassDirection:
    direction_map: dict[str, Any] = rules.get("direction_map", {})
    candidates: list[tuple[str, int]] = []

    for direction, bounds in direction_map.items():
        score = 0
        g_min = bounds.get("growth_min")
        g_max = bounds.get("growth_max")
        r_min = bounds.get("risk_min")
        r_max = bounds.get("risk_max")
        if g_min is not None and growth >= float(g_min):
            score += 1
        elif g_min is not None:
            score -= 2
        if g_max is not None and growth <= float(g_max):
            score += 1
        elif g_max is not None:
            score -= 2
        if r_min is not None and risk >= float(r_min):
            score += 1
        elif r_min is not None:
            score -= 2
        if r_max is not None and risk <= float(r_max):
            score += 1
        elif r_max is not None:
            score -= 2
        candidates.append((direction, score))

    candidates.sort(key=lambda item: item[1], reverse=True)
    best = candidates[0][0] if candidates else "NW"
    if best not in _DIRECTION_LABELS:
        return "NW"
    return best  # type: ignore[return-value]


def _classify_risk_regime(
    market: MarketIndicators,
    growth_score: float,
    risk_score: float,
    rules: dict[str, Any],
) -> tuple[RiskRegime, float, list[ScoreBreakdownItem]]:
    regime_rules = rules.get("regime_rules", {})
    drawdown = _kospi_drawdown_pct(market)
    vs_ma = _kospi_vs_ma200_pct(market)
    vix = market.vix
    breakdown: list[ScoreBreakdownItem] = []

    crisis_vix = float(regime_rules.get("crisis_vix", 30))
    crisis_dd = float(regime_rules.get("crisis_kospi_drawdown", -15))
    if vix >= crisis_vix:
        breakdown.append(
            ScoreBreakdownItem(axis="regime", indicator="vix_crisis", contribution=1.0, detail=f"VIX {vix:.1f}≥{crisis_vix}")
        )
        return RiskRegime.CRISIS, 0.85, breakdown
    if drawdown is not None and drawdown <= crisis_dd:
        breakdown.append(
            ScoreBreakdownItem(
                axis="regime", indicator="kospi_crisis_drawdown", contribution=1.0, detail=f"drawdown {drawdown:.1f}%"
            )
        )
        return RiskRegime.CRISIS, 0.75, breakdown

    risk_off_vix = float(regime_rules.get("risk_off_vix", 25))
    risk_off_dd = float(regime_rules.get("risk_off_drawdown", -10))
    if vix >= risk_off_vix:
        breakdown.append(
            ScoreBreakdownItem(axis="regime", indicator="vix_risk_off", contribution=1.0, detail=f"VIX {vix:.1f}")
        )
        return RiskRegime.RISK_OFF, 0.75, breakdown
    if drawdown is not None and drawdown <= risk_off_dd:
        breakdown.append(
            ScoreBreakdownItem(axis="regime", indicator="kospi_risk_off", contribution=1.0, detail=f"drawdown {drawdown:.1f}%")
        )
        return RiskRegime.RISK_OFF, 0.75, breakdown

    caution_vix = float(rules.get("compass", {}).get("vix", {}).get("caution_below", 25))
    if vix >= caution_vix - 3 or risk_score < -0.15:
        return RiskRegime.CAUTION, 0.65, breakdown

    risk_on_vix = float(regime_rules.get("risk_on_vix_max", 18))
    requires_ma = bool(regime_rules.get("risk_on_requires_ma200", True))
    ma_ok = vs_ma is not None and vs_ma >= 0
    if vix > 0 and vix <= risk_on_vix and growth_score >= 0.2 and (ma_ok or not requires_ma):
        return RiskRegime.RISK_ON, 0.7, breakdown

    return RiskRegime.YELLOW_STABLE, 0.6, breakdown


def _manual_regime_to_risk(regime: str) -> RiskRegime | None:
    upper = regime.upper()
    mapping = {
        "RISK_ON": RiskRegime.RISK_ON,
        "YELLOW_STABLE": RiskRegime.YELLOW_STABLE,
        "CAUTION": RiskRegime.CAUTION,
        "RISK_OFF": RiskRegime.RISK_OFF,
        "CRISIS": RiskRegime.CRISIS,
        "RED": RiskRegime.RISK_OFF,
        "GREEN": RiskRegime.RISK_ON,
    }
    for key, value in mapping.items():
        if key in upper:
            return value
    return None


def _manual_regime_effective(market: MarketIndicators, use_manual_regime: bool) -> tuple[str | None, bool]:
    """Returns (regime_raw, expired). 만료 시 None → 산출 레짐만 사용."""
    if not use_manual_regime:
        return None, False
    raw = (market.regime or "").strip()
    if not raw or raw.upper() in {"NEUTRAL", "AUTO", ""}:
        return None, False
    expires = getattr(market, "regime_expires_date", None)
    if expires and market.date[:10] > expires[:10]:
        return None, True
    return raw, False


def compute_compass(
    market: MarketIndicators,
    rules: dict[str, Any],
    *,
    use_manual_regime: bool = True,
    data_gate: str = "GREEN",
    execution_level: int = 1,
    tier2: MacroTier2 | None = None,
    output_dir: Path | None = None,
    judgment_history: list[dict[str, Any]] | None = None,
) -> CompassResult:
    growth, growth_detail, growth_bd = score_growth(market, rules)
    inflation, inflation_detail, inflation_bd = score_inflation(market, rules)
    liquidity, liquidity_detail, liquidity_bd = score_liquidity(market, rules)
    risk, risk_detail, risk_bd = score_risk_appetite(market, rules)

    tier1 = {
        "growth": growth,
        "inflation": inflation,
        "liquidity": liquidity,
        "risk_appetite": risk,
    }
    score_breakdown = growth_bd + inflation_bd + liquidity_bd + risk_bd

    if tier2 is not None:
        tier2_axes, tier2_bd = score_tier2_axes(tier2, rules)
        blend_w = float(rules.get("tier2", {}).get("blend_weight", 0.30))
        blended = blend_axis_scores(tier1, tier2_axes, blend_w)
        growth = blended["growth"]
        inflation = blended["inflation"]
        liquidity = blended["liquidity"]
        risk = blended["risk_appetite"]
        growth_detail += f" | Tier2 blend {blend_w:.0%}"
        score_breakdown.extend(tier2_bd)

    computed_phase, phase_conf = classify_market_phase(growth, rules)
    computed_regime, regime_conf, regime_bd = _classify_risk_regime(market, growth, risk, rules)
    direction = _resolve_compass_direction(growth, risk, rules)

    history = judgment_history
    if history is None and output_dir is not None:
        confirm = max(
            int((rules.get("hysteresis") or {}).get("regime_confirm_runs", 2) or 2),
            int((rules.get("hysteresis") or {}).get("phase_confirm_runs", 2) or 2),
        )
        history = read_judgment_log_tail(judgment_log_path(output_dir), n=max(confirm + 2, 8))
    history = history or []

    applied_phase, phase_h_note = apply_phase_hysteresis(computed_phase, history, rules)

    manual_raw, regime_expired = _manual_regime_effective(market, use_manual_regime)
    parsed_manual = _manual_regime_to_risk(manual_raw) if manual_raw else None
    applied = computed_regime
    override = OverrideInfo(active=False)
    hysteresis_note = phase_h_note

    if regime_expired and (market.regime or "").strip().upper() not in ("", "NEUTRAL", "AUTO"):
        override = OverrideInfo(
            active=False,
            reason="manual_regime_expired",
            timestamp=market.date,
        )
        applied, regime_h_note = apply_regime_hysteresis(computed_regime, history, rules)
        if regime_h_note:
            hysteresis_note = "; ".join(x for x in (hysteresis_note, regime_h_note) if x)
    elif parsed_manual and parsed_manual != computed_regime:
        applied = parsed_manual
        override = OverrideInfo(
            active=True,
            reason=getattr(market, "regime_override_reason", None) or "manual_regime_input",
            timestamp=market.date,
        )
    elif parsed_manual:
        applied = parsed_manual
    else:
        applied, regime_h_note = apply_regime_hysteresis(computed_regime, history, rules)
        if regime_h_note:
            hysteresis_note = "; ".join(x for x in (hysteresis_note, regime_h_note) if x)

    score_breakdown = score_breakdown + regime_bd

    signals = [
        CompassSignal(key="growth", label="성장(시장)", score=growth, detail=growth_detail),
        CompassSignal(key="inflation", label="인플레이션", score=inflation, detail=inflation_detail),
        CompassSignal(key="liquidity", label="유동성", score=liquidity, detail=liquidity_detail),
        CompassSignal(key="risk_appetite", label="리스크 선호", score=risk, detail=risk_detail),
    ]

    summary = (
        f"{_DIRECTION_LABELS[direction]} | "
        f"시장국면 {applied_phase.value} · 적용레짐 {applied.value}"
    )

    return CompassResult(
        date=market.date,
        market_phase=applied_phase,
        computed_market_phase=computed_phase,
        phase_confidence=round(phase_conf, 2),
        computed_regime=computed_regime,
        regime_confidence=round(regime_conf, 2),
        compass_direction=direction,
        compass_summary=summary,
        growth_score=round(growth, 3),
        inflation_score=round(inflation, 3),
        liquidity_score=round(liquidity, 3),
        risk_appetite_score=round(risk, 3),
        signals=signals,
        score_breakdown=score_breakdown,
        manual_regime=manual_raw,
        applied_regime=applied,
        override=override,
        data_gate=data_gate,
        execution_level=execution_level,
        hysteresis_note=hysteresis_note,
    )
