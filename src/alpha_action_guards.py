from __future__ import annotations

from typing import Any

from src.models import ActionType, GapRow, TradeAction

_BLOCK_BUY_REVIEW = frozenset({"TRIM", "REPLACE_CANDIDATE"})


def _review_map(holdings_review: list[dict[str, Any]] | None) -> dict[str, str]:
    if not holdings_review:
        return {}
    out: dict[str, str] = {}
    for h in holdings_review:
        t = str(h.get("ticker", "")).strip()
        if t:
            out[t] = str(h.get("review_action", "")).strip()
    return out


def apply_holdings_review_guards(
    actions: list[TradeAction],
    gap_rows: list[GapRow],
    holdings_review: list[dict[str, Any]] | None,
) -> list[TradeAction]:
    """holdings_review TRIM/REPLACE와 trade Buy-allowed 충돌 방지."""
    gaps = {r.ticker: r for r in gap_rows}
    reviews = _review_map(holdings_review)
    guarded: list[TradeAction] = []

    for act in actions:
        row = gaps.get(act.ticker)
        rev = reviews.get(act.ticker)
        if row is None or row.asset_group != "kr_alpha":
            guarded.append(act)
            continue

        if act.action == "Buy-allowed":
            if rev in _BLOCK_BUY_REVIEW:
                guarded.append(
                    act.model_copy(
                        update={
                            "action": "Wait",
                            "reason": f"holdings_review {rev} — 신규 매수 불가",
                            "allowed_size_pct": 0,
                        }
                    )
                )
                continue
            if row.current_weight <= 0 and rev == "TRIM":
                guarded.append(
                    act.model_copy(
                        update={
                            "action": "Wait",
                            "reason": "미보유 종목 — TRIM 리뷰와 Buy 충돌, 신규 매수 보류",
                            "allowed_size_pct": 0,
                        }
                    )
                )
                continue

        guarded.append(act)

    return guarded
