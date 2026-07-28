from __future__ import annotations

from typing import Any

from src.compass.models import MarketPhase, ScoreBreakdownItem
from src.models import MarketIndicators


def _sp500_drawdown_pct(market: MarketIndicators) -> float | None:
    if market.sp500_recent_high <= 0 or market.sp500 <= 0:
        return None
    return (market.sp500 / market.sp500_recent_high - 1) * 100


def _sp500_vs_ma200_pct(market: MarketIndicators) -> float | None:
    if market.sp500 <= 0:
        return None
    if hasattr(market, "sp500_200ma") and market.sp500_200ma > 0:  # type: ignore[attr-defined]
        return (market.sp500 / market.sp500_200ma - 1) * 100  # type: ignore[attr-defined]
    return None


def _kospi_drawdown_pct(market: MarketIndicators) -> float | None:
    if market.kospi_recent_high <= 0 or market.kospi <= 0:
        return None
    return (market.kospi / market.kospi_recent_high - 1) * 100


def _kospi_vs_ma200_pct(market: MarketIndicators) -> float | None:
    if market.kospi_200ma <= 0 or market.kospi <= 0:
        return None
    return (market.kospi / market.kospi_200ma - 1) * 100


def _flow_tags(rules: dict[str, Any]) -> tuple[set[str], set[str]]:
    compass = rules.get("compass", {})
    inflow = {t.lower() for t in compass.get("foreign_flow", {}).get("inflow", [])}
    outflow = {t.lower() for t in compass.get("foreign_flow", {}).get("outflow", [])}
    return inflow, outflow


def score_growth(
    market: MarketIndicators, rules: dict[str, Any]
) -> tuple[float, str, list[ScoreBreakdownItem]]:
    kospi_rules = rules.get("compass", {}).get("kospi", {})
    drawdown = _kospi_drawdown_pct(market)
    vs_ma = _kospi_vs_ma200_pct(market)
    score = 0.0
    parts: list[str] = []
    breakdown: list[ScoreBreakdownItem] = []

    if vs_ma is not None:
        premium = float(kospi_rules.get("ma200_premium_expansion", 5))
        if vs_ma >= premium:
            contrib = 0.5
            detail = f"KOSPI 200MA 대비 +{vs_ma:.1f}% (확장)"
        elif vs_ma >= 0:
            contrib = 0.2
            detail = f"KOSPI 200MA 상회 (+{vs_ma:.1f}%)"
        elif vs_ma >= -5:
            contrib = -0.1
            detail = f"KOSPI 200MA 근접 ({vs_ma:.1f}%)"
        else:
            contrib = -0.5
            detail = f"KOSPI 200MA 하회 ({vs_ma:.1f}%)"
        score += contrib
        parts.append(detail)
        breakdown.append(ScoreBreakdownItem(axis="growth", indicator="kospi_vs_200ma", contribution=contrib, detail=detail))

    if drawdown is not None:
        contraction = float(kospi_rules.get("drawdown_contraction", -10))
        recovery = float(kospi_rules.get("drawdown_recovery", -5))
        if drawdown >= recovery:
            contrib = 0.3
            detail = f"고점 대비 {drawdown:+.1f}% (강세)"
        elif drawdown >= contraction:
            contrib = -0.1
            detail = f"고점 대비 {drawdown:+.1f}% (조정)"
        else:
            contrib = -0.4
            detail = f"고점 대비 {drawdown:+.1f}% (깊은 조정)"
        score += contrib
        parts.append(detail)
        breakdown.append(
            ScoreBreakdownItem(axis="growth", indicator="kospi_drawdown", contribution=contrib, detail=detail)
        )

    flow = market.foreign_flow_3d.lower()
    inflow_tags, outflow_tags = _flow_tags(rules)
    if flow in inflow_tags:
        contrib = 0.2
        detail = "외국인 순매수"
        score += contrib
        parts.append(detail)
        breakdown.append(
            ScoreBreakdownItem(axis="growth", indicator="foreign_flow_3d", contribution=contrib, detail=detail)
        )
    elif flow in outflow_tags:
        contrib = -0.2
        detail = "외국인 순매도"
        score += contrib
        parts.append(detail)
        breakdown.append(
            ScoreBreakdownItem(axis="growth", indicator="foreign_flow_3d", contribution=contrib, detail=detail)
        )

    sp500_rules = rules.get("compass", {}).get("sp500", {})
    sp_dd = _sp500_drawdown_pct(market)
    if sp_dd is not None:
        recovery = float(sp500_rules.get("drawdown_recovery", -5))
        contraction = float(sp500_rules.get("drawdown_contraction", -10))
        if sp_dd >= recovery:
            contrib = 0.15
            detail = f"S&P500 고점 대비 {sp_dd:+.1f}% (글로벌 성장)"
        elif sp_dd >= contraction:
            contrib = -0.05
            detail = f"S&P500 조정 {sp_dd:.1f}%"
        else:
            contrib = -0.2
            detail = f"S&P500 깊은 조정 {sp_dd:.1f}%"
        score += contrib
        parts.append(detail)
        breakdown.append(
            ScoreBreakdownItem(axis="growth", indicator="sp500_drawdown", contribution=contrib, detail=detail)
        )

    score = max(-1.0, min(1.0, score))
    return score, "; ".join(parts) if parts else "성장 신호 부족", breakdown


