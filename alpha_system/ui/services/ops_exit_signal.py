"""Proposal-book exit cues — step take-profit (Review-only).

Recommended ops rule (2026-07-19):
  S0 thesis/hard → 전량
  S1 target hit → 환금 절반 (수량 내림)
  S2a proposal drop → 잔여 전량
  S2c time-cap (default 4 weeks at/above target, no target refresh) → 전량
  S근접 → 줄이기 ¼ 스텝 only (optional pre-hit)
Does not write target_portfolio or place orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal, Optional

OpsSignalKind = Literal["hold", "trim", "cash_half", "exit_full", "missing", "invalid"]

_LABELS: dict[OpsSignalKind, str] = {
    "hold": "유지",
    "trim": "줄이기",
    "cash_half": "환금",
    "exit_full": "전량",
    "missing": "목표없음",
    "invalid": "데이터없음",
}

# Pre-hit proximity: one step only (¼). At-hit is always half (S1).
_PROX_TRIM_STEP_PCT = 25
_PROX_TRIM_MIN = 70.0
_DEFAULT_TIME_CAP_WEEKS = 4


@dataclass(frozen=True)
class OpsExitSignal:
    kind: OpsSignalKind
    label: str
    detail: str
    trim_pct: Optional[int] = None
    proximity_pct: Optional[float] = None
    exit_leg: str = "NONE"
    momentum_override: bool = False
    rationale: str = ""
    step_id: str = ""


def _to_float(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_date(v: Any) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    s = str(v).strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _has_fund_or_val_targets(ticker_targets: dict[str, Any]) -> bool:
    val = ticker_targets.get("valuation")
    fund = ticker_targets.get("fundamental")
    if isinstance(val, dict) and any(v is not None and v != "" for v in val.values()):
        return True
    if isinstance(fund, dict) and any(v is not None and v != "" for v in fund.values()):
        return True
    return False


def _target_price_and_spot(
    prices: dict[str, Any],
    ticker_targets: dict[str, Any],
) -> tuple[float | None, float | None]:
    target_px = _to_float(ticker_targets.get("target_price"))
    cur = _to_float(
        prices.get("current_price") or prices.get("close") or prices.get("price")
    )
    return target_px, cur


def _price_proximity_pct(
    prices: dict[str, Any],
    ticker_targets: dict[str, Any],
    fundamentals: dict[str, Any] | None = None,
) -> float | None:
    """0–100+ style proximity; >=100 means at/above target."""
    fundamentals = fundamentals or {}
    target_px, cur = _target_price_and_spot(prices, ticker_targets)
    if target_px is not None and target_px > 0 and cur is not None and cur > 0:
        return round(cur / target_px * 100.0, 1)

    val = ticker_targets.get("valuation") if isinstance(ticker_targets.get("valuation"), dict) else {}
    pbr_max = _to_float((val or {}).get("pbr_max"))
    pbr = _to_float(fundamentals.get("pbr") or prices.get("pbr"))
    if pbr_max is not None and pbr_max > 0 and pbr is not None:
        return round(pbr / pbr_max * 100.0, 1)
    return None


def _is_target_hit(
    prices: dict[str, Any],
    ticker_targets: dict[str, Any],
    fundamentals: dict[str, Any] | None = None,
) -> bool:
    prox = _price_proximity_pct(prices, ticker_targets, fundamentals)
    if prox is not None and prox >= 100.0 - 1e-9:
        return True
    # Fallback: assess_take_profit VAL hit
    try:
        from src.alpha.take_profit_thesis import assess_take_profit

        tp = assess_take_profit(
            "x",
            fundamentals=fundamentals or {},
            prices=prices,
            targets=ticker_targets,
        )
        return bool(tp.val_hit or tp.exit_leg in {"VAL", "BOTH"})
    except Exception:
        return False


def _time_cap_fired(
    ticker_targets: dict[str, Any],
    *,
    as_of: date | None,
    weeks: int,
) -> bool:
    """True only after recorded target-hit date is older than N weeks.

    Uses ``target_hit_as_of`` only — never ``approved_as_of``. Approving a
    target weeks ago must not skip S1 (half cash) on the first hit day.
    Until hit date is recorded, S2c stays inactive (S1 applies at hit).
    """
    if weeks <= 0:
        return False
    as_of = as_of or date.today()
    d = _parse_date(ticker_targets.get("target_hit_as_of"))
    if d is None:
        return False
    return as_of >= d + timedelta(weeks=int(weeks))


def classify_ops_exit_signal(
    ticker: str,
    *,
    fundamentals: dict[str, Any] | None = None,
    prices: dict[str, Any] | None = None,
    ticker_targets: dict[str, Any] | None = None,
    in_proposal: bool = True,
    thesis_flags: dict[str, Any] | None = None,
    momentum_score: float | None = None,
    bands: list[dict] | None = None,
    momentum_override_threshold: float = 70.0,
    remaining_upside_pct: float | None = None,
    as_of: date | None = None,
    time_cap_weeks: int = _DEFAULT_TIME_CAP_WEEKS,
) -> OpsExitSignal:
    """Step map → operator-facing cue (Review-only)."""
    del bands, momentum_override_threshold  # reserved; pre-hit uses fixed ¼ step
    from src.alpha.take_profit_thesis import assess_thesis_break

    t = str(ticker).zfill(6) if str(ticker).isdigit() else str(ticker)
    per = ticker_targets if isinstance(ticker_targets, dict) else {}
    prices = prices or {}
    fundamentals = fundamentals or {}

    # S0 — thesis / hard
    tb = assess_thesis_break(t, flags=thesis_flags)
    if tb.active:
        return OpsExitSignal(
            kind="exit_full",
            label=_LABELS["exit_full"],
            detail="논지·하드 · 전량 환금 · 권고(사람 집행)",
            trim_pct=100,
            exit_leg="NONE",
            rationale=tb.rationale,
            step_id="S0",
        )

    # S2a — left proposal book (rotation)
    if not in_proposal:
        return OpsExitSignal(
            kind="exit_full",
            label=_LABELS["exit_full"],
            detail="제안 탈락 · 잔여 전량 환금 · 로테이션",
            trim_pct=100,
            rationale=f"{t}: not in proposal_book",
            step_id="S2a",
        )

    has_any_target = bool(per) and (
        _has_fund_or_val_targets(per) or _to_float(per.get("target_price")) is not None
    )
    if not has_any_target:
        return OpsExitSignal(
            kind="missing",
            label=_LABELS["missing"],
            detail="E에서 목표가 채우기",
            rationale=f"{t}: no exit target",
            step_id="E",
        )

    # Price/PBR missing → never emit hold/trim from thin air
    prox = _price_proximity_pct(prices, per, fundamentals)
    if prox is None:
        return OpsExitSignal(
            kind="invalid",
            label=_LABELS["invalid"],
            detail="데이터 없음 — 신호 무효 (가격·PBR 확인)",
            rationale=f"{t}: target set but no usable spot/pbr",
            step_id="DATA",
        )

    hit = _is_target_hit(prices, per, fundamentals)

    # S2c — time cap while still at/above target
    if hit and _time_cap_fired(per, as_of=as_of, weeks=time_cap_weeks):
        return OpsExitSignal(
            kind="exit_full",
            label=_LABELS["exit_full"],
            detail=f"도달 후 {time_cap_weeks}주 목표가 미갱신 · 전량 환금",
            trim_pct=100,
            proximity_pct=prox,
            exit_leg="VAL",
            rationale=f"{t}: time_cap_{time_cap_weeks}w",
            step_id="S2c",
        )

    # S1 — target hit → half cash
    if hit:
        half = 50
        if momentum_score is not None and float(momentum_score) >= 70:
            # Soften one step only in wording; still half floor for cash rule
            pass
        return OpsExitSignal(
            kind="cash_half",
            label=_LABELS["cash_half"],
            detail="목표가 도달 · 수량 절반(내림) · 권고(사람 집행)",
            trim_pct=half,
            proximity_pct=prox if prox is not None else 100.0,
            exit_leg="VAL",
            momentum_override=bool(
                momentum_score is not None and float(momentum_score) >= 70
            ),
            rationale=f"{t}: S1 half at target",
            step_id="S1",
        )

    # S근접 — single ¼ step when close but not hit
    if prox is not None and prox >= _PROX_TRIM_MIN:
        return OpsExitSignal(
            kind="trim",
            label=_LABELS["trim"],
            detail=f"목표가 근접 · ¼ 스텝({_PROX_TRIM_STEP_PCT}%) · 권고",
            trim_pct=_PROX_TRIM_STEP_PCT,
            proximity_pct=prox,
            exit_leg="VAL",
            rationale=f"{t}: pre-hit step {prox}%",
            step_id="Sprox",
        )

    if remaining_upside_pct is not None:
        detail = f"목표까지 약 {float(remaining_upside_pct):+.1f}%"
    elif prox is not None:
        detail = f"목표 근접 약 {float(prox):.0f}%"
    else:
        detail = "목표 미근접 · 유지"
    return OpsExitSignal(
        kind="hold",
        label=_LABELS["hold"],
        detail=detail,
        proximity_pct=prox,
        rationale=f"{t}: hold",
        step_id="HOLD",
    )


def _fmt_won(v: Any) -> str | None:
    x = _to_float(v)
    if x is None:
        return None
    return f"{int(round(x)):,}원"


def _detail_with_ladder_prices(
    sig: OpsExitSignal,
    extra: dict[str, Any],
    row: Any,
) -> str:
    """Replace ¼/환금 wording with the matching ladder cell in won."""
    # L1 trail / L3 crash keep their own wording
    sid = sig.step_id or ""
    if sid.startswith("L1") or sid.startswith("L3"):
        return sig.detail
    rungs = extra.get("ladder_rungs") if isinstance(extra, dict) else None
    high = None
    if isinstance(extra, dict):
        high = extra.get("ladder_high")
    if high is None:
        high = getattr(row, "target_price", None)

    if sig.kind == "trim":
        px = None
        if isinstance(rungs, (list, tuple)) and len(rungs) >= 3:
            px = _fmt_won(rungs[2])
        if px:
            return f"줄이기 {px} (25%) · 권고"
        return sig.detail

    if sig.kind == "cash_half":
        px = None
        if isinstance(rungs, (list, tuple)) and len(rungs) >= 5:
            px = _fmt_won(rungs[4])
        if px is None:
            px = _fmt_won(high)
        if px:
            return f"절반 환금 {px} · 권고(사람 집행)"
        return sig.detail

    if sig.kind == "exit_full" and sig.step_id == "S2c":
        px = None
        if isinstance(rungs, (list, tuple)) and len(rungs) >= 5:
            px = _fmt_won(rungs[4])
        if px is None:
            px = _fmt_won(high)
        if px:
            return f"전량 {px} · 도달 후 4주"
        return sig.detail

    return sig.detail


def apply_ops_exit_signals(
    rows: list[Any],
    *,
    proposal_tickers: set[str],
    fundamentals_by_ticker: dict[str, dict[str, Any]],
    exit_tickers: dict[str, Any],
    defaults: dict[str, Any] | None = None,
    check_proposal_membership: bool = True,
    as_of: date | None = None,
    trail_by_ticker: dict[str, tuple[float, float | None]] | None = None,
    apply_trail: bool = True,
    closes_by_ticker: dict[str, list[float]] | None = None,
    apply_crash: bool = True,
    trim_notes: dict[str, dict[str, Any]] | None = None,
) -> None:
    """Mutate PortfolioRow list in place with exit cues (L0 + L1 trail + L3 crash)."""
    defaults = defaults or {}
    mom_thr = float(defaults.get("momentum_override_threshold") or 70.0)
    time_cap = int(defaults.get("exit_time_cap_weeks") or _DEFAULT_TIME_CAP_WEEKS)
    prop = {str(t).zfill(6) if str(t).isdigit() else str(t) for t in proposal_tickers}
    trail_map = trail_by_ticker or {}
    closes_map = closes_by_ticker or {}
    notes = trim_notes or {}
    t1 = t2 = t3 = None
    c1 = c2 = c3 = None
    crash_n = 5
    if apply_trail:
        from alpha_system.ui.services.trail_exit_signal import (
            trail_from_snapshot,
            trail_params_from_defaults,
        )

        t1, t2, t3 = trail_params_from_defaults(defaults)
    if apply_crash:
        from alpha_system.ui.services.crash_defense_signal import (
            build_reentry_ladder,
            classify_crash_defense,
            crash_params_from_defaults,
            ladder_as_extra,
            merge_l0_l1_l3,
        )

        c1, c2, c3, crash_n = crash_params_from_defaults(defaults)

    for row in rows:
        t = str(row.ticker).zfill(6) if str(row.ticker).isdigit() else str(row.ticker)
        per = exit_tickers.get(t) or {}
        if not isinstance(per, dict):
            per = {}
        fund = dict(fundamentals_by_ticker.get(t) or {})
        prices = {"current_price": row.current_price}
        if row.current_pbr is not None:
            fund = {**fund, "pbr": row.current_pbr}
        in_prop = True if not check_proposal_membership else (t in prop)
        mom = None
        extra = row.extra or {}
        if extra.get("momentum_score") is not None:
            mom = _to_float(extra.get("momentum_score"))
        sig = classify_ops_exit_signal(
            t,
            fundamentals=fund,
            prices=prices,
            ticker_targets=per,
            in_proposal=in_prop,
            bands=defaults.get("exit_partial_frac_bands"),
            momentum_score=mom,
            momentum_override_threshold=mom_thr,
            remaining_upside_pct=row.remaining_upside_pct,
            as_of=as_of,
            time_cap_weeks=time_cap,
        )
        trail_meta: dict[str, Any] = {}
        crash_meta: dict[str, Any] = {}
        l1 = None
        closes = list(closes_map.get(t) or [])
        close = _to_float(row.current_price)
        if apply_trail and t1 is not None:
            snap = trail_map.get(t)
            high_52w = None
            if snap is not None:
                close = snap[0] if close is None else close
                high_52w = snap[1]
            elif extra.get("high_52w") is not None:
                high_52w = _to_float(extra.get("high_52w"))
            highs = closes if closes else None
            l1 = trail_from_snapshot(
                close=close,
                high_52w=high_52w,
                closes=closes or None,
                highs=highs,
                t1=t1,
                t2=t2 or 0.20,
                t3=t3 or 0.28,
            )
            if l1 is not None:
                trail_meta = {
                    "trail_kind": l1.kind,
                    "trail_drawdown": round(l1.drawdown, 4),
                    "trail_peak": l1.peak,
                    "trail_label": l1.label,
                    "trail_channel": l1.channel_break,
                }

        l3 = None
        if apply_crash and c1 is not None and closes:
            l3 = classify_crash_defense(
                closes,
                last=close,
                l1_drawdown=None if l1 is None else l1.drawdown,
                c1=c1,
                c2=c2 or -0.18,
                c3=c3 or -0.25,
                n=crash_n,
            )
            crash_meta = {
                "crash_kind": l3.kind,
                "crash_code": l3.code,
                "crash_ret_nd": round(l3.ret_nd, 4),
                "crash_n_days": l3.n_days,
                "crash_low": l3.crash_low,
                "crash_label": l3.label,
                "crash_full_hint": l3.suggest_full_review,
            }
            note = notes.get(t) or {}
            trim_frac = 0.0
            crash_low = l3.crash_low
            if l3.kind in {"trim", "cash_half"} and l3.trim_pct:
                trim_frac = float(l3.trim_pct) / 100.0
            if note.get("trim_frac"):
                try:
                    trim_frac = max(trim_frac, float(note["trim_frac"]))
                except (TypeError, ValueError):
                    pass
            if note.get("crash_low"):
                try:
                    crash_low = float(note["crash_low"]) or crash_low
                except (TypeError, ValueError):
                    pass
            if trim_frac > 0 and crash_low > 0:
                ladder = build_reentry_ladder(
                    crash_low=crash_low,
                    last=float(close or l3.last or 0),
                    trim_frac=trim_frac,
                    closes=closes,
                )
                crash_meta.update(ladder_as_extra(ladder))

        if apply_crash and c1 is not None:
            sig = merge_l0_l1_l3(sig, l1, l3)
        elif apply_trail and t1 is not None and l1 is not None:
            from alpha_system.ui.services.trail_exit_signal import merge_l0_l1

            sig = merge_l0_l1(sig, l1)

        row.ops_signal = sig.kind
        row.ops_signal_label = sig.label
        row.ops_signal_detail = _detail_with_ladder_prices(sig, extra, row)
        row.ops_trim_pct = sig.trim_pct
        row.extra = {
            **extra,
            "book": extra.get("book") or ("proposal" if in_prop else "ops"),
            "ops_exit_leg": sig.exit_leg,
            "ops_proximity_pct": sig.proximity_pct,
            "ops_momentum_override": sig.momentum_override,
            "ops_rationale": sig.rationale,
            "ops_step_id": sig.step_id,
            **trail_meta,
            **crash_meta,
        }


def actionable_ops_signals(rows: list[Any]) -> list[Any]:
    """Home '익절 점검': 줄이기 / 환금 / 전량 / 목표없음."""
    return [
        r
        for r in rows
        if getattr(r, "ops_signal", "") in {
            "trim",
            "cash_half",
            "exit_full",
            "missing",
            "invalid",
        }
    ]
