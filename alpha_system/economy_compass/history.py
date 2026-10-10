"""Precomputed stage → asset frequency table (Review-only)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from alpha_system.economy_compass.sleeves import SLEEVE_IDS, _LABELS

_DATA = Path(__file__).resolve().parent / "data" / "stage_asset_frequency.json"


@dataclass(frozen=True)
class FrequencyCell:
    sleeve_id: str
    label: str
    win_rate: Optional[float]
    median_ret: Optional[float]
    n_months: int


@dataclass(frozen=True)
class FrequencyTable:
    stage: Optional[int]
    cells: tuple[FrequencyCell, ...]
    note: str
    sources: tuple[str, ...]
    available: bool


def _load_raw() -> dict[str, Any]:
    try:
        raw = json.loads(_DATA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def frequency_for_stage(stage: int | None) -> FrequencyTable:
    """Lookup precomputed win rates; fail-open empty if stage/data missing."""
    raw = _load_raw()
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    note = str(meta.get("note") or "사전계산 빈도 · 참고용")
    sources = tuple(str(x) for x in (meta.get("sources") or []) if x)
    if stage is None:
        return FrequencyTable(
            stage=None,
            cells=(),
            note=note,
            sources=sources,
            available=False,
        )
    by_stage = raw.get("by_stage") if isinstance(raw.get("by_stage"), dict) else {}
    bucket = by_stage.get(str(int(stage)))
    if not isinstance(bucket, dict):
        return FrequencyTable(
            stage=int(stage),
            cells=(),
            note=note,
            sources=sources,
            available=False,
        )
    cells: list[FrequencyCell] = []
    for sid in SLEEVE_IDS:
        cell = bucket.get(sid)
        if not isinstance(cell, dict):
            cells.append(
                FrequencyCell(
                    sleeve_id=sid,
                    label=_LABELS.get(sid, sid),
                    win_rate=None,
                    median_ret=None,
                    n_months=0,
                )
            )
            continue
        wr = cell.get("win_rate")
        mr = cell.get("median_ret")
        try:
            wr_f = float(wr) if wr is not None else None
        except (TypeError, ValueError):
            wr_f = None
        try:
            mr_f = float(mr) if mr is not None else None
        except (TypeError, ValueError):
            mr_f = None
        try:
            n = int(cell.get("n_months") or 0)
        except (TypeError, ValueError):
            n = 0
        cells.append(
            FrequencyCell(
                sleeve_id=sid,
                label=_LABELS.get(sid, sid),
                win_rate=wr_f,
                median_ret=mr_f,
                n_months=n,
            )
        )
    return FrequencyTable(
        stage=int(stage),
        cells=tuple(cells),
        note=note,
        sources=sources,
        available=bool(cells),
    )
