"""Load hold/exit review edition parameters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class HoldExitReviewConfig:
    edition_label: str
    weeks_out_before_rotate: int
    min_rotate_score_gap: float
    price_drawdown_thesis_pct: float
    management_cap_pct: float
    forbid_pct_take_profit: bool
    forbid_pct_stop_loss: bool
    monthly_trade_review: bool
    history_relpath: str

    @property
    def history_path(self) -> Path:
        return Path(self.history_relpath)


def load_hold_exit_config(root: Path) -> HoldExitReviewConfig:
    path = root / "alpha_system" / "config" / "hold_exit_review.yaml"
    raw: dict[str, Any] = {}
    if path.is_file():
        with path.open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    block = raw.get("hold_exit_review") or {}
    return HoldExitReviewConfig(
        edition_label=str(block.get("edition_label") or "보유·매도 Review v1"),
        weeks_out_before_rotate=int(block.get("weeks_out_before_rotate") or 4),
        min_rotate_score_gap=float(block.get("min_rotate_score_gap") or 15.0),
        price_drawdown_thesis_pct=float(block.get("price_drawdown_thesis_pct") or 20.0),
        management_cap_pct=float(block.get("management_cap_pct") or 15.0),
        forbid_pct_take_profit=bool(block.get("forbid_pct_take_profit", True)),
        forbid_pct_stop_loss=bool(block.get("forbid_pct_stop_loss", True)),
        monthly_trade_review=bool(block.get("monthly_trade_review", True)),
        history_relpath=str(block.get("history_relpath") or "data/local/hold_exit_proposal_weeks.jsonl"),
    )
