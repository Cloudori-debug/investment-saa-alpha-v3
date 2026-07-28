"""Target valuation worksheet modify rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional

from alpha_system.journal.recorder import append_record
from alpha_system.schema import AlphaSystemConfig


ModifyReasonType = Literal["fundamental_event", "price_move", "other"]


@dataclass(frozen=True)
class TargetValuationModifyResult:
    allowed: bool
    warn_only: bool
    detail: str
    journal_id: Optional[str] = None


def modify_target_valuation(
    cfg: AlphaSystemConfig,
    *,
    ticker: str,
    as_of: date,
    reason_type: ModifyReasonType,
    rationale: str,
    journal: bool = True,
) -> TargetValuationModifyResult:
    """
    Fundamental-event edits require rationale + journal.
    Price-move rationale → WARN only (still recorded if journal=True).
    """
    rules = dict(cfg.exit.target_valuation_modify or {})
    allowed_reasons = set(rules.get("allowed_reasons") or ["fundamental_event"])
    price_warn = bool(rules.get("price_move_warn", True))
    text = (rationale or "").strip()
    if not text:
        return TargetValuationModifyResult(
            allowed=False,
            warn_only=False,
            detail="rationale text required for target valuation modify",
        )

    if reason_type == "price_move" and price_warn:
        jid = None
        if journal:
            rec = append_record(
                action_kind="WARN_TARGET_VALUATION_MODIFY",
                as_of=as_of,
                subject=ticker,
                rationale=text,
                trigger_snapshot={"reason_type": reason_type},
                score_snapshot={},
                payload={"warn_only": True, "price_move": True},
            )
            jid = rec.entry_id
        return TargetValuationModifyResult(
            allowed=False,
            warn_only=True,
            detail="price-move target modify → WARN only (fundamental_event required)",
            journal_id=jid,
        )

    if reason_type not in allowed_reasons:
        return TargetValuationModifyResult(
            allowed=False,
            warn_only=False,
            detail=f"reason_type={reason_type} not in allowed_reasons={sorted(allowed_reasons)}",
        )

    jid = None
    if journal:
        rec = append_record(
            action_kind="TARGET_VALUATION_MODIFY",
            as_of=as_of,
            subject=ticker,
            rationale=text,
            trigger_snapshot={"reason_type": reason_type},
            score_snapshot={},
            payload={"allowed": True},
        )
        jid = rec.entry_id
    return TargetValuationModifyResult(
        allowed=True,
        warn_only=False,
        detail=f"target valuation modify accepted ({reason_type})",
        journal_id=jid,
    )
