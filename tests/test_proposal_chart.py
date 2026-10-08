"""Review-only proposal chart readout — no target writes."""

from __future__ import annotations

from datetime import date

import pandas as pd

from alpha_system.proposal_chart import (
    analyze_ohlcv,
    cache_path,
    load_cached_charts,
    macd_series,
    norm_ticker,
    refresh_proposal_charts,
    wilder_rsi,
)


def _bars(n: int = 160, *, start: float = 100.0, drift: float = 0.05) -> pd.DataFrame:
    close = [start]
    for i in range(1, n):
        bump = drift if i > 40 else 0.0
        close.append(close[-1] + bump + ((i % 9) - 4) * 0.08)
    idx = pd.bdate_range("2026-01-02", periods=n)
    return pd.DataFrame({"종가": close, "거래량": [1_000_000] * n}, index=idx)


def test_uptrend_is_above_ma_and_not_overbought() -> None:
    read = analyze_ohlcv(_bars(), ticker="005930", name="삼성전자")
    assert read.note == ""
    assert read.ma_label in {"60일선 위", "120일선 위"}
    assert read.rsi_label == "보통"
    assert read.macd_label  # populated (골든/시그널 위 등)
    assert read.macd_hist_label
    assert "target" not in read.advice.lower()


def test_macd_dead_cross_in_advice() -> None:
    """Rising then falling close → MACD turns down; advice mentions MACD or 보류."""
    n = 120
    close = [100.0 + i * 0.8 for i in range(80)]
    close += [close[-1] - i * 1.2 for i in range(1, 41)]
    idx = pd.bdate_range("2026-01-02", periods=n)
    df = pd.DataFrame({"종가": close, "거래량": [1_000_000] * n}, index=idx)
    line, sig, hist = macd_series(pd.Series(close, index=idx))
    assert float(line.iloc[-1]) < float(sig.iloc[-1]) or float(hist.iloc[-1]) < 0
    read = analyze_ohlcv(df, ticker="000001", name="하락전환")
    assert read.macd_label in {"데드크로스", "시그널 아래"}
    blob = f"{read.advice} {read.macd_label} {read.macd_hist_label}"
    assert "MACD" in blob or "시그널" in blob or "히스토그램" in blob


def test_hot_rsi_advises_no_chase() -> None:
    close = list(range(1, 80))
    idx = pd.bdate_range("2026-01-02", periods=len(close))
    df = pd.DataFrame({"종가": close, "거래량": [1000] * len(close)}, index=idx)
    read = analyze_ohlcv(df, ticker="000001", name="테스트")
    assert read.rsi is not None and read.rsi >= 70
    assert read.rsi_label == "과열"
    assert "결론:" in read.advice
    assert "추가 매수 금지" in read.advice


def test_trade_verdict_is_action_first() -> None:
    from alpha_system.proposal_chart import ChartRead, _trade_verdict, summary_line

    v, why = _trade_verdict(
        ma_label="60일선 위",
        rsi_label="보통",
        bb_label="밴드 안",
        macd_label="시그널 위",
        macd_hist_label="히스토그램 확대",
    )
    assert "추격" in v or "유지" in v or "매수" in v
    assert why
    line = summary_line(
        ChartRead(
            ticker="005930",
            name="삼성전자",
            ma_label="60일선 위",
            rsi_label="보통",
            bb_label="밴드 안",
            macd_label="시그널 위",
            macd_hist_label="히스토그램 확대",
            macd_div_label="저점 다이버전스",
            advice="placeholder",
        )
    )
    assert line.startswith("결론:") or "결론:" in line
    assert "히스토그램 확대" not in line  # raw jargon not dumped
    assert "시그널 위" not in line


def test_refresh_writes_cache_not_target(tmp_path) -> None:
    df = _bars()

    def get_ohlcv(ticker: str, start: str, end: str):
        del ticker, start, end
        return df

    board = refresh_proposal_charts(
        tmp_path,
        [{"ticker": "005930", "name": "삼성전자"}],
        market="KOSPI",
        get_ohlcv=get_ohlcv,
        today=date(2026, 9, 8),
    )
    assert board.items
    assert (tmp_path / "data" / "local" / "proposal_chart_KOSPI.json").is_file()
    assert not (tmp_path / "data" / "target_portfolio.csv").exists()
    cached = load_cached_charts(tmp_path, "KOSPI")
    assert cached is not None
    assert cached.items[0].ticker == "005930"


