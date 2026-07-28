from __future__ import annotations

from src.execution_scope import (
    apply_execution_scope_to_actions,
    derive_alpha_approval,
    derive_alpha_permissions,
    derive_execution_scope,
)
from src.models import GapRow, PositionRow, TargetRow, TradeAction


def _gap(ticker: str, group: str, cur: float, tgt: float) -> GapRow:
    return GapRow(
        ticker=ticker,
        name=ticker,
        asset_group=group,
        current_weight=cur,
        target_weight=tgt,
        gap=round(tgt - cur, 2),
        min_weight=0,
        max_weight=100,
        status="Not in target" if cur > 0 and tgt == 0 else "Underweight",
        in_target=tgt > 0,
    )


def test_derive_alpha_permissions_risk_reduce_only():
    perm, pos = derive_alpha_permissions(
        alpha_data_gate="GREEN",
        execution_scope="ETF_ONLY",
        execution_policy={"kr_alpha_risk_trim_under_etf_only": True},
    )
    assert perm == "BLOCK_NEW_BUY"
    assert pos == "RISK_REDUCE_ONLY"


def test_etf_only_masks_kr_alpha_executable():
    gaps = [
        _gap("005830", "kr_alpha", 5.0, 4.0),
        _gap("069500", "domestic_beta", 0.0, 10.0),
    ]
    raw = [
        TradeAction(ticker="005830", name="DB", action="Replace", reason="not in target", allowed_size_pct=-5, priority="High"),
        TradeAction(ticker="069500", name="KODEX", action="Wait", reason="no trigger", allowed_size_pct=0, priority="Medium"),
    ]
    executable, review = apply_execution_scope_to_actions(raw, gaps, "ETF_ONLY")
    kr_exec = next(a for a in executable if a.ticker == "005830")
    assert kr_exec.action == "Review-only"
    assert "Replace" in kr_exec.reason
    assert kr_exec.priority == "Low"
    assert len(review) == 1
    assert review[0].action == "Replace"


def test_derive_alpha_approval_restricted_on_etf_only():
    assert derive_alpha_approval("GREEN", "ETF_ONLY") == "RESTRICTED"
    assert derive_alpha_approval("GREEN", "FULL_WITH_ALPHA") == "APPROVED"


def test_derive_execution_scope_yellow():
    assert derive_execution_scope(
        data_gate="YELLOW",
        portfolio_gate="GREEN",
        alpha_data_gate="GREEN",
        health_overall="warn",
    ) == "ETF_ONLY"


def test_etf_only_alpha_review_masks_kr_alpha():
    from src.execution_scope import apply_execution_scope_to_actions
    from src.models import TradeAction

    gaps = [
        GapRow(
            ticker="005830",
            name="DB",
            asset_group="kr_alpha",
            current_weight=5.0,
            target_weight=4.0,
            gap=-1.0,
            min_weight=0,
            max_weight=10,
            status="Overweight",
            in_target=True,
        ),
    ]
    raw = [
        TradeAction(
            ticker="005830",
            name="DB",
            action="Buy-allowed",
            reason="trigger",
            allowed_size_pct=0,
            priority="High",
        ),
    ]
    executable, _ = apply_execution_scope_to_actions(raw, gaps, "ETF_ONLY_ALPHA_REVIEW")
    assert executable[0].action == "Review-only"
