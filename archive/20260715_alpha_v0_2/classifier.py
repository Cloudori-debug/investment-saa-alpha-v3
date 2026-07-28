from __future__ import annotations

from typing import Any

from src.alpha_v0_2.schemas import Classification, NewBuyStatus, ScoredRow


def classify_row(
    row: ScoredRow,
    *,
    portfolio_new_buy_allowed: bool,
    cfg: dict[str, Any],
) -> ScoredRow:
    bands = cfg.get("score_bands", {})
    core_min = float(bands.get("core_min", 80))
    active_min = float(bands.get("active_min", 70))
    candidate_min = float(bands.get("candidate_min", 60))
    watch_min = float(bands.get("watch_min", 50))

    if not row.exclusion_pass:
        row.classification = "Excluded"
        row.new_buy_status = "forbidden"
        row.reason = "exclusion_fail"
        return row

    if not row.quality_pass:
        if row.in_portfolio:
            row.classification = "Legacy"
            row.reason = "held_not_new_buy_eligible"
        else:
            row.classification = "Excluded"
            row.reason = "quality_fail"
        row.new_buy_status = "forbidden"
        return row

    if not row.momentum_pass:
        if row.in_portfolio:
            if (row.rel_return_90d or 0) < -5 and (row.rel_return_120d or 0) < -5:
                row.classification = "Exit"
                row.reason = "momentum_fail_exit_review"
            else:
                row.classification = "Legacy"
                row.reason = "momentum_fail_legacy"
        else:
            row.classification = "Watch" if row.total_score >= watch_min else "Excluded"
            row.reason = "momentum_fail_no_new_buy"
        row.new_buy_status = "forbidden"
        return row

    if row.total_score >= core_min and row.catalyst_score >= 40:
        row.classification = "Core"
        row.reason = "quality_value_momentum_catalyst"
    elif row.total_score >= active_min:
        row.classification = "Active"
        row.reason = "active_candidate"
    elif row.total_score >= candidate_min:
        row.classification = "Candidate"
        row.reason = "candidate_watchlist"
    elif row.total_score >= watch_min:
        row.classification = "Watch"
        row.reason = "watch_only"
    elif row.in_portfolio:
        row.classification = "Legacy"
        row.reason = "low_score_held"
    else:
        row.classification = "Excluded"
        row.reason = "score_below_watch"

    if row.classification in {"Legacy", "Exit", "Excluded", "Watch"}:
        row.new_buy_status = "forbidden"
    elif row.classification == "Candidate":
        row.new_buy_status = "research_only"
    elif row.classification in {"Core", "Active"}:
        if portfolio_new_buy_allowed and row.current_weight_pct < float(
            cfg.get("risk_budget", {}).get("single_name_core_max_pct", 5)
        ):
            row.new_buy_status = "allowed_if_budget"
        else:
            row.new_buy_status = "research_only"
            if not portfolio_new_buy_allowed:
                row.reason += "; alpha_overweight"
    else:
        row.new_buy_status = "forbidden"

    if row.classification == "Exit":
        row.new_buy_status = "forbidden"

    return row


def legacy_classification_label(grade: str, action: str = "") -> str:
    g = (grade or "").upper()
    if g == "A":
        return "Hold/Core"
    if g == "B":
        return "Watch"
    if g in {"C", "REJECT"}:
        return "Replace"
    return action or "—"
