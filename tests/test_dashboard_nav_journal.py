"""Nav + auto-journal + journal filter smoke tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from alpha_system.entry import TriggerSnapshot, evaluate_entry
from alpha_system.journal import clear_entries, list_entries
from alpha_system.loader import load_config
from alpha_system.ui.services.auto_journal import sync_system_journal
from alpha_system.ui.services.context import PortfolioRow
from alpha_system.ui.services.journal_filters import categorize, filter_entries
from alpha_system.ui.services.nav import ALL_PAGES, PAGE_CECS, PAGE_EVENTS, PAGE_RULES
from alpha_system.ui.services.runtime_state import RuntimeState


def test_page_labels_include_events_and_rules() -> None:
    assert PAGE_EVENTS in ALL_PAGES
    assert PAGE_RULES in ALL_PAGES
    assert PAGE_CECS in ALL_PAGES
    assert "설정·이벤트" not in ALL_PAGES


def test_primary_pages_sellable_ia_order() -> None:
    from alpha_system.ui.services.nav import (
        NAV_MAIN_PAGES,
        NAV_MORE_PAGES,
        PAGE_DISPLAY_NAMES,
        PAGE_HINTS,
        PRIMARY_PAGES,
        page_display_name,
    )

    assert PRIMARY_PAGES[0] == "홈"
    assert PRIMARY_PAGES[1] == "결재함"
    assert PRIMARY_PAGES[2] == "포트폴리오"
    assert "레짐" in PRIMARY_PAGES
    assert PAGE_HINTS["홈"]
    assert "점수" in PAGE_HINTS["결재함"] or "주간" in PAGE_HINTS["결재함"]
    assert "실보유" in PAGE_HINTS["포트폴리오"]
    assert PAGE_DISPLAY_NAMES["홈"] == "오늘"
    assert PAGE_DISPLAY_NAMES["결재함"] == "확인"
    assert PAGE_DISPLAY_NAMES["포트폴리오"] == "포트폴리오"
    assert page_display_name("결재함", badge=3) == "확인 · 3"
    assert NAV_MAIN_PAGES == ("홈", "결재함", "포트폴리오")
    assert "저널" in NAV_MORE_PAGES
    assert "설정" in NAV_MORE_PAGES


def test_journal_filter_categories() -> None:
    assert categorize("TRANCHE_STATE_TRANSITION") == "집행·전이"
    assert categorize("HARD_RULE_BLOCK") == "차단"
    assert categorize("DATA_REFRESH_FAIL") == "데이터"
    assert categorize("T2_EVENT_RECORD") == "입력"
    assert categorize("WARN_DISCRETIONARY") == "재량"
    assert categorize("REDUCE_COMPLETE") == "집행·전이"
    assert categorize("TRANCHE_EXEC_FILL") == "집행·전이"
    assert categorize("CHECKLIST_RECHECK") == "경고"


def test_auto_journal_records_state_transition(tmp_path: Path) -> None:
    clear_entries()
    cfg = load_config()
    runtime = RuntimeState()
    runtime.journaled_tranche_states = {"T1": "PENDING", "T2": "PENDING", "T3": "PENDING", "T4": "PENDING"}
    runtime.journaled_trigger_met = {"T1": False, "T2": False, "T3": False, "T4": False}

    ev = evaluate_entry(
        cfg,
        TriggerSnapshot(
            as_of=date(2026, 7, 16),
            system_started=True,
            go_live_date=date(2026, 7, 16),
        ),
        journal=False,
    )
    written = sync_system_journal(
        as_of=date(2026, 7, 16),
        runtime=runtime,
        entry_eval=ev,
        portfolio_rows=[],
        pre_launch=False,
    )
    assert "TRANCHE_STATE_TRANSITION" in written or "TRIGGER_FIRED" in written
    kinds = {e.action_kind for e in list_entries()}
    assert kinds & {"TRANCHE_STATE_TRANSITION", "TRIGGER_FIRED"}
    # second sync should not duplicate same snapshot
    n1 = len(list_entries())
    sync_system_journal(
        as_of=date(2026, 7, 16),
        runtime=runtime,
        entry_eval=ev,
        portfolio_rows=[],
        pre_launch=False,
    )
    assert len(list_entries()) == n1
    clear_entries()


def test_filter_entries_by_category() -> None:
    clear_entries()
    from alpha_system.journal import append_record

    append_record(action_kind="DATA_REFRESH_OK", as_of=date.today(), subject="*", rationale="ok")
    append_record(action_kind="T2_EVENT_RECORD", as_of=date.today(), subject="x", rationale="manual")
    data_only = filter_entries(list_entries(), "데이터")
    assert all(categorize(e.action_kind) == "데이터" for e in data_only)
    clear_entries()
