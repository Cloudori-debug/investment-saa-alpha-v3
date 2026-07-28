"""Alpha Signal Board — per-stock timing signals (grade ≠ action_state)."""

from __future__ import annotations



from dataclasses import dataclass, asdict

from pathlib import Path

from typing import Any



import pandas as pd



from src.alpha.investor_flows import get_flow_for_ticker as _legacy_get_flow_for_ticker
from src.alpha_v2_gate import get_flow_for_ticker_unified


def get_flow_for_ticker(data_dir: Path, ticker: str) -> dict[str, Any]:
    """Shared flow read path — v1 decision logic unchanged downstream."""
    try:
        return get_flow_for_ticker_unified(data_dir, ticker)
    except Exception:
        return _legacy_get_flow_for_ticker(data_dir, ticker)

from src.alpha.schemas import AlphaCandidate, HoldingReview

from src.alpha.sector_mapping import load_krx_sector_mapping, resolve_sector

from src.alpha.take_profit_thesis import (
    assess_take_profit,
    assess_thesis_break,
    exit_source_tag_tb,
    load_exit_targets,
    trim_source_tag_tp,
)

from src.csv_utils import write_dataframe_csv

from src.field_normalize import normalize_sector



SIGNAL_BOARD_COLUMNS = [

    "ticker",

    "name",

    "grade",

    "action_state",

    "thesis",

    "fundamental_signal",

    "valuation_signal",

    "volume_signal",

    "flow_signal",

    "flow_score",

    "flow_blocker",

    "price_signal",

    "catalyst_signal",

    "risk_blocker",

    "missing_for_buy",

    "buy_trigger",

    "add_trigger",

    "trim_trigger",

    "exit_trigger",

    "confidence",

    "sector",

    "sector_source",

    "current_weight_pct",

    "target_weight_pct",

    "total_score",

    "eligible_action",

    "review_action",

    "exit_leg",

    "targets_missing",

    "trim_source_tag",

    "tp_partial_frac",

    "tp_signal_strength",

    "tp_rationale",

    "momentum_override_applied",

    "fund_proximity_pct",

    "val_proximity_pct",

]



ACTION_STATES = frozenset({
    "Exclude",
    "Watch",
    "Buy-ready",
    "Buy-allowed",
    "Hold",
    "Add",
    "Trim",
    "Replace-review",
    "Exit-review",
    "Exit",
})

FLOW_BUY_BLOCKERS = frozenset({"DISTRIBUTION", "STALE"})

HARD_EXIT_TRIGGERS = frozenset({
    "thesis_damage",
    "severe_fundamental_deterioration",
    "accounting_issue",
    "liquidity_crisis",
    "risk_limit_hard_breach",
})


def detect_hard_exit_triggers(
    cand_dict: dict[str, Any],
    review: HoldingReview | None = None,
) -> set[str]:
    """Explicit hard-exit flags only — score downgrade alone does not qualify."""
    triggers: set[str] = set()
    for key in HARD_EXIT_TRIGGERS:
        val = cand_dict.get(key)
        if val is True or str(val or "").lower() == "true":
            triggers.add(key)
    return triggers





@dataclass

class SignalBoardRow:

    ticker: str

    name: str

    grade: str

    action_state: str

    thesis: str

    fundamental_signal: str

    valuation_signal: str

    volume_signal: str

    flow_signal: str

    price_signal: str

    catalyst_signal: str

    risk_blocker: str

    missing_for_buy: str

    buy_trigger: str

    add_trigger: str

    trim_trigger: str

    exit_trigger: str

    confidence: str

    flow_score: float = 0.0

    flow_blocker: str = ""

    sector: str = "unknown"

    sector_source: str = ""

    current_weight_pct: float = 0.0

    target_weight_pct: float = 0.0

    total_score: float = 0.0

    eligible_action: str = ""

    review_action: str = ""

    exit_leg: str = "NONE"

    targets_missing: bool = True

    trim_source_tag: str = "—"

    tp_partial_frac: float = 0.0

    tp_signal_strength: float = 0.0

    tp_rationale: str = ""

    momentum_override_applied: bool = False

    fund_proximity_pct: float | None = None

    val_proximity_pct: float | None = None





def format_missing_kv(missing: dict[str, str]) -> str:

    if not missing:

        return "—"

    return "; ".join(f"{k}:{v}" for k, v in missing.items())





