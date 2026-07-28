from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class TargetMatrixResult:
    draft: pd.DataFrame
    changes: pd.DataFrame
    replace_pairs: pd.DataFrame
    warnings: list[str]


def _tier_band(tier: str, cfg: dict) -> dict:
    bands = cfg.get("bands", {})
    key = "satellite" if str(tier).lower() == "satellite" else "core"
    if key not in bands:
        key = "default"
    return bands.get(key, bands.get("default", {}))


def sleeve_to_portfolio(sleeve_pct: float, kr_alpha_weight: float) -> float:
    return round(sleeve_pct * kr_alpha_weight / 100.0, 2)


def portfolio_to_sleeve(portfolio_pct: float, kr_alpha_weight: float) -> float:
    if kr_alpha_weight <= 0:
        return 0.0
    return round(portfolio_pct * 100.0 / kr_alpha_weight, 2)


def compute_bands(
    target_weight: float,
    tier: str,
    cfg: dict,
    kr_alpha_weight: float,
) -> tuple[float, float]:
    band = _tier_band(tier, cfg)
    min_w = round(target_weight * float(band.get("min_weight_ratio", 0.5)), 2)
    max_w = round(target_weight * float(band.get("max_weight_ratio", 1.5)), 2)
    portfolio_max = float(band.get("portfolio_max", 8.0))
    if str(tier) == "Satellite":
        single_sleeve = float(cfg.get("satellite_cap", {}).get("single_name_sleeve_pct", 5))
        portfolio_max = min(portfolio_max, sleeve_to_portfolio(single_sleeve, kr_alpha_weight))
    max_w = min(max_w, portfolio_max)
    if min_w > max_w:
        min_w = max_w
    return min_w, max_w


def _row_from_score(row: pd.Series, kr_alpha_weight: float, cfg: dict, *, action: str, reason: str) -> dict:
    tier = str(row.get("tier", "Core"))
    sleeve = float(row.get("sleeve_weight_suggested", 0) or 0)
    if sleeve <= 0:
        band = _tier_band(tier, cfg)
        sleeve = float(band.get("default_sleeve_pct", 4.0))
    target = float(row.get("portfolio_weight_suggested", 0) or 0)
    if target <= 0:
        target = sleeve_to_portfolio(sleeve, kr_alpha_weight)
    min_w, max_w = compute_bands(target, tier, cfg, kr_alpha_weight)
    return {
        "ticker": row["ticker"],
        "name": row.get("name", ""),
        "asset_group": "kr_alpha",
        "sector": row.get("sector", ""),
        "role": row.get("role_suggested", row.get("role", "")),
        "tier": tier,
        "target_weight": target,
        "min_weight": min_w,
        "max_weight": max_w,
        "sleeve_weight": portfolio_to_sleeve(target, kr_alpha_weight),
        "matrix_action": action,
        "change_reason": reason,
    }


def _pick_replacement(
    exit_row: pd.Series,
    candidates: pd.DataFrame,
    used: set[str],
    cfg: dict,
) -> pd.Series | None:
    if candidates.empty:
        return None
    rep = cfg.get("replace", {})
    min_grade = rep.get("min_grade", "B")
    grade_order = {"A": 2, "B": 1, "C": 0}
    min_rank = grade_order.get(str(min_grade), 1)

    pool = candidates.copy()
    pool = pool[~pool["ticker"].isin(used)]
    pool = pool[pool["grade"].map(lambda g: grade_order.get(str(g), 0) >= min_rank)]
    if pool.empty:
        return None

    exit_sector = str(exit_row.get("sector", ""))
    if rep.get("prefer_different_sector", True) and exit_sector:
        diff = pool[pool["sector"] != exit_sector]
        if not diff.empty:
            pool = diff

    pool = pool.sort_values("rank" if "rank" in pool.columns else "composite_score", ascending=[True] if "rank" in pool.columns else False)
    return pool.iloc[0]


