"""Economy Review cash gap → portfolio warn (no auto trade)."""

from __future__ import annotations

from alpha_system.ui.services.alpha_book_ops import cash_review_alert


def test_no_alert_below_stage_3() -> None:
    assert (
        cash_review_alert(
            stage=2,
            review_cash_pct=25.0,
            actual_cash_pct=5.0,
            cash_name="단기채",
        )
        is None
    )


def test_warn_when_under_review_by_10pp() -> None:
    alert = cash_review_alert(
        stage=3,
        review_cash_pct=40.0,
        actual_cash_pct=28.0,
        cash_name="KODEX 단기채권PLUS",
    )
    assert alert is not None
    assert alert.level == "warn"
    assert "부족 12.0%p" in alert.body
    assert "실측" not in alert.body
    assert "자동매매" in alert.body


def test_alert_when_under_by_20pp_or_stage4() -> None:
    a20 = cash_review_alert(
        stage=3,
        review_cash_pct=40.0,
        actual_cash_pct=15.0,
        cash_name="단기채",
    )
    assert a20 is not None
    assert a20.level == "alert"
    assert "부족 25.0%p" in a20.body
    assert "실측" not in a20.body

    a4 = cash_review_alert(
        stage=4,
        review_cash_pct=60.0,
        actual_cash_pct=55.0,
        cash_name="단기채",
    )
    assert a4 is not None
    assert a4.level == "warn"
    assert "방어 구간" in a4.body
    assert "실측" not in a4.body


def test_missing_actual_still_warns() -> None:
    alert = cash_review_alert(
        stage=3,
        review_cash_pct=40.0,
        actual_cash_pct=None,
        cash_name="단기채",
    )
    assert alert is not None
    assert alert.level == "warn"
    assert "Review 단기채≈40%" in alert.body
    assert "미보유" not in alert.body
    assert "실측" not in alert.body


def test_cash_defense_row_matches_stock_row_chrome() -> None:
    from alpha_system.ui.pages.portfolio import _cash_defense_row_html

    html = _cash_defense_row_html(
        ticker="214980",
        name="KODEX 단기채권PLUS",
        stage=3,
        review_cash=40.0,
        review_eq=60.0,
        actual_cash=None,
        book_cash=10.0,
        book_equity=90.0,
        equity_actual=None,
        n_equity=0,
        alert_level="warn",
        alert_body=(
            "나침반 단계 3 · Review 단기채≈40% · "
            "KODEX 단기채권PLUS을 Review 목표로 맞출지 내일 검토 "
            "(자동매매·target 변경 없음)."
        ),
    )
    assert "pf-list" in html and "pf-row-main" in html
    assert "pf-chart-hint" in html
    assert "214980" in html
    assert "KODEX 단기채권PLUS" in html
    assert "장부방어" in html
    assert "목표 ≈40%" in html
    assert "장부 10%" in html
    assert "실측" not in html
    assert "미보유" not in html
    assert "내일 검토" in html
    assert "목표보유 개별주 90%" in html
    assert "pf-chart-read" in html
    assert "자동매매" in html


def test_cash_defense_shows_equity_held_without_cash() -> None:
    from alpha_system.ui.pages.portfolio import _cash_defense_row_html

    html = _cash_defense_row_html(
        ticker="214980",
        name="KODEX 단기채권PLUS",
        stage=3,
        review_cash=40.0,
        review_eq=60.0,
        actual_cash=0.0,
        book_cash=10.0,
        book_equity=90.0,
        equity_actual=100.0,
        n_equity=6,
        alert_level="alert",
        alert_body=(
            "나침반 단계 3 · Review 단기채≈40% · 목표 대비 부족 40.0%p"
        ),
        cash_held=False,
        value_basis="",
    )
    assert "미보유" not in html
    assert "실측" not in html
    assert "6종" in html
    assert "장부 10%" in html
    assert "목표 ≈40%" in html
    assert "목표보유 개별주 90%" in html


def test_actual_map_equal_weight_when_ops_have_no_value(tmp_path) -> None:
    from types import SimpleNamespace

    from alpha_system.ui.services.alpha_book_ops import (
        AlphaBookOpsPolicy,
        build_alpha_actual_map,
    )

    policy = AlphaBookOpsPolicy(
        equity_share=0.9,
        cash_share=0.1,
        cash_ticker="214980",
        cash_name="KODEX 단기채권PLUS",
        target_names=6,
        equity_weight_mode="equal",
        band_rel=0.25,
        exclude_zero_qty=True,
        regime_cash_guidance={},
        signal_priority=(),
        raw={},
    )
    ops = [
        SimpleNamespace(ticker="005930", name="삼성전자", weight_pct=0, quantity=0),
        SimpleNamespace(ticker="000660", name="SK하이닉스", weight_pct=0, quantity=0),
    ]
    actual = build_alpha_actual_map(tmp_path, ops, policy)
    assert set(actual) == {"005930", "000660"}
    assert "214980" not in actual
    assert abs(actual["005930"][0] - 50.0) < 0.01