def flow_blocker_for_signal(flow_signal: str) -> str:

    if flow_signal == "DISTRIBUTION":

        return "flow_distribution"

    if flow_signal == "STALE":

        return "flow_stale"

    return ""





def _axis_fundamental(cand: dict[str, Any], fund: dict[str, Any] | None) -> tuple[str, bool]:

    q = float(cand.get("quality_score") or 0)

    parts: list[str] = []

    ok = q >= 55

    if q >= 65:

        parts.append(f"quality {q:.0f} strong")

    elif q >= 50:

        parts.append(f"quality {q:.0f} neutral")

    else:

        parts.append(f"quality {q:.0f} weak")

        ok = False

    if fund:

        roe = fund.get("roe")

        if roe is not None:

            parts.append(f"ROE {float(roe):.1f}%")

            if float(roe) < 5:

                ok = False

        debt = fund.get("debt_ratio")

        if debt is not None and float(debt) > 200:

            parts.append("debt elevated")

            ok = False

    return " · ".join(parts), ok





def _axis_valuation(cand: dict[str, Any], fund: dict[str, Any] | None) -> tuple[str, bool]:

    v = float(cand.get("valuation_score") or 0)

    ok = v >= 55

    parts = [f"valuation {v:.0f}" + (" attractive" if v >= 60 else " fair" if v >= 50 else " stretched")]

    if fund:

        for label, key in (("PER", "per"), ("PBR", "pbr")):

            val = fund.get(key)

            if val is not None:

                parts.append(f"{label} {float(val):.1f}")

    return " · ".join(parts), ok





def _axis_volume(px: dict[str, Any] | None) -> tuple[str, bool]:

    if not px:

        return "price data missing", False

    tv = float(px.get("trading_value_20d") or 0)

    ok = tv >= 2_000_000_000

    if tv >= 5_000_000_000:

        text = f"liquidity strong (TV20 {tv/1e9:.1f}B)"

    elif ok:

        text = f"liquidity OK (TV20 {tv/1e9:.1f}B)"

    else:

        text = f"liquidity thin (TV20 {tv/1e9:.1f}B)"

    return text, ok





def _axis_flow(flow_info: dict[str, Any]) -> tuple[str, bool, float, str]:

    signal = str(flow_info.get("flow_signal") or "STALE")

    score = float(flow_info.get("flow_score") or 0)

    f5 = flow_info.get("foreign_5d_mcap_pct")

    parts = [signal]

    if f5 not in (None, ""):

        try:

            parts.append(f"foreign 5d {float(f5):+.2f}% mcap")

        except (TypeError, ValueError):

            pass

    if flow_info.get("source") == "missing":

        parts.append("data not wired")

    ok = signal in {"ACCUMULATION", "MILD_ACCUMULATION", "NEUTRAL"}

    blocker = flow_blocker_for_signal(signal)

    return " · ".join(parts), ok, score, blocker





def _axis_price(cand: dict[str, Any], px: dict[str, Any] | None) -> tuple[str, bool]:

    m = float(cand.get("momentum_score") or 0)

    ok = m >= 55

    parts = [f"momentum {m:.0f}"]

    if px:

        dist = px.get("distance_from_52w_high")

        r1m = px.get("return_1m")

        if dist is not None:

            parts.append(f"52w dist {float(dist):.1f}%")

            if float(dist) < -25:

                ok = ok and float(r1m or 0) > -5

        if r1m is not None:

            parts.append(f"1m {float(r1m):+.1f}%")

    return " · ".join(parts), ok





def _axis_catalyst(cand: dict[str, Any]) -> tuple[str, bool]:

    sr = float(cand.get("shareholder_return_score") or 0)

    reason = str(cand.get("key_reason") or cand.get("penalty_reason") or "")

    ok = sr >= 55

    text = f"shareholder_return {sr:.0f}"

    if reason:

        text += f" · {reason[:80]}"

    return text, ok





def _thesis_text(cand: dict[str, Any], sector: str) -> str:

    grade = cand.get("grade", "")

    return (

        f"QVM+SR alpha candidate ({grade}) · sector={sector} · "

        f"{cand.get('key_reason') or 'factor composite'}"

    )[:200]





