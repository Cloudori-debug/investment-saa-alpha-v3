from __future__ import annotations

from src.alpha_action_guards import apply_holdings_review_guards
from src.execution_scope import (
    apply_dry_run_scope_cap,
    derive_execution_scope,
    scope_blocks_kr_alpha_execution,
)
from src.models import GapRow, TradeAction


def _gap(ticker: str, cur: float, tgt: float) -> GapRow:
    return GapRow(
        ticker=ticker,
        name=ticker,
        asset_group="kr_alpha",
        current_weight=cur,
        target_weight=tgt,
        gap=round(tgt - cur, 2),
        min_weight=0,
        max_weight=10,
        status="Underweight",
        in_target=tgt > 0,
    )


def test_dry_run_caps_full_with_alpha():
    assert apply_dry_run_scope_cap("FULL_WITH_ALPHA", 2) == "ETF_ONLY_ALPHA_REVIEW"
    assert apply_dry_run_scope_cap("FULL_WITH_ALPHA", 10) == "FULL_WITH_ALPHA"
    assert scope_blocks_kr_alpha_execution("ETF_ONLY_ALPHA_REVIEW")


def test_derive_execution_scope_with_dry_run():
    scope = derive_execution_scope(
        data_gate="GREEN",
        portfolio_gate="GREEN",
        alpha_data_gate="GREEN",
        health_overall="pass",
        dry_run_days=1,
    )
    assert scope == "ETF_ONLY_ALPHA_REVIEW"


def test_holdings_review_blocks_buy_on_trim():
    gaps = [_gap("030190", 0.0, 1.4)]
    raw = [
        TradeAction(
            ticker="030190",
            name="NICE",
            action="Buy-allowed",
            reason="trigger",
            allowed_size_pct=1.4,
            priority="High",
        )
    ]
    review = [{"ticker": "030190", "review_action": "TRIM"}]
    out = apply_holdings_review_guards(raw, gaps, review)
    assert out[0].action == "Wait"
    assert "TRIM" in out[0].reason
