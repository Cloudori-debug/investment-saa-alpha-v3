from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from src.screener import assign_grade


def _priority(action: str, rule_id: str, cfg: dict) -> str:
    pri = cfg.get("action_priority", {})
    if action == "Replace" and rule_id.startswith("H"):
        return "High"
    if rule_id in {"T03"} or rule_id.startswith("H"):
        return "High"
    if action in {"Trim", "Replace"} and rule_id.startswith(("S", "T")):
        return "Medium"
    if rule_id in pri.get("high", []):
        return "High"
    if rule_id in pri.get("medium", []):
        return "Medium"
    return "Low"


def _drawdown_from_high(row: pd.Series) -> float | None:
    close = row.get("close")
    high = row.get("high_52w")
    if close is None or high is None or pd.isna(close) or pd.isna(high) or float(high) <= 0:
        return None
    return (float(close) / float(high) - 1.0) * 100.0


def _check_hard(row: pd.Series, rule: dict[str, Any]) -> bool:
    check = rule.get("check")
    if check == "managed_or_halted":
        return bool(row.get("is_managed")) or bool(row.get("is_halted"))
    if check == "audit_not_unqualified":
        return str(row.get("audit_opinion", "unqualified")).lower() != "unqualified"
    if check == "consecutive_loss_2y":
        y1, y2 = row.get("net_income_y1"), row.get("net_income_y2")
        return y1 is not None and y2 is not None and float(y1) < 0 and float(y2) < 0
    if check == "debt_ratio_above_max":
        if bool(row.get("is_financial")):
            return False
        debt = row.get("debt_ratio")
        return debt is not None and not pd.isna(debt) and float(debt) > float(rule.get("debt_ratio_max", 200))
    if check == "grade_reject_streak":
        return str(row.get("grade")) == "Reject"
    if check == "fundamentals_not_verified":
        verified = row.get("verified")
        return str(verified).lower() not in {"true", "1", "yes"}
    if check == "governance_red_flag":
        return bool(row.get("governance_red"))
    if check == "satellite_momentum_collapse":
        if str(row.get("tier")) != "Satellite":
            return False
        sm = row.get("score_m")
        r6 = row.get("return_6m")
        if sm is None or r6 is None or pd.isna(sm) or pd.isna(r6):
            return False
        return float(sm) < float(rule.get("max_score_m", 40)) and float(r6) < float(rule.get("max_return_6m", -0.15))
    return False


def _check_soft(row: pd.Series, rule: dict[str, Any]) -> bool:
    if rule.get("enabled") is False:
        return False
    check = rule.get("check")
    if check == "composite_below":
        comp = float(row.get("composite_raw", row.get("composite_score", 0)))
        return comp < float(rule.get("threshold", 45))
    if check == "grade_streak":
        return str(row.get("grade")) == str(rule.get("grade", "C"))
    if check == "value_trap":
        return float(row.get("score_q", 0)) < float(rule.get("max_score_q", 40)) and float(
            row.get("score_v", 0)
        ) < float(rule.get("max_score_v", 35))
    if check == "overweight_vs_target":
        gap = row.get("weight_gap_pct")
        return gap is not None and not pd.isna(gap) and float(gap) > float(rule.get("threshold_pct", 5))
    if check == "core_to_satellite_weak":
        if str(row.get("tier")) != "Core":
            return False
        sm = row.get("score_m")
        return bool(row.get("satellite_track")) and sm is not None and float(sm) < float(rule.get("max_score_m", 55))
    if check == "role_downgrade_to_watch":
        return str(row.get("grade")) == "C"
    return False


def _check_tier(row: pd.Series, rule: dict[str, Any]) -> bool:
    if rule.get("enabled") is False:
        return False
    check = rule.get("check")
    if check == "score_m_below":
        sm = row.get("score_m")
        return sm is not None and not pd.isna(sm) and float(sm) < float(rule.get("threshold", 50))
    if check == "negative_return_6m_and_low_m":
        r6 = row.get("return_6m")
        sm = row.get("score_m")
        if r6 is None or sm is None or pd.isna(r6) or pd.isna(sm):
            return False
        return float(r6) < float(rule.get("max_return_6m", 0)) and float(sm) < float(rule.get("max_score_m", 55))
    if check == "momentum_satellite_drawdown":
        if str(row.get("role_suggested")) != str(rule.get("role", "momentum_satellite")):
            return False
        dd = _drawdown_from_high(row)
        return dd is not None and dd <= float(rule.get("drawdown_from_52w_high_pct", -20))
    if check == "grade_drop_with_low_composite":
        return float(row.get("composite_raw", 0)) < float(rule.get("max_composite_raw", 60))
    if check == "grade_to_c":
        return str(row.get("grade")) == str(rule.get("grade", "C"))
    if check == "hold_if_quality_ok":
        return float(row.get("score_q", 0)) >= float(rule.get("min_score_q", 50))
    return False


def _invalidate_incumbent(row: pd.Series, exit_type: str, action: str) -> pd.Series:
    out = row.copy()
    if exit_type in {"Soft", "Hard", "Park"} or action in {"Trim", "Replace", "Park"}:
        out["incumbent_bonus_applied"] = False
        out["composite_score"] = float(out.get("composite_raw", out.get("composite_score", 0)))
        out["grade"] = assign_grade(out, out.get("_scoring_cfg", {}), use_bonus=False)
    else:
        out["incumbent_bonus_applied"] = bool(float(out.get("incumbent_bonus", 0)) > 0)
    return out


