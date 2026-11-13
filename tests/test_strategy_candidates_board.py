"""전략 투자 후보 · 확인① 연동 · 포트 유니버스 기본."""

from __future__ import annotations

from pathlib import Path

from alpha_system.ui.services.strategy_candidates_board import (
    build_strategy_candidates,
    candidates_section_html,
    candidates_table_rows,
    persist_candidates_after_quant,
    theme_slug_for_strategy,
)


ROOT = Path(__file__).resolve().parents[1]


class _R:
    def __init__(self, ticker: str, name: str, w: float = 10.0) -> None:
        self.ticker = ticker
        self.name = name
        self.weight_pct = w


def test_build_includes_soft_and_etf() -> None:
    b = build_strategy_candidates(
        ROOT,
        market="KOSPI",
        mid_soft_rows=[_R("005930", "삼성전자", 12.0)],
        short_prop_rows=[_R("000660", "SK하이닉스", 8.0)],
    )
    assert b.writes_target is False
    assert any(c.ticker == "005930" for c in b.by_strategy["mid_soft"])
    assert any(c.ticker == "000660" for c in b.by_strategy["short_momentum"])
    assert b.by_strategy["sixty_forty"]
    assert b.by_strategy["golden_butterfly"]
    assert "static_book" in b.by_strategy
    assert b.by_strategy["static_book"]
    assert all(c.role == "가계 본체 ETF" for c in b.by_strategy["static_book"])
    assert b.by_strategy["dual_momentum"] is not None
    rows = candidates_table_rows(b, strategy_id="mid_soft")
    assert rows and rows[0]["티커"] == "005930"
    assert theme_slug_for_strategy("mid_soft") == "soft"
    assert theme_slug_for_strategy("dual_momentum") == "dual"
    # 포트 유니버스 기본 = 추천 스택만 (60/40 등 Lab 후보 숨김)
    stack_rows = candidates_table_rows(b, ops_stack_only=True)
    stack_sids = {r["_sid"] for r in stack_rows}
    assert "static_book" in stack_sids
    assert "mid_soft" in stack_sids
    assert "sixty_forty" not in stack_sids
    assert "계좌" in stack_rows[0]
    assert "계좌%" in stack_rows[0]
    assert "가계%" in stack_rows[0]
    assert "포트%" in stack_rows[0]  # 하위호환=가계%
    assert "비중" in stack_rows[0]
    assert "전략" in stack_rows[0]
    port_sum = sum(float(r["_port"]) for r in stack_rows if r.get("_port"))
    assert abs(port_sum - 100.0) < 0.15
    # Soft 12% · E50 → 개별 합 6 · 삼성전자만이면 가계% 6 · 일반 계좌内 40
    soft_row = next(r for r in stack_rows if r["티커"] == "005930")
    assert float(soft_row["_port"]) == 6.0
    assert soft_row["계좌"] == "일반"
    assert abs(float(soft_row["_acct_pct"]) - 40.0) < 0.05  # 6/15*100
    assert soft_row["비중"].endswith("%")
    # 계좌内 합=100
    for acct in ("pension", "taxable"):
        acct_sum = sum(
            float(r["_acct_pct"])
            for r in stack_rows
            if r.get("_acct") == acct and r.get("_acct_pct")
        )
        assert abs(acct_sum - 100.0) < 0.2
    # 연금 행이 일반보다 앞에
    first_tax = next(i for i, r in enumerate(stack_rows) if r.get("_acct") == "taxable")
    assert all(r.get("_acct") == "pension" for r in stack_rows[:first_tax])
    html = candidates_section_html(b, title="전략별 투자 후보", ops_stack_only=True)
    assert "계좌%" in html
    assert "가계%" in html
    assert "연금·ISA" in html
    assert ">비중<" in html
    assert "pf-cand-theme-soft" in html
    assert "pf-cand-theme-static-pick" in html
    assert "계좌 이분" in html
    assert "pf-cand-legend" in html
    assert "본체(나침반적합)" in html
    assert "60/40" not in html  # Lab 후보 미표시
    assert "background:#c7d7f8" in html  # Soft 인라인 색
    assert "pf-cand-theme-dual" in html or "듀얼" in html
    assert "border-left:4px solid" in html
    assert "<style>" in html
    assert html.count("중기 Soft") >= 1


def test_refresh_py_wires_candidates() -> None:
    src = (
        ROOT / "alpha_system" / "ui" / "services" / "refresh.py"
    ).read_text(encoding="utf-8")
    assert "persist_candidates_after_quant" in src


def test_portfolio_universe_default_and_cands() -> None:
    pf = (
        ROOT / "alpha_system" / "ui" / "pages" / "portfolio.py"
    ).read_text(encoding="utf-8")
    assert 'st.session_state["portfolio_section"] = tab_universe' in pf
    assert "(tab_universe, tab_ops)" in pf
    uni = (
        ROOT
        / "alpha_system"
        / "ui"
        / "services"
        / "portfolio_universe_board.py"
    ).read_text(encoding="utf-8")
    assert "build_strategy_candidates" in uni
    ops = (
        ROOT / "alpha_system" / "ui" / "pages" / "strategy_ops.py"
    ).read_text(encoding="utf-8")
    assert "sec_cands" in ops or "투자 후보" in ops
    assert "sec_actions" in ops or "실행" in ops
    assert "static_book" in ops
    assert "pf-strat-sum" in ops
    assert "GEM" in ops or "듀얼" in ops
    assert callable(persist_candidates_after_quant)
