"""Take-profit (TP-A/B) and thesis-break (TB) — Review-only pure assessments.

Signal strength is a universe percentile / condition-hit score — never labelled
as probability / win-rate. See docs/EXIT_TAKEPROFIT_THESIS_SPEC.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from src.config import load_yaml

DEFAULT_EXIT_PARTIAL_FRAC_BANDS: list[dict[str, float]] = [
    {"min_strength": 70.0, "max_strength": 80.0, "partial_frac": 0.10},
    {"min_strength": 80.0, "max_strength": 90.0, "partial_frac": 0.20},
    {"min_strength": 90.0, "max_strength": 100.0, "partial_frac": 0.30},
]

DEFAULT_MOMENTUM_OVERRIDE_THRESHOLD = 70.0

ExitLeg = Literal["NONE", "FUND", "VAL", "BOTH"]
TakeProfitAction = Literal["Hold", "Trim", "Exit-review"]
ThesisRuleId = Literal["TB-01", "TB-02", "TB-03", "NONE"]
ThesisAction = Literal["Hold", "Trim", "Exit", "Exit-review", "Demote-review"]


@dataclass(frozen=True)
class TakeProfitAssessment:
    fund_hit: bool
    val_hit: bool
    signal_strength: float
    strength_components: str
    momentum_score: float | None
    momentum_override_applied: bool
    suggested_action: TakeProfitAction
    exit_leg: ExitLeg
    partial_frac: float
    rationale: str
    targets_missing: bool = False
    fund_proximity_pct: float | None = None
    val_proximity_pct: float | None = None


@dataclass(frozen=True)
class ThesisBreakAssessment:
    active: bool
    rule_id: ThesisRuleId
    suggested_action: ThesisAction
    rationale: str


def default_bands() -> list[dict[str, float]]:
    return [dict(b) for b in DEFAULT_EXIT_PARTIAL_FRAC_BANDS]


def load_exit_targets(path: Path) -> dict[str, Any]:
    """Load kr_alpha_exit_targets.yaml. Missing file → empty tickers + default bands."""
    if not path.exists():
        return {
            "version": "0.1",
            "defaults": {
                "exit_partial_frac_bands": default_bands(),
                "momentum_override_threshold": DEFAULT_MOMENTUM_OVERRIDE_THRESHOLD,
            },
            "tickers": {},
        }
    raw = load_yaml(path) or {}
    defaults = dict(raw.get("defaults") or {})
    if not defaults.get("exit_partial_frac_bands"):
        defaults["exit_partial_frac_bands"] = default_bands()
    if "momentum_override_threshold" not in defaults:
        defaults["momentum_override_threshold"] = DEFAULT_MOMENTUM_OVERRIDE_THRESHOLD
    tickers = raw.get("tickers") or {}
    if not isinstance(tickers, dict):
        tickers = {}
    normalized: dict[str, Any] = {}
    for k, v in tickers.items():
        key = str(k).zfill(6) if str(k).isdigit() else str(k)
        normalized[key] = v
    return {
        "version": str(raw.get("version") or "0.1"),
        "defaults": defaults,
        "tickers": normalized,
    }


def resolve_partial_frac_from_strength(
    signal_strength: float,
    bands: list[dict] | None = None,
) -> float:
    """Stair-step map. Below lowest min_strength → 0.0 (Hold).

    Interval: [min, max) for non-top bands; top band includes max.
    Exact 70/80/90 hit the band that starts at that min (upper band wins).
    """
    ordered = sorted(bands or default_bands(), key=lambda b: float(b["min_strength"]))
    if not ordered:
        return 0.0
    s = float(signal_strength)
    top_lo = float(ordered[-1]["min_strength"])
    for band in reversed(ordered):
        lo = float(band["min_strength"])
        hi = float(band["max_strength"])
        frac = float(band["partial_frac"])
        if lo == top_lo:
            if s >= lo and s <= hi + 1e-9:
                return frac
        elif s >= lo and s < hi:
            return frac
    return 0.0


def apply_momentum_counter_check(
    partial_frac: float,
    *,
    exit_leg: str,
    momentum_score: float | None,
    bands: list[dict] | None = None,
    momentum_override_threshold: float = DEFAULT_MOMENTUM_OVERRIDE_THRESHOLD,
) -> tuple[float, bool]:
    """VAL/BOTH + strong momentum → one stair step down. FUND never affected."""
    if exit_leg not in {"VAL", "BOTH"}:
        return float(partial_frac), False
    if momentum_score is None:
        return float(partial_frac), False
    if float(momentum_score) < float(momentum_override_threshold):
        return float(partial_frac), False
    if float(partial_frac) <= 0:
        return 0.0, False

    ordered = sorted(bands or default_bands(), key=lambda b: float(b["partial_frac"]))
    uniq: list[float] = []
    for b in ordered:
        f = float(b["partial_frac"])
        if not uniq or abs(f - uniq[-1]) > 1e-9:
            uniq.append(f)
    cur = float(partial_frac)
    idx = None
    for i, f in enumerate(uniq):
        if abs(f - cur) < 1e-9:
            idx = i
            break
    if idx is None:
        idx = min(range(len(uniq)), key=lambda i: abs(uniq[i] - cur))
    if idx <= 0:
        return 0.0, True
    return uniq[idx - 1], True


def _to_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _truthy(val: Any) -> bool:
    if val is True:
        return True
    if val is False or val is None:
        return False
    return str(val).strip().lower() in {"true", "1", "yes", "y", "done", "completed"}


def _fund_defined(ft: dict[str, Any]) -> bool:
    if _to_float(ft.get("roe_min")) is not None:
        return True
    if _to_float(ft.get("payout_min")) is not None:
        return True
    if ft.get("buyback_done") is True:
        return True
    return False


def _val_defined(vt: dict[str, Any]) -> bool:
    if _to_float(vt.get("pbr_max")) is not None:
        return True
    if _to_float(vt.get("premium_to_fair_pct")) is not None:
        return True
    if vt.get("overheat_flag") is not None:
        return True
    return False


def _fund_conditions(
    fundamentals: dict[str, Any],
    fund_targets: dict[str, Any],
) -> tuple[list[bool], list[str]]:
    hits: list[bool] = []
    labels: list[str] = []
    roe_min = _to_float(fund_targets.get("roe_min"))
    if roe_min is not None:
        roe = _to_float(fundamentals.get("roe") or fundamentals.get("ROE"))
        hits.append(roe is not None and roe >= roe_min)
        labels.append("roe")
    payout_min = _to_float(fund_targets.get("payout_min"))
    if payout_min is not None:
        payout = _to_float(
            fundamentals.get("payout_ratio")
            or fundamentals.get("dividend_payout")
            or fundamentals.get("payout")
        )
        hits.append(payout is not None and payout >= payout_min)
        labels.append("payout")
    if fund_targets.get("buyback_done") is True:
        actual = _truthy(fundamentals.get("buyback_done")) or _truthy(
            fundamentals.get("buyback_executed")
        )
        hits.append(actual)
        labels.append("buyback")
    return hits, labels


def _val_hit(
    fundamentals: dict[str, Any],
    prices: dict[str, Any],
    val_targets: dict[str, Any],
    overheat: bool | None,
) -> tuple[bool, float | None, str]:
    notes: list[str] = []
    hit = False
    pbr_max = _to_float(val_targets.get("pbr_max"))
    if pbr_max is not None:
        pbr = _to_float(fundamentals.get("pbr") or fundamentals.get("PBR") or prices.get("pbr"))
        if pbr is not None and pbr >= pbr_max:
            hit = True
            notes.append(f"pbr {pbr:.2f}>={pbr_max}")
    prem_max = _to_float(val_targets.get("premium_to_fair_pct"))
    if prem_max is not None:
        prem = _to_float(prices.get("premium_to_fair_pct") or fundamentals.get("premium_to_fair_pct"))
        if prem is not None and prem >= prem_max:
            hit = True
            notes.append(f"premium {prem:.1f}>={prem_max}")
    if overheat is True or _truthy(val_targets.get("overheat_flag")) or _truthy(prices.get("overheat")):
        hit = True
        notes.append("overheat")
    strength = _to_float(
        prices.get("valuation_score")
        or prices.get("v_rank")
        or fundamentals.get("valuation_score")
        or fundamentals.get("v_rank")
    )
    return hit, strength, "; ".join(notes) if notes else ""


def _ratio_proximity_pct(current: float | None, target: float | None) -> float | None:
    """current/target*100 capped to [0, 100]. None if either side missing/invalid."""
    if current is None or target is None or target <= 0:
        return None
    return round(min(100.0, max(0.0, float(current) / float(target) * 100.0)), 1)


def compute_leg_proximity(
    fundamentals: dict[str, Any],
    targets: dict[str, Any],
    prices: dict[str, Any] | None = None,
) -> tuple[float | None, float | None]:
    """Return (fund_proximity_pct, val_proximity_pct), 0~100, capped.

    Purely mechanical distance-to-threshold. NOT a probability/forecast.
    None if that leg has no target defined for this ticker.
    """
    fundamentals = fundamentals or {}
    prices = prices or {}
    targets = targets or {}
    fund_t = targets.get("fundamental") if isinstance(targets.get("fundamental"), dict) else {}
    val_t = targets.get("valuation") if isinstance(targets.get("valuation"), dict) else {}
    fund_t = fund_t or {}
    val_t = val_t or {}

    fund_prox: float | None = None
    if _fund_defined(fund_t):
        parts: list[float] = []
        roe_min = _to_float(fund_t.get("roe_min"))
        if roe_min is not None:
            roe = _to_float(fundamentals.get("roe") or fundamentals.get("ROE"))
            p = _ratio_proximity_pct(roe, roe_min)
            if p is not None:
                parts.append(p)
        payout_min = _to_float(fund_t.get("payout_min"))
        if payout_min is not None:
            payout = _to_float(
                fundamentals.get("payout_ratio")
                or fundamentals.get("dividend_payout")
                or fundamentals.get("payout")
            )
            p = _ratio_proximity_pct(payout, payout_min)
            if p is not None:
                parts.append(p)
        if fund_t.get("buyback_done") is True:
            done = _truthy(fundamentals.get("buyback_done")) or _truthy(
                fundamentals.get("buyback_executed")
            )
            parts.append(100.0 if done else 0.0)
        fund_prox = round(min(parts), 1) if parts else None

    val_prox: float | None = None
    if _val_defined(val_t):
        parts_v: list[float] = []
        pbr_max = _to_float(val_t.get("pbr_max"))
        if pbr_max is not None:
            pbr = _to_float(
                fundamentals.get("pbr") or fundamentals.get("PBR") or prices.get("pbr")
            )
            p = _ratio_proximity_pct(pbr, pbr_max)
            if p is not None:
                parts_v.append(p)
        prem_max = _to_float(val_t.get("premium_to_fair_pct"))
        if prem_max is not None:
            prem = _to_float(
                prices.get("premium_to_fair_pct") or fundamentals.get("premium_to_fair_pct")
            )
            p = _ratio_proximity_pct(prem, prem_max)
            if p is not None:
                parts_v.append(p)
        # overheat_flag alone: no continuous proximity metric
        val_prox = round(min(parts_v), 1) if parts_v else None

    return fund_prox, val_prox


def format_proximity_display(
    fund_proximity_pct: float | None,
    val_proximity_pct: float | None,
    *,
    targets_missing: bool,
    exit_leg: str,
) -> str:
    """UI label for 근접도 column. Uses '근접도' wording only — never 확률."""
    if targets_missing:
        return "—"
    leg = str(exit_leg or "NONE").strip().upper()
    if leg in {"FUND", "VAL", "BOTH"}:
        return "도달"
    parts: list[str] = []
    if fund_proximity_pct is not None:
        parts.append(f"FUND {float(fund_proximity_pct):.1f}% 근접")
    if val_proximity_pct is not None:
        parts.append(f"VAL {float(val_proximity_pct):.1f}% 근접")
    return " / ".join(parts) if parts else "—"


def format_proximity_gap_suffix(
    fund_proximity_pct: float | None,
    val_proximity_pct: float | None,
) -> str:
    """Compact suffix for Gap 익절상태 when 미도달, e.g. '(VAL 84%)'."""
    bits: list[str] = []
    if fund_proximity_pct is not None:
        bits.append(f"FUND {float(fund_proximity_pct):.1f}%")
    if val_proximity_pct is not None:
        bits.append(f"VAL {float(val_proximity_pct):.1f}%")
    if not bits:
        return ""
    return "(" + " · ".join(bits) + ")"


def assess_take_profit(
    ticker: str,
    *,
    fundamentals: dict[str, Any] | None = None,
    prices: dict[str, Any] | None = None,
    targets: dict[str, Any] | None = None,
    momentum_score: float | None = None,
    overheat: bool | None = None,
    bands: list[dict] | None = None,
    momentum_override_threshold: float = DEFAULT_MOMENTUM_OVERRIDE_THRESHOLD,
) -> TakeProfitAssessment:
    fundamentals = fundamentals or {}
    prices = prices or {}
    targets = targets or {}
    use_bands = bands or default_bands()

    fund_t = targets.get("fundamental") if isinstance(targets.get("fundamental"), dict) else {}
    val_t = targets.get("valuation") if isinstance(targets.get("valuation"), dict) else {}
    fund_t = fund_t or {}
    val_t = val_t or {}

    targets_missing = not _fund_defined(fund_t) and not _val_defined(val_t)
    if targets_missing:
        return TakeProfitAssessment(
            fund_hit=False,
            val_hit=False,
            signal_strength=0.0,
            strength_components="",
            momentum_score=momentum_score,
            momentum_override_applied=False,
            suggested_action="Hold",
            exit_leg="NONE",
            partial_frac=0.0,
            rationale=f"{ticker}: targets_missing — no TP-A/B targets",
            targets_missing=True,
            fund_proximity_pct=None,
            val_proximity_pct=None,
        )

    fund_prox, val_prox = compute_leg_proximity(fundamentals, targets, prices)

    fund_hits, fund_labels = _fund_conditions(fundamentals, fund_t)
    fund_hit = bool(fund_hits) and all(fund_hits)
    fund_strength = (sum(1 for h in fund_hits if h) / len(fund_hits) * 100.0) if fund_hits else 0.0

    val_hit, val_strength_raw, val_note = _val_hit(fundamentals, prices, val_t, overheat)
    if val_hit:
        val_strength = float(val_strength_raw) if val_strength_raw is not None else 75.0
    else:
        val_strength = float(val_strength_raw) if val_strength_raw is not None else 0.0

    use_fund = _fund_defined(fund_t)
    use_val = _val_defined(val_t)
    effective_fund = fund_hit if use_fund else False
    effective_val = val_hit if use_val else False

    components: list[str] = []
    strength_candidates: list[float] = []
    if use_fund and effective_fund:
        n_ok = sum(1 for h in fund_hits if h)
        components.append(f"TP-A {fund_strength:.1f}(펀더멘털 {n_ok}/{len(fund_hits)})")
        strength_candidates.append(fund_strength)
    elif use_fund:
        components.append(f"TP-A 미달({','.join(fund_labels) or 'fund'})")
    if use_val and effective_val:
        note_bit = f": {val_note}" if val_note else ""
        components.append(f"TP-B {val_strength:.1f}(밸류{note_bit})")
        strength_candidates.append(val_strength)
    elif use_val:
        components.append("TP-B 미달")

    strength = max(strength_candidates) if strength_candidates else 0.0
    strength_components = " / ".join(components)

    if effective_fund and effective_val:
        exit_leg: ExitLeg = "BOTH"
    elif effective_fund:
        exit_leg = "FUND"
    elif effective_val:
        exit_leg = "VAL"
    else:
        exit_leg = "NONE"

    partial = resolve_partial_frac_from_strength(strength, use_bands) if exit_leg != "NONE" else 0.0
    mom = (
        momentum_score
        if momentum_score is not None
        else _to_float(prices.get("momentum_score") or fundamentals.get("momentum_score"))
    )
    partial2, mom_applied = apply_momentum_counter_check(
        partial,
        exit_leg=exit_leg,
        momentum_score=mom,
        bands=use_bands,
        momentum_override_threshold=momentum_override_threshold,
    )

    rationale_parts = [strength_components] if strength_components else []
    if mom_applied:
        rationale_parts.append(
            f"but momentum {float(mom):.1f}(지속성 강함) → 카운터체크로 "
            f"{partial * 100:.0f}%→{partial2 * 100:.0f}% 하향"
        )
    if exit_leg == "NONE":
        rationale_parts.append("목표가 미도달")
    rationale = f"{ticker}: " + " · ".join(p for p in rationale_parts if p)

    if exit_leg == "NONE" or partial2 <= 0:
        action: TakeProfitAction = "Hold"
    elif exit_leg == "BOTH" and strength >= 90.0 and partial2 >= 0.20:
        action = "Exit-review"
    else:
        action = "Trim"

    return TakeProfitAssessment(
        fund_hit=effective_fund,
        val_hit=effective_val,
        signal_strength=round(strength, 2),
        strength_components=strength_components,
        momentum_score=mom,
        momentum_override_applied=mom_applied,
        suggested_action=action,
        exit_leg=exit_leg,
        partial_frac=round(partial2, 4),
        rationale=rationale,
        targets_missing=False,
        fund_proximity_pct=fund_prox,
        val_proximity_pct=val_prox,
    )


def assess_thesis_break(
    ticker: str,
    *,
    flags: dict[str, Any] | None = None,
    catalyst: dict[str, Any] | None = None,
) -> ThesisBreakAssessment:
    flags = flags or {}
    catalyst = catalyst or {}

    def _flag(*keys: str) -> bool:
        for k in keys:
            if _truthy(flags.get(k)) or _truthy(catalyst.get(k)):
                return True
        return False

    if _flag("thesis_damage", "thesis_broken", "thesis_break"):
        return ThesisBreakAssessment(
            active=True,
            rule_id="TB-01",
            suggested_action="Exit",
            rationale=f"{ticker}: TB-01 THESIS_BREAK — thesis damaged",
        )
    if _flag("accounting_issue", "governance_red", "audit_issue"):
        return ThesisBreakAssessment(
            active=True,
            rule_id="TB-03",
            suggested_action="Exit",
            rationale=f"{ticker}: TB-03 tail/accounting — map to Hard Replace",
        )
    if _flag("policy_retreat", "policy_thesis", "policy_delay"):
        return ThesisBreakAssessment(
            active=True,
            rule_id="TB-02",
            suggested_action="Demote-review",
            rationale=f"{ticker}: TB-02 POLICY_THESIS — demote/trim review",
        )
    return ThesisBreakAssessment(
        active=False,
        rule_id="NONE",
        suggested_action="Hold",
        rationale=f"{ticker}: no thesis-break flags",
    )


def trim_source_tag_tp(assessment: TakeProfitAssessment) -> str:
    if assessment.targets_missing:
        return "targets_missing"
    if assessment.exit_leg == "NONE" or assessment.suggested_action == "Hold":
        return "—"
    if assessment.exit_leg == "FUND":
        return "trim:TP-A"
    if assessment.exit_leg == "VAL":
        return "trim:TP-B"
    if assessment.exit_leg == "BOTH":
        return "trim:TP-BOTH"
    return "trim:TP-*"


def exit_source_tag_tb(assessment: ThesisBreakAssessment) -> str:
    if not assessment.active:
        return "—"
    return f"exit:{assessment.rule_id}"