def review_holding(
    row: pd.Series,
    exit_cfg: dict[str, Any],
    scoring_cfg: dict[str, Any],
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    as_of = as_of or date.today()
    row = row.copy()
    row["_scoring_cfg"] = scoring_cfg

    exit_type = "None"
    exit_rule_id = ""
    exit_reason = ""
    action = "Hold"
    matched: list[tuple[int, str, str, str]] = []

    for rule in exit_cfg.get("hard_exit", []):
        if _check_hard(row, rule):
            matched.append((0, rule["id"], rule.get("reason", ""), rule.get("action", "Replace")))

    for rule in exit_cfg.get("soft_exit", []):
        if _check_soft(row, rule):
            matched.append((1, rule["id"], rule.get("reason", ""), rule.get("action", "Trim")))

    tier_rules = exit_cfg.get("tier_exit", {})
    tier_key = "satellite" if str(row.get("tier")) == "Satellite" else "core"
    for rule in tier_rules.get(tier_key, []):
        if _check_tier(row, rule):
            matched.append((2, rule["id"], rule.get("reason", ""), rule.get("action", "Hold")))

    park_days = None
    park_start = row.get("park_start_date")
    park_review_due = None
    if park_start and not pd.isna(park_start):
        start = pd.to_datetime(park_start).date()
        park_days = (as_of - start).days
        max_days = int(exit_cfg.get("park", {}).get("max_days", 90))
        park_review_due = start.toordinal()
        park_review_due = date.fromordinal(start.toordinal() + max_days)
        if park_days >= max_days:
            matched.append((1, "P90", "park_max_days", "Replace"))
            exit_type = "Park"

    if matched:
        matched.sort(key=lambda x: x[0])
        _, exit_rule_id, exit_reason, action = matched[0]
        if exit_rule_id.startswith("H") or exit_rule_id.startswith("P90"):
            exit_type = "Hard" if exit_rule_id.startswith("H") else "Park"
        elif action in {"Trim", "Replace"}:
            exit_type = "Soft" if exit_type != "Park" else exit_type
        else:
            exit_type = "None" if action == "Hold" else "Soft"

    row = _invalidate_incumbent(row, exit_type, action)

    return {
        "ticker": row.get("ticker"),
        "name": row.get("name", ""),
        "role": row.get("role_suggested", ""),
        "tier": row.get("tier", ""),
        "composite_score": round(float(row.get("composite_score", 0)), 2),
        "composite_raw": round(float(row.get("composite_raw", 0)), 2),
        "grade": row.get("grade", ""),
        "exit_type": exit_type,
        "exit_rule_id": exit_rule_id,
        "exit_reason": exit_reason,
        "incumbent_bonus_applied": bool(row.get("incumbent_bonus_applied", False)),
        "park_start_date": park_start if park_start is not None else "",
        "park_days": park_days if park_days is not None else "",
        "park_review_due": park_review_due.isoformat() if park_review_due else "",
        "action_suggested": action if exit_type != "None" else "Hold",
        "action_priority": _priority(action, exit_rule_id, exit_cfg),
        "as_of": as_of.isoformat(),
    }


def run_exit_review(
    merged: pd.DataFrame,
    scores: pd.DataFrame,
    held: pd.DataFrame,
    exit_cfg: dict[str, Any],
    scoring_cfg: dict[str, Any],
    target: pd.DataFrame,
    *,
    all_positions: pd.DataFrame | None = None,
    as_of: date | None = None,
) -> pd.DataFrame:
    if held.empty:
        return pd.DataFrame()

    as_of = as_of or date.today()
    portfolio_base = all_positions if all_positions is not None and not all_positions.empty else held
    total_portfolio = float(portfolio_base["current_value"].sum()) if "current_value" in portfolio_base.columns else 0.0

    held = held.copy()
    if total_portfolio > 0 and "current_value" in held.columns:
        held["portfolio_weight"] = held["current_value"] / total_portfolio * 100.0
    else:
        held["portfolio_weight"] = 0.0

    target_map = {}
    if not target.empty and "target_weight" in target.columns:
        target_map = target.set_index("ticker")["target_weight"].to_dict()

    reviews: list[dict[str, Any]] = []
    for _, pos in held.iterrows():
        ticker = pos["ticker"]
        score_row = scores[scores["ticker"] == ticker]
        if score_row.empty:
            continue
        row = score_row.iloc[0].copy()
        fund = merged[merged["ticker"] == ticker]
        if not fund.empty:
            for col in fund.columns:
                if col not in row.index or pd.isna(row.get(col)):
                    row[col] = fund.iloc[0][col]

        tw = target_map.get(ticker)
        if tw is not None and not pd.isna(tw):
            row["weight_gap_pct"] = float(pos.get("portfolio_weight", 0)) - float(tw)
        else:
            row["weight_gap_pct"] = None

        reviews.append(
            review_holding(row, exit_cfg, scoring_cfg, as_of=as_of)
        )

    return pd.DataFrame(reviews)