def _confidence(passes: int, total: int, grade: str, *, flow_signal: str = "NEUTRAL") -> str:

    if flow_signal == "STALE":

        return "Low"

    if grade == "A" and passes >= 4 and flow_signal not in FLOW_BUY_BLOCKERS:

        return "High"

    if passes >= 3 and grade in {"A", "B"}:

        return "Medium"

    return "Low"





def derive_action_state(

    *,

    grade: str,

    eligible_action: str,

    review_action: str | None,

    current_weight: float,

    target_weight: float,

    axis_passes: int,

    sector_resolved: bool,

    sector_unknown_rate: float,

    alpha_auto_buy_allowed: bool,

    data_gate: str,
    flow_signal: str = "STALE",
    hard_exit_triggers: set[str] | frozenset[str] | None = None,
    executable_replace: bool = False,
) -> tuple[str, dict[str, str], list[str]]:

    """Return action_state, missing_for_buy kv map, risk_blockers."""

    missing: dict[str, str] = {}

    blockers: list[str] = []

    flow_blocks_buy = flow_signal in FLOW_BUY_BLOCKERS



    if flow_signal == "DISTRIBUTION":

        blockers.append("flow_distribution")

        missing["flow_signal"] = "DISTRIBUTION"

    elif flow_signal == "STALE":

        blockers.append("flow_stale")

        missing["flow_signal"] = "STALE"



    if grade in {"Reject", "D"}:
        return "Exclude", missing, blockers

    hard_triggers = set(hard_exit_triggers or ())
    overweight = current_weight > 0 and target_weight > 0 and current_weight > target_weight + 2.0

    # 1) Hard exit before trim — thesis damage or severe risk outranks position sizing.
    if hard_triggers:
        if "thesis_damage" in hard_triggers:
            blockers.append("thesis_damage")
            return "Exit", missing, blockers
        blockers.append(sorted(hard_triggers)[0])
        return "Exit-review", missing, blockers

    # 2) Trim — overweight / explicit TRIM when thesis intact.
    if review_action == "TRIM" or (overweight and current_weight >= 8.0):
        if overweight:
            blockers.append("position_overweight")
        return "Trim", missing, blockers

    if current_weight > 0 and overweight:
        return "Trim", missing, blockers + ["position_overweight"]

    # 3) Replace-review — screen fail / low score, not executable by default.
    if review_action == "REPLACE_CANDIDATE":
        blockers.append("screen_fail_or_low_score")
        if not executable_replace:
            missing["executable_replace"] = "false"
        else:
            missing["executable_replace"] = "true"
        return "Replace-review", missing, blockers

    if current_weight > 0 and review_action in {None, "KEEP", "WATCH"}:
        if not sector_resolved:
            missing["sector_known"] = "false"
            blockers.append("sector_unknown")
            return "Hold", missing, blockers
        if (
            grade in {"A", "B"}
            and axis_passes >= 3
            and alpha_auto_buy_allowed
            and not flow_blocks_buy
        ):
            return "Add", missing, blockers
        if flow_blocks_buy and grade in {"A", "B"} and axis_passes >= 3:
            missing.setdefault("flow_signal", flow_signal)
        return "Hold", missing, blockers

    if eligible_action == "NO_NEW":
        return "Exclude", missing, blockers

    if not sector_resolved or sector_unknown_rate > 0.3:
        missing["sector_known"] = "false"
        blockers.append("sector_unknown")

    if data_gate == "RED":

        blockers.append("alpha_data_gate_red")

        missing["data_gate_green"] = "false"



    if not alpha_auto_buy_allowed:

        blockers.append("alpha_auto_buy_blocked")



    if grade == "C":

        missing["grade_B_or_higher"] = "false"



    passes_buy = (

        grade in {"A", "B"}

        and axis_passes >= 4

        and sector_resolved

        and alpha_auto_buy_allowed

        and data_gate != "RED"

        and eligible_action == "BUY_CANDIDATE"

        and not flow_blocks_buy

    )

    if passes_buy:

        return "Buy-allowed", missing, blockers



    buy_ready = (

        grade in {"A", "B"}

        and axis_passes >= 3

        and sector_resolved

        and data_gate != "RED"

        and not flow_blocks_buy

    )

    if buy_ready:

        if not alpha_auto_buy_allowed:

            missing["execution_permission"] = "blocked"

        if eligible_action != "BUY_CANDIDATE":

            missing["eligible_action_buy_candidate"] = "false"

        return "Buy-ready", missing, blockers



    if (

        grade in {"A", "B"}

        and axis_passes >= 2

        and sector_resolved

        and data_gate != "RED"

        and flow_signal == "ACCUMULATION"

        and not flow_blocks_buy

    ):

        if not alpha_auto_buy_allowed:

            missing["execution_permission"] = "blocked"

        if eligible_action != "BUY_CANDIDATE":

            missing["eligible_action_buy_candidate"] = "false"

        return "Buy-ready", missing, blockers



    if not sector_resolved:

        return "Watch", missing, blockers



    return "Watch", missing, blockers





