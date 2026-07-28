from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from src.data_refresh.prices_refresh import TierAPricesResult, _normalize_ticker, ensure_tier_a_prices


def collect_tier_h_tickers(data_dir: Path) -> set[str]:
    """Tier H — 하케다카 50종 필수 갱신 대상 (Tier A와 별도)."""
    from src.hakedaka_gate import resolve_hakedaka_registry

    tickers: set[str] = set()
    for row in resolve_hakedaka_registry(data_dir):
        raw = str(row.get("ticker", "")).strip()
        if raw and raw.zfill(6) != "000000":
            tickers.add(_normalize_ticker(raw))
    return tickers


@dataclass
class TierHPricesResult:
    as_of: str
    required_count: int
    missing_before: int
    added: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    coverage_pct: float = 0.0


def ensure_tier_h_prices(
    data_dir: Path,
    as_of: str,
    *,
    fetch_missing: bool = True,
) -> TierHPricesResult:
    """하케다카 50 시세 — prices.csv merge (100% 목표)."""
    import os

    import pandas as pd

    required = collect_tier_h_tickers(data_dir)
    prices_path = data_dir / "prices.csv"
    have: set[str] = set()
    if prices_path.exists():
        df = pd.read_csv(prices_path, dtype=str, keep_default_na=False)
        have = {_normalize_ticker(t) for t in df["ticker"].tolist()}

    missing_before = len(required - have)
    added: list[str] = []
    failed: list[str] = []
    warnings: list[str] = []

    if fetch_missing and missing_before > 0 and os.environ.get("PYTEST_CURRENT_TEST") is None:
        from src.data_refresh.prices_refresh import fetch_and_merge_prices

        added, failed = fetch_and_merge_prices(
            data_dir, required, as_of, only_missing=True,
        )

    if prices_path.exists():
        df = pd.read_csv(prices_path, dtype=str, keep_default_na=False)
        have = {_normalize_ticker(t) for t in df["ticker"].tolist()}

    still_missing = sorted(required - have)
    if still_missing:
        warnings.append(f"Tier H 미수집 {len(still_missing)}종: {', '.join(still_missing[:8])}")

    coverage = (len(required - set(still_missing)) / len(required) * 100) if required else 100.0
    return TierHPricesResult(
        as_of=as_of,
        required_count=len(required),
        missing_before=missing_before,
        added=added,
        failed=failed or still_missing,
        warnings=warnings,
        coverage_pct=round(coverage, 2),
    )


def refresh_tier_h_snapshot(data_dir: Path, as_of: str | None = None) -> TierHPricesResult:
    as_of_date = as_of or date.today().isoformat()
    tier_h = ensure_tier_h_prices(data_dir, as_of_date, fetch_missing=True)
    if tier_h.missing_before == 0:
        extra = collect_tier_h_tickers(data_dir)
        ensure_tier_a_prices(
            data_dir, as_of_date, top_n=0, extra_tickers=extra, refresh_existing=True,
        )
    return tier_h
