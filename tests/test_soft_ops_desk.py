"""중기 Soft 운영 데스크 A/B/C (Review-only)."""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from alpha_system.ui.services.next_buy_queue import (
    NextBuyItem,
    NextBuyQueue,
    queue_to_table_rows,
)
from alpha_system.ui.services.soft_ops_desk import (
    SoftOpsLegend,
    SoftOpsDesk,
    build_soft_ops_desk,
    _build_hold_table,
    _build_rotation_table,
    _hold_program_human,
)
from alpha_system.ui.services.weight_action import WeightAction


ROOT = Path(__file__).resolve().parents[1]


def _row(
    ticker: str,
    *,
    name: str = "",
    weight: float = 10.0,
    score: float = 60.0,
    held: bool = False,
    price: float = 10000.0,
    target: float = 15000.0,
    eligibility: bool = True,
    r1: float = 0.02,
    r6: float = 0.05,
    ops_book: str = "mid",
) -> SimpleNamespace:
    return SimpleNamespace(
        ticker=ticker,
        name=name or ticker,
        weight_pct=weight,
        total_score=score,
        is_held=held,
        current_price=price,
        target_price=target,
        has_target=True,
        eligibility=eligibility,
        return_1m=r1,
        return_6m=r6,
        ops_signal="hold",
        ops_signal_label="유지",
        ops_trim_pct=None,
        cap_near=False,
        extra={
            "ops_book": ops_book,
            "book": "ops" if held else "proposal",
            "return_1m": r1,
            "return_6m": r6,
            "trading_value_20d": 2e9,
        },
    )


def test_queue_to_table_rows_order() -> None:
    q = NextBuyQueue(
        items=(
            NextBuyItem(
                ticker="005930",
                name="삼성전자",
                total_score=61.0,
                upside_pct=20.0,
                why="x",
                return_1m=0.03,
            ),
            NextBuyItem(
                ticker="000660",
                name="SK하이닉스",
                total_score=60.0,
                upside_pct=10.0,
                why="y",
                return_1m=-0.01,
            ),
        ),
        top_k=8,
        sell_pressure=False,
        n_eligible=2,
    )
    rows = queue_to_table_rows(q)
    assert len(rows) == 2
    assert rows[0]["순위"] == 1
    assert rows[0]["티커"] == "005930"


def test_soft_out_exit_softened() -> None:
    act = WeightAction(
        kind="exit_full",
        primary="전량",
        body="제안 탈락 · 잔여 전량",
        tone="hot",
        priority=10,
        delta_pct=None,
        board_line="전량 x",
        stance="매도",
        move_pct=100.0,
    )
    prog, human = _hold_program_human(in_soft=False, act=act)
    assert prog == "슬롯 밖"
    assert "밀림" in human
    assert "매도" in human or "Review" in human


def test_rotation_empty_without_sells() -> None:
    q = NextBuyQueue(items=(), top_k=8, sell_pressure=False, n_eligible=0)
    assert _build_rotation_table([], q) == []


def test_rotation_row_when_sell() -> None:
    q = NextBuyQueue(
        items=(
            NextBuyItem(
                ticker="000660",
                name="SK하이닉스",
                total_score=60.0,
                upside_pct=12.0,
                why="x",
            ),
        ),
        top_k=8,
        sell_pressure=True,
        n_eligible=1,
    )
    sell_row = _row("005930", name="삼성전자", held=True)
    act = WeightAction(
        kind="cash_half",
        primary="환금 50%",
        body="환금",
        tone="hot",
        priority=20,
        delta_pct=None,
        board_line="환금 삼성전자 005930 · 50%",
        stance="매도",
        move_pct=50.0,
    )
    rows = _build_rotation_table([(sell_row, act)], q)
    assert len(rows) == 1
    assert "005930" in rows[0]["팔"]
    assert "000660" in rows[0]["살"]


def test_hold_table_columns() -> None:
    ops = [_row("005930", name="삼성전자", held=True, weight=15.0)]
    act = WeightAction(
        kind="hold",
        primary="유지",
        body="유지",
        tone="ok",
        priority=100,
        delta_pct=None,
        board_line="",
        stance="유지",
        move_pct=0.0,
    )
    rows = _build_hold_table(
        ops, soft={"005930"}, action_by={"005930": act}
    )
    assert len(rows) == 1
    assert rows[0]["보유"] == "Y"
    assert "프로그램" in rows[0]
    assert "사람" in rows[0]
    assert rows[0]["Soft관계"] == "슬롯 안"


def test_desk_abc_and_disjoint() -> None:
    soft = [
        _row("005930", name="삼성전자", weight=20.0, score=65.0, held=True),
        _row("000660", name="SK하이닉스", weight=20.0, score=64.0, held=False),
    ]
    ops = [soft[0]]
    scoreboard = soft + [
        _row(
            "035420",
            name="NAVER",
            weight=0.0,
            score=62.0,
            held=False,
            price=180000.0,
            target=220000.0,
            r1=0.04,
        ),
    ]
    ctx = SimpleNamespace(
        root=str(ROOT),
        screen_market="KOSPI",
        market="KOSPI",
        portfolio_rows=soft,
        ops_portfolio_rows=ops,
        scoreboard_rows=scoreboard,
        proposal_blocked_rows=[],
        source_data_dir=str(ROOT / "data"),
    )
    desk = build_soft_ops_desk(ctx, root=ROOT)
    assert isinstance(desk, SoftOpsDesk)
    assert desk.writes_target is False
    assert desk.legend.line_ko
    assert "매도" in desk.legend.line_ko or "순위" in desk.legend.line_ko
    assert len(desk.slot_rows) >= 1
    assert desk.hold_rows or True
    assert desk.track_note_ko
    assert isinstance(desk.track_rows, tuple)
    prop = set(desk.proposal_tickers)
    wait = set(desk.wait_tickers)
    assert prop & wait == set()
    # 사람 열·우선 = soft_trade_priority 기본안
    if desk.slot_rows:
        assert "사람" in desk.slot_rows[0]
        assert "우선" in desk.slot_rows[0]
        # 미보유 슬롯은 미정 문구가 아님
        new_slots = [r for r in desk.slot_rows if r.get("우선") is not None]
        assert new_slots
        assert "미정 · 살지" not in str(new_slots[0]["사람"])


def test_desk_empty_ctx() -> None:
    ctx = SimpleNamespace(
        root=str(ROOT),
        screen_market="KOSPI",
        market="KOSPI",
        portfolio_rows=[],
        ops_portfolio_rows=[],
        scoreboard_rows=[],
        proposal_blocked_rows=[],
        source_data_dir=str(ROOT / "data"),
    )
    desk = build_soft_ops_desk(ctx, root=ROOT)
    assert desk.slot_rows == ()
    assert desk.writes_target is False
