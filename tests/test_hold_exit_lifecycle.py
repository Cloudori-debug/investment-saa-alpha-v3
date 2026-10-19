"""Hold/exit Review edition — lifecycle and cue merge."""

from __future__ import annotations

from alpha_system.hold_exit_review.config import HoldExitReviewConfig
from alpha_system.hold_exit_review.cue_merge import unify_with_lifecycle
from alpha_system.hold_exit_review.lifecycle import evaluate_lifecycle
from alpha_system.proposal_chart import ChartRead


def _cfg() -> HoldExitReviewConfig:
    return HoldExitReviewConfig(
        edition_label="test",
        weeks_out_before_rotate=4,
        min_rotate_score_gap=15.0,
        price_drawdown_thesis_pct=20.0,
        management_cap_pct=15.0,
        forbid_pct_take_profit=True,
        forbid_pct_stop_loss=True,
        monthly_trade_review=True,
        history_relpath="data/local/test_hold_exit.jsonl",
    )


def test_first_week_out_is_just_dropped_not_silent_hold() -> None:
    v = evaluate_lifecycle(
        cfg=_cfg(),
        is_ops_row=True,
        in_proposal=False,
        weeks_out=0,
        ops_kind="hold",
        cap_over=False,
        weight_pct=8.0,
        avg_price=36000.0,
        current_price=30000.0,
        total_score=60.0,
        best_alternate_score=80.0,
        extra={},
    )
    assert v.state == "just_dropped"
    assert "이번 주" in v.why


def test_watch_before_rotate_weeks() -> None:
    v = evaluate_lifecycle(
        cfg=_cfg(),
        is_ops_row=True,
        in_proposal=False,
        weeks_out=2,
        ops_kind="hold",
        cap_over=False,
        weight_pct=8.0,
        avg_price=10000.0,
        current_price=9500.0,
        total_score=60.0,
        best_alternate_score=80.0,
        extra={},
    )
    assert v.state == "watch"
    assert "2/4" in v.why or "2" in v.why


def test_rotate_when_gap_and_weeks() -> None:
    v = evaluate_lifecycle(
        cfg=_cfg(),
        is_ops_row=True,
        in_proposal=False,
        weeks_out=4,
        ops_kind="hold",
        cap_over=False,
        weight_pct=8.0,
        avg_price=10000.0,
        current_price=9500.0,
        total_score=60.0,
        best_alternate_score=80.0,
        extra={},
    )
    assert v.state == "rotate_review"
    assert v.rotate_gap_ok


def test_thesis_on_drawdown() -> None:
    v = evaluate_lifecycle(
        cfg=_cfg(),
        is_ops_row=True,
        in_proposal=True,
        weeks_out=0,
        ops_kind="hold",
        cap_over=False,
        weight_pct=8.0,
        avg_price=10000.0,
        current_price=7500.0,
        total_score=60.0,
        best_alternate_score=None,
        extra={},
    )
    assert v.state == "thesis_review"


def test_ops_card_watch_allowed_and_trigger() -> None:
    from alpha_system.hold_exit_review.ops_card import build_ops_card

    view = evaluate_lifecycle(
        cfg=_cfg(),
        is_ops_row=True,
        in_proposal=False,
        weeks_out=2,
        ops_kind="hold",
        cap_over=False,
        weight_pct=8.0,
        avg_price=10000.0,
        current_price=9500.0,
        total_score=60.0,
        best_alternate_score=80.0,
        extra={"book": "ops"},
    )
    card = build_ops_card(
        cfg=_cfg(),
        view=view,
        extra={"book": "ops"},
        current_price=9500.0,
        ops_kind="hold",
        total_score=60.0,
        in_proposal=False,
        is_ops=True,
    )
    assert card.data_gate == "정상"
    assert card.thesis == "약화"
    assert "추가매수 금지" in card.allowed
    assert "2/4" in card.trigger


def test_ops_card_missing_price_is_not_sell() -> None:
    from alpha_system.hold_exit_review.ops_card import build_ops_card

    view = evaluate_lifecycle(
        cfg=_cfg(),
        is_ops_row=True,
        in_proposal=True,
        weeks_out=0,
        ops_kind="hold",
        cap_over=False,
        weight_pct=8.0,
        avg_price=None,
        current_price=None,
        total_score=60.0,
        best_alternate_score=None,
        extra={"book": "ops"},
    )
    card = build_ops_card(
        cfg=_cfg(),
        view=view,
        extra={"book": "ops"},
        current_price=None,
        ops_kind="hold",
        total_score=60.0,
        in_proposal=True,
        is_ops=True,
    )
    assert card.data_gate == "일부 누락"
    assert "매도" not in card.allowed


def test_ops_card_html_has_four_cells() -> None:
    from alpha_system.hold_exit_review.widgets import chart_read_html
    from alpha_system.ui.services.context import PortfolioRow

    row = PortfolioRow(
        ticker="005930",
        name="삼성전자",
        weight_pct=8.0,
        initial_weight_pct=8.0,
        avg_price=36000.0,
        current_price=33000.0,
        target_price=None,
        target_progress=None,
        remaining_upside_pct=None,
        has_target=False,
        target_detail="",
        cap_pct=25.0,
        cap_headroom_pct=None,
        cap_near=False,
        extra={
            "book": "ops",
            "hold_exit_state": "watch",
            "hold_exit_label": "관찰",
            "hold_exit_why": "제안 밖 2/4주",
            "ops_data_gate": "정상",
            "ops_data_gate_detail": "시세·점수 기준으로 Review 가능.",
            "ops_thesis": "약화",
            "ops_thesis_detail": "제안 이탈",
            "ops_allowed": "보유 · 추가매수 금지",
            "ops_trigger": "제안 밖 2/4주",
        },
    )
    html = chart_read_html(row, None)
    # Collapsed ops cue is one compact line (grid detail → expand).
    assert "he-ops-grid" not in html
    assert "추가매수 금지" in html
    assert "정상" in html


def test_lifecycle_overrides_cue_headline() -> None:
    chart = ChartRead(
        ticker="005930",
        name="삼성",
        ma_label="60일선 위",
        rsi_label="보통",
        bb_label="밴드 안",
        macd_label="골든크로스",
        macd_hist_label="히스토그램 확대",
    )
    cue = unify_with_lifecycle(
        ops_kind="hold",
        ops_label="유지",
        chart=chart,
        lifecycle_state="rotate_review",
        lifecycle_label="교체 검토",
        lifecycle_why="제안 밖 4주",
        lifecycle_weeks_out=4,
    )
    assert "교체" in cue.headline
    assert "4주" in cue.why or "교체" in cue.why
