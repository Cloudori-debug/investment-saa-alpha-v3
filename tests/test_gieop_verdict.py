"""기업해부 판정 파일 — Review 관문. 점수·target 불변."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from alpha_system.ui.services.gieop_alpha_seed import SRC_SOFT, AlphaGieopCandidate
from alpha_system.ui.services.gieop_fusion_desk import (
    FusionRow,
    build_fusion_desk,
    build_quant_cover,
    fusion_status_html,
)
from alpha_system.ui.services.gieop_observe_board import (
    PORT_BUY_REVIEW,
    PORT_SELL_REVIEW,
    PortfolioBridgeRow,
)
from alpha_system.ui.services.gieop_today_loop import build_today_gieop_loop
from alpha_system.ui.services.gieop_verdict import load_verdicts, parse_verdict


def _verdict(gate: str, **extra: object) -> dict:
    raw = {
        "schema": "alpha-gieop-verdict/v1",
        "ticker": "383220",
        "company": "F&F",
        "as_of": "2026-11-06",
        "price_date": "2026-11-04",
        "gate": gate,
        "blockers": ["3분기 실적 미공시"],
        "next_check": "2026-11-10 잠정실적",
        "report": "F&F.md",
    }
    raw.update(extra)
    return raw


def test_hold_chip_names_first_blocker() -> None:
    v = parse_verdict(_verdict("HOLD"), today=date(2026, 11, 6))
    assert v is not None
    assert v.effective_gate == "HOLD"
    assert v.stale is False
    assert v.chip_ko == "해부 HOLD · 3분기 실적 미공시"


def test_pass_stales_when_next_check_or_price_is_newer() -> None:
    past = parse_verdict(
        _verdict("PASS", next_check="2026-11-01 잠정"),
        today=date(2026, 11, 6),
    )
    assert past is not None
    assert past.effective_gate == "HOLD"
    assert past.stale is True
    newer = parse_verdict(
        _verdict("PASS"),
        today=date(2026, 11, 6),
        book_price_date="2026-11-06",
    )
    assert newer is not None
    assert newer.effective_gate == "HOLD"
    fresh = parse_verdict(
        _verdict("PASS"),
        today=date(2026, 11, 6),
        book_price_date="2026-11-04",
    )
    assert fresh is not None
    assert fresh.effective_gate == "PASS"
    assert fresh.chip_ko == "해부 PASS"


def test_fail_stays_fail() -> None:
    v = parse_verdict(
        _verdict("FAIL", next_check="2020-01-01"),
        today=date(2026, 11, 6),
        book_price_date="2026-11-06",
    )
    assert v is not None
    assert v.effective_gate == "FAIL"
    assert v.stale is False


def test_bad_schema_is_ignored(tmp_path: Path) -> None:
    folder = tmp_path / "verdicts"
    folder.mkdir()
    (folder / "383220.json").write_text(
        json.dumps({"schema": "other", "ticker": "383220", "gate": "PASS"}),
        encoding="utf-8",
    )
    assert load_verdicts(tmp_path, today=date(2026, 11, 6)) == {}


def test_fusion_reads_verdict_without_finishing_tasks(tmp_path: Path, monkeypatch) -> None:
    from alpha_system.ui.services import gieop_fusion_desk as mod

    drafts = tmp_path / "내조사"
    drafts.mkdir()
    (drafts / "seed.json").write_text(
        json.dumps(
            {
                "meta": {"ticker": "383220", "company": "F&F"},
                "tasks": [{"id": "P01", "status": "NOT_STARTED"}],
            }
        ),
        encoding="utf-8",
    )
    verdicts = drafts / "verdicts"
    verdicts.mkdir()
    (verdicts / "383220.json").write_text(
        json.dumps(_verdict("HOLD")),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        mod,
        "resolve_gieop_paths",
        lambda root: type("P", (), {"drafts_dir": drafts})(),
    )
    monkeypatch.setattr(mod, "_load_value_by", lambda root, market: ({}, "2026-11-04"))
    board = build_fusion_desk(
        tmp_path,
        market="KOSPI",
        candidates=[
            AlphaGieopCandidate("383220", "F&F", "", SRC_SOFT, "", True, False, True)
        ],
    )
    assert board.n_draft_idle == 1
    assert board.n_draft_done == 0
    assert board.rows[0].verdict is not None
    assert board.rows[0].verdict.effective_gate == "HOLD"
    html = fusion_status_html(board)
    assert "관문" in html
    assert "해부 HOLD" in html
    assert "target 불변" in html


def test_today_loop_locks_hold_and_drops_fail_buy() -> None:
    q = build_quant_cover(in_soft=True, pass_value=True, value_row=None)
    hold = parse_verdict(_verdict("HOLD"), today=date(2026, 11, 6))
    fail = parse_verdict(
        _verdict("FAIL", ticker="073240"),
        today=date(2026, 11, 6),
    )
    rows = [
        FusionRow("383220", "F&F", "Soft", True, True, None, q, hold),
        FusionRow("073240", "금호", "Soft", True, True, None, q, fail),
    ]
    board = build_today_gieop_loop(market="KOSPI", fusion_rows=rows, max_picks=3)
    tickers = [p.ticker for p in board.picks]
    assert "073240" not in tickers
    assert "383220" in tickers
    locked = board.picks[0]
    assert locked.buy_locked is True
    assert locked.port_action == PORT_BUY_REVIEW
    assert locked.port_action_ko == "사 Review 잠금"
    assert "실행 전" in locked.next_ko
    assert board.writes_target is False

    sell = FusionRow("073240", "금호", "보유", False, False, None, q, fail)
    kept = build_today_gieop_loop(
        market="KOSPI",
        fusion_rows=[sell],
        bridge_rows=[
            PortfolioBridgeRow(
                "073240",
                "금호",
                "",
                False,
                True,
                PORT_SELL_REVIEW,
                "팔 Review",
                "",
            )
        ],
        max_picks=3,
    )
    assert kept.picks[0].port_action == PORT_SELL_REVIEW
    assert kept.picks[0].buy_locked is True
    assert "해부 FAIL" in kept.picks[0].next_ko
