from __future__ import annotations

from typing import Any

import pandas as pd

from src.factors import score_momentum, score_quality, score_risk, score_shareholder, score_value
from src.gate import run_gate


def _composite(weights: dict[str, float], scores: dict[str, float]) -> float:
    total = sum(weights[k] * scores[k] for k in weights)
    return round(total, 2)


def satellite_track_eligible(row: pd.Series, cfg: dict[str, Any]) -> bool:
    m_cfg = cfg.get("momentum", {})
    score_m = float(row.get("score_m", 0))
    ret6 = row.get("return_6m")
    if ret6 is None or pd.isna(ret6):
        return False
    return score_m >= float(m_cfg.get("satellite_min_score", 60)) and float(ret6) > float(
        m_cfg.get("satellite_min_return_6m", 0)
    )


def assign_grade(row: pd.Series, cfg: dict[str, Any], *, use_bonus: bool = True) -> str:
    g_cfg = cfg.get("grades", {})
    demotion = cfg.get("demotion", {})
    composite = float(row["composite_raw"] if not use_bonus else row["composite_score"])
    q = float(row["score_q"])
    v = float(row["score_v"])

    if not bool(row.get("gate_pass", False)) or row.get("data_gate") == "RED":
        return "Reject"

    grade = "Reject"
    a_cfg = g_cfg.get("A", {})
    if composite >= float(a_cfg.get("min_composite", 70)) and q >= float(a_cfg.get("min_q", 55)) and v >= float(
        a_cfg.get("min_v", 50)
    ):
        grade = "A"
    elif composite >= float(g_cfg.get("B", {}).get("min_composite", 55)):
        if bool(row.get("satellite_track")):
            if float(row.get("score_m", 0)) >= float(g_cfg.get("B", {}).get("satellite_min_m", 60)):
                grade = "B"
            else:
                grade = "C"
        else:
            grade = "B"
    elif composite >= float(g_cfg.get("C", {}).get("min_composite", 45)):
        grade = "C"

    if q < float(demotion.get("q_floor", 40)):
        grade = {"A": "B", "B": "C"}.get(grade, grade)
    if v < float(demotion.get("value_trap_v", 35)) and q < float(demotion.get("value_trap_q", 50)):
        grade = {"A": "B", "B": "C", "C": "C"}.get(grade, grade)

    return grade


def assign_role(row: pd.Series, cfg: dict[str, Any]) -> str:
    rules = cfg.get("role_rules", [])
    sector = str(row.get("sector", ""))
    tier = str(row.get("tier", ""))
    scores = {
        "q": float(row.get("score_q", 0)),
        "v": float(row.get("score_v", 0)),
        "sr": float(row.get("score_sr", 0)),
        "m": float(row.get("score_m", 0)),
    }
    div = row.get("dividend_yield")
    div_val = float(div) if div is not None and not pd.isna(div) else 0.0
    opm = row.get("opm")
    sector_df = row.get("_sector_opm_median")
    opm_above = sector_df is not None and opm is not None and not pd.isna(opm) and float(opm) >= float(sector_df)

    for rule in rules:
        if rule.get("default"):
            return str(rule["role"])
        if rule.get("tier") == "Satellite" and tier != "Satellite":
            continue
        if rule.get("min_m") and scores["m"] < float(rule["min_m"]):
            continue
        min_r6 = rule.get("min_return_6m")
        if min_r6 is not None:
            r6 = row.get("return_6m")
            if r6 is None or pd.isna(r6) or float(r6) < float(min_r6):
                continue
        if rule.get("sectors") and sector not in rule.get("sectors", []):
            continue
        if rule.get("min_sr") and scores["sr"] < float(rule["min_sr"]):
            continue
        if rule.get("min_q") and scores["q"] < float(rule["min_q"]):
            continue
        if rule.get("min_v") and scores["v"] < float(rule["min_v"]):
            continue
        if rule.get("min_dividend_yield") and div_val < float(rule["min_dividend_yield"]):
            continue
        if rule.get("require_holding") and not bool(row.get("is_holding")):
            continue
        if rule.get("require_opm_above_sector_median") and not opm_above:
            continue
        return str(rule["role"])
    return "value_quality"


def assign_tier(grade: str, satellite_track: bool) -> str:
    if grade in {"C", "Reject"}:
        return "—"
    if satellite_track and grade in {"A", "B"}:
        return "Satellite"
    if grade == "A" or (grade == "B" and not satellite_track):
        return "Core"
    return "—"


def suggest_sleeve_weight(row: pd.Series, cfg: dict[str, Any]) -> float:
    sw = cfg.get("sleeve_weight", {})
    composite = float(row["composite_score"])
    tier = row.get("tier")
    if tier == "Satellite":
        s = sw.get("satellite", {})
        base = float(s.get("base", 3.0))
        scale = float(s.get("composite_scale", 2.0))
        ref = float(s.get("composite_ref", 55))
        cap = float(s.get("max", 5.0))
    else:
        s = sw.get("core", {})
        base = float(s.get("base", 4.0))
        scale = float(s.get("composite_scale", 2.0))
        ref = float(s.get("composite_ref", 70))
        cap = float(s.get("max", 8.0))
    extra = max(0.0, (composite - ref) / max(1.0, 100 - ref) * scale)
    return round(min(base + extra, cap), 2)


