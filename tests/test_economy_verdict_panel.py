"""Asset-move conclusion + why-drivers — no duplicate essay panels."""

from __future__ import annotations

from alpha_system.economy_compass.compass import build_compass
from alpha_system.economy_compass.mean_reversion_review import build_mean_reversion_board
from alpha_system.economy_compass.stress_overlay import build_bubble_stress_board
from alpha_system.economy_signal import EconomySignal, SignalInput
from alpha_system.ui.services.economy_compass_board import (
    alpha_ops_bridge_html,
    asset_move_board_html,
    executable_compact_html,
    why_drivers_html,
)


def _sig(stage: int = 3) -> EconomySignal:
    return EconomySignal(
        stage=stage,
        equity_share=0.60,
        cash_share=0.40,
        stage_label="중립",
        tightening=4,
        known=5,
        inputs=[
            SignalInput(key="real_us", label="실질", value=2.78, score=2, unit="%"),
            SignalInput(key="hy_oas", label="HY", value=323.0, score=0, unit="bp"),
            SignalInput(key="curve", label="커브", value=0.35, score=0, unit="%p"),
            SignalInput(key="fed_hike", label="연준", value=0.25, score=2, unit="%p"),
        ],
        fetched_at="2026-10-19T12:40:00+00:00",
        detail="정책 목표",
    )


def test_asset_move_shows_forest_directions() -> None:
    signal = _sig()
    compass = build_compass(signal)
    html = asset_move_board_html(
        signal=signal,
        compass=compass,
        playbook_title="종목 자세 · 중립",
        playbook_tone="wait",
        action_lines=(("중기", "노른자만"), ("단기", "추격↓")),
        scoreline="긴축 4 / 10",
    )
    assert "자산 움직임" in html
    assert "60%" in html and "40%" in html
    assert "숲 슬리브" in html
    assert "줄임" in html or "늘림" in html or "유지" in html
    assert "노른자만" in html
    # No full ETF catalog in conclusion
    assert "TIGER" not in html


def test_why_drivers_material_only() -> None:
    signal = _sig()
    stress = build_bubble_stress_board(signal)
    mean_rev = build_mean_reversion_board(signal, kospi_band=None)
    # Force empty band path without loading CSV: pass board after rebuild with empty
    from alpha_system.economy_compass.kospi_valuation_band import build_kospi_valuation_band

    mean_rev = build_mean_reversion_board(
        signal, kospi_band=build_kospi_valuation_band(history=[])
    )
    html = why_drivers_html(
        stress=stress,
        mean_rev=mean_rev,
        scoreline="긴축 4 / 10",
    )
    assert "왜 이렇게" in html
    assert "긴축 4 / 10" in html
    assert "실질" in html
    # Full essay panels not duplicated
    assert "숲 리스크" not in html
    assert "시총 ≠ 현금" not in html


def test_alpha_ops_bridge_points_to_portfolio() -> None:
    html = alpha_ops_bridge_html(
        playbook_title="종목 자세 · 중립",
        playbook_tone="wait",
        action_lines=(("중기", "노른자만"), ("단기", "추격↓")),
    )
    assert "알파 위성으로 넘기기" in html
    assert "포트폴리오" in html
    assert "팔기" in html
    assert "사기" in html
    assert "노른자만" in html


def test_executable_table_portfolio_form() -> None:
    signal = _sig()
    compass = build_compass(signal)
    html = executable_compact_html(compass)
    assert "eco-exec-table" in html
    assert "<th>코드</th>" in html
    assert "<th>상품</th>" in html
    assert "<th>장부≈</th>" in html
    assert "360750" in html
    assert "TIGER" in html
    assert "rowspan" in html
