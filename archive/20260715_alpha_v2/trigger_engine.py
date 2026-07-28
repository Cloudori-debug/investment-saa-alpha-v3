from __future__ import annotations

from typing import Any

from src.alpha_flow.flow_classifier import is_flow_record_stale, stale_warning_note
from src.alpha_v2.schemas import CANDIDATE_ONLY_NOTE


def _is_stale_flow(row: dict[str, Any]) -> bool:
    return is_flow_record_stale(row)


def _is_fresh_flow(row: dict[str, Any]) -> bool:
    return not _is_stale_flow(row) and str(row.get("flow_confidence", "LOW")).upper() != "LOW"


def _pension_flow_weakening(row: dict[str, Any]) -> bool:
    return (
        row.get("pension_streak_direction") == "sell"
        or float(row.get("pension_net_buy_20d") or 0) < 0
        or row.get("turning_sell_signal")
        or float(row.get("flow_score") or 0) < 0
    )


def _position_returns(positions_meta: dict[str, dict[str, float]], ticker: str) -> dict[str, float]:
    return positions_meta.get(ticker, {})


def _grade_downgrade_b_to_weak(row: dict[str, Any]) -> bool:
    grade_v1 = str(row.get("grade_v1") or row.get("legacy_grade") or "")
    grade_v2 = str(row.get("grade") or "")
    return grade_v1 == "B" and grade_v2 in {"C", "D", "Reject"}


def _base_buy_permission(row: dict[str, Any], *, actual_buy_allowed: int, no_trade: bool) -> bool:
    if actual_buy_allowed <= 0 or no_trade:
        return False
    if row.get("grade") in {"Reject", "D"}:
        return False
    if row.get("shadow_watch"):
        return False
    if not row.get("executable_universe"):
        return False
    if row.get("value_trap_flag"):
        return False
    if not row.get("liquidity_flag", True):
        return False
    return True


def _trim_watch_eligible(
    row: dict[str, Any],
    *,
    positions_meta: dict[str, dict[str, float]],
) -> tuple[bool, str]:
    if _is_stale_flow(row):
        return False, ""

    ticker = row["ticker"]
    ret = _position_returns(positions_meta, ticker)
    reasons: list[str] = []

    if row.get("pension_streak_direction") == "sell" and int(row.get("pension_streak_days") or 0) >= 5:
        reasons.append("pension_sell_streak>=5")
    p20 = row.get("pension_net_buy_20d")
    if p20 is not None and float(p20) < 0 and str(row.get("flow_confidence", "LOW")).upper() != "LOW":
        reasons.append("pension_net_buy_20d<0")
    if row.get("pension_foreign_co_sell"):
        reasons.append("pension_foreign_co_sell")
    if row.get("turning_sell_signal"):
        reasons.append("turning_sell")
    if _grade_downgrade_b_to_weak(row):
        reasons.append("grade_downgrade_B_to_C/D")
    profit_return = float(ret.get("profit_return") or 0)
    loss_return = float(ret.get("loss_return") or 0)
    if profit_return >= 15 and _pension_flow_weakening(row):
        reasons.append("profit>=15%_flow_weakening")
    if loss_return <= -8 and row.get("pension_foreign_co_sell"):
        reasons.append("loss<=-8%_co_sell")

    if reasons:
        return True, "; ".join(reasons)
    return False, ""


def build_flow_triggers(
    rows: list[dict[str, Any]],
    *,
    actual_buy_allowed: int,
    no_trade: bool,
    execution_scope: str,
    held_tickers: set[str] | None = None,
    positions_meta: dict[str, dict[str, float]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return buy_watch, trim_watch, stale_warnings (held positions with stale flow only)."""
    buy_watch: list[dict[str, Any]] = []
    trim_watch: list[dict[str, Any]] = []
    stale_warnings: list[dict[str, Any]] = []
    review_only = no_trade or execution_scope == "NO_TRADE"
    held = held_tickers or set()
    positions_meta = positions_meta or {}

    for row in rows:
        ticker = row["ticker"]
        if _is_stale_flow(row) and ticker in held:
            stale_warnings.append({
                "ticker": ticker,
                "name": row.get("name", ""),
                "flow_data_stale_warning": True,
                "flow_confidence": "LOW",
                "flow_signal_state": "stale",
                "note": stale_warning_note(held=True),
            })
        if _is_stale_flow(row):
            continue

        base = {
            "ticker": ticker,
            "name": row.get("name", ""),
            "market": row.get("market", "KOSPI"),
            "grade": row.get("grade", ""),
            "flow_signal_state": row.get("flow_signal_state", "neutral"),
            "flow_score": row.get("flow_score", 0),
            "flow_confidence": row.get("flow_confidence", "LOW"),
            "review_only": review_only,
            "note": CANDIDATE_ONLY_NOTE,
        }

        buy_perm = _base_buy_permission(row, actual_buy_allowed=actual_buy_allowed, no_trade=no_trade)
        buy_ok = (
            _is_fresh_flow(row)
            and row.get("grade") in {"A", "B"}
            and row.get("executable_universe")
            and not row.get("value_trap_flag")
            and float(row.get("flow_score") or 0) > 0
            and float(row.get("pension_net_buy_20d") or 0) > 0
            and row.get("pension_streak_direction") != "sell"
        )
        if buy_ok:
            entry = dict(base)
            entry["buy_watch"] = True
            entry["trim_watch"] = False
            entry["buy_permission"] = buy_perm
            entry["reason"] = "flow accumulation watch — not buy approval"
            if row.get("pension_streak_days", 0) >= 5:
                entry["reason"] += "; streak>=5"
            if row.get("pension_foreign_co_buy"):
                entry["reason"] += "; co_buy"
            if row.get("turning_buy_signal"):
                entry["reason"] += "; turning_buy"
            buy_watch.append(entry)

        trim_ok, trim_reason = _trim_watch_eligible(row, positions_meta=positions_meta)
        if trim_ok:
            entry = dict(base)
            entry["buy_watch"] = False
            entry["trim_watch"] = True
            entry["buy_permission"] = False
            entry["reason"] = f"trim review only — {trim_reason}"
            trim_watch.append(entry)

    for lst in (buy_watch, trim_watch):
        for entry in lst:
            if actual_buy_allowed <= 0:
                entry["buy_permission"] = False
            if review_only:
                entry["allowed_actions"] = "Hold / Trim / Exit Review only"
                entry["new_buy_allowed"] = False
    return buy_watch, trim_watch, stale_warnings


def build_positions_meta(positions: list[Any]) -> dict[str, dict[str, float]]:
    """profit_return / loss_return % for trim triggers on holdings."""
    out: dict[str, dict[str, float]] = {}
    for pos in positions:
        ticker = str(getattr(pos, "ticker", "")).zfill(6)
        qty = float(getattr(pos, "quantity", 0) or 0)
        if qty <= 0:
            continue
        avg = float(getattr(pos, "avg_price", 0) or 0)
        current = float(getattr(pos, "current_price", 0) or 0)
        if avg <= 0 or current <= 0:
            continue
        ret_pct = (current - avg) / avg * 100
        out[ticker] = {
            "profit_return": ret_pct if ret_pct > 0 else 0.0,
            "loss_return": ret_pct if ret_pct < 0 else 0.0,
        }
    return out
