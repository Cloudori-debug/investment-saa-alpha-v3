"""Economy compass — sleeve bands, frequency fail-open, page wire."""

from __future__ import annotations

from pathlib import Path

from alpha_system.economy_compass import (
    build_compass,
    executable_lines,
    sleeve_bands_for_stage,
)
from alpha_system.economy_compass.cache import (
    PROXY_SERIES,
    load_compass_snapshot,
    save_compass_snapshot,
)
from alpha_system.economy_compass.history import frequency_for_stage
from alpha_system.economy_signal import EconomySignal, SignalInput, assemble_signal


def test_sleeve_bands_stage3_defensive_shift() -> None:
    bands = sleeve_bands_for_stage(3)
    assert len(bands) == 4
    by_id = {b.sleeve_id: b for b in bands}
    assert by_id["equity"].pct == 35.0
    assert by_id["cash"].pct == 25.0
    assert by_id["equity"].action == "줄임"
    assert by_id["cash"].action in {"늘림", "유지"}
    assert sum(b.pct for b in bands) == 100.0


def test_sleeve_bands_fail_open_unknown_stage() -> None:
    assert sleeve_bands_for_stage(None) == []
    assert sleeve_bands_for_stage(0) == []
    assert sleeve_bands_for_stage(99) == []


def test_frequency_table_has_four_sleeves() -> None:
    table = frequency_for_stage(4)
    assert table.available
    assert len(table.cells) == 4
    equity = next(c for c in table.cells if c.sleeve_id == "equity")
    assert equity.win_rate is not None
    assert equity.win_rate < 50
    cash = next(c for c in table.cells if c.sleeve_id == "cash")
    assert cash.win_rate is not None
    assert cash.win_rate > equity.win_rate


def test_frequency_fail_open_missing_stage() -> None:
    table = frequency_for_stage(None)
    assert not table.available
    assert table.cells == ()


def test_build_compass_from_signal_and_cache(tmp_path: Path) -> None:
    signal = assemble_signal(
        [
            SignalInput(key="hy_oas", label="HY", value=550.0, unit="bp", score=2),
            SignalInput(key="real_us", label="real", value=2.5, unit="%", score=2),
            SignalInput(key="fed_hike", label="fed", value=0.5, unit="%p", score=2),
            SignalInput(key="boj_hike", label="boj", value=0.0, unit="%p", score=0),
            SignalInput(key="curve", label="curve", value=-0.5, unit="%p", score=2),
        ]
    )
    view = build_compass(signal)
    assert view.stage is not None
    assert len(view.sleeves) == 4
    assert view.frequency.available
    assert view.metric_hints
    assert "기술" in view.regime_warning or view.stage < 4
    path = save_compass_snapshot(tmp_path, view)
    assert path.exists()
    snap = load_compass_snapshot(tmp_path)
    assert snap is not None
    assert snap.get("target_portfolio_written") is False
    assert "equity" in PROXY_SERIES
    assert len(snap.get("sleeves") or []) == 4


def test_build_compass_none_fail_open() -> None:
    view = build_compass(None)
    assert view.stage is None
    assert view.sleeves == ()
    assert not view.frequency.available
    assert "포트폴리오" in view.kr_link


def test_executable_picks_diversified_per_sleeve() -> None:
    from alpha_system.economy_compass.executable import leg_book_pct

    bands = sleeve_bands_for_stage(3)
    lines = executable_lines(bands)
    assert len(lines) == 4
    by_id = {x.sleeve_id: x for x in lines}
    assert by_id["equity"].ticker == "360750"  # primary = largest weight
    assert len(by_id["equity"].legs) == 3
    assert len(by_id["bonds"].legs) == 3
    assert len(by_id["cash"].legs) == 2
    assert len(by_id["gold"].legs) == 2
    for pick in lines:
        w = sum(leg.sleeve_weight_pct for leg in pick.legs)
        assert abs(w - 100.0) < 0.5
    # stage-3 equity 35% × 50% sleeve weight ≈ 17.5%
    assert leg_book_pct(35.0, 50.0) == 17.5
    assert sum(x.pct for x in lines) == 100.0
    assert executable_lines([]) == ()


def test_economy_page_wires_compass() -> None:
    page = Path(__file__).resolve().parents[1].joinpath(
        "alpha_system", "ui", "pages", "economy.py"
    ).read_text(encoding="utf-8")
    assert "build_compass" in page
    assert "_render_executable" not in page
    assert "_render_history" in page
    assert "_render_kr_link" in page
    assert "history_panel_html" in page
    assert "refresh_compass_inputs" in page or "save_compass_snapshot" in page
    assert "st.expander" in page
    assert "sec_more" in page
    assert "_render_compass_tab" in page
    assert "_render_pension_tab" in page
    assert page.index("_render_compass_tab") < page.index("_render_pension_tab")
    assert page.index("_render_history") < page.index("_render_kr_link")
    assert "fetch_pension_briefing" in page
    assert "refresh_pension_briefing" in page
    assert "import pension" not in page
    assert "from pension" not in page


def test_board_html_helpers() -> None:
    from alpha_system.ui.services.economy_compass_board import (
        history_panel_html,
        risk_horizon_panel_html,
        sleeves_panel_html,
    )

    view = build_compass(
        EconomySignal(
            stage=3,
            equity_share=0.55,
            cash_share=0.45,
            stage_label="중립",
            tightening=4,
            known=5,
            inputs=[],
            fetched_at="",
            detail="",
        )
    )
    html = sleeves_panel_html(view)
    assert "eco-sleeve-grid" in html
    assert "주식" in html
    assert "eco-exec-card" in html
    assert "360750" in html
    assert "TIGER" in html
    assert "eco-exec-legs" in html
    assert "195930" in html  # euro diversifier (not 195980 EM)
    assert "305080" in html  # US 10y primary duration (envelope)
    assert "453850" in html  # US 30y tilt only
    assert "장부≈" in html
    hist = history_panel_html(view)
    assert "eco-hist-table" in hist
    assert "월 승률" in hist
    assert "비검증" in hist
    assert "eco-hist-banner" in hist
    risk = risk_horizon_panel_html()
    assert "eco-risk" in risk
    assert "eco-risk-grid" in risk
    assert "시총 ≠ 현금" in risk
    assert "주식·국채 동시약세" in risk
    assert "target" in risk
    assert "자동매도" in risk or "자동매매" in risk
    assert "youtube" not in risk.lower()
    assert "유튜브" not in risk
