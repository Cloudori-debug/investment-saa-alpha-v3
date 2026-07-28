from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.alpha.schemas import PriceRecord, UniverseRecord

MarketTier = Literal["Core", "Mid", "Watch", "Shadow", "Exclude"]
ExecutableFlag = Literal["eligible", "shadow_watch", "excluded"]


@dataclass(frozen=True)
class MarketFilterResult:
    ticker: str
    market: str
    market_cap: float
    avg_turnover_20d: float
    tier: MarketTier
    executable_universe: bool
    buy_permission: bool
    shadow_watch: bool
    reason: str


def _tier_kospi(market_cap: float, turnover: float) -> tuple[MarketTier, bool, bool, str]:
    if market_cap < 200_000_000_000 or turnover < 2_000_000_000:
        return "Exclude", False, False, "below KOSPI minimum cap/liquidity"
    if market_cap >= 1_000_000_000_000 and turnover >= 5_000_000_000:
        return "Core", True, False, "KOSPI Core"
    if market_cap >= 500_000_000_000 and turnover >= 3_000_000_000:
        return "Mid", True, False, "KOSPI Mid"
    if market_cap >= 200_000_000_000 and turnover >= 2_000_000_000:
        return "Watch", True, False, "KOSPI Watch"
    return "Exclude", False, False, "KOSPI liquidity/cap mismatch"


def _tier_kosdaq(market_cap: float, turnover: float) -> tuple[MarketTier, bool, bool, str]:
    if market_cap < 100_000_000_000 or turnover < 1_000_000_000:
        return "Exclude", False, False, "below KOSDAQ minimum cap/liquidity"
    if market_cap >= 500_000_000_000 and turnover >= 5_000_000_000:
        return "Core", True, False, "KOSDAQ Core"
    if market_cap >= 300_000_000_000 and turnover >= 3_000_000_000:
        return "Mid", True, False, "KOSDAQ Mid"
    if market_cap >= 100_000_000_000 and turnover >= 1_000_000_000:
        return "Shadow", False, True, "KOSDAQ Shadow Watch — review-only"
    return "Exclude", False, False, "KOSDAQ liquidity/cap mismatch"


def classify_market_tier(
    rec: UniverseRecord,
    price: PriceRecord | None,
) -> MarketFilterResult:
    market = (rec.market or "KOSPI").upper()
    market_cap = float(price.market_cap if price and price.market_cap else 0)
    turnover = float(price.trading_value_20d if price and price.trading_value_20d else 0)

    if market == "KOSDAQ":
        tier, executable, shadow, reason = _tier_kosdaq(market_cap, turnover)
    else:
        tier, executable, shadow, reason = _tier_kospi(market_cap, turnover)

    buy_permission = executable and not shadow
    return MarketFilterResult(
        ticker=rec.ticker,
        market=market,
        market_cap=market_cap,
        avg_turnover_20d=turnover,
        tier=tier,
        executable_universe=executable or shadow,
        buy_permission=buy_permission,
        shadow_watch=shadow,
        reason=reason,
    )
