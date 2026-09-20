"""Home status one-liners."""

from __future__ import annotations

from datetime import date

from alpha_system.ui.services.data_freshness import SourceStatus
from alpha_system.ui.services.home_status import age_ko, freshness_line, status_line


def test_status_line_pre_launch_no_holdings() -> None:
    assert status_line(pre_launch=True, held_n=0, next_title="정량 스냅샷 갱신") == (
        "가동 전 · 실보유 없음 · 정량 스냅샷 갱신"
    )


def test_status_line_live_with_holdings() -> None:
    assert status_line(pre_launch=False, held_n=4, next_title=None) == (
        "가동 중 · 실보유 4종 · 오늘 할 일 없음"
    )


def test_freshness_line_mixed() -> None:
    today = date(2026, 8, 28)
    sources = [
        SourceStatus(
            key="prices",
            label="현재가",
            path="data/prices.csv",
            as_of=date(2026, 8, 27),
            recommended_days=1,
            stale=True,
            exists=True,
        ),
        SourceStatus(
            key="benchmark",
            label="벤치마크",
            path="data/market_indicators.csv",
            as_of=date(2026, 7, 24),
            recommended_days=7,
            stale=True,
            exists=True,
        ),
        SourceStatus(
            key="kospi_pbr_history",
            label="T3",
            path="data/kospi_market_pbr_history.csv",
            as_of=date(2026, 6, 30),
            recommended_days=35,
            stale=True,
            exists=True,
        ),
    ]
    line, attention = freshness_line(sources, today)
    assert line == "종가 어제"
    assert attention is True
    assert age_ko(date(2026, 8, 28), today) == "오늘"
