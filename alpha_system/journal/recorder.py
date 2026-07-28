"""Append-only journal schema and store (§7.4)."""

from __future__ import annotations

import itertools
import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional


class JournalValidationError(ValueError):
    """Raised when required journal fields are missing."""


_counter = itertools.count(1)
_lock = threading.Lock()
_ENTRIES: list["JournalRecord"] = []
_DEFAULT_PATH: Path | None = None
_HYDRATED_PATH: Path | None = None


@dataclass(frozen=True)
class JournalRecord:
    """Immutable journal row — never mutate after append."""

    entry_id: str
    recorded_at: str
    action_kind: str
    as_of: str
    subject: str  # ticker, tranche id, or "*"
    # 판단 근거 (자유 텍스트) — 항상 허용, 권장
    rationale: str
    # 재량 청산 사후검증용 — WARN_DISCRETIONARY 시 필수
    discretionary_reason: Optional[str]
    trigger_snapshot: Mapping[str, Any]
    score_snapshot: Mapping[str, Any]
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "recorded_at": self.recorded_at,
            "action_kind": self.action_kind,
            "as_of": self.as_of,
            "subject": self.subject,
            "rationale": self.rationale,
            "discretionary_reason": self.discretionary_reason,
            "trigger_snapshot": dict(self.trigger_snapshot),
            "score_snapshot": dict(self.score_snapshot),
            "payload": dict(self.payload),
        }


def configure_journal_path(path: Path | None) -> None:
    """Optional JSONL sink (append-only file). None = memory only."""
    global _DEFAULT_PATH
    _DEFAULT_PATH = path


def _require_discretionary(action_kind: str, discretionary_reason: Optional[str]) -> None:
    if action_kind in {"WARN_DISCRETIONARY", "exit_warn_discretionary"}:
        if not discretionary_reason or not str(discretionary_reason).strip():
            raise JournalValidationError(
                "discretionary_reason is required for WARN_DISCRETIONARY "
                "(post-hoc review of rule deviations)"
            )


def append_record(
    *,
    action_kind: str,
    as_of: date | str,
    subject: str,
    rationale: str = "",
    discretionary_reason: Optional[str] = None,
    trigger_snapshot: Mapping[str, Any] | None = None,
    score_snapshot: Mapping[str, Any] | None = None,
    payload: Mapping[str, Any] | None = None,
    journal_path: Path | None = None,
) -> JournalRecord:
    """
    Append-only write. No update/delete API is provided on purpose.
    (clear_entries is test-only.)
    """
    _require_discretionary(action_kind, discretionary_reason)
    as_of_s = as_of.isoformat() if isinstance(as_of, date) else str(as_of)
    with _lock:
        n = next(_counter)
        record = JournalRecord(
            entry_id=f"J{n:06d}",
            recorded_at=datetime.now(timezone.utc).isoformat(),
            action_kind=action_kind,
            as_of=as_of_s,
            subject=subject,
            rationale=rationale or "",
            discretionary_reason=(
                str(discretionary_reason).strip() if discretionary_reason else None
            ),
            trigger_snapshot=dict(trigger_snapshot or {}),
            score_snapshot=dict(score_snapshot or {}),
            payload=dict(payload or {}),
        )
        _ENTRIES.append(record)
        sink = journal_path if journal_path is not None else _DEFAULT_PATH
        if sink is not None:
            sink.parent.mkdir(parents=True, exist_ok=True)
            with sink.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        return record


# Backward-compatible thin wrapper used by §7.3 exit
def record_action(*, kind: str, payload: dict[str, Any]) -> JournalRecord:
    return append_record(
        action_kind=str(payload.get("action_type") or kind),
        as_of=str(payload.get("as_of") or date.today().isoformat()),
        subject=str(payload.get("ticker") or payload.get("subject") or "*"),
        rationale=str(payload.get("rationale") or payload.get("detail") or ""),
        discretionary_reason=payload.get("discretionary_reason"),
        trigger_snapshot=dict(payload.get("trigger_snapshot") or {}),
        score_snapshot=dict(payload.get("score_snapshot") or {}),
        payload={k: v for k, v in payload.items() if k not in {
            "as_of", "ticker", "subject", "rationale", "detail",
            "discretionary_reason", "trigger_snapshot", "score_snapshot",
            "action_type",
        }},
    )


def list_entries(
    *,
    kind: str | None = None,
    action_kind: str | None = None,
) -> list[JournalRecord]:
    with _lock:
        rows = list(_ENTRIES)
    if kind is not None:
        # legacy filter: payload-ish — match action_kind contains or equals
        rows = [e for e in rows if kind in (e.action_kind, e.payload.get("kind", ""))]
    if action_kind is not None:
        rows = [e for e in rows if e.action_kind == action_kind]
    return rows


def list_discretionary_warnings() -> list[JournalRecord]:
    return [
        e
        for e in list_entries()
        if e.action_kind in {"WARN_DISCRETIONARY", "exit_warn_discretionary"}
    ]


def clear_entries() -> None:
    """Test helper only — not part of production API surface."""
    with _lock:
        _ENTRIES.clear()


def load_jsonl(path: Path) -> list[JournalRecord]:
    """Read-only load of an append-only JSONL journal file."""
    if not path.exists():
        return []
    out: list[JournalRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        out.append(
            JournalRecord(
                entry_id=data["entry_id"],
                recorded_at=data["recorded_at"],
                action_kind=data["action_kind"],
                as_of=data["as_of"],
                subject=data["subject"],
                rationale=data.get("rationale") or "",
                discretionary_reason=data.get("discretionary_reason"),
                trigger_snapshot=data.get("trigger_snapshot") or {},
                score_snapshot=data.get("score_snapshot") or {},
                payload=data.get("payload") or {},
            )
        )
    return out


def ensure_journal_hydrated(path: Path) -> None:
    """Load JSONL into memory once per path (append-only UI reads/writes)."""
    global _HYDRATED_PATH
    configure_journal_path(path)
    if _HYDRATED_PATH == path:
        return
    with _lock:
        existing_ids = {e.entry_id for e in _ENTRIES}
        for rec in load_jsonl(path):
            if rec.entry_id not in existing_ids:
                _ENTRIES.append(rec)
                existing_ids.add(rec.entry_id)
        _HYDRATED_PATH = path
