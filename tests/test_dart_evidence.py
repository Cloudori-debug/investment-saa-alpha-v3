"""OpenDART evidence layer — status rules, fail-open, no score blend."""

from __future__ import annotations

from alpha_system.ui.services.dart_evidence import (
    build_evidence_board,
    build_ticker_evidence,
    classify_kind,
    classify_status,
    is_correction_title,
    latest_buyback_chain_withdrawn,
    link_event_chains,
    merge_events,
    parse_amount_krw,
    parse_tgast_amount_row,
    parse_tsstk_amount_row,
    withdrawn_buyback_gate_candidates,
)


def test_classify_kind_and_status() -> None:
    assert classify_kind("자기주식취득결정") == "buyback"
    assert classify_status("자기주식취득결정") == "resolved"
    assert classify_status("자기주식취득결과보고서") == "completed"
    assert classify_status("자기주식취득결정철회") == "withdrawn"
    assert classify_status("자기주식취득현황") == "in_progress"
    assert classify_kind("현금배당결정") == "div"
    assert classify_kind("유형자산양도결정") == "asset_sale"
    assert classify_kind("사업보고서") is None


def test_correction_and_amount() -> None:
    assert is_correction_title("[기재정정] 자기주식취득결정")
    amt, note = parse_amount_krw("자기주식취득결정(100억원)")
    assert amt == 10_000_000_000
    assert "억" in note
    none_amt, none_note = parse_amount_krw("자기주식취득결정")
    assert none_amt is None
    assert none_note == "미확인"


def test_merge_dedupes_and_keeps_correction() -> None:
    events = merge_events(
        [
            {
                "kind": "buyback",
                "date": "2026-05-15",
                "title": "자기주식취득결정",
                "rcept_no": "20260515000001",
            },
            {
                "kind": "buyback",
                "date": "2026-05-15",
                "title": "자기주식취득결정",
                "rcept_no": "20260515000001",
            },
            {
                "kind": "buyback",
                "date": "2026-05-16",
                "title": "[기재정정] 자기주식취득결정",
                "rcept_no": "20260516000002",
            },
        ]
    )
    assert len(events) == 2
    assert events[0].is_correction is True
    assert events[1].status == "resolved"


def test_build_distinguishes_miss_vs_none() -> None:
    miss = build_ticker_evidence("005930", [], fetch_error="timeout")
    assert miss.data_status == "fetch_error"
    assert "구분" in miss.headline or "실패" in miss.headline

    empty = build_ticker_evidence("005930", [])
    assert empty.data_status == "no_events"

    ok = build_ticker_evidence(
        "005930",
        [
            {
                "kind": "buyback",
                "date": "2026-05-15",
                "title": "자기주식취득결정",
                "rcept_no": "1",
            }
        ],
    )
    assert ok.data_status == "ok"
    assert "자사주" in ok.headline


def test_board_missing_key() -> None:
    board = build_evidence_board(
        ["005930"],
        {},
        missing_key=True,
    )
    assert board[0].data_status == "missing_key"


def test_chain_links_decision_correction_withdrawn() -> None:
    merged = merge_events(
        [
            {
                "kind": "buyback",
                "date": "2026-05-01",
                "title": "자기주식취득결정",
                "rcept_no": "1",
            },
            {
                "kind": "buyback",
                "date": "2026-05-10",
                "title": "[기재정정] 자기주식취득결정",
                "rcept_no": "2",
            },
            {
                "kind": "buyback",
                "date": "2026-05-20",
                "title": "자기주식취득결정철회",
                "rcept_no": "3",
            },
        ]
    )
    chained = link_event_chains(merged)
    assert len(chained) == 3
    ids = {e.chain_id for e in chained}
    assert len(ids) == 1
    roles = {e.chain_role for e in chained}
    assert "withdrawn" in roles
    assert "initial" in roles or "correction" in roles


def test_tsstk_amount_and_enrich() -> None:
    amt, note = parse_tsstk_amount_row(
        {"aqpln_prc_ostk": "1,000,000,000", "aqpln_prc_estk": "-"}
    )
    assert amt == 1_000_000_000
    assert note == "tsstkAqDecsn"
    tamt, tnote = parse_tgast_amount_row({"trfdtl_trfprc": "2500000000"})
    assert tamt == 2_500_000_000
    assert "환원가정금지" in tnote
    item = build_ticker_evidence(
        "005930",
        [
            {
                "kind": "buyback",
                "date": "2026-05-15",
                "title": "자기주식취득결정",
                "rcept_no": "99",
            }
        ],
        amount_by_rcept={"99": (2_000_000_000, "tsstkAqDecsn")},
    )
    assert item.events[0].amount_krw == 2_000_000_000


def test_withdrawn_gate_candidate_fail_open() -> None:
    ok = build_ticker_evidence(
        "005930",
        [
            {
                "kind": "buyback",
                "date": "2026-05-15",
                "title": "자기주식취득결정",
                "rcept_no": "1",
            }
        ],
    )
    assert latest_buyback_chain_withdrawn(ok) is None
    bad = build_ticker_evidence(
        "000660",
        [
            {
                "kind": "buyback",
                "date": "2026-05-01",
                "title": "자기주식취득결정",
                "rcept_no": "1",
            },
            {
                "kind": "buyback",
                "date": "2026-06-01",
                "title": "자기주식취득결정철회",
                "rcept_no": "2",
            },
        ],
    )
    assert latest_buyback_chain_withdrawn(bad) is not None
    cands = withdrawn_buyback_gate_candidates([ok, bad])
    assert [t for t, _ in cands] == ["000660"]
    err = build_ticker_evidence("111111", [], fetch_error="x")
    assert withdrawn_buyback_gate_candidates([err]) == []
