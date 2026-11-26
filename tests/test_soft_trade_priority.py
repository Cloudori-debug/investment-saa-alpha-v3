"""중기 Soft 매매 우선순위 · 사람 열 기본안."""

from __future__ import annotations

from types import SimpleNamespace

from alpha_system.ui.services.soft_trade_priority import (
    activist_human_default,
    rank_soft_trade_hints,
)


def _row(
    ticker: str,
    *,
    name: str = "",
    price: float = 10000.0,
    target: float | None = 15000.0,
    score: float = 60.0,
    held: bool = False,
    has_target: bool = True,
    gap: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        ticker=ticker,
        name=name or ticker,
        current_price=price,
        target_price=target,
        has_target=has_target and target is not None,
        total_score=score,
        is_held=held,
        target_gap_kind=gap,
    )


def test_today_slots_cap_and_order() -> None:
    rows = [
        _row("000001", name="얇음", price=9700, target=10000, score=90),  # 3%
        _row("000002", name="여유A", price=8000, target=10000, score=70),  # 20%
        _row("000003", name="여유B", price=7000, target=10000, score=65),  # 30%
        _row("000004", name="여유C", price=6000, target=10000, score=50),  # 40%
        _row("000005", name="무목표", price=10000, target=None, score=99),
    ]
    hints = rank_soft_trade_hints(rows, held=set(), today_buy_max=2)
    by = {h.ticker: h for h in hints}
    assert by["000005"].stance == "보류"
    assert "목표가 없음" in by["000005"].human_ko
    assert by["000001"].stance == "패스"
    # 여유 큰 순 · 오늘≤2
    assert by["000004"].today_slot is True
    assert by["000003"].today_slot is True
    assert by["000002"].today_slot is False
    assert by["000002"].stance == "보류"
    assert "한도" in by["000002"].human_ko
    assert by["000004"].rank < by["000003"].rank < by["000002"].rank


def test_quant_draft_conditional() -> None:
    rows = [
        _row(
            "000010",
            name="초안",
            price=8800,
            target=10000,
            score=80,
            gap="quant_draft",
        ),  # 12% < 15%
        _row(
            "000011",
            name="초안여유",
            price=7000,
            target=10000,
            score=70,
            gap="quant_draft",
        ),  # 30%
    ]
    hints = rank_soft_trade_hints(rows, held=set(), today_buy_max=2)
    by = {h.ticker: h for h in hints}
    assert by["000010"].stance == "보류"
    assert "초안" in by["000010"].human_ko
    assert by["000011"].stance == "조건부사기"
    assert by["000011"].today_slot is True


def test_held_excluded() -> None:
    rows = [
        _row("005930", name="삼성", held=True, score=99),
        _row("000660", name="하이닉스", held=False, score=50),
    ]
    hints = rank_soft_trade_hints(
        rows, held={"005930"}, today_buy_max=2
    )
    assert [h.ticker for h in hints] == ["000660"]


def test_activist_human_default() -> None:
    assert "합산 금지" in activist_human_default(today_rank=1, today_max=1)
    assert "한도 밖" in activist_human_default(today_rank=None)
    assert "6M" in activist_human_default(weak_6m=True)