def score_inflation(
    market: MarketIndicators, rules: dict[str, Any]
) -> tuple[float, str, list[ScoreBreakdownItem]]:
    compass = rules.get("compass", {})
    score = 0.0
    parts: list[str] = []
    breakdown: list[ScoreBreakdownItem] = []

    oil_shock = float(compass.get("oil_brent", {}).get("shock_above", 90))
    oil_low = float(compass.get("oil_brent", {}).get("deflation_below", 60))
    if market.oil_brent >= oil_shock:
        contrib = 0.5
        detail = f"유가 ${market.oil_brent:.0f} (인플레 압력)"
        score += contrib
        parts.append(detail)
        breakdown.append(ScoreBreakdownItem(axis="inflation", indicator="oil_brent", contribution=contrib, detail=detail))
    elif market.oil_brent <= oil_low and market.oil_brent > 0:
        contrib = -0.3
        detail = f"유가 ${market.oil_brent:.0f} (디플레이션 우려)"
        score += contrib
        parts.append(detail)
        breakdown.append(ScoreBreakdownItem(axis="inflation", indicator="oil_brent", contribution=contrib, detail=detail))
    elif market.oil_brent > 0:
        parts.append(f"유가 ${market.oil_brent:.0f} (중립)")

    rising = float(compass.get("korea_10y", {}).get("rising_above", 4.5))
    falling = float(compass.get("korea_10y", {}).get("falling_below", 3.0))
    if market.korea_10y >= rising:
        contrib = 0.3
        detail = f"국채 {market.korea_10y:.2f}% (금리 상승)"
        score += contrib
        parts.append(detail)
        breakdown.append(ScoreBreakdownItem(axis="inflation", indicator="korea_10y", contribution=contrib, detail=detail))
    elif market.korea_10y <= falling and market.korea_10y > 0:
        contrib = -0.2
        detail = f"국채 {market.korea_10y:.2f}% (금리 하락)"
        score += contrib
        parts.append(detail)
        breakdown.append(ScoreBreakdownItem(axis="inflation", indicator="korea_10y", contribution=contrib, detail=detail))

    fx_stress = float(compass.get("usdkrw", {}).get("stress_above", 1550))
    if market.usdkrw >= fx_stress:
        contrib = 0.2
        detail = f"환율 {market.usdkrw:.0f}원 (수입물가 압력)"
        score += contrib
        parts.append(detail)
        breakdown.append(ScoreBreakdownItem(axis="inflation", indicator="usdkrw", contribution=contrib, detail=detail))

    gold_rules = rules.get("compass", {}).get("gold", {})
    oil_for_gold = float(gold_rules.get("inflation_hedge_oil_above", 85))
    if market.gold > 0 and market.oil_brent >= oil_for_gold:
        contrib = 0.15
        detail = f"금 ${market.gold:.0f} + 유가 (인플레 헤지 수요)"
        score += contrib
        parts.append(detail)
        breakdown.append(
            ScoreBreakdownItem(axis="inflation", indicator="gold_inflation_hedge", contribution=contrib, detail=detail)
        )

    score = max(-1.0, min(1.0, score))
    return score, "; ".join(parts) if parts else "인플레 신호 중립", breakdown


def score_liquidity(
    market: MarketIndicators, rules: dict[str, Any]
) -> tuple[float, str, list[ScoreBreakdownItem]]:
    compass = rules.get("compass", {})
    score = 0.0
    parts: list[str] = []
    breakdown: list[ScoreBreakdownItem] = []

    vix = market.vix
    risk_on = float(compass.get("vix", {}).get("risk_on_below", 18))
    caution = float(compass.get("vix", {}).get("caution_below", 25))
    if vix > 0:
        if vix < risk_on:
            contrib = 0.4
            detail = f"VIX {vix:.1f} (유동성 양호)"
        elif vix < caution:
            contrib = 0.0
            detail = f"VIX {vix:.1f} (중립)"
        else:
            contrib = -0.5
            detail = f"VIX {vix:.1f} (유동성 경색)"
        score += contrib
        parts.append(detail)
        breakdown.append(ScoreBreakdownItem(axis="liquidity", indicator="vix", contribution=contrib, detail=detail))

    falling = float(compass.get("korea_10y", {}).get("falling_below", 3.0))
    if 0 < market.korea_10y <= falling:
        contrib = 0.2
        detail = "금리 하락 = 완화적 환경"
        score += contrib
        parts.append(detail)
        breakdown.append(ScoreBreakdownItem(axis="liquidity", indicator="korea_10y", contribution=contrib, detail=detail))

    if market.gold > 0 and market.vix > float(compass.get("gold", {}).get("safe_haven_vix_above", 22)):
        contrib = -0.15
        detail = f"금 ${market.gold:.0f} + VIX {market.vix:.1f} (안전자산 선호)"
        score += contrib
        parts.append(detail)
        breakdown.append(
            ScoreBreakdownItem(axis="liquidity", indicator="gold_safe_haven", contribution=contrib, detail=detail)
        )

    score = max(-1.0, min(1.0, score))
    return score, "; ".join(parts) if parts else "유동성 신호 중립", breakdown


