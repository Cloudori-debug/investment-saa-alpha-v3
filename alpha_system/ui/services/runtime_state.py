"""Persisted runtime flags for dashboard (events, tranche ack, refresh meta)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from alpha_system.entry.models import TrancheState
from alpha_system.schema import TrancheId


@dataclass
class RuntimeState:
    events_fired: set[str] = field(default_factory=set)
    cancelled_events: set[str] = field(default_factory=set)
    thesis_damage_active: bool = False
    thesis_damage_cancelled: bool = False
    tranche_states: dict[str, str] = field(default_factory=dict)
    tranche_meta: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_refresh: dict[str, str] = field(default_factory=dict)
    swap_hits: dict[str, int] = field(default_factory=dict)
    go_live_date: Optional[str] = None  # ISO date; UI declaration (config may stay null)
    journaled_tranche_states: dict[str, str] = field(default_factory=dict)
    journaled_trigger_met: dict[str, bool] = field(default_factory=dict)
    journaled_cap_tone: dict[str, str] = field(default_factory=dict)
    journaled_block_keys: list[str] = field(default_factory=list)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "events_fired": sorted(self.events_fired),
            "cancelled_events": sorted(self.cancelled_events),
            "thesis_damage_active": self.thesis_damage_active,
            "thesis_damage_cancelled": self.thesis_damage_cancelled,
            "tranche_states": self.tranche_states,
            "tranche_meta": self.tranche_meta,
            "last_refresh": self.last_refresh,
            "swap_hits": self.swap_hits,
            "go_live_date": self.go_live_date,
            "journaled_tranche_states": self.journaled_tranche_states,
            "journaled_trigger_met": self.journaled_trigger_met,
            "journaled_cap_tone": self.journaled_cap_tone,
            "journaled_block_keys": self.journaled_block_keys,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "RuntimeState":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            events_fired=set(data.get("events_fired") or []),
            cancelled_events=set(data.get("cancelled_events") or []),
            thesis_damage_active=bool(data.get("thesis_damage_active")),
            thesis_damage_cancelled=bool(data.get("thesis_damage_cancelled")),
            tranche_states=dict(data.get("tranche_states") or {}),
            tranche_meta=dict(data.get("tranche_meta") or {}),
            last_refresh=dict(data.get("last_refresh") or {}),
            swap_hits=dict(data.get("swap_hits") or {}),
            go_live_date=data.get("go_live_date"),
            journaled_tranche_states=dict(data.get("journaled_tranche_states") or {}),
            journaled_trigger_met={
                k: bool(v) for k, v in (data.get("journaled_trigger_met") or {}).items()
            },
            journaled_cap_tone=dict(data.get("journaled_cap_tone") or {}),
            journaled_block_keys=list(data.get("journaled_block_keys") or []),
        )

    def effective_go_live(self) -> Optional[date]:
        if not self.go_live_date:
            return None
        try:
            return date.fromisoformat(str(self.go_live_date)[:10])
        except ValueError:
            return None

    def effective_events(self) -> frozenset[str]:
        return frozenset(self.events_fired - self.cancelled_events)

    def effective_thesis_damage(self) -> bool:
        if self.thesis_damage_cancelled:
            return False
        return self.thesis_damage_active

    def prior_tranche_states(self) -> dict[TrancheId, TrancheState]:
        out: dict[TrancheId, TrancheState] = {}
        for tid in ("T1", "T2", "T3", "T4"):
            raw = self.tranche_states.get(tid)
            if raw:
                try:
                    out[tid] = TrancheState(raw)  # type: ignore[arg-type]
                except ValueError:
                    continue
        return out

    def prior_tranche_meta(self) -> dict[TrancheId, dict[str, Any]]:
        return {k: dict(v) for k, v in self.tranche_meta.items() if k in ("T1", "T2", "T3", "T4")}  # type: ignore[misc]

    def touch_refresh(self, kind: str) -> None:
        self.last_refresh[kind] = datetime.now(timezone.utc).isoformat()


def sync_runtime_from_journal(state: RuntimeState, journal_path: Path) -> RuntimeState:
    """Replay T2 / thesis / cancel entries onto runtime (idempotent)."""
    from alpha_system.journal.recorder import load_jsonl

    if not journal_path.exists():
        return state
    events: set[str] = set()
    cancelled: set[str] = set()
    thesis = False
    thesis_cancel = False
    for rec in load_jsonl(journal_path):
        kind = rec.action_kind
        if kind == "T2_EVENT_RECORD":
            eid = rec.payload.get("event_id") or rec.subject
            if rec.payload.get("cancel"):
                cancelled.add(str(eid))
            else:
                events.add(str(eid))
        elif kind == "THESIS_DAMAGE_FLAG":
            if rec.payload.get("cancel"):
                thesis_cancel = True
                thesis = False
            else:
                thesis = True
        elif kind == "T2_EVENT_CANCEL":
            eid = rec.payload.get("event_id") or rec.subject
            cancelled.add(str(eid))
        elif kind == "THESIS_DAMAGE_CANCEL":
            thesis_cancel = True
            thesis = False
        elif kind == "GO_LIVE_DECLARE":
            gld = rec.payload.get("go_live_date") or rec.as_of
            if gld:
                state.go_live_date = str(gld)[:10]
    state.events_fired = events
    state.cancelled_events = cancelled
    state.thesis_damage_active = thesis and not thesis_cancel
    state.thesis_damage_cancelled = thesis_cancel
    return state