def build_target_draft(
    current_target: pd.DataFrame,
    scores: pd.DataFrame,
    candidates: pd.DataFrame,
    exit_review: pd.DataFrame,
    cfg: dict[str, Any],
    *,
    kr_alpha_weight: float,
) -> TargetMatrixResult:
    warnings: list[str] = []
    changes: list[dict] = []
    pairs: list[dict] = []

    if kr_alpha_weight <= 0:
        raise ValueError("kr_alpha_weight must be > 0")

    # Base matrix: current target + held (scores) union
    frames: list[pd.DataFrame] = []
    if not current_target.empty:
        frames.append(current_target.copy())
    held_scores = scores[scores["is_held"] == True] if "is_held" in scores.columns else pd.DataFrame()  # noqa: E712
    if not held_scores.empty:
        hs = held_scores[["ticker", "name", "sector", "role_suggested", "tier", "portfolio_weight_suggested", "sleeve_weight_suggested"]].copy()
        hs = hs.rename(columns={"role_suggested": "role"})
        hs["target_weight"] = hs["portfolio_weight_suggested"].fillna(0)
        hs["min_weight"] = 0.0
        hs["max_weight"] = 0.0
        frames.append(hs)
    if frames:
        base = pd.concat(frames, ignore_index=True)
        base["ticker"] = base["ticker"].astype(str).str.zfill(6)
        base = base.sort_values("target_weight", ascending=False).drop_duplicates(subset=["ticker"], keep="first")
    else:
        base = pd.DataFrame()
    score_map = scores.set_index("ticker") if not scores.empty else pd.DataFrame()

    rows: dict[str, dict] = {}
    for _, r in base.iterrows():
        t = str(r["ticker"]).zfill(6)
        tier = str(r.get("tier", "Core"))
        if tier in {"nan", "None", "", "—", "-"}:
            tier = "Core"
        role = r.get("role", r.get("role_suggested", ""))
        sector = r.get("sector", "")
        if t in score_map.index:
            sr = score_map.loc[t]
            tier = str(sr.get("tier", tier))
            role = role or str(sr.get("role_suggested", ""))
            sector = sector or str(sr.get("sector", ""))
        tw = float(r.get("target_weight", 0) or 0)
        if tw <= 0 and t in score_map.index:
            tw = float(score_map.loc[t].get("portfolio_weight_suggested", 0) or 0)
        min_w, max_w = compute_bands(tw if tw > 0 else sleeve_to_portfolio(4.0, kr_alpha_weight), tier, cfg, kr_alpha_weight)
        rows[t] = {
            "ticker": t,
            "name": r.get("name", score_map.loc[t].get("name", "") if t in score_map.index else ""),
            "asset_group": "kr_alpha",
            "sector": sector,
            "role": role,
            "tier": tier,
            "target_weight": tw,
            "min_weight": float(r.get("min_weight", min_w) or min_w),
            "max_weight": float(r.get("max_weight", max_w) or max_w),
            "sleeve_weight": portfolio_to_sleeve(tw, kr_alpha_weight),
            "matrix_action": "keep",
            "change_reason": "",
        }

    used_candidates: set[str] = set()
    max_pairs = int(cfg.get("replace", {}).get("max_pairs_per_run", 5))
    pair_count = 0

    if not exit_review.empty:
        for _, ex in exit_review.iterrows():
            t = str(ex["ticker"]).zfill(6)
            action = str(ex.get("action_suggested", "Hold"))

            if t not in rows and action in {"Replace", "Trim"}:
                sr = score_map.loc[t] if t in score_map.index else ex
                tw = float(sr.get("portfolio_weight_suggested", 0) or 0) if isinstance(sr, pd.Series) else 0.0
                rows[t] = {
                    "ticker": t,
                    "name": ex.get("name", ""),
                    "asset_group": "kr_alpha",
                    "sector": sr.get("sector", "") if isinstance(sr, pd.Series) else "",
                    "role": ex.get("role", ""),
                    "tier": ex.get("tier", "-"),
                    "target_weight": tw,
                    "min_weight": 0.0,
                    "max_weight": 0.0,
                    "sleeve_weight": portfolio_to_sleeve(tw, kr_alpha_weight),
                    "matrix_action": "keep",
                    "change_reason": "",
                }

            if t not in rows:
                continue
            old = float(rows[t]["target_weight"])

            if action == "Replace" and pair_count < max_pairs:
                rows[t]["target_weight"] = 0.0
                rows[t]["matrix_action"] = "remove"
                rows[t]["change_reason"] = f"{ex.get('exit_rule_id', '')} {ex.get('exit_reason', '')}".strip()
                changes.append({
                    "ticker": t,
                    "action": "remove",
                    "old_weight": old,
                    "new_weight": 0.0,
                    "reason": rows[t]["change_reason"],
                    "paired_with": "",
                })

                score_row = score_map.loc[t] if t in score_map.index else ex
                score_row = pd.Series({**score_row.to_dict(), "sector": rows[t].get("sector", score_row.get("sector", ""))})
                cand = _pick_replacement(score_row, candidates, used_candidates, cfg)
                if cand is not None:
                    ct = str(cand["ticker"]).zfill(6)
                    new_row = _row_from_score(cand, kr_alpha_weight, cfg, action="add", reason=f"replace_in for {t}")
                    if ct in rows and float(rows[ct].get("target_weight", 0)) > 0:
                        rows[ct]["target_weight"] = max(float(rows[ct]["target_weight"]), float(new_row["target_weight"]))
                        rows[ct]["matrix_action"] = "add"
                        rows[ct]["change_reason"] = new_row["change_reason"]
                        rows[ct]["role"] = new_row["role"]
                        rows[ct]["tier"] = new_row["tier"]
                    else:
                        rows[ct] = new_row
                    used_candidates.add(ct)
                    pair_count += 1
                    pairs.append({
                        "exit_ticker": t,
                        "exit_name": rows[t]["name"],
                        "candidate_ticker": ct,
                        "candidate_name": new_row["name"],
                        "rank": int(cand.get("rank", 0)),
                        "reason": new_row["change_reason"],
                    })
                    changes.append({
                        "ticker": ct,
                        "action": "add",
                        "old_weight": 0.0,
                        "new_weight": new_row["target_weight"],
                        "reason": f"replace {t}",
                        "paired_with": t,
                    })
                else:
                    warnings.append(f"Replace {t}: 후보 없음")

            elif action == "Trim":
                floor = float(rows[t]["min_weight"])
                if cfg.get("trim", {}).get("floor_to_min", True):
                    new_w = max(floor, old * float(cfg.get("trim", {}).get("ratio_of_current", 0.7)))
                else:
                    new_w = old * float(cfg.get("trim", {}).get("ratio_of_current", 0.7))
                new_w = round(new_w, 2)
                rows[t]["target_weight"] = new_w
                rows[t]["matrix_action"] = "trim"
                rows[t]["change_reason"] = str(ex.get("exit_reason", "trim"))
                rows[t]["sleeve_weight"] = portfolio_to_sleeve(new_w, kr_alpha_weight)
                changes.append({"ticker": t, "action": "trim", "old_weight": old, "new_weight": new_w, "reason": rows[t]["change_reason"], "paired_with": ""})

    # Active rows with positive weight
    draft_rows = [r for r in rows.values() if float(r["target_weight"]) > 0]

    # Normalize to kr_alpha_weight
    if cfg.get("normalize", {}).get("enabled", True) and draft_rows:
        total = sum(float(r["target_weight"]) for r in draft_rows)
        if total > 0 and abs(total - kr_alpha_weight) > float(cfg.get("normalize", {}).get("tolerance_pct", 0.5)):
            scale = kr_alpha_weight / total
            for r in draft_rows:
                old = float(r["target_weight"])
                r["target_weight"] = round(old * scale, 2)
                r["min_weight"] = round(float(r["min_weight"]) * scale, 2)
                r["max_weight"] = round(float(r["max_weight"]) * scale, 2)
                r["sleeve_weight"] = portfolio_to_sleeve(r["target_weight"], kr_alpha_weight)
            warnings.append(f"normalized {total:.2f}% -> {kr_alpha_weight:.2f}%")

    # Satellite cap check
    sat_sleeve = sum(float(r["sleeve_weight"]) for r in draft_rows if r.get("tier") == "Satellite")
    cap = float(cfg.get("satellite_cap", {}).get("sleeve_max_pct", 25))
    if sat_sleeve > cap:
        warnings.append(f"Satellite sleeve {sat_sleeve:.1f}% > cap {cap}%")

    draft = pd.DataFrame(draft_rows)
    if not draft.empty:
        draft = draft.sort_values("target_weight", ascending=False)

    return TargetMatrixResult(
        draft=draft,
        changes=pd.DataFrame(changes),
        replace_pairs=pd.DataFrame(pairs),
        warnings=warnings,
    )
