"""Rescore trigger evaluation + action-queue signals (never mutates CECS/scores)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

from alpha_system.schema import AlphaSystemConfig

# Disclosure-style (already in alpha_system.yaml rescore_triggers)
DISCLOSURE_TRIGGER_IDS: frozenset[str] = frozenset(
    {
        "value_up_program_disclosure",
        "treasury_share_cancellation_resolution",
        "dividend_articles_amendment",
    }
)

# Consensus / event watch — listed for future wiring; auto-ingest NOT available via PyKRX/DART
CONSENSUS_TRIGGER_IDS: frozenset[str] = frozenset(
    {
        "earnings_surprise",
        "rating_downgrade",
        "target_gap_narrowed",
    }
)

KNOWN_TRIGGER_IDS = DISCLOSURE_TRIGGER_IDS | CONSENSUS_TRIGGER_IDS


@dataclass(frozen=True)
class RescoreDecision:
    should_rescore: bool
    matched_triggers: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class RescoreQueueItem:
    """Payload for home action queue — human review only."""

    key: str
    title: str
    detail: str
    triggers: tuple[str, ...]
    tickers: tuple[str, ...]
    as_of: str
    source: str


def evaluate_rescore_triggers(
    cfg: AlphaSystemConfig,
    *,
    as_of: date,
    fired_events: Iterable[str] = (),
) -> RescoreDecision:
    """
    Hook only: match fired event ids against config.rescore_triggers.
    Never adjusts CECS or total_score.
    """
    triggers = list(cfg.scoring.rescore_triggers or [])
    if not triggers:
        return RescoreDecision(
            should_rescore=False,
            matched_triggers=(),
            reason=(
                f"as_of={as_of.isoformat()}: rescore_triggers [TODO] empty — "
                "hook idle (no default calendar)"
            ),
        )
    fired = set(fired_events)
    matched = tuple(sorted(t for t in triggers if t in fired))
    if matched:
        return RescoreDecision(
            should_rescore=True,
            matched_triggers=matched,
            reason=f"matched rescore triggers: {list(matched)}",
        )
    return RescoreDecision(
        should_rescore=False,
        matched_triggers=(),
        reason="configured triggers present but none fired in this snapshot",
    )


def build_rescore_queue_item(
    decision: RescoreDecision,
    *,
    as_of: date,
    tickers: Sequence[str] = (),
    source: str = "rescore_hook",
) -> RescoreQueueItem | None:
    if not decision.should_rescore:
        return None
    tks = tuple(str(t).zfill(6) if str(t).isdigit() else str(t) for t in tickers)
    trig = ", ".join(decision.matched_triggers)
    who = ", ".join(f"`{t}`" for t in tks) if tks else "관련 종목"
    return RescoreQueueItem(
        key=f"rescore_{as_of.isoformat()}_{'_'.join(decision.matched_triggers)[:80]}",
        title="재채점 검토 필요",
        detail=(
            f"{who} — 트리거: {trig}. "
            "CECS 점수는 자동 변경되지 않습니다. 결재함에서 재검토하세요."
        ),
        triggers=decision.matched_triggers,
        tickers=tks,
        as_of=as_of.isoformat(),
        source=source,
    )


def evaluate_manual_consensus_signals(
    rows: Sequence[Mapping[str, Any]],
    *,
    as_of: date,
) -> RescoreDecision:
    """
    Manual weekly / JSON signals only (no live consensus feed).
    Expected row keys: event_id (one of CONSENSUS_TRIGGER_IDS), optional ticker.
    Thresholds (SUE ±%, gap %) stay TODO — presence of a filled row fires review.
    """
    matched: list[str] = []
    for row in rows:
        eid = str(row.get("event_id") or row.get("trigger") or "").strip()
        if eid in CONSENSUS_TRIGGER_IDS:
            matched.append(eid)
    matched_u = tuple(sorted(set(matched)))
    if matched_u:
        return RescoreDecision(
            should_rescore=True,
            matched_triggers=matched_u,
            reason=(
                f"as_of={as_of.isoformat()}: manual consensus signals {list(matched_u)} "
                "(no auto score change; thresholds TODO)"
            ),
        )
    return RescoreDecision(
        should_rescore=False,
        matched_triggers=(),
        reason=f"as_of={as_of.isoformat()}: no manual consensus signals",
    )
