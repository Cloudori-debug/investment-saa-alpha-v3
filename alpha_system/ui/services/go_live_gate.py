"""Pre-launch checklist + go-live gate (hard-block style)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from alpha_system.schema import AlphaSystemConfig
from alpha_system.ui.services.ui_copy import copy_get


@dataclass(frozen=True)
class ChecklistItem:
    key: str
    title: str
    why: str
    todo: str
    ok: bool


@dataclass(frozen=True)
class ChecklistStatus:
    items: list[ChecklistItem]
    pre_launch: bool
    go_live_date: Optional[date]

    @property
    def done(self) -> int:
        return sum(1 for i in self.items if i.ok)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def blocking(self) -> list[ChecklistItem]:
        return [i for i in self.items if not i.ok]

    @property
    def ready_for_go_live(self) -> bool:
        return all(i.ok for i in self.items)


def assess_checklist(
    cfg: AlphaSystemConfig,
    *,
    root: Path,
    go_live_date: Optional[date],
    cecs_path: Path | None = None,
) -> ChecklistStatus:
    pre_launch = go_live_date is None
    cecs_path = cecs_path or (root / "data" / "cecs_manual_scoring_template.csv")
    hist_path = root / "data" / "kospi_market_pbr_history.csv"

    final_n, total_n = _cecs_counts(cecs_path)
    score_ok = cfg.scoring.score_cutoff is not None
    # Ops A (2026-07-25): CECS no longer blocks go-live — rank is quant-only.
    cecs_ok = True
    t3_ok = hist_path.exists() and _csv_has_rows(hist_path)

    items = [
        ChecklistItem(
            key="score_cutoff",
            title=copy_get("checklist", "score_cutoff", "title"),
            why=copy_get("checklist", "score_cutoff", "why"),
            todo=copy_get("checklist", "score_cutoff", "todo"),
            ok=score_ok,
        ),
        ChecklistItem(
            key="cecs_final",
            title=copy_get("checklist", "cecs_final", "title"),
            why=copy_get(
                "checklist", "cecs_final", "why", final=final_n, total=total_n
            ),
            todo=copy_get("checklist", "cecs_final", "todo"),
            ok=cecs_ok,
        ),
        ChecklistItem(
            key="t3_history",
            title=copy_get("checklist", "t3_history", "title"),
            why=copy_get("checklist", "t3_history", "why"),
            todo=copy_get("checklist", "t3_history", "todo"),
            ok=t3_ok,
        ),
    ]
    return ChecklistStatus(items=items, pre_launch=pre_launch, go_live_date=go_live_date)


def block_go_live_reasons(checklist: ChecklistStatus) -> list[str]:
    return [f"{i.title} ({i.todo})" for i in checklist.blocking]


def _cecs_counts(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    df = pd.read_csv(path, dtype=str)
    if df.empty:
        return 0, 0
    total = len(df)
    final = int((df.get("status", pd.Series(dtype=str)) == "final").sum()) if "status" in df.columns else 0
    return final, total


def _csv_has_rows(path: Path) -> bool:
    try:
        df = pd.read_csv(path)
        return not df.empty
    except Exception:
        return False
