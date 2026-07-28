"""Rescore signals never mutate scores; queue + manual consensus only."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from alpha_system.schema import AlphaSystemConfig, ScoringConfig
from alpha_system.scoring.pending_rescore import load_pending, upsert_pending
from alpha_system.scoring.rescore import (
    build_rescore_queue_item,
    evaluate_manual_consensus_signals,
    evaluate_rescore_triggers,
)
from alpha_system.ui.services.action_queue import ActionSeverity, build_action_queue
from alpha_system.entry.evaluate import EntryEvaluation
from alpha_system.exit.evaluate import ExitEvaluation
from alpha_system.swap.observe import SwapObserveEvaluation


def _cfg(triggers: list[str]) -> AlphaSystemConfig:
    # Minimal: load real yaml then override scoring triggers
    from alpha_system.loader import load_config

    root = Path(__file__).resolve().parents[1]
    cfg = load_config(root / "alpha_system" / "config" / "alpha_system.yaml")
    return cfg.model_copy(
        update={"scoring": ScoringConfig(score_cutoff=cfg.scoring.score_cutoff, rescore_triggers=triggers)}
    )


def test_disclosure_match_no_auto_score_flag() -> None:
    cfg = _cfg(["value_up_program_disclosure"])
    d = evaluate_rescore_triggers(
        cfg,
        as_of=date(2026, 7, 19),
        fired_events=["value_up_program_disclosure"],
    )
    assert d.should_rescore is True
    item = build_rescore_queue_item(d, as_of=date(2026, 7, 19), tickers=["006260"])
    assert item is not None
    assert "자동 변경되지 않습니다" in item.detail


def test_manual_consensus_and_pending(tmp_path: Path) -> None:
    path = tmp_path / "pending_rescore_reviews.json"
    decision = evaluate_manual_consensus_signals(
        [{"event_id": "rating_downgrade", "ticker": "033780"}],
        as_of=date(2026, 7, 19),
    )
    assert decision.should_rescore is True
    item = build_rescore_queue_item(
        decision, as_of=date(2026, 7, 19), tickers=["033780"]
    )
    assert item is not None
    upsert_pending(
        {
            "key": item.key,
            "title": item.title,
            "detail": item.detail,
            "triggers": list(item.triggers),
            "tickers": list(item.tickers),
            "as_of": item.as_of,
            "source": item.source,
        },
        path=path,
    )
    loaded = load_pending(path)
    assert len(loaded) == 1
    assert loaded[0]["triggers"] == ["rating_downgrade"]


def test_action_queue_includes_rescore() -> None:
    items = build_action_queue(
        entry_eval=EntryEvaluation(
            as_of=date(2026, 7, 19),
            statuses=[],
            actions=[],
            warnings=[],
            todo_fields=[],
        ),
        exit_eval=ExitEvaluation(
            as_of=date(2026, 7, 19),
            actions=[],
            warnings=[],
            todo_fields=[],
            window_end_report=None,
        ),
        swap_eval=SwapObserveEvaluation(as_of=date(2026, 7, 19), candidates=[]),
        stale_sources=[],
        pre_launch=False,
        pending_rescores=[
            {
                "key": "rescore_test",
                "title": "재채점 검토 필요",
                "detail": "test",
                "triggers": ["earnings_surprise"],
                "tickers": ["000270"],
            }
        ],
    )
    assert any(i.panel_kind == "rescore" for i in items)
    assert any(i.severity == ActionSeverity.WARN for i in items if i.key == "rescore_test")
