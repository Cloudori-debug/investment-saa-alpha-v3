"""Portfolio verdict / ops playbook — conclusion-first hierarchy."""

from __future__ import annotations

from types import SimpleNamespace

from alpha_system.ui.pages.portfolio import (
    _fold_lead_html,
    _ops_playbook_html,
    _portfolio_verdict_html,
    _portfolio_verdict_html_unified,
    _proposal_empty_message,
    _proposal_map_html,
)


def test_portfolio_verdict_counts_and_actions() -> None:
    held = [
        SimpleNamespace(ticker="005930", ops_signal="cash_half", name="삼성전자"),
        SimpleNamespace(ticker="000660", ops_signal="trim", name="SK하이닉스"),
        SimpleNamespace(ticker="035420", ops_signal="hold", name="NAVER"),
    ]
    prop = [SimpleNamespace(ticker="005930", name="삼성전자")]
    ctx = SimpleNamespace(
        portfolio_rows=prop,
        proposal_blocked_rows=[SimpleNamespace(ticker="000270")],
        ops_portfolio_rows=held,
        screen_market="KOSPI",
        screen_horizon="mid",
        root=".",
        source_data_dir=None,
    )
    html = _portfolio_verdict_html(ctx)
    assert "결론" in html
    assert ">1<" in html or "최종 제안" in html
    assert "환금" in html or "줄이기" in html
    assert "자동주문" in html or "target" in html


def test_ops_playbook_sell_hold_buy_order() -> None:
    mid = SimpleNamespace(
        portfolio_rows=[
            SimpleNamespace(ticker="005930", name="삼성전자"),
            SimpleNamespace(ticker="000660", name="SK하이닉스"),
        ],
        proposal_blocked_rows=[],
        ops_portfolio_rows=[
            SimpleNamespace(ticker="005930", ops_signal="hold", name="삼성전자"),
            SimpleNamespace(ticker="035420", ops_signal="cash_half", name="NAVER"),
        ],
        screen_market="KOSPI",
        screen_horizon="mid",
        root=".",
        source_data_dir=None,
    )
    short = SimpleNamespace(
        portfolio_rows=[],
        proposal_blocked_rows=[],
        ops_portfolio_rows=[],
        screen_market="KOSPI",
        screen_horizon="short",
        root=".",
        source_data_dir=None,
    )
    html = _ops_playbook_html(mid, short, root=".")
    assert "팔기" in html
    assert "유지" in html
    assert "사기" in html
    assert "오늘 매매" in html
    assert "나침반" in html
    assert "제안만" in html or "사 Review" in html
    # unified alias
    assert "팔기" in _portfolio_verdict_html_unified(mid, short)


def test_fold_lead_has_purpose_do_ignore() -> None:
    html = _fold_lead_html(
        purpose="보조만",
        do_now="집합만 보기",
        ignore="자동주문",
    )
    assert "이 칸" in html
    assert "지금" in html
    assert "무시" in html
    assert "보조만" in html
    assert "자동주문" in html


def test_short_proposal_empty_not_cutoff_scare() -> None:
    msg = _proposal_empty_message(short=True, n_blocked=4)
    assert "합격선 고장" in msg or "중기" in msg
    assert "점수표를 점검" not in msg
    html = _proposal_map_html(
        short=True,
        quality_sort=False,
        n_eligible=0,
        n_blocked=4,
        n_held=0,
    )
    assert "사도 됨" in html
    assert "지금은 안 삼" in html
    assert "SHORT_PROFIT" not in html
    assert "중기" in html or "파킹" in html
