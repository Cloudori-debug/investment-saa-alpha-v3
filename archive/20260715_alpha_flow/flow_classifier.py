"""Unified flow stale / state classification — review-only, not buy permission."""
from __future__ import annotations

from typing import Any

STALE_STALENESS_DAYS_THRESHOLD = 3
STALE_SOURCES = frozenset({"template", "missing"})
STALE_CONFIDENCE = "LOW"
STALE_SIGNAL_STATE = "stale"
STALE_FLOW_SIGNAL = "STALE"


def _truthy(val: Any) -> bool:
    return str(val).lower() in {"true", "1", "yes"}


def is_flow_record_stale(rec: dict[str, Any] | None) -> bool:
    """Single stale gate for v1 investor_flows, v2 overlay, and Flow UI."""
    if not rec:
        return True
    if _truthy(rec.get("stale_flag")) or _truthy(rec.get("flow_data_stale")):
        return True
    if str(rec.get("flow_signal_state") or "").lower() == STALE_SIGNAL_STATE:
        return True
    if str(rec.get("flow_signal") or "") == STALE_FLOW_SIGNAL:
        return True
    try:
        if int(rec.get("staleness_days") or 0) >= STALE_STALENESS_DAYS_THRESHOLD:
            return True
    except (TypeError, ValueError):
        return True
    if "source" in rec and str(rec.get("source") or "").strip().lower() in STALE_SOURCES:
        return True
    return False


def apply_stale_policy(row: dict[str, Any]) -> dict[str, Any]:
    """If stale: suppress watches, force LOW confidence and stale state."""
    out = dict(row)
    if not is_flow_record_stale(out):
        return out
    out.update({
        "flow_data_stale": True,
        "stale_flag": True,
        "flow_signal_state": STALE_SIGNAL_STATE,
        "flow_confidence": STALE_CONFIDENCE,
        "flow_signal": STALE_FLOW_SIGNAL,
        "buy_watch": False,
        "trim_watch": False,
    })
    return out


def classify_flow_state(
    *,
    pension_net_20d: float | None,
    foreign_net_20d: float | None,
    co_buy: bool = False,
    co_sell: bool = False,
    turning_buy: bool = False,
    turning_sell: bool = False,
    stale: bool = False,
) -> str:
    if stale:
        return STALE_SIGNAL_STATE
    p20 = float(pension_net_20d or 0)
    f20 = float(foreign_net_20d or 0)
    if co_buy:
        return "co_buy"
    if co_sell:
        return "co_sell"
    if turning_buy:
        return "turning_buy"
    if turning_sell:
        return "turning_sell"
    if p20 > 0 and f20 >= 0:
        return "accumulation"
    if p20 < 0:
        return "distribution"
    return "neutral"


def apply_execution_gates(
    row: dict[str, Any],
    *,
    actual_buy_allowed: int,
    no_trade: bool,
    execution_scope: str | None = None,
) -> dict[str, Any]:
    """NO_TRADE / Actual Buy Allowed=0 → buy_permission false, review_only true."""
    out = dict(row)
    review_only = no_trade or str(execution_scope or "") == "NO_TRADE"
    out["review_only"] = review_only
    if actual_buy_allowed <= 0 or review_only:
        out["buy_permission"] = False
    elif "buy_permission" not in out:
        out["buy_permission"] = False
    if review_only:
        out.setdefault("allowed_actions", "Hold / Trim / Exit Review only")
        out["new_buy_allowed"] = False
    return out


def count_fresh_stale(records: list[dict[str, Any]]) -> dict[str, int]:
    stale = sum(1 for r in records if is_flow_record_stale(r))
    total = len(records)
    return {
        "fresh_flow_count": total - stale,
        "stale_flow_count": stale,
        "total_flow_count": total,
    }


def stale_warning_note(*, held: bool = False) -> str:
    if held:
        return "수급 데이터 stale — Trim/Buy Watch 판단 보류"
    return "수급 데이터 stale — warning only (LOW confidence)"


STALE_REASONS = frozenset({
    "source_missing",
    "pykrx_fetch_failed",
    "cache_too_old",
    "ticker_not_supported",
    "date_missing",
    "market_mismatch",
    "zero_or_null_flow",
    "parse_error",
    "flow_signal_stale",
    "fresh",
})


def classify_stale_reason(
    rec: dict[str, Any] | None,
    *,
    ticker: str = "",
    pykrx_failed: bool = False,
    parse_error: bool = False,
) -> str:
    """Classify why a flow row is stale (or fresh)."""
    if parse_error:
        return "parse_error"
    if pykrx_failed:
        return "pykrx_fetch_failed"
    if not rec:
        return "source_missing"
    src = str(rec.get("source") or "").strip().lower()
    if src in {"missing", "template", ""}:
        return "source_missing"
    if not str(rec.get("date") or "").strip():
        return "date_missing"
    if str(rec.get("flow_signal") or "") == STALE_FLOW_SIGNAL:
        if src == "cache_stale":
            return "cache_too_old"
        if pykrx_failed:
            return "pykrx_fetch_failed"
        return "flow_signal_stale"
    try:
        if int(rec.get("staleness_days") or 0) >= STALE_STALENESS_DAYS_THRESHOLD:
            return "cache_too_old"
    except (TypeError, ValueError):
        return "parse_error"
    f5 = rec.get("foreign_5d_sum")
    i5 = rec.get("institution_5d_sum")
    if f5 in (None, "", 0) and i5 in (None, "", 0):
        fd = rec.get("foreign_net_value")
        id_ = rec.get("institution_net_value")
        if fd in (None, "", 0) and id_ in (None, "", 0):
            return "zero_or_null_flow"
    if is_flow_record_stale(rec):
        return "flow_signal_stale"
    return "fresh"


def summarize_stale_reasons(reasons: list[str]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for r in reasons:
        summary[r] = summary.get(r, 0) + 1
    return dict(sorted(summary.items(), key=lambda x: -x[1]))