def _truncate_display(text: str, max_len: int) -> str:
    """Truncate report table cells without splitting key tokens (blocked/false)."""
    if len(text) <= max_len:
        return text
    for sep in (" + ", "; "):
        if sep not in text:
            continue
        parts = text.split(sep)
        out = parts[0]
        for part in parts[1:]:
            candidate = f"{out}{sep}{part}"
            if len(candidate) <= max_len:
                out = candidate
            else:
                break
        if len(out) < len(text):
            return out + "…"
        return out
    if " " in text[:max_len]:
        cut = text[: max_len - 1].rsplit(" ", 1)[0]
        if cut:
            return cut + "…"
    return text[: max_len - 1] + "…"


def _buy_trigger_text(missing: dict[str, str], axis_ok: dict[str, bool]) -> str:

    triggers = []

    if missing.get("sector_known") == "false":

        triggers.append("sector mapped")

    if missing.get("execution_permission") == "blocked":

        triggers.append("alpha_auto_buy 승인 필요(현재 BLOCKED)")

    if missing.get("eligible_action_buy_candidate") == "false":

        triggers.append("screener BUY_CANDIDATE grade")

    if missing.get("flow_signal") in {"STALE", "DISTRIBUTION"}:

        triggers.append(f"flow not {missing['flow_signal']}")

    if not axis_ok.get("price"):

        triggers.append("momentum/price recovery")

    if not axis_ok.get("volume"):

        triggers.append("volume sustain")

    if not axis_ok.get("flow"):

        triggers.append("flow confirmation (optional)")

    return " + ".join(triggers) if triggers else "all core axes met — await execution gate"





def _exit_trigger_text(action: str, *, executable_replace: bool = False) -> str:
    if action == "Exit":
        return "thesis damage confirmed — exit when approved"
    if action == "Exit-review":
        return "hard risk breach — human review before exit"
    if action == "Replace-review":
        note = "executable replace" if executable_replace else "not executable"
        return f"screen fail / low score — replace candidate ({note})"
    if action == "Trim":
        return "target band / concentration — trim not exit"
    return "—"


