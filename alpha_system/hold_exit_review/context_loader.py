"""Load dashboard context with hold/exit enrichment."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from alpha_system.hold_exit_review.config import load_hold_exit_config
from alpha_system.hold_exit_review.enrich import attach_extra_hold_exit_slot, enrich_context_hold_exit
from alpha_system.ui.services.context import DashboardContext, load_context


def load_context_hold_exit(
    root: Path,
    *,
    market: Optional[str] = None,
    horizon: Optional[str] = None,
    as_of: Optional[date] = None,
) -> DashboardContext:
    ctx = load_context(root, market=market, horizon=horizon, as_of=as_of)
    attach_extra_hold_exit_slot(ctx)
    cfg = load_hold_exit_config(root)
    enrich_context_hold_exit(ctx, cfg)
    ctx.extra_hold_exit["edition_label"] = cfg.edition_label
    return ctx