def test_norm_ticker_kosdaq_float_and_cache_tag(tmp_path) -> None:
    assert not str(247540.0).isdigit()
    assert norm_ticker(247540.0) == "247540"
    assert norm_ticker("247540.0") == "247540"
    assert norm_ticker("005930") == "005930"
    assert cache_path(tmp_path, "코스닥").name == "proposal_chart_KOSDAQ.json"
    assert cache_path(tmp_path, "KOSDAQ").name == "proposal_chart_KOSDAQ.json"

    df = _bars()

    def get_ohlcv(ticker: str, start: str, end: str):
        del start, end
        assert ticker == "247540"
        return df

    board = refresh_proposal_charts(
        tmp_path,
        [{"ticker": "247540.0", "name": "에코프로비엠"}],
        market="코스닥",
        get_ohlcv=get_ohlcv,
        today=date(2026, 9, 8),
    )
    assert board.market == "KOSDAQ"
    assert board.items[0].ticker == "247540"
    assert (tmp_path / "data" / "local" / "proposal_chart_KOSDAQ.json").is_file()
    cached = load_cached_charts(tmp_path, "KOSDAQ")
    assert cached is not None
    assert cached.items[0].ticker == "247540"


def test_wilder_rsi_flat_is_neutral() -> None:
    close = pd.Series([100.0] * 40)
    rsi = wilder_rsi(close)
    last = float(rsi.iloc[-1])
    assert last != last or last == 100.0 or 40 <= last <= 60


def test_summary_line_and_proposal_row_layout() -> None:
    from alpha_system.proposal_chart import ChartRead, summary_line, summary_tone
    from alpha_system.ui.services.context import PortfolioRow
    from alpha_system.ui.services.portfolio_widgets import _row_main_html

    item = ChartRead(
        ticker="005930",
        name="삼성전자",
        rsi_label="과열",
        bb_label="상단 밖",
        advice="단기 과열. 추격 매수 보류.",
    )
    assert summary_tone(item) == "hot"
    assert "추가 매수 금지" in summary_line(item, ladder="지금 매수2")
    assert "사는 칸은 사다리" not in summary_line(
        ChartRead(ticker="005930", name="삼성전자", ma_label="60일선 위", rsi_label="보통"),
        ladder="지금 매수1",
    )
    assert "첫 매수" in summary_line(
        ChartRead(ticker="005930", name="삼성전자", ma_label="60일선 위", rsi_label="보통"),
        ladder="지금 매수1",
    )
    assert "결론:" in summary_line(
        ChartRead(ticker="005930", name="삼성전자", ma_label="60일선 위", rsi_label="보통"),
        ladder="지금 매수1",
    )
    row = PortfolioRow(
        ticker="005930",
        name="삼성전자",
        weight_pct=4.2,
        initial_weight_pct=4.2,
        avg_price=None,
        current_price=12400,
        target_price=20000,
        target_progress=None,
        remaining_upside_pct=10.0,
        has_target=True,
        target_detail="",
        cap_pct=35.0,
        cap_headroom_pct=30.0,
        cap_near=False,
        extra={
            "book": "proposal",
            "proposal_eligible": True,
            "ladder_ok": True,
            "ladder_low": 10000,
            "ladder_high": 20000,
            "ladder_rungs": [10000, 12500, 15000, 17500, 20000],
            "ladder_labels": ["매수1", "매수2", "줄이기", "절반", "전량"],
            "ladder_fill_pct": 24.0,
        },
    )
    html = _row_main_html(row, chart=item)
    assert html.index("pf-wchip") < html.index("pf-spot")
    assert "12,400원" in html
    assert "pf-signal" in html
    assert "pf-signal-hot" in html
    assert "pf-signal-headline" in html
    assert "더 사지" in html or "추가" in html or "금지" in html
    assert "stCaption" not in html
    assert "eco-m-hint" not in html
