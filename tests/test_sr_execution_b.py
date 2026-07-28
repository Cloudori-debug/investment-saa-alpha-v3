"""B안: execution continuity → score_sr (SR4)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
ALPHA = ROOT / "alpha_portfolio"
sys.path.insert(0, str(ALPHA))

from src.execution_continuity import quarters_hit_to_score, resolve_execution_continuity  # noqa: E402
from src.factors import score_shareholder  # noqa: E402


def test_quarters_rubric() -> None:
    assert quarters_hit_to_score(0) == 0.0
    assert quarters_hit_to_score(2) == 50.0
    assert quarters_hit_to_score(4) == 100.0
    assert quarters_hit_to_score(9) == 100.0


def test_resolve_prefers_explicit_quarters() -> None:
    score, prov = resolve_execution_continuity({"execution_quarters_hit": 3, "dividend_yield": 0})
    assert score == 75.0
    assert prov == "quarters"


def test_resolve_proxy_snapshot() -> None:
    score, prov = resolve_execution_continuity(
        {"dividend_yield": 3.0, "buyback_3y": True, "payout_ratio": 35}
    )
    assert prov == "proxy_snapshot"
    assert score == 100.0  # 2+1+1


def test_score_sr_includes_execution_weight() -> None:
    cfg = yaml.safe_load((ALPHA / "config" / "alpha_scoring.yaml").read_text(encoding="utf-8"))
    weak = pd.Series(
        {
            "dividend_yield": 3.0,
            "payout_ratio": 35.0,
            "buyback_3y": False,
            "execution_quarters_hit": 0,
        }
    )
    strong = pd.Series(
        {
            "dividend_yield": 3.0,
            "payout_ratio": 35.0,
            "buyback_3y": False,
            "execution_quarters_hit": 4,
        }
    )
    s_weak, _ = score_shareholder(weak, cfg)
    s_strong, _ = score_shareholder(strong, cfg)
    assert s_strong > s_weak