def build_merged_frame(
    fundamentals: pd.DataFrame,
    price_snapshot: pd.DataFrame,
    shareholder: pd.DataFrame,
    held_tickers: set[str],
) -> pd.DataFrame:
    df = fundamentals.copy()
    if not price_snapshot.empty:
        px = price_snapshot.copy()
        if "ticker" in px.columns:
            px["ticker"] = px["ticker"].astype(str).str.zfill(6)
        price_cols = [c for c in px.columns if c not in {"as_of"}]
        df = df.merge(px[price_cols], on="ticker", how="left", suffixes=("", "_px"))
    if not shareholder.empty:
        sh_cols = [c for c in shareholder.columns if c not in {"ticker", "as_of"}]
        df = df.merge(shareholder[["ticker", *sh_cols]], on="ticker", how="left", suffixes=("", "_sh"))
    df["is_held"] = df["ticker"].isin(held_tickers)
    if "name_px" in df.columns and "name" not in df.columns:
        df["name"] = df["name_px"]
    return df


def run_screener(
    df: pd.DataFrame,
    gate_cfg: dict[str, Any],
    scoring_cfg: dict[str, Any],
    *,
    kr_alpha_weight: float | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    gated = run_gate(df, gate_cfg) if "gate_pass" not in df.columns else df.copy()

    work = gated.copy()
    work["score_q"] = work.apply(lambda r: score_quality(r, work, scoring_cfg), axis=1).round(2)
    work["score_v"] = work.apply(lambda r: score_value(r, work, scoring_cfg), axis=1).round(2)

    sr_scores: list[float] = []
    sr_gates: list[str] = []
    for _, row in work.iterrows():
        sr, gate = score_shareholder(row, scoring_cfg)
        sr_scores.append(round(sr, 2))
        sr_gates.append(gate)
    work["score_sr"] = sr_scores
    work["score_r"] = work.apply(lambda r: score_risk(r, scoring_cfg), axis=1).round(2)
    work["score_m"] = work.apply(lambda r: score_momentum(r, work, scoring_cfg), axis=1).round(2)

    work["_sector_opm_median"] = work.groupby("sector")["opm"].transform("median")

    cw = scoring_cfg.get("composite_weights", {})
    core_w = cw.get("core", {})
    sat_w = cw.get("satellite", {})

    composites_core: list[float] = []
    composites_sat: list[float] = []
    satellite_flags: list[bool] = []
    for _, row in work.iterrows():
        scores = {
            "q": row["score_q"],
            "v": row["score_v"],
            "sr": row["score_sr"],
            "r": row["score_r"],
            "m": row["score_m"],
        }
        cc = _composite(core_w, scores)
        cs = _composite(sat_w, scores)
        composites_core.append(cc)
        composites_sat.append(cs)
        satellite_flags.append(satellite_track_eligible(row, scoring_cfg))

    work["satellite_track"] = satellite_flags
    work["composite_core"] = composites_core
    work["composite_satellite"] = composites_sat
    work["composite_raw"] = [
        cs if st and cs >= cc else cc for cc, cs, st in zip(composites_core, composites_sat, satellite_flags, strict=True)
    ]
    bonus = float(scoring_cfg.get("incumbent_bonus", 3))
    work["incumbent_bonus"] = work["is_held"].map(lambda h: bonus if h else 0.0)
    work["composite_score"] = (work["composite_raw"] + work["incumbent_bonus"]).clip(upper=100).round(2)

    work["data_gate"] = "GREEN"
    for idx, row in work.iterrows():
        if not bool(row.get("gate_pass")):
            work.at[idx, "data_gate"] = "RED"
        elif str(row.get("verified", "")).strip().lower() == "stub":
            work.at[idx, "data_gate"] = "YELLOW"
        elif sr_gates[work.index.get_loc(idx)] == "YELLOW" or pd.isna(row.get("dividend_yield")):
            work.at[idx, "data_gate"] = "YELLOW"

    work["grade"] = work.apply(lambda r: assign_grade(r, scoring_cfg), axis=1)
    work["tier"] = [
        assign_tier(g, st) for g, st in zip(work["grade"], work["satellite_track"], strict=True)
    ]
    work["role_suggested"] = work.apply(lambda r: assign_role(r, scoring_cfg), axis=1)
    work["sleeve_weight_suggested"] = work.apply(lambda r: suggest_sleeve_weight(r, scoring_cfg), axis=1)

    if kr_alpha_weight is not None:
        work["portfolio_weight_suggested"] = (
            work["sleeve_weight_suggested"] * float(kr_alpha_weight) / 100.0
        ).round(2)
    else:
        work["portfolio_weight_suggested"] = None

    score_cols = [
        "ticker", "name", "sector", "gate_pass", "gate_fail_reason",
        "score_q", "score_v", "score_sr", "score_r", "score_m",
        "composite_raw", "composite_score", "incumbent_bonus",
        "grade", "role_suggested", "tier", "satellite_track",
        "is_held", "data_gate", "sleeve_weight_suggested", "portfolio_weight_suggested",
    ]
    scores_df = work[[c for c in score_cols if c in work.columns]].copy()
    if "as_of" in work.columns:
        scores_df["as_of"] = work["as_of"]

    candidates = scores_df[scores_df["grade"].isin(["A", "B"])].copy()
    candidates = candidates.sort_values("composite_score", ascending=False)
    candidates["rank"] = range(1, len(candidates) + 1)
    candidates["reason"] = candidates.apply(
        lambda r: f"Q{ r['score_q']:.0f} V{ r['score_v']:.0f} SR{ r['score_sr']:.0f} tier={r['tier']}",
        axis=1,
    )

    cap = scoring_cfg.get("sector_caps", {})
    max_per = int(cap.get("max_candidates_per_sector", 5))
    if max_per and not candidates.empty:
        candidates = (
            candidates.sort_values(["sector", "composite_score"], ascending=[True, False])
            .groupby("sector", group_keys=False)
            .head(max_per)
            .sort_values("rank")
        )

    return scores_df, candidates
