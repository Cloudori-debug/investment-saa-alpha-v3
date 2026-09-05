"""Post-cutoff qualitative overlay — gates and ±K rank swaps.

Does not change total_score (Ops A). Does not write target_portfolio.csv.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from alpha_system.scoring.engine import NameScore

DEFAULT_MAX_SWAP_SLOTS = 2
OVERLAY_FILENAME = "qual_rank_overlay.json"

GATE_REASONS = ("downgrade", "negative_watch", "pension_exit", "control_purpose")
GATE_REASON_KO = {
    "downgrade": "신평 강등",
    "negative_watch": "부정적 관찰",
    "pension_exit": "연기금 이탈",
    "control_purpose": "경영참여",
}


def norm_ticker(raw: object) -> str:
    text = str(raw or "").strip()
    if text.isdigit():
        return text.zfill(6)
    return text


def require_source_url(url: str) -> str:
    text = str(url or "").strip()
    low = text.lower()
    if not (low.startswith("http://") or low.startswith("https://")):
        raise ValueError("출처 URL이 필요합니다 (http:// 또는 https://).")
    return text


@dataclass(frozen=True)
class QualGate:
    ticker: str
    reason: str
    source_url: str
    note: str = ""
    as_of: str = ""
    active: bool = True

    def label_ko(self) -> str:
        return GATE_REASON_KO.get(self.reason, self.reason)


@dataclass(frozen=True)
class QualSwap:
    promote: str
    demote: str
    source_url: str
    note: str = ""
    as_of: str = ""
    active: bool = True


@dataclass(frozen=True)
class QualOverlay:
    version: str = "1"
    max_swap_slots: int = DEFAULT_MAX_SWAP_SLOTS
    gates: tuple[QualGate, ...] = ()
    swaps: tuple[QualSwap, ...] = ()

    def active_gates(self) -> tuple[QualGate, ...]:
        return tuple(g for g in self.gates if g.active)

    def active_swaps(self) -> tuple[QualSwap, ...]:
        return tuple(s for s in self.swaps if s.active)

    def gated_tickers(self) -> set[str]:
        return {g.ticker for g in self.active_gates()}

    def is_empty(self) -> bool:
        return not self.active_gates() and not self.active_swaps()


def empty_overlay(*, max_swap_slots: int = DEFAULT_MAX_SWAP_SLOTS) -> QualOverlay:
    return QualOverlay(max_swap_slots=max(1, int(max_swap_slots)))


def apply_qual_overlay(
    passed: Sequence[NameScore],
    overlay: QualOverlay | None,
) -> tuple[list[NameScore], list[str]]:
    """Filter gated names, then apply ±K pairwise swaps. Order is otherwise kept.

    ``passed`` must already be cutoff-eligible and sorted by the caller
    (quant weight_input descending).
    """
    ordered = list(passed)
    warnings: list[str] = []
    if overlay is None or overlay.is_empty():
        return ordered, warnings

    gated = overlay.gated_tickers()
    if gated:
        kept: list[NameScore] = []
        dropped: list[str] = []
        for row in ordered:
            ticker = norm_ticker(row.ticker)
            if ticker in gated:
                dropped.append(ticker)
                continue
            kept.append(row)
        ordered = kept
        if dropped:
            warnings.append(
                "qual gate: excluded "
                + ", ".join(dropped)
                + " (cutoff unchanged; next eligible may fill)"
            )

    index = {norm_ticker(s.ticker): i for i, s in enumerate(ordered)}
    max_slots = max(1, int(overlay.max_swap_slots))
    for swap in overlay.active_swaps():
        up = swap.promote
        down = swap.demote
        if up == down:
            warnings.append(f"qual swap skipped: {up} promote=demote")
            continue
        if up in gated or down in gated:
            warnings.append(
                f"qual swap skipped: {up}/{down} — gated name cannot be swapped"
            )
            continue
        i = index.get(up)
        j = index.get(down)
        if i is None or j is None:
            warnings.append(
                f"qual swap skipped: {up}/{down} — not in cutoff-eligible list"
            )
            continue
        if abs(i - j) > max_slots:
            warnings.append(
                f"qual swap skipped: {up}/{down} — "
                f"|rank Δ|={abs(i - j)} > max {max_slots}"
            )
            continue
        ordered[i], ordered[j] = ordered[j], ordered[i]
        index[up], index[down] = j, i
        warnings.append(f"qual swap: {up} ↔ {down} (slots {abs(i - j)})")
    return ordered, warnings


def overlay_to_dict(overlay: QualOverlay) -> dict:
    return {
        "version": overlay.version,
        "max_swap_slots": int(overlay.max_swap_slots),
        "gates": [
            {
                "ticker": g.ticker,
                "reason": g.reason,
                "source_url": g.source_url,
                "note": g.note,
                "as_of": g.as_of,
                "active": bool(g.active),
            }
            for g in overlay.gates
        ],
        "swaps": [
            {
                "promote": s.promote,
                "demote": s.demote,
                "source_url": s.source_url,
                "note": s.note,
                "as_of": s.as_of,
                "active": bool(s.active),
            }
            for s in overlay.swaps
        ],
    }


def overlay_from_dict(raw: Mapping[str, object] | None) -> QualOverlay:
    data = dict(raw or {})
    slots = int(data.get("max_swap_slots") or DEFAULT_MAX_SWAP_SLOTS)
    gates: list[QualGate] = []
    for item in data.get("gates") or []:
        if not isinstance(item, Mapping):
            continue
        reason = str(item.get("reason") or "").strip()
        if reason not in GATE_REASONS:
            continue
        ticker = norm_ticker(item.get("ticker"))
        if not ticker:
            continue
        gates.append(
            QualGate(
                ticker=ticker,
                reason=reason,
                source_url=str(item.get("source_url") or "").strip(),
                note=str(item.get("note") or "").strip(),
                as_of=str(item.get("as_of") or "").strip(),
                active=bool(item.get("active", True)),
            )
        )
    swaps: list[QualSwap] = []
    for item in data.get("swaps") or []:
        if not isinstance(item, Mapping):
            continue
        promote = norm_ticker(item.get("promote"))
        demote = norm_ticker(item.get("demote"))
        if not promote or not demote:
            continue
        swaps.append(
            QualSwap(
                promote=promote,
                demote=demote,
                source_url=str(item.get("source_url") or "").strip(),
                note=str(item.get("note") or "").strip(),
                as_of=str(item.get("as_of") or "").strip(),
                active=bool(item.get("active", True)),
            )
        )
    return QualOverlay(
        version=str(data.get("version") or "1"),
        max_swap_slots=max(1, slots),
        gates=tuple(gates),
        swaps=tuple(swaps),
    )


def overlay_path(root: Path) -> Path:
    return Path(root) / "data" / OVERLAY_FILENAME


def load_qual_overlay(path: Path | None) -> QualOverlay:
    if path is None or not path.exists():
        return empty_overlay()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_overlay()
    if not isinstance(raw, dict):
        return empty_overlay()
    return overlay_from_dict(raw)


def save_qual_overlay(path: Path, overlay: QualOverlay) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(overlay_to_dict(overlay), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def add_gate(
    overlay: QualOverlay,
    *,
    ticker: str,
    reason: str,
    source_url: str,
    note: str = "",
    as_of: date | str | None = None,
) -> QualOverlay:
    if reason not in GATE_REASONS:
        raise ValueError(f"unknown gate reason: {reason}")
    url = require_source_url(source_url)
    tk = norm_ticker(ticker)
    day = _as_of(as_of)
    gates = tuple(g for g in overlay.gates if not (g.ticker == tk and g.active))
    gates = gates + (
        QualGate(
            ticker=tk,
            reason=reason,
            source_url=url,
            note=str(note or "").strip(),
            as_of=day,
            active=True,
        ),
    )
    return QualOverlay(
        version=overlay.version,
        max_swap_slots=overlay.max_swap_slots,
        gates=gates,
        swaps=overlay.swaps,
    )


_OPENDART_GATE_KINDS = frozenset({"control_purpose", "pension_exit"})


def apply_opendart_flag_gates(
    overlay: QualOverlay,
    flags: Sequence[Any],
    *,
    as_of: date | str | None = None,
) -> tuple[QualOverlay, tuple[str, ...]]:
    """Add OpenDART control/pension flags as overlay gates. Does not mix scores."""
    wanted: dict[str, dict[str, Any]] = {}
    for raw in flags:
        tk = norm_ticker(getattr(raw, "ticker", "") or "")
        kind = str(getattr(raw, "kind", "") or "")
        if not tk or kind not in _OPENDART_GATE_KINDS:
            continue
        wanted.setdefault(tk, {})[kind] = raw
    if not wanted:
        return overlay, ()
    day = _as_of(as_of)
    applied: list[str] = []
    gates = list(overlay.gates)
    for tk, by_kind in wanted.items():
        have = {g.reason for g in overlay.active_gates() if g.ticker == tk}
        missing = {k: v for k, v in by_kind.items() if k not in have}
        if not missing:
            continue
        for kind, item in missing.items():
            url = str(getattr(item, "source_url", "") or "https://opendart.fss.or.kr/")
            gates.append(
                QualGate(
                    ticker=tk,
                    reason=kind,
                    source_url=require_source_url(url),
                    note=str(getattr(item, "note", "") or "").strip(),
                    as_of=day,
                    active=True,
                )
            )
        applied.append(tk)
    if not applied:
        return overlay, ()
    return (
        QualOverlay(
            version=overlay.version,
            max_swap_slots=overlay.max_swap_slots,
            gates=tuple(gates),
            swaps=overlay.swaps,
        ),
        tuple(applied),
    )


def clear_gate(overlay: QualOverlay, ticker: str) -> QualOverlay:
    tk = norm_ticker(ticker)
    gates = tuple(
        QualGate(
            ticker=g.ticker,
            reason=g.reason,
            source_url=g.source_url,
            note=g.note,
            as_of=g.as_of,
            active=False if g.ticker == tk and g.active else g.active,
        )
        for g in overlay.gates
    )
    return QualOverlay(
        version=overlay.version,
        max_swap_slots=overlay.max_swap_slots,
        gates=gates,
        swaps=overlay.swaps,
    )


def add_swap(
    overlay: QualOverlay,
    *,
    promote: str,
    demote: str,
    source_url: str,
    note: str = "",
    as_of: date | str | None = None,
) -> QualOverlay:
    url = require_source_url(source_url)
    up = norm_ticker(promote)
    down = norm_ticker(demote)
    if up == down:
        raise ValueError("같은 종목끼리는 자리를 바꿀 수 없습니다.")
    day = _as_of(as_of)
    swaps = overlay.swaps + (
        QualSwap(
            promote=up,
            demote=down,
            source_url=url,
            note=str(note or "").strip(),
            as_of=day,
            active=True,
        ),
    )
    return QualOverlay(
        version=overlay.version,
        max_swap_slots=overlay.max_swap_slots,
        gates=overlay.gates,
        swaps=swaps,
    )


def clear_swap(overlay: QualOverlay, *, promote: str, demote: str) -> QualOverlay:
    up = norm_ticker(promote)
    down = norm_ticker(demote)
    swaps = tuple(
        QualSwap(
            promote=s.promote,
            demote=s.demote,
            source_url=s.source_url,
            note=s.note,
            as_of=s.as_of,
            active=(
                False
                if s.active and s.promote == up and s.demote == down
                else s.active
            ),
        )
        for s in overlay.swaps
    )
    return QualOverlay(
        version=overlay.version,
        max_swap_slots=overlay.max_swap_slots,
        gates=overlay.gates,
        swaps=swaps,
    )


def journal_overlay_change(
    *,
    action_kind: str,
    subject: str,
    rationale: str,
    as_of: date | str,
    payload: Mapping[str, object] | None = None,
    journal_path: Path | None = None,
) -> None:
    from alpha_system.journal import append_record

    append_record(
        action_kind=action_kind,
        as_of=as_of,
        subject=subject,
        rationale=rationale,
        trigger_snapshot={"source": "qual_overlay"},
        payload=dict(payload or {}),
        journal_path=journal_path,
    )


def _as_of(value: date | str | None) -> str:
    if value is None:
        return date.today().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip() or date.today().isoformat()