def score_risk_appetite(
    market: MarketIndicators, rules: dict[str, Any]
) -> tuple[float, str, list[ScoreBreakdownItem]]:
    compass = rules.get("compass", {})
    score = 0.0
    parts: list[str] = []
    breakdown: list[ScoreBreakdownItem] = []

    vix = market.vix
    stable = float(compass.get("vix", {}).get("stable_below", 22))
    risk_off = float(compass.get("vix", {}).get("risk_off_below", 30))
    if vix > 0:
        if vix < stable:
            contrib = 0.4
            detail = f"VIX {vix:.1f} (Risk-On)"
        elif vix < risk_off:
            contrib = -0.2
            detail = f"VIX {vix:.1f} (경계)"
        else:
            contrib = -0.6
            detail = f"VIX {vix:.1f} (Risk-Off)"
        score += contrib
        parts.append(detail)
        breakdown.append(
            ScoreBreakdownItem(axis="risk_appetite", indicator="vix", contribution=contrib, detail=detail)
        )

    drawdown = _kospi_drawdown_pct(market)
    if drawdown is not None:
        if drawdown >= -3:
            contrib = 0.2
            score += contrib
            breakdown.append(
                ScoreBreakdownItem(
                    axis="risk_appetite",
                    indicator="kospi_drawdown",
                    contribution=contrib,
                    detail=f"KOSPI 고점 근접 ({drawdown:+.1f}%)",
                )
            )
        elif drawdown <= -10:
            contrib = -0.3
            detail = f"KOSPI 조정 {drawdown:.1f}%"
            score += contrib
            parts.append(detail)
            breakdown.append(
                ScoreBreakdownItem(axis="risk_appetite", indicator="kospi_drawdown", contribution=contrib, detail=detail)
            )

    flow = market.foreign_flow_3d.lower()
    inflow_tags, outflow_tags = _flow_tags(rules)
    if flow in inflow_tags:
        contrib = 0.2
        score += contrib
        breakdown.append(
            ScoreBreakdownItem(
                axis="risk_appetite", indicator="foreign_flow_3d", contribution=contrib, detail="외국인 순매수"
            )
        )
    elif flow in outflow_tags:
        contrib = -0.2
        score += contrib
        breakdown.append(
            ScoreBreakdownItem(
                axis="risk_appetite", indicator="foreign_flow_3d", contribution=contrib, detail="외국인 순매도"
            )
        )

    if market.sp500 > 0:
        sp_dd = _sp500_drawdown_pct(market)
        if sp_dd is not None and sp_dd >= -3:
            contrib = 0.15
            score += contrib
            breakdown.append(
                ScoreBreakdownItem(
                    axis="risk_appetite",
                    indicator="sp500_drawdown",
                    contribution=contrib,
                    detail=f"S&P500 고점 근접 ({sp_dd:+.1f}%)",
                )
            )
        elif sp_dd is not None and sp_dd <= -10:
            contrib = -0.2
            score += contrib
            parts.append(f"S&P500 조정 {sp_dd:.1f}%")
            breakdown.append(
                ScoreBreakdownItem(
                    axis="risk_appetite", indicator="sp500_drawdown", contribution=contrib,
                    detail=f"S&P500 조정 {sp_dd:.1f}%",
                )
            )

    if market.gold > 0 and market.vix >= float(compass.get("gold", {}).get("safe_haven_vix_above", 22)):
        contrib = -0.25
        score += contrib
        parts.append(f"금 안전자산 ({market.gold:.0f})")
        breakdown.append(
            ScoreBreakdownItem(
                axis="risk_appetite", indicator="gold_safe_haven", contribution=contrib,
                detail="Risk-Off · gold bid",
            )
        )

    score = max(-1.0, min(1.0, score))
    return score, "; ".join(parts) if parts else "리스크 선호 중립", breakdown


def classify_market_phase(growth_score: float, rules: dict[str, Any]) -> tuple[MarketPhase, float]:
    phase_rules = rules.get("phase_rules", {})
    expansion_min = float(phase_rules.get("expansion_min_growth", 0.35))
    recovery_min = float(phase_rules.get("recovery_min_growth", 0.0))
    contraction_max = float(phase_rules.get("contraction_max_growth", -0.25))

    if growth_score >= expansion_min:
        return MarketPhase.MARKET_EXPANSION, min(1.0, 0.5 + (growth_score - expansion_min))
    if growth_score >= recovery_min:
        return MarketPhase.MARKET_RECOVERY, min(1.0, 0.4 + growth_score * 0.5)
    if growth_score >= contraction_max:
        return MarketPhase.MARKET_SLOWDOWN, min(1.0, 0.4 + abs(growth_score) * 0.3)
    return MarketPhase.MARKET_CONTRACTION, min(1.0, 0.5 + abs(growth_score - contraction_max))


# backward compatibility alias
classify_economic_phase = classify_market_phase
