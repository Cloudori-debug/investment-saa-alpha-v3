from __future__ import annotations

from pathlib import Path

import pytest

from src.decision.shadow_performance import (
    classify_blocked_outcome,
    derive_primary_blocker,
    compute_saa_proxy_returns,
)


def test_derive_primary_blocker_priority() -> None:
    blocked = ["alpha_trade_blocked", "dry_run", "data_gate_red"]
    assert derive_primary_blocker(blocked) == "data_gate_red"


def test_classify_blocked_outcome() -> None:
    assert classify_blocked_outcome(-2.0) == "GOOD_BLOCK"
    assert classify_blocked_outcome(3.0) == "BAD_BLOCK"
    assert classify_blocked_outcome(0.5) == "NEUTRAL"
    assert classify_blocked_outcome(None) == ""


def test_saa_proxy_returns_from_history(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "saa_profiles.yaml").write_text(
        """
default_profile: defensive_balanced
profiles:
  defensive_balanced:
    groups:
      cash_short_bond: 40
      domestic_beta: 10
      global_beta: 10
      fx_dollar: 3
      hedge_alt: 4
      income_alt: 2
      kr_alpha: 31
    group_bounds:
      cash_short_bond: {min: 25, max: 55}
""",
        encoding="utf-8",
    )
    (data_dir / "market_indicators_history.csv").write_text(
        "date,kospi,sp500,gold\n"
        "2026-06-17,2500,5000,2700\n"
        "2026-06-18,2550,5050,2710\n"
        "2026-06-19,2600,5100,2720\n",
        encoding="utf-8",
    )
    out = compute_saa_proxy_returns(data_dir, "2026-06-19")
    assert out["benchmark_saa_return_1d"] is not None
    assert out["benchmark_saa_return_1d"] > 0
