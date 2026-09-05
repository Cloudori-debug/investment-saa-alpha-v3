"""Score engine: eligibility (absolute cutoff) + weight_input (sizing input)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from alpha_system.schema import AlphaSystemConfig, ConfigTodoError
from alpha_system.scoring.cecs import CatalystInputs, calculate_cecs
from alpha_system.scoring.factors import FIVE_FACTORS, load_scoring_config


@dataclass
class NameScore:
    ticker: str
    name: str
    factors: dict[str, float]
    total_score: float
    # None when score_cutoff is [TODO] — never invent a default cutoff
    eligibility: Optional[bool]
    weight_input: float
    eligibility_reason: str
    cecs_subs: dict[str, float] = field(default_factory=dict)
    # Normalized sector key for concentration cap (= sector_group). Empty → per-ticker bucket.
    sector: str = ""


def _rollup_factor_score(row: dict[str, Any], weights: dict[str, float]) -> float:
    total_w = 0.0
    acc = 0.0
    for key, w in weights.items():
        val = row.get(key)
        if val is None:
            continue
        acc += float(val) * float(w)
        total_w += float(w)
    if total_w <= 0:
        return 0.0
    return round(acc / total_w, 4)


def _blend_total(
    factor_score_total: float,
    cecs: float,
    blend: dict[str, float],
) -> float:
    w_f = float(blend.get("factor_score_total", 1.0))
    w_c = float(blend.get("cecs", 0.0))
    denom = w_f + w_c
    if denom <= 0:
        return factor_score_total
    return round((factor_score_total * w_f + cecs * w_c) / denom, 4)


def _quality_gate(
    *,
    score_q: Optional[float],
    quality_inputs_ok: Optional[bool],
    min_q: Optional[float],
) -> Optional[str]:
    """Return a fail reason, or None if quality does not block eligibility."""
    if quality_inputs_ok is False:
        return "품질 재료 없음 — 판정 불가"
    if min_q is None or score_q is None:
        return None
    if float(score_q) < float(min_q):
        return f"품질 하한 미달: score_q={score_q} < {min_q}"
    return None


def quality_inputs_present(*, roe: Any = None, roe_3y_avg: Any = None) -> bool:
    """True when a numeric ROE exists (quality can be judged)."""
    for val in (roe_3y_avg, roe):
        if val is None:
            continue
        if isinstance(val, float) and pd.isna(val):
            continue
        text = str(val).strip()
        if not text or text.lower() in {"nan", "none"}:
            continue
        try:
            float(text)
        except (TypeError, ValueError):
            continue
        return True
    return False


def _cutoff_eligibility(
    *,
    total: float,
    cutoff: Optional[float],
    score_q: Optional[float],
    quality_inputs_ok: Optional[bool],
    min_q: Optional[float],
    reason_ok: str,
    reason_low: str,
) -> tuple[Optional[bool], str, float]:
    blocked = _quality_gate(
        score_q=score_q, quality_inputs_ok=quality_inputs_ok, min_q=min_q
    )
    if blocked:
        return False, blocked, 0.0
    if cutoff is None:
        return (
            None,
            "score_cutoff [TODO] unset — eligibility not decided (no silent default)",
            total,
        )
    if total >= float(cutoff):
        return True, reason_ok, total
    return False, reason_low, 0.0


def score_name(
    *,
    ticker: str,
    name: str = "",
    score_q: Optional[float] = None,
    score_v: Optional[float] = None,
    score_sr: Optional[float] = None,
    score_r: Optional[float] = None,
    score_m: Optional[float] = None,
    factor_score_total: Optional[float] = None,
    cecs_inputs: Optional[CatalystInputs] = None,
    cecs: Optional[float] = None,
    quality_inputs_ok: Optional[bool] = None,
    system_cfg: AlphaSystemConfig,
    scoring_cfg: dict[str, Any] | None = None,
) -> NameScore:
    """
    Build dual outputs:
      - eligibility: absolute cutoff vs config score_cutoff (None if TODO)
      - weight_input: total_score if eligible is True; 0 if False; total_score if cutoff TODO
        (sizing module must still refuse when cutoff unset)
    """
    scfg = scoring_cfg or load_scoring_config()
    row = {
        "score_q": score_q,
        "score_v": score_v,
        "score_sr": score_sr,
        "score_r": score_r,
        "score_m": score_m,
    }

    if factor_score_total is None:
        factor_score_total = _rollup_factor_score(
            {k: v for k, v in row.items() if v is not None},
            dict(scfg.get("factor_score_weights") or {}),
        )

    cecs_subs: dict[str, float] = {}
    blend = dict(scfg.get("total_score_blend") or {})
    cecs_blend_w = float(blend.get("cecs", 0.0) or 0.0)
    if cecs is None and cecs_inputs is None and cecs_blend_w > 1e-12:
        # CECS still in the blend: do not invent a silent 0.5.
        factors = {
            "score_q": float(score_q) if score_q is not None else float("nan"),
            "score_v": float(score_v) if score_v is not None else float("nan"),
            "score_sr": float(score_sr) if score_sr is not None else float("nan"),
            "score_r": float(score_r) if score_r is not None else float("nan"),
            "cecs": float("nan"),
            "factor_score_total": float(factor_score_total),
        }
        provisional = round(float(factor_score_total), 4)
        return NameScore(
            ticker=ticker,
            name=name,
            factors=factors,
            total_score=provisional,
            eligibility=None,
            weight_input=provisional,
            eligibility_reason=(
                "CECS unscored — eligibility not decided (no silent default)"
            ),
            cecs_subs=cecs_subs,
        )
    if cecs is None and cecs_inputs is None:
        # Ops A: CECS weight 0 — rank from factors only; cutoff still applies.
        total = round(float(factor_score_total), 4)
        factors = {
            "score_q": float(score_q) if score_q is not None else float("nan"),
            "score_v": float(score_v) if score_v is not None else float("nan"),
            "score_sr": float(score_sr) if score_sr is not None else float("nan"),
            "score_r": float(score_r) if score_r is not None else float("nan"),
            "cecs": float("nan"),
            "factor_score_total": float(factor_score_total),
        }
        cutoff = system_cfg.scoring.score_cutoff
        min_q = getattr(system_cfg.scoring, "quality_min_score", None)
        eligibility, reason, weight_input = _cutoff_eligibility(
            total=total,
            cutoff=cutoff,
            score_q=score_q,
            quality_inputs_ok=quality_inputs_ok,
            min_q=min_q,
            reason_ok=(
                f"eligible: total_score={total} >= cutoff={cutoff} (Ops A, CECS 미반영)"
            ),
            reason_low=(
                f"ineligible: total_score={total} < cutoff={cutoff} (Ops A, CECS 미반영)"
            ),
        )
        return NameScore(
            ticker=ticker,
            name=name,
            factors=factors,
            total_score=total,
            eligibility=eligibility,
            weight_input=weight_input,
            eligibility_reason=reason,
            cecs_subs=cecs_subs,
        )

    if cecs is None:
        inputs = cecs_inputs
        cecs = calculate_cecs(
            inputs,
            weights=dict(scfg.get("cecs_weights") or {}),
            policy_penalty_weight=float(
                scfg.get("policy_dependency_penalty_weight", 0.15)
            ),
        )
        cecs_subs = {
            "disclosure_status": inputs.disclosure_status,
            "execution_continuity": inputs.execution_continuity,
            "pension_flow_score": inputs.pension_flow_score,
            "investment_purpose_flag": inputs.investment_purpose_flag,
            "independent_catalyst_flag": inputs.independent_catalyst_flag,
            "policy_dependency_flag": inputs.policy_dependency_flag,
        }
    elif cecs_inputs is not None:
        cecs_subs = {
            "disclosure_status": cecs_inputs.disclosure_status,
            "execution_continuity": cecs_inputs.execution_continuity,
            "pension_flow_score": cecs_inputs.pension_flow_score,
            "investment_purpose_flag": cecs_inputs.investment_purpose_flag,
            "independent_catalyst_flag": cecs_inputs.independent_catalyst_flag,
            "policy_dependency_flag": cecs_inputs.policy_dependency_flag,
        }

    factors = {
        "score_q": float(score_q) if score_q is not None else float("nan"),
        "score_v": float(score_v) if score_v is not None else float("nan"),
        "score_sr": float(score_sr) if score_sr is not None else float("nan"),
        "score_r": float(score_r) if score_r is not None else float("nan"),
        "cecs": float(cecs),
        # retained for blend / sizing diagnostics — not in FIVE_FACTORS
        "factor_score_total": float(factor_score_total),
    }

    total = _blend_total(
        float(factor_score_total),
        float(cecs),
        dict(scfg.get("total_score_blend") or {}),
    )

    cutoff = system_cfg.scoring.score_cutoff
    min_q = getattr(system_cfg.scoring, "quality_min_score", None)
    eligibility, reason, weight_input = _cutoff_eligibility(
        total=total,
        cutoff=cutoff,
        score_q=score_q,
        quality_inputs_ok=quality_inputs_ok,
        min_q=min_q,
        reason_ok=f"eligible: total_score={total} >= cutoff={cutoff}",
        reason_low=f"ineligible: total_score={total} < cutoff={cutoff}",
    )

    return NameScore(
        ticker=ticker,
        name=name,
        factors=factors,
        total_score=total,
        eligibility=eligibility,
        weight_input=weight_input,
        eligibility_reason=reason,
        cecs_subs=cecs_subs,
    )


def require_eligibility_decided(score: NameScore) -> bool:
    if score.eligibility is None:
        raise ConfigTodoError(
            "[TODO] scoring.score_cutoff unset — cannot decide eligibility"
        )
    return bool(score.eligibility)


def score_frame(
    df: pd.DataFrame,
    system_cfg: AlphaSystemConfig,
    *,
    scoring_cfg: dict[str, Any] | None = None,
) -> list[NameScore]:
    """
    Score rows. Expected columns (optional unless noted):
      ticker (required), name,
      score_q, score_v, score_sr, score_r, score_m, factor_score_total, cecs,
      CECS subs if cecs missing.
    """
    if "ticker" not in df.columns:
        raise ValueError("score_frame requires 'ticker' column")
    scfg = scoring_cfg or load_scoring_config()
    out: list[NameScore] = []
    for _, raw in df.iterrows():
        ticker = str(raw["ticker"])
        cecs_val = raw["cecs"] if "cecs" in df.columns and pd.notna(raw.get("cecs")) else None
        inputs = None
        if cecs_val is None:
            # Build CECS inputs only from real sub-scores; never fabricate 0.5.
            # If the required subs are absent, score_name leaves eligibility undecided.
            inputs = _cecs_inputs_from_row(
                raw, ticker=ticker, name=str(raw.get("name") or "")
            )
        fst = raw.get("factor_score_total")
        out.append(
            score_name(
                ticker=ticker,
                name=str(raw.get("name") or ""),
                score_q=_opt_float(raw, "score_q"),
                score_v=_opt_float(raw, "score_v"),
                score_sr=_opt_float(raw, "score_sr"),
                score_r=_opt_float(raw, "score_r"),
                score_m=_opt_float(raw, "score_m"),
                factor_score_total=float(fst) if fst is not None and pd.notna(fst) else None,
                cecs_inputs=inputs,
                cecs=float(cecs_val) if cecs_val is not None else None,
                quality_inputs_ok=_opt_bool(raw, "quality_inputs_ok"),
                system_cfg=system_cfg,
                scoring_cfg=scfg,
            )
        )
    return out


def _opt_float(row: pd.Series, col: str) -> Optional[float]:
    if col not in row.index or row.get(col) is None or pd.isna(row.get(col)):
        return None
    return float(row.get(col))


def _opt_bool(row: pd.Series, col: str) -> Optional[bool]:
    if col not in row.index or row.get(col) is None or pd.isna(row.get(col)):
        return None
    text = str(row.get(col)).strip().lower()
    if not text:
        return None
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    if text in {"0", "false", "f", "no", "n"}:
        return False
    return None


# CECS sub-scores that are actually blended (T2-mapped subs are excluded from scoring).
REQUIRED_CECS_SUBS = (
    "execution_continuity",
    "pension_flow_score",
    "investment_purpose_flag",
)


def _cecs_inputs_from_row(
    row: pd.Series, *, ticker: str, name: str
) -> Optional[CatalystInputs]:
    """Build CECS inputs only when all scored subs exist — never fabricate a neutral 0.5."""
    values: dict[str, float] = {}
    for key in REQUIRED_CECS_SUBS:
        val = row.get(key)
        if val is None or pd.isna(val):
            return None
        values[key] = float(val)
    pdf = row.get("policy_dependency_flag")
    penalty = 0.0 if pdf is None or pd.isna(pdf) else float(pdf)
    return CatalystInputs(
        ticker=ticker,
        name=name,
        execution_continuity=values["execution_continuity"],
        pension_flow_score=values["pension_flow_score"],
        investment_purpose_flag=values["investment_purpose_flag"],
        policy_dependency_flag=penalty,
    )


def scores_to_frame(scores: list[NameScore]) -> pd.DataFrame:
    rows = []
    for s in scores:
        row = {
            "ticker": s.ticker,
            "name": s.name,
            "total_score": s.total_score,
            "eligibility": s.eligibility,
            "weight_input": s.weight_input,
            "eligibility_reason": s.eligibility_reason,
            **{k: s.factors.get(k) for k in FIVE_FACTORS},
        }
        rows.append(row)
    return pd.DataFrame(rows)
