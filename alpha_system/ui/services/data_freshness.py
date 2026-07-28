"""Data source freshness vs recommended cadence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import yaml


@dataclass(frozen=True)
class SourceStatus:
    key: str
    label: str
    path: str
    as_of: Optional[date]
    recommended_days: Optional[int]
    stale: bool
    exists: bool
    detail: str = ""


def load_dashboard_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"data_sources": {}}
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _parse_as_of(value: Any) -> Optional[date]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _file_mtime_as_of(path: Path) -> Optional[date]:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime).date()


def inspect_sources(
    root: Path,
    *,
    dashboard_cfg_path: Path,
    today: date | None = None,
) -> list[SourceStatus]:
    today = today or date.today()
    cfg = load_dashboard_config(dashboard_cfg_path)
    sources = cfg.get("data_sources") or {}
    rows: list[SourceStatus] = []
    for key, spec in sources.items():
        rel = spec.get("path", "")
        fpath = root / str(rel)
        exists = fpath.exists()
        as_of_col = spec.get("as_of_column")
        as_of: Optional[date] = None
        detail = ""
        if exists and as_of_col:
            try:
                df = pd.read_csv(fpath, nrows=5000)
                if as_of_col in df.columns and not df.empty:
                    as_of = _parse_as_of(df[as_of_col].max())
            except Exception as exc:
                detail = f"as_of 읽기 실패: {exc}"
        elif exists:
            as_of = _file_mtime_as_of(fpath)
            detail = "파일 수정일 기준"
        rec_days = spec.get("recommended_days")
        stale = False
        if rec_days is not None and as_of is not None:
            stale = (today - as_of).days > int(rec_days)
        rows.append(
            SourceStatus(
                key=key,
                label=str(spec.get("label") or key),
                path=str(rel),
                as_of=as_of,
                recommended_days=int(rec_days) if rec_days is not None else None,
                stale=stale,
                exists=exists,
                detail=detail,
            )
        )
    return rows
