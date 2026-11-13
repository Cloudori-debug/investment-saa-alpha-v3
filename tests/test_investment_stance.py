"""Active Soft stance — Park Honggi high-rate prep (Review-only)."""

from __future__ import annotations

from pathlib import Path

from alpha_system.ui.services.investment_stance import (
    investment_stance_html,
    load_investment_stance,
    merge_playbook_cards,
    stance_todos,
)


def test_load_active_phg_stance() -> None:
    root = Path(__file__).resolve().parents[1]
    st = load_investment_stance(root)
    assert st is not None
    assert st.active == "phg_high_rate_202611"
    assert st.writes_target is False
    assert st.equity_pct_hint == 50
    assert st.cash_pct_hint == 50
    assert any("본질" in x or "배당" in x for x in st.do_ko)
    assert any("전량 청산" in x for x in st.dont_ko)


def test_stance_html_and_todos() -> None:
    root = Path(__file__).resolve().parents[1]
    st = load_investment_stance(root)
    html = investment_stance_html(st)
    assert "고금리" in html or "본질" in html
    assert "하지 않는다" in html
    assert "Review-only" in html
    todos = stance_todos(st, limit=2)
    assert todos and "방향" in todos[0]
    merged = merge_playbook_cards([("중기", "게이트")], st)
    assert merged[0][0] == "방향"
