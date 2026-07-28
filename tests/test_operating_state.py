from __future__ import annotations

from types import SimpleNamespace

from src.models import TradeAction
from src.operating_state import derive_operating_state


def _hc(name: str, status: str, message: str = ""):
    return SimpleNamespace(name=name, status=status, message=message)


def test_error_on_critical_health_fail():
    bundle = derive_operating_state(
        system_status="YELLOW",
        data_gate="GREEN",
        execution_scope="ETF_ONLY",
        alpha_approval="RESTRICTED",
        dry_run_days=5,
        executable_actions=[],
        review_actions=[],
        health_checks=[_hc("positions", "fail", "합계 0")],
    )
    assert bundle.operating_state == "ERROR"


def test_blocked_when_wait_underweight_on_yellow_gate():
    bundle = derive_operating_state(
        system_status="YELLOW",
        data_gate="YELLOW",
        execution_scope="ETF_ONLY",
        alpha_approval="RESTRICTED",
        dry_run_days=3,
        executable_actions=[
            TradeAction(
                ticker="069500",
                name="KODEX 200",
                action="Wait",
                reason="Underweight but stop-buy or data caution",
                allowed_size_pct=0,
                priority="High",
            ),
        ],
        review_actions=[],
        buy_triggers_active=True,
    )
    assert bundle.operating_state == "BLOCKED"
    assert bundle.has_executable_trade is False
    assert "Data Gate YELLOW" in bundle.blocked_reasons


def test_kr_alpha_review_not_execute_etf():
    bundle = derive_operating_state(
        system_status="GREEN",
        data_gate="GREEN",
        execution_scope="ETF_ONLY",
        alpha_approval="RESTRICTED",
        dry_run_days=10,
        executable_actions=[],
        review_actions=[
            TradeAction(
                ticker="000660",
                name="SK하이닉스",
                action="Replace",
                reason="theoretical",
                allowed_size_pct=0,
                priority="Low",
            ),
        ],
        gap_rows=[SimpleNamespace(ticker="000660", asset_group="kr_alpha")],
    )
    assert bundle.operating_state in {"BLOCKED", "NO_ACTION"}
    assert bundle.has_executable_etf_trade is False


def test_execute_etf_when_buy_allowed():
    bundle = derive_operating_state(
        system_status="GREEN",
        data_gate="GREEN",
        execution_scope="ETF_ONLY",
        alpha_approval="RESTRICTED",
        dry_run_days=10,
        executable_actions=[
            TradeAction(
                ticker="069500",
                name="KODEX 200",
                action="Buy-allowed",
                reason="trigger ok",
                allowed_size_pct=2.0,
                priority="High",
            ),
        ],
        review_actions=[],
        gap_rows=[SimpleNamespace(ticker="069500", asset_group="domestic_beta")],
    )
    assert bundle.operating_state == "EXECUTE_ETF"
    assert bundle.has_executable_etf_trade is True


def test_review_target_when_draft_only():
    bundle = derive_operating_state(
        system_status="GREEN",
        data_gate="GREEN",
        execution_scope="FULL_WITH_ALPHA",
        alpha_approval="APPROVED",
        dry_run_days=10,
        executable_actions=[
            TradeAction(
                ticker="069500",
                name="KODEX",
                action="Hold",
                reason="ok",
                allowed_size_pct=0,
                priority="Low",
            ),
        ],
        review_actions=[],
        target_draft_pending=True,
        gap_rows=[SimpleNamespace(ticker="069500", asset_group="domestic_beta")],
    )
    assert bundle.operating_state == "REVIEW_TARGET"
    assert "target_draft" in bundle.secondary_tasks[0]


def test_no_action_when_quiet():
    bundle = derive_operating_state(
        system_status="GREEN",
        data_gate="GREEN",
        execution_scope="ETF_ONLY",
        alpha_approval="RESTRICTED",
        dry_run_days=10,
        executable_actions=[
            TradeAction(
                ticker="069500",
                name="KODEX",
                action="Hold",
                reason="on target",
                allowed_size_pct=0,
                priority="Low",
            ),
        ],
        review_actions=[],
        buy_triggers_active=False,
    )
    assert bundle.operating_state == "NO_ACTION"


def test_dry_run_in_caution_not_error():
    bundle = derive_operating_state(
        system_status="YELLOW",
        data_gate="YELLOW",
        execution_scope="ETF_ONLY",
        alpha_approval="RESTRICTED",
        dry_run_days=2,
        executable_actions=[],
        review_actions=[],
        buy_triggers_active=False,
    )
    assert bundle.operating_state == "NO_ACTION"
    assert bundle.operating_state != "ERROR"
    assert any("dry-run" in c for c in bundle.caution_reasons)
