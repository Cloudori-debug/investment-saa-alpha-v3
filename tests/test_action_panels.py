"""Action-queue processing panels — panel_kind routing + journal wiring."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from alpha_system.entry.evaluate import EntryEvaluation
from alpha_system.entry.models import EntryActionType, TrancheState
from alpha_system.exit.evaluate import ExitEvaluation
from alpha_system.exit.models import ExitAction, ExitActionType, ExitReason
from alpha_system.journal import append_record, clear_entries, list_entries
from alpha_system.schema import TrancheId
from alpha_system.swap.observe import SwapCandidate, SwapObserveEvaluation
from alpha_system.ui.services.action_queue import ActionSeverity, build_action_queue
from alpha_system.ui.services.journal_filters import categorize
from alpha_system.ui.services.ui_copy import copy_get, load_ui_copy


_ASOF = date(2026, 7, 16)


def _empty_entry() -> EntryEvaluation:
    return EntryEvaluation(
        as_of=_ASOF, statuses=[], actions=[], warnings=[], todo_fields=[]
    )


def _empty_exit() -> ExitEvaluation:
    return ExitEvaluation(as_of=_ASOF, actions=[], warnings=[], todo_fields=[])


def _empty_swap() -> SwapObserveEvaluation:
    return SwapObserveEvaluation(as_of=_ASOF, candidates=[])


def test_ui_copy_action_panel_principle() -> None:
    load_ui_copy.cache_clear()
    text = copy_get("action_panel", "principle")
    assert "증권사에서" in text
    assert "판정과 기록" in text
    assert "관찰 모드" in copy_get("action_panel", "swap_observe_only")
    assert "운용 데이터 축적" in copy_get("action_panel", "swap_observe_only")
    assert "{next}" in (load_ui_copy().get("action_queue") or {}).get("today_none", "")


def test_build_queue_assigns_panel_kinds() -> None:
    exit_eval = ExitEvaluation(
        as_of=_ASOF,
        actions=[
            ExitAction(
                ticker="005930",
                action_type=ExitActionType.REDUCE,
                reason=ExitReason.MARKET_VALUE_CAP,
                as_of=_ASOF,
                detail="cap exceeded",
            )
        ],
        warnings=[],
        todo_fields=[],
    )
    swap_eval = SwapObserveEvaluation(
        as_of=_ASOF,
        candidates=[
            SwapCandidate(
                held_ticker="000660",
                candidate_ticker="035420",
                held_score=40.0,
                candidate_score=55.0,
                score_gap_pct=37.5,
                consecutive_hits=2,
            )
        ],
    )
    stale = [
        SimpleNamespace(
            key="prices",
            label="prices.csv",
            as_of=date(2026, 1, 1),
            recommended_days=7,
            path="data/prices.csv",
            stale=True,
            detail="",
        )
    ]
    checklist_item = SimpleNamespace(
        key="score_cutoff",
        title="score_cutoff 미확정",
        why="cutoff empty",
        todo="set scoring.score_cutoff",
    )

    pre = build_action_queue(
        entry_eval=_empty_entry(),
        exit_eval=_empty_exit(),
        swap_eval=_empty_swap(),
        stale_sources=[],
        pre_launch=True,
        checklist_blocking=[checklist_item],
    )
    assert len(pre) == 1
    assert pre[0].panel_kind == "checklist"
    assert pre[0].payload["check_key"] == "score_cutoff"

    live = build_action_queue(
        entry_eval=_empty_entry(),
        exit_eval=exit_eval,
        swap_eval=swap_eval,
        stale_sources=stale,  # type: ignore[arg-type]
        cap_over_holdings=[("005930", "삼성전자", 42.0, 35.0)],
        pre_launch=False,
    )
    kinds = {i.panel_kind for i in live}
    assert "reduce" in kinds
    assert "swap" in kinds
    assert "data" in kinds
    swap = next(i for i in live if i.panel_kind == "swap")
    assert swap.payload["held"] == "000660"
    assert swap.severity == ActionSeverity.INFO
    reduce = next(i for i in live if i.key == "cap_005930")
    assert reduce.payload["weight_pct"] == 42.0


def test_build_queue_execute_panel_for_ready_tranche() -> None:
    status = MagicMock()
    status.tranche_id = TrancheId.T1
    status.state = TrancheState.READY
    status.trigger_met = True
    status.weight = 0.25
    entry = EntryEvaluation(
        as_of=_ASOF,
        statuses=[status],
        actions=[
            MagicMock(
                tranche_id=TrancheId.T1,
                action_type=EntryActionType.EXECUTE,
                blocked=False,
            )
        ],
        warnings=[],
        todo_fields=[],
    )
    items = build_action_queue(
        entry_eval=entry,
        exit_eval=_empty_exit(),
        swap_eval=_empty_swap(),
        stale_sources=[],
        pre_launch=False,
    )
    exec_items = [i for i in items if i.panel_kind == "execute"]
    assert exec_items
    assert all(i.payload.get("tranche_id") == "T1" for i in exec_items)


def test_panel_journal_kinds_categorized() -> None:
    assert categorize("REDUCE_COMPLETE") == "집행·전이"
    assert categorize("TRANCHE_EXEC_FILL") == "집행·전이"
    assert categorize("TRANCHE_EXEC_ACK") == "집행·전이"
    assert categorize("CHECKLIST_RECHECK") == "경고"


def test_reduce_complete_and_defer_journal(tmp_path=None) -> None:
    clear_entries()
    append_record(
        action_kind="REDUCE_COMPLETE",
        as_of=date.today(),
        subject="005930",
        rationale="cap reduce done",
        payload={"fill_price": 70000.0, "fill_qty": 10},
    )
    append_record(
        action_kind="WARN_DISCRETIONARY",
        as_of=date.today(),
        subject="005930",
        rationale="cap reduce deferred",
        discretionary_reason="시장 변동성 대기",
        payload={"kind": "reduce_defer"},
    )
    kinds = {e.action_kind for e in list_entries()}
    assert "REDUCE_COMPLETE" in kinds
    assert "WARN_DISCRETIONARY" in kinds
    clear_entries()
