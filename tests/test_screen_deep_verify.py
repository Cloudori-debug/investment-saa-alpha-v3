"""Screen-pool PH-CVS-style deep verify — cache only, no score mix."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from alpha_system.review.screen_deep_verify import (
    build_screen_verify,
    load_screen_verify,
    save_screen_verify,
    screen_verify_attention_html,
)
from alpha_system.ui.services.opendart_evidence_board import opendart_join_html


def test_build_automates_fund_proxies(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "hakedaka_fundamentals.csv").write_text(
        "ticker,net_cash_to_market_cap,treasury_share_ratio,"
        "largest_shareholder_pct,buyback_3y,related_party_risk_flag,"
        "fcf_annual,cash_and_equivalents,short_term_financial_assets,"
        "holding_company_discount_proxy,nav_discount_proxy_pct\n"
        "005930,0.1,0.02,15.0,true,false,"
        "500000000000,100000000000,0,,50\n"
        "092230,0.2,0.01,18.0,false,false,"
        "-10000000000,200000000000,80000000000,0.5,40\n",
        encoding="utf-8",
    )
    watch = {
        "evidence": [
            {
                "ticker": "005930",
                "data_status": "ok",
                "headline": "자사주 취득",
                "events": [
                    {
                        "kind": "buyback",
                        "status": "resolved",
                        "date": "2026-05-01",
                        "title": "자기주식취득결정",
                        "rcept_no": "1",
                        "source_url": "",
                    }
                ],
            },
            {
                "ticker": "092230",
                "data_status": "no_events",
                "headline": "관련 공시 없음",
                "events": [],
            },
        ],
        "flags": [],
        "metrics": [
            {"ticker": "005930", "control_purpose": False, "largest_shareholder_pct": 15.0},
            {"ticker": "092230", "control_purpose": False},
        ],
    }
    board = build_screen_verify(
        tmp_path,
        data_dir=data,
        tickers=["005930", "092230"],
        names={"005930": "삼성전자", "092230": "KPX홀딩스"},
        proposal_tickers=["005930"],
        blocked_tickers=[],
        opendart_watch=watch,
        min_hits=2,
        as_of="2026-10-18",
    )
    by = {r.ticker: r for r in board.rows}
    k930 = {c.key: c.status for c in by["005930"].checks}
    assert k930["hakedaka"] == "PASS"
    assert k930["opendart_evidence"] == "PASS"
    assert k930["control_flag"] == "PASS"
    assert k930["capital_waterfall"] == "PASS"
    assert k930["cash_attribution"] == "PASS"
    assert k930["restricted_cash"] == "PASS"
    assert k930["nav_double_count"] == "PASS"
    assert by["005930"].overall == "ok"
    assert by["005930"].verdict == "pass_review"

    kpx = {c.key: c for c in by["092230"].checks}
    assert kpx["opendart_evidence"].status == "PASS"
    assert "탐색완료" in kpx["opendart_evidence"].note
    assert kpx["capital_waterfall"].status == "FAIL"
    assert kpx["cash_attribution"].status == "FAIL"
    assert kpx["restricted_cash"].status == "FAIL"  # STFA/cash high
    assert kpx["nav_double_count"].status == "FAIL"
    assert by["092230"].overall == "warn"
    # Soft FAILs → 보류 (not 제외검토); book is 관찰 → watch
    assert by["092230"].book == "관찰"
    assert by["092230"].verdict == "watch"

    # Proposal + soft FAIL → hold
    board2 = build_screen_verify(
        tmp_path,
        data_dir=data,
        tickers=["092230"],
        names={"092230": "KPX홀딩스"},
        proposal_tickers=["092230"],
        opendart_watch=watch,
        min_hits=2,
    )
    assert board2.rows[0].verdict == "hold"

    path = save_screen_verify(data, board)
    assert path.exists()
    assert load_screen_verify(data).available
    html = screen_verify_attention_html(board2)
    assert "보류" in html
    assert "한눈 표" in html
    assert "정량" in html


def test_join_uses_screen_verify_columns() -> None:
    from alpha_system.review.screen_deep_verify import (
        CheckItem,
        ScreenVerifyRow,
        assign_review_verdict,
    )

    sv = [
        assign_review_verdict(
            ScreenVerifyRow(
                ticker="005930",
                name="삼성전자",
                book="제안",
                overall="warn",
                headline="자동 FAIL",
                warn_tags=["하케다카hitFAIL"],
                checks=[
                    CheckItem("hakedaka", "하케다카 hit", "FAIL", "0/2"),
                ],
            )
        )
    ]
    assert sv[0].verdict == "hold"
    html = opendart_join_html(
        proposal_rows=[
            SimpleNamespace(ticker="005930", name="삼성전자", total_score=70.0, score_sr=50.0)
        ],
        blocked_rows=[],
        scoreboard_rows=[
            SimpleNamespace(ticker="005930", total_score=70.0, score_sr=50.0)
        ],
        board=[],
        flags=[],
        gated=set(),
        names={"005930": "삼성전자"},
        screen_verify_rows=sv,
    )
    assert "판정" in html
    assert "보류" in html
    assert "심층·사유" in html
    assert "공시·게이트" in html


def test_exclude_review_on_control_fail() -> None:
    from alpha_system.review.screen_deep_verify import CheckItem, ScreenVerifyRow, assign_review_verdict

    row = assign_review_verdict(
        ScreenVerifyRow(
            ticker="000660",
            name="SK하이닉스",
            book="제안",
            overall="warn",
            headline="지배",
            checks=[
                CheckItem("control_flag", "경영참여·지배", "FAIL", "control"),
            ],
        )
    )
    assert row.verdict == "exclude_review"
