"""Method B stats helpers (stdlib DSR — no scipy)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtest.compass_method_b.stats import deflated_sharpe_ratio, expected_max_sr


def test_expected_max_sr_increases_with_trials() -> None:
    a = expected_max_sr(2, t=500)
    b = expected_max_sr(16, t=500)
    assert b > a > 0


def test_dsr_random_noise_not_significant() -> None:
    rng = np.random.default_rng(0)
    r = pd.Series(rng.normal(0, 0.01, size=800))
    out = deflated_sharpe_ratio(r, n_trials=16)
    assert out["n_obs"] == 800
    # Pure noise should not pass a high DSR bar
    assert out["dsr"] < 0.95


def test_dsr_strong_signal_high() -> None:
    rng = np.random.default_rng(1)
    r = pd.Series(0.002 + rng.normal(0, 0.005, size=800))
    out = deflated_sharpe_ratio(r, n_trials=16)
    assert out["sr_hat_ann"] > 0
    assert out["dsr"] > 0.5
