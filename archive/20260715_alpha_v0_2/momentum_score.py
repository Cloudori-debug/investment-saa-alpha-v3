from __future__ import annotations

from typing import Any

from src.alpha.schemas import PriceRecord

from src.alpha_v0_2.config_loader import clamp_score
from src.alpha_v0_2.schemas import GateResult


def _bench_returns(prices_by_ticker: dict[str, PriceRecord], cfg: dict[str, Any]) -> tuple[float, float]:
    bench_ticker = str(cfg.get("momentum", {}).get("benchmark_ticker", "069500"))
    bench = prices_by_ticker.get(bench_ticker)
    if bench is None:
        return 0.0, 0.0
    r90 = bench.return_3m if cfg.get("momentum", {}).get("use_return_3m_as_90d", True) else bench.return_1m
    r120 = bench.return_6m if cfg.get("momentum", {}).get("use_return_6m_as_120d", True) else bench.return_3m
    return float(r90 or 0), float(r120 or 0)


def score_momentum(
    price: PriceRecord | None,
    prices_by_ticker: dict[str, PriceRecord],
    cfg: dict[str, Any],
) -> GateResult:
    if price is None:
        return GateResult(passed=False, score=0.0, reasons=["no_price"])

    bench_90, bench_120 = _bench_returns(prices_by_ticker, cfg)
    r90 = float(price.return_3m or 0)
    r120 = float(price.return_6m or 0)
    rel90 = round((r90 - bench_90) * 100, 2)
    rel120 = round((r120 - bench_120) * 100, 2)

    mcfg = cfg.get("momentum", {})
    min90 = float(mcfg.get("min_relative_90d", 0.0))
    min120 = float(mcfg.get("min_relative_120d", 0.0))

    reasons: list[str] = []
    points = 0.0
    if rel90 >= min90:
        points += 1.0
    else:
        reasons.append(f"rel90_{rel90:.1f}p")
    if rel120 >= min120:
        points += 1.0
    else:
        reasons.append(f"rel120_{rel120:.1f}p")
    if rel90 > rel120 - 5:
        points += 1.0
    else:
        reasons.append("momentum_deteriorating")

    score = clamp_score(points / 3 * 100)
    passed = rel90 >= min90 and rel120 >= min120
    if not passed:
        reasons.append("momentum_fail_new_buy_block")

    gate = GateResult(
        passed=passed,
        score=score,
        reasons=reasons,
        rel_return_90d=rel90,
        rel_return_120d=rel120,
    )
    return gate


def momentum_relative_returns(
    price: PriceRecord | None,
    prices_by_ticker: dict[str, PriceRecord],
    cfg: dict[str, Any],
) -> tuple[float | None, float | None]:
    if price is None:
        return None, None
    bench_90, bench_120 = _bench_returns(prices_by_ticker, cfg)
    return (
        round((float(price.return_3m or 0) - bench_90) * 100, 2),
        round((float(price.return_6m or 0) - bench_120) * 100, 2),
    )