def build_alpha_signal_board(

    *,

    candidates: list[AlphaCandidate],

    holdings_review: list[HoldingReview],

    graded_by_ticker: dict[str, dict[str, Any]],

    fundamentals: dict[str, Any],

    prices: dict[str, Any],

    data_dir: Path,

    sector_coverage: dict[str, Any] | None = None,

    alpha_auto_buy_permission: str = "BLOCKED",

    data_gate: str = "GREEN",

    alpha_sector_data_gate: str = "GREEN",

) -> list[SignalBoardRow]:

    mapping = load_krx_sector_mapping(data_dir)

    sector_cov = sector_coverage or {}

    shortlist_unknown = float(sector_cov.get("shortlist_unknown_rate") or 0)

    alpha_auto_buy_ok = alpha_auto_buy_permission == "ALLOWED"

    exit_cfg = load_exit_targets(data_dir / "kr_alpha_exit_targets.yaml")
    exit_defaults = exit_cfg.get("defaults") or {}
    exit_bands = exit_defaults.get("exit_partial_frac_bands")
    mom_thr = float(exit_defaults.get("momentum_override_threshold") or 70.0)
    exit_tickers = exit_cfg.get("tickers") or {}

    holdings_by_ticker = {h.ticker: h for h in holdings_review}

    tickers_seen: set[str] = set()



    rows: list[SignalBoardRow] = []



    def _process(ticker: str, cand_dict: dict[str, Any], review: HoldingReview | None) -> None:

        if ticker in tickers_seen:

            return

        tickers_seen.add(ticker)



        name = cand_dict.get("name") or (review.name if review else ticker)

        sector_info = resolve_sector(

            ticker,

            name,

            str(cand_dict.get("sector") or ""),

            mapping,

        )

        sector = sector_info["sector"]

        fund = fundamentals.get(ticker)

        fund_d = fund.model_dump() if hasattr(fund, "model_dump") else (fund or {})

        px = prices.get(ticker)

        px_d = px.model_dump() if hasattr(px, "model_dump") else (px or {})



        flow_info = get_flow_for_ticker(data_dir, ticker)

        flow_sig = str(flow_info.get("flow_signal") or "STALE")



        f_sig, f_ok = _axis_fundamental(cand_dict, fund_d)

        v_sig, v_ok = _axis_valuation(cand_dict, fund_d)

        vol_sig, vol_ok = _axis_volume(px_d)

        flow_text, flow_ok, flow_score, flow_blocker = _axis_flow(flow_info)

        p_sig, p_ok = _axis_price(cand_dict, px_d)

        c_sig, c_ok = _axis_catalyst(cand_dict)



        axis_ok = {

            "fundamental": f_ok,

            "valuation": v_ok,

            "volume": vol_ok,

            "flow": flow_ok,

            "price": p_ok,

            "catalyst": c_ok,

        }

        passes = sum(1 for v in axis_ok.values() if v)



        grade = str(cand_dict.get("grade") or (review.grade if review else "C"))

        if not sector_info["resolved"] and grade == "A":

            grade = "B"



        cw = float(review.current_weight if review else 0)

        tw = float(review.target_weight if review else 0)

        review_action = review.review_action if review else None
        hard_triggers = detect_hard_exit_triggers(cand_dict, review)
        exec_replace = (
            alpha_auto_buy_ok
            and str(cand_dict.get("executable_replace", "")).lower() == "true"
        )

        action, missing, blockers = derive_action_state(
            grade=grade,
            eligible_action=str(cand_dict.get("eligible_action") or ""),
            review_action=review_action,
            current_weight=cw,
            target_weight=tw,
            axis_passes=passes,
            sector_resolved=bool(sector_info["resolved"]),
            sector_unknown_rate=shortlist_unknown,
            alpha_auto_buy_allowed=alpha_auto_buy_ok,
            data_gate=data_gate,
            flow_signal=flow_sig,
            hard_exit_triggers=hard_triggers,
            executable_replace=exec_replace,
        )



        if alpha_sector_data_gate == "YELLOW_DATA_LIMITED" and action in {"Buy-allowed", "Add"}:

            action = "Buy-ready"

            blockers.append("sector_data_limited")

            missing["sector_coverage"] = "below_threshold"



        conf = _confidence(passes, 6, grade, flow_signal=flow_sig)

        missing_text = format_missing_kv(missing)

        blocker_text = "; ".join(blockers) if blockers else "—"

        tkey = str(ticker).zfill(6) if str(ticker).isdigit() else str(ticker)
        tp_targets = exit_tickers.get(tkey) or exit_tickers.get(ticker) or {}
        if not isinstance(tp_targets, dict):
            tp_targets = {}
        mom_score = cand_dict.get("momentum_score")
        try:
            mom_f = float(mom_score) if mom_score is not None else None
        except (TypeError, ValueError):
            mom_f = None
        price_ctx = dict(px_d) if isinstance(px_d, dict) else {}
        if "valuation_score" not in price_ctx and cand_dict.get("valuation_score") is not None:
            price_ctx["valuation_score"] = cand_dict.get("valuation_score")
        fund_ctx = dict(fund_d) if isinstance(fund_d, dict) else {}
        tp = assess_take_profit(
            ticker,
            fundamentals=fund_ctx,
            prices=price_ctx,
            targets=tp_targets,
            momentum_score=mom_f,
            bands=exit_bands,
            momentum_override_threshold=mom_thr,
        )
        tb = assess_thesis_break(ticker, flags=cand_dict)
        tp_tag = trim_source_tag_tp(tp)
        tb_tag = exit_source_tag_tb(tb)

        trim_bits: list[str] = []
        if cw > 0:
            trim_bits.append(f"trim:score weight>{tw:.1f}%+2%p or review TRIM")
        if tp.suggested_action == "Trim" and not tp.targets_missing:
            trim_bits.append(
                f"{tp_tag} partial={tp.partial_frac:.0%} strength={tp.signal_strength:.0f}"
            )
        elif tp.targets_missing and cw > 0:
            trim_bits.append("targets_missing")
        trim_text = "; ".join(trim_bits) if trim_bits else "—"

        exit_base = _exit_trigger_text(
            action,
            executable_replace=missing.get("executable_replace") == "true",
        )
        exit_bits = [exit_base] if exit_base and exit_base != "—" else []
        if tb.active:
            exit_bits.insert(0, f"{tb_tag} {tb.rationale}")
        if tp.suggested_action == "Exit-review":
            exit_bits.append(f"{tp_tag} {tp.rationale}")
        exit_text = "; ".join(exit_bits) if exit_bits else "—"

        rows.append(

            SignalBoardRow(

                ticker=ticker,

                name=name,

                grade=grade,

                action_state=action,

                thesis=_thesis_text(cand_dict, sector),

                fundamental_signal=f_sig,

                valuation_signal=v_sig,

                volume_signal=vol_sig,

                flow_signal=flow_text,

                flow_score=flow_score,

                flow_blocker=flow_blocker,

                price_signal=p_sig,

                catalyst_signal=c_sig,

                risk_blocker=blocker_text,

                missing_for_buy=missing_text,

                buy_trigger=_buy_trigger_text(missing, axis_ok),

                add_trigger="target band room + Buy-allowed + alpha gate" if action == "Hold" else "—",

                trim_trigger=trim_text,

                exit_trigger=exit_text,

                confidence=conf,

                sector=sector,

                sector_source=str(sector_info.get("source", "")),

                current_weight_pct=cw,

                target_weight_pct=tw,

                total_score=float(cand_dict.get("total_score") or 0),

                eligible_action=str(cand_dict.get("eligible_action") or ""),

                review_action=str(review_action or ""),

                exit_leg=tp.exit_leg,

                targets_missing=tp.targets_missing,

                trim_source_tag=tp_tag if tp_tag != "—" else ("trim:score" if cw > 0 else "—"),

                tp_partial_frac=tp.partial_frac,

                tp_signal_strength=tp.signal_strength,

                tp_rationale=tp.rationale,

                momentum_override_applied=tp.momentum_override_applied,

                fund_proximity_pct=tp.fund_proximity_pct,

                val_proximity_pct=tp.val_proximity_pct,

            )

        )



    for c in candidates:

        cd = c.model_dump()

        _process(c.ticker, cd, holdings_by_ticker.get(c.ticker))



    for h in holdings_review:

        if h.ticker in tickers_seen:

            continue

        cd = graded_by_ticker.get(h.ticker, {

            "ticker": h.ticker,

            "name": h.name,

            "grade": h.grade,

            "total_score": h.alpha_score,

            "eligible_action": "NO_NEW",

        })

        _process(h.ticker, cd, h)



    order = {
        "Buy-allowed": 0,
        "Buy-ready": 1,
        "Add": 2,
        "Hold": 3,
        "Trim": 4,
        "Replace-review": 5,
        "Exit-review": 6,
        "Exit": 7,
        "Watch": 8,
        "Exclude": 9,
    }

    rows.sort(key=lambda r: (order.get(r.action_state, 9), -r.total_score))

    return rows





