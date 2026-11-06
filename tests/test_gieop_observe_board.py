"""기업해부 관찰 보드 UI 로더 · 포트 Soft×보유 교차."""

from __future__ import annotations

import json
from pathlib import Path

from alpha_system.ui.services.gieop_observe_board import (
    ObserveUiRow,
    PORT_BUY_REVIEW,
    PORT_MAINTAIN,
    PORT_PARK,
    PORT_SELL_REVIEW,
    build_portfolio_bridge,
    classify_port_action,
    load_observe_ui_board,
    observe_board_html,
    portfolio_bridge_html,
)


def test_load_missing(tmp_path: Path) -> None:
    board = load_observe_ui_board(tmp_path, market="KOSPI")
    assert board.available is False
    html = observe_board_html(board)
    assert "pf-gieop" in html


def test_load_deep_pick(tmp_path: Path) -> None:
    out = tmp_path / "data" / "local"
    out.mkdir(parents=True)
    payload = {
        "market": "KOSPI",
        "as_of": "2026-10-30",
        "model_version": "krx-low-pbr-observe-v1",
        "counts": {"심층": 1, "정밀관찰": 2},
        "note": "Review-only",
        "deep_pick": [
            {
                "ticker": "005880",
                "name": "대한해운",
                "tier": "심층",
                "observe_score": 170,
                "judgment_ko": "논리가치",
                "next_action_ko": "기업해부",
                "pbr_press": 0.27,
                "pass_value": True,
                "crash_flag": False,
                "in_soft": False,
                "gics": "산업재",
            }
        ],
        "rows": [
            {
                "ticker": "072710",
                "name": "농심홀딩스",
                "tier": "정밀관찰",
                "observe_score": 80,
                "judgment_ko": "시총 미달",
                "next_action_ko": "짧게",
                "pbr_press": 0.29,
                "pass_value": False,
                "crash_flag": False,
                "in_soft": False,
            }
        ],
    }
    (out / "krx_low_pbr_observe_KOSPI.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    board = load_observe_ui_board(tmp_path, market="KOSPI")
    assert board.available is True
    assert board.deep_pick[0].ticker == "005880"
    assert board.watch_top[0].name == "농심홀딩스"
    html = observe_board_html(board)
    assert "대한해운" in html
    assert "농심홀딩스" in html


def test_classify_four_ways() -> None:
    assert classify_port_action(in_soft=True, in_held=True) == PORT_MAINTAIN
    assert classify_port_action(in_soft=True, in_held=False) == PORT_BUY_REVIEW
    assert classify_port_action(in_soft=False, in_held=True) == PORT_SELL_REVIEW
    assert classify_port_action(in_soft=False, in_held=False) == PORT_PARK


def test_portfolio_bridge_counts() -> None:
    deep = [
        ObserveUiRow(
            "111111", "A", "심층", 100, "", "", None, True, False, False, ""
        ),
        ObserveUiRow(
            "222222", "B", "심층", 90, "", "", None, True, False, False, ""
        ),
        ObserveUiRow(
            "333333", "C", "정밀관찰", 80, "", "", None, False, False, False, ""
        ),
        ObserveUiRow(
            "444444", "D", "심층", 70, "", "", None, False, False, False, ""
        ),
    ]
    bridge = build_portfolio_bridge(
        deep,
        soft_tickers=["111111", "222222"],
        held_tickers=["111111", "333333"],
    )
    assert bridge.n_maintain == 1  # 111111
    assert bridge.n_buy == 1  # 222222
    assert bridge.n_sell == 1  # 333333
    assert bridge.n_park == 1  # 444444
    assert "사 1" in bridge.summary_line_ko()
    html = portfolio_bridge_html(bridge)
    assert "포트 연결" in html
    assert "사 Review" in html
    assert "유지·해부확인" in html
