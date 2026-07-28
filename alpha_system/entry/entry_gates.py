"""Entry gates — target valuation pre-fill requirement."""

from __future__ import annotations

from typing import Mapping, Sequence

from alpha_system.schema import AlphaSystemConfig


def check_entry_target_valuation(
    cfg: AlphaSystemConfig,
    *,
    ticker: str,
    has_target_valuation: bool,
) -> tuple[bool, str]:
    """
    Return (blocked, detail).

    Confirmed: new entry blocked when per-name target valuation is missing.
    """
    _ = ticker
    if not cfg.exit.entry_require_target_valuation:
        return False, "entry_require_target_valuation=false"
    if has_target_valuation:
        return False, "target valuation on file"
    return (
        True,
        "entry blocked: per-name target valuation missing "
        "(exit.entry_require_target_valuation=true)",
    )


def missing_entry_target_tickers(
    cfg: AlphaSystemConfig,
    *,
    entry_tickers: Sequence[str] | None,
    has_target_by_ticker: Mapping[str, bool] | None = None,
) -> list[str]:
    """
    Shared SoT for UI fills and attempt_execute.

    When entry_require_target_valuation is on:
      - entry_tickers is None → sentinel ["*"] meaning "call omitted" (fail closed)
      - entry_tickers is [] → no names to check (ok)
      - otherwise list tickers that lack approved target valuation
    """
    if not cfg.exit.entry_require_target_valuation:
        return []
    if entry_tickers is None:
        return ["*"]
    missing: list[str] = []
    for raw in entry_tickers:
        ticker = str(raw).zfill(6)
        has_tv = bool((has_target_by_ticker or {}).get(ticker, False))
        blocked, detail = check_entry_target_valuation(
            cfg, ticker=ticker, has_target_valuation=has_tv
        )
        if blocked:
            missing.append(f"{ticker} ({detail})")
    return missing