def load_signal_board_from_csv(path: Path) -> list[SignalBoardRow]:
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype=str)
    float_fields = {
        "flow_score", "current_weight_pct", "target_weight_pct", "total_score",
        "tp_partial_frac", "tp_signal_strength", "fund_proximity_pct", "val_proximity_pct",
    }
    bool_fields = {"targets_missing", "momentum_override_applied"}
    rows: list[SignalBoardRow] = []
    for raw in df.to_dict(orient="records"):
        item: dict[str, Any] = {}
        for field in SignalBoardRow.__dataclass_fields__:
            val = raw.get(field, "")
            if field in float_fields:
                if val in (None, "", "nan", "None"):
                    item[field] = None if field.endswith("proximity_pct") else 0.0
                else:
                    item[field] = float(val)
            elif field in bool_fields:
                item[field] = str(val).strip().lower() in {"true", "1", "yes"}
            else:
                item[field] = "" if val in (None, "nan") else val
        rows.append(SignalBoardRow(**item))
    return rows


def write_alpha_signal_board(path: Path, rows: list[SignalBoardRow]) -> None:

    df = pd.DataFrame([asdict(r) for r in rows], columns=SIGNAL_BOARD_COLUMNS)

    write_dataframe_csv(path, df, columns=SIGNAL_BOARD_COLUMNS)





