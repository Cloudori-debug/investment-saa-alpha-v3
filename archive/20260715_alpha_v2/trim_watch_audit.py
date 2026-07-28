from __future__ import annotations

from typing import Any

from src.models import PositionRow, TargetRow


TRIM_DETAIL_COLUMNS = [
    "ticker",
    "name",
    "market",
    "sector",
    "current_weight",
    "holding_flag",
    "target_flag",
    "trim_category",
    "grade_prev",
    "grade_current",
    "grade_change",
    "total_score_v1",
    "total_score_v2_shadow",
    "flow_confidence",
    "flow_data_stale",
    "pension_streak_direction",
    "pension_streak_days",
    "pension_net_buy_20d",
    "pension_foreign_co_sell",
    "turning_sell_signal",
    "profit_return",
    "loss_return",
    "trim_reason",
    "buy_permission",
    "review_only",
]


def _grade_change(grade_prev: str, grade_current: str) -> str:
    if not grade_prev or not grade_current or grade_prev == grade_current:
        return ""
    return f"{grade_prev}->{grade_current}"


def _weight_pct(positions: list[PositionRow], ticker: str) -> float:
    total = sum(float(p.current_value or 0) for p in positions if str(p.ticker).upper() != "CASH")
    if total <= 0:
        return 0.0
    for p in positions:
        if str(p.ticker).zfill(6) == ticker:
            return round(float(p.current_value or 0) / total * 100, 2)
    return 0.0


def build_trim_watch_detail_rows(
    trim_watch: list[dict[str, Any]],
    scored_by_ticker: dict[str, dict[str, Any]],
    *,
    positions: list[PositionRow],
    targets: list[TargetRow] | None,
    positions_meta: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    held = {
        str(p.ticker).zfill(6)
        for p in positions
        if float(p.quantity or 0) > 0 and str(p.ticker).upper() != "CASH"
    }
    target_tickers = {
        str(t.ticker).zfill(6)
        for t in (targets or [])
        if float(t.target_weight or 0) > 0
    }

    rows: list[dict[str, Any]] = []
    for entry in trim_watch:
        ticker = str(entry.get("ticker", "")).zfill(6)
        src = scored_by_ticker.get(ticker, {})
        grade_prev = str(src.get("grade_v1") or "")
        grade_current = str(entry.get("grade") or src.get("grade") or "")
        is_held = ticker in held
        is_target = ticker in target_tickers
        category = "held_or_target" if (is_held or is_target) else "informational"
        ret = positions_meta.get(ticker, {})
        reason = str(entry.get("reason") or "")
        if reason.startswith("trim review only — "):
            reason = reason.replace("trim review only — ", "", 1)

        rows.append({
            "ticker": ticker,
            "name": entry.get("name") or src.get("name", ""),
            "market": entry.get("market") or src.get("market", "KOSPI"),
            "sector": src.get("sector", ""),
            "current_weight": _weight_pct(positions, ticker),
            "holding_flag": is_held,
            "target_flag": is_target,
            "trim_category": category,
            "grade_prev": grade_prev,
            "grade_current": grade_current,
            "grade_change": _grade_change(grade_prev, grade_current),
            "total_score_v1": src.get("total_score_v1"),
            "total_score_v2_shadow": src.get("total_score_v2_shadow"),
            "flow_confidence": entry.get("flow_confidence") or src.get("flow_confidence", "LOW"),
            "flow_data_stale": bool(src.get("flow_data_stale")),
            "pension_streak_direction": src.get("pension_streak_direction", ""),
            "pension_streak_days": src.get("pension_streak_days", 0),
            "pension_net_buy_20d": src.get("pension_net_buy_20d"),
            "pension_foreign_co_sell": src.get("pension_foreign_co_sell", False),
            "turning_sell_signal": src.get("turning_sell_signal", False),
            "profit_return": ret.get("profit_return"),
            "loss_return": ret.get("loss_return"),
            "trim_reason": reason,
            "buy_permission": entry.get("buy_permission", False),
            "review_only": entry.get("review_only", True),
        })
    return rows


def validate_trim_watch_detail(rows: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    stale_in_trim = [r["ticker"] for r in rows if r.get("flow_data_stale")]
    if stale_in_trim:
        failures.append(f"stale_in_trim_watch:{','.join(stale_in_trim)}")

    valid_tokens = (
        "pension_sell_streak",
        "pension_net_buy_20d",
        "pension_foreign_co_sell",
        "turning_sell",
        "grade_downgrade",
        "profit>=",
        "loss<=",
    )
    for r in rows:
        reason = str(r.get("trim_reason") or "")
        gc = str(r.get("grade_change") or "")
        if not reason:
            failures.append(f"missing_trim_reason:{r.get('ticker')}")
            continue
        if not gc and not any(tok in reason for tok in valid_tokens):
            failures.append(f"grade_only_or_invalid_trim:{r.get('ticker')}")

    held_count = sum(1 for r in rows if r.get("trim_category") == "held_or_target")
    info_count = sum(1 for r in rows if r.get("trim_category") == "informational")

    return {
        "passed": len(failures) == 0,
        "failures": failures,
        "trim_watch_total": len(rows),
        "trim_watch_held_or_target": held_count,
        "trim_watch_informational": info_count,
    }
