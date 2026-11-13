"""계좌 이분 할 일 · 역발상 Soft 게이트."""

from __future__ import annotations

from pathlib import Path

from alpha_system.ui.services.account_ops_checklist import (
    ACCOUNT_BUDGET_PCT,
    ACCOUNT_PENSION,
    ACCOUNT_TAXABLE,
    DAY_BUY_CAP_PCT,
    account_ops_checklist_html,
    build_account_ops_checklist,
    build_contrarian_gate_steps,
)
from alpha_system.ui.services.strategy_candidates_board import (
    StrategyCandidate,
    StrategyCandidatesBundle,
    build_strategy_candidates,
)

ROOT = Path(__file__).resolve().parents[1]


class _R:
    def __init__(self, ticker: str, name: str, w: float = 10.0) -> None:
        self.ticker = ticker
        self.name = name
        self.weight_pct = w


def test_budget_split_85_15() -> None:
    assert ACCOUNT_BUDGET_PCT[ACCOUNT_PENSION] == 85.0
    assert ACCOUNT_BUDGET_PCT[ACCOUNT_TAXABLE] == 15.0


def test_checklist_todos_and_no_target() -> None:
    b = build_strategy_candidates(
        ROOT,
        market="KOSPI",
        mid_soft_rows=[_R("005930", "삼성전자", 12.0)],
        short_prop_rows=[_R("000660", "SK하이닉스", 8.0)],
    )
    cl = build_account_ops_checklist(b, soft_funded_from_pension=False)
    assert cl.writes_target is False
    assert cl.review_only is True
    assert cl.account_budget_pct[ACCOUNT_PENSION] == 85.0
    assert len(cl.pension_items) == 2
    assert len(cl.taxable_items) == 2
    assert any("정적" in i.title_ko for i in cl.pension_items)
    assert any("Soft" in i.title_ko for i in cl.taxable_items)
    assert any("합산" in i.done_when_ko for i in cl.pension_items)


def test_fear_alone_not_buy_pass() -> None:
    steps = build_contrarian_gate_steps(
        soft_equity_n=1,
        observe_deep_or_precise=True,
        logic_or_essence_ok=True,
        gieop_gate="PASS",
        fear_tone="hot",
        fear_as_buy_signal=True,
        day_buy_pct=20.0,
        soft_funded_from_pension=False,
    )
    fear = next(s for s in steps if s.id == "fear")
    assert fear.status == "fail"
    cl = build_account_ops_checklist(
        StrategyCandidatesBundle(as_of="t", market="KOSPI"),
        observe_deep_or_precise=True,
        logic_or_essence_ok=True,
        gieop_gate="PASS",
        fear_tone="hot",
        fear_as_buy_signal=True,
        day_buy_pct=20.0,
    )
    assert cl.gate_verdict == "fail"
    assert "대기" in cl.gate_line_ko or "실패" in cl.gate_line_ko


def test_day_cap_over_33_fails() -> None:
    steps = build_contrarian_gate_steps(
        soft_equity_n=1,
        observe_deep_or_precise=True,
        logic_or_essence_ok=True,
        gieop_gate="PASS",
        fear_tone="ok",
        day_buy_pct=DAY_BUY_CAP_PCT + 1,
        soft_funded_from_pension=False,
    )
    day = next(s for s in steps if s.id == "day_cap")
    assert day.status == "fail"


def test_pension_funding_soft_fails() -> None:
    steps = build_contrarian_gate_steps(
        soft_equity_n=1,
        observe_deep_or_precise=True,
        logic_or_essence_ok=True,
        gieop_gate="PASS",
        fear_tone="ok",
        day_buy_pct=20.0,
        soft_funded_from_pension=True,
    )
    acct = next(s for s in steps if s.id == "account")
    assert acct.status == "fail"


def test_html_contains_accounts() -> None:
    empty = StrategyCandidatesBundle(
        as_of="t",
        market="KOSPI",
        by_strategy={
            "static_book": [
                StrategyCandidate(
                    "static_book",
                    "본체",
                    "069500",
                    "KODEX200",
                    weight_pct=100.0,
                    role="가계 본체 ETF",
                )
            ],
            "dual_momentum": [],
            "mid_soft": [],
            "short_momentum": [],
        },
    )
    cl = build_account_ops_checklist(empty)
    html = account_ops_checklist_html(cl)
    assert "연금·ISA" in html
    assert "일반" in html
    assert "역발상" in html
    assert cl.writes_target is False


def test_spec_and_buy_sell_wired() -> None:
    spec = (ROOT / "docs" / "ACCOUNT_SPLIT_OPS_SPEC.md").read_text(encoding="utf-8")
    assert "합산" in spec
    assert "역발상" in spec
    assert "Fear ⇏ Buy" in spec or "허가증" in spec
    theory = (
        ROOT
        / "docs"
        / "research"
        / "strategies"
        / "contrarian-soft-gate-theory.md"
    ).read_text(encoding="utf-8")
    assert "Fear ⇏ Buy" in theory or "Fear_hot" in theory
    assert "A. 심리" in theory and "B. 가치" in theory
    bs = (ROOT / "docs" / "BUY_SELL_MAP.md").read_text(encoding="utf-8")
    assert "ACCOUNT_SPLIT_OPS_SPEC" in bs
    assert "계좌 이분" in bs
    uni = (
        ROOT / "alpha_system" / "ui" / "services" / "portfolio_universe_board.py"
    ).read_text(encoding="utf-8")
    assert "account_ops_checklist" in uni
    assert "account_ops_caption" in uni