def summarize_signal_board(rows: list[SignalBoardRow]) -> dict[str, Any]:

    by_state: dict[str, list[str]] = {}

    for r in rows:

        by_state.setdefault(r.action_state, []).append(f"{r.name}({r.ticker})")

    return {

        "total": len(rows),

        "by_action_state": {k: len(v) for k, v in by_state.items()},

        "buy_allowed": [r.ticker for r in rows if r.action_state == "Buy-allowed"],

        "buy_ready": [r.ticker for r in rows if r.action_state == "Buy-ready"],

        "watch": [r.ticker for r in rows if r.action_state == "Watch"],

        "trim": [r.ticker for r in rows if r.action_state == "Trim"],
        "replace_review": [r.ticker for r in rows if r.action_state == "Replace-review"],
        "exit_review": [r.ticker for r in rows if r.action_state == "Exit-review"],
        "exit": [r.ticker for r in rows if r.action_state == "Exit"],
    }





def _action_state_display(row: SignalBoardRow) -> str:
    """Show raw review vs final state when priority rules override review label."""
    raw_review = str(row.review_action or "").strip()
    review_norm = "" if raw_review.lower() in {"", "nan", "none"} else raw_review
    if row.review_action == "REPLACE_CANDIDATE" and row.action_state == "Trim":
        return f"{row.action_state} (review: REPLACE_CANDIDATE · overweight priority)"
    if row.review_action == "REPLACE_CANDIDATE" and row.action_state == "Replace-review":
        return row.action_state
    if review_norm and review_norm not in {row.action_state, "KEEP", "WATCH"}:
        if row.action_state not in {"Exit", "Exit-review", "Replace-review"}:
            return f"{row.action_state} (review: {review_norm})"
    return row.action_state


def format_signal_board_report_section(rows: list[SignalBoardRow], summary: dict[str, Any]) -> list[str]:

    lines = [

        "## 오늘의 Alpha Action Summary",

        "",

        f"- **Buy-allowed**: {len(summary.get('buy_allowed', []))} · "
        f"**Buy-ready**: {len(summary.get('buy_ready', []))} · "
        f"**Watch**: {len(summary.get('watch', []))} · "
        f"**Trim**: {len(summary.get('trim', []))} · "
        f"**Replace-review**: {len(summary.get('replace_review', []))} · "
        f"**Exit-review**: {len(summary.get('exit_review', []))} · "
        f"**Exit**: {len(summary.get('exit', []))}",
        "",
        "> `Exit`/`Exit-review`는 thesis·리스크 확정 시에만. `Replace-review`는 교체 검토(기본 not executable).",

        "",

        "| 종목 | 상태 | 등급 | 섹터 | 신뢰도 | 부족 조건 | 매수 트리거 |",

        "|------|------|------|------|--------|-----------|-------------|",

    ]

    display_limit = 20
    display_rows = rows[:display_limit]
    for r in display_rows:

        lines.append(

            f"| {r.name} ({r.ticker}) | **{_action_state_display(r)}** | {r.grade} | {r.sector} | "

            f"{r.confidence} | {_truncate_display(r.missing_for_buy, 56)} | "
            f"{_truncate_display(r.buy_trigger, 72)} |"

        )

    if len(rows) > display_limit:
        shown_by_state: dict[str, int] = {}
        for r in display_rows:
            shown_by_state[r.action_state] = shown_by_state.get(r.action_state, 0) + 1
        total_by_state = summary.get("by_action_state") or {}
        partial: list[str] = []
        for state, total in sorted(total_by_state.items()):
            shown = shown_by_state.get(state, 0)
            if int(total) > shown:
                partial.append(f"{state} {shown}/{total} 표시")
        note = ", ".join(partial) if partial else f"전체 {len(rows)}건 중 {display_limit}건만 표시"
        lines.extend([
            "",
            f"> 표는 우선순위 상위 **{display_limit}행**만 표시합니다 — {note}. "
            "전체 목록은 `alpha_signal_board.csv` 참조.",
        ])

    lines.append("")

    return lines


