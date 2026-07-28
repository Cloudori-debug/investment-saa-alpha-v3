"""Early Alpha Engine v0.1 — event/volume/breakout pilot-entry shadow layer."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.data_loader import load_positions
from src.data_refresh.price_store import normalize_ticker

EARLY_ALPHA_DISCLAIMER = (
    "Early Alpha v0.1 is shadow pilot-entry only. It does not create confirmation buy "
    "permission and does not modify trade_actions or final_execution_decision. "
    "Pilot entries require manual approval, stop_level, and Confirmation Engine upgrade for full size."
)

EarlyGrade = str


@dataclass
class EarlyAlphaSignal:
    ticker: str
    name: str
    date: str
    total_score: int
    early_grade: EarlyGrade
    catalyst_type: str
    catalyst_summary: str
    catalyst_score: int
    volume_score: int
    price_action_score: int
    moving_average_score: int
    flow_score: int
    risk_penalty: int
    volume_ratio: float | None
    price_breakout_level: float | None
    support_level: float | None
    stop_level: float | None
    invalidation_condition: str
    allowed_action: str
    allowed_position_fraction: float
    confidence: str
    reason: str
    missing_data: list[str] = field(default_factory=list)
    confirmation_trigger: str = ""
    do_not_chase_zone: str = ""
    pilot_only: bool = True

    def to_row(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "date": self.date,
            "total_score": self.total_score,
            "early_grade": self.early_grade,
            "catalyst_type": self.catalyst_type,
            "catalyst_summary": self.catalyst_summary,
            "catalyst_score": self.catalyst_score,
            "volume_score": self.volume_score,
            "price_action_score": self.price_action_score,
            "moving_average_score": self.moving_average_score,
            "flow_score": self.flow_score,
            "risk_penalty": self.risk_penalty,
            "volume_ratio": self.volume_ratio if self.volume_ratio is not None else "",
            "price_breakout_level": self.price_breakout_level or "",
            "support_level": self.support_level or "",
            "stop_level": self.stop_level or "",
            "invalidation_condition": self.invalidation_condition,
            "allowed_action": self.allowed_action,
            "allowed_position_fraction": self.allowed_position_fraction,
            "confidence": self.confidence,
            "reason": self.reason,
            "missing_data": ";".join(self.missing_data),
            "confirmation_trigger": self.confirmation_trigger,
            "do_not_chase_zone": self.do_not_chase_zone,
            "pilot_only": self.pilot_only,
        }


def load_early_alpha_config(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "early_alpha_config.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _parse_date(s: str) -> datetime | None:
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _load_prices(data_dir: Path) -> dict[str, dict[str, Any]]:
    path = data_dir / "prices.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    out: dict[str, dict[str, Any]] = {}
    for r in df.to_dict(orient="records"):
        t = normalize_ticker(str(r.get("ticker", "")))
        if not t:
            continue
        row: dict[str, Any] = {"date": r.get("date", "")}
        for col in df.columns:
            if col in {"date", "ticker"}:
                continue
            try:
                row[col] = float(r[col]) if str(r[col]).strip() else None
            except ValueError:
                row[col] = r[col]
        out[t] = row
    return out


def _load_price_history_recent(data_dir: Path, ticker: str, n: int = 10) -> list[dict[str, Any]]:
    path = data_dir / "prices_history.csv"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if normalize_ticker(row.get("ticker", "")) == ticker:
                rows.append(row)
    return rows[-n:]


def _load_candidate_universe(data_dir: Path, output_dir: Path, config: dict[str, Any]) -> dict[str, str]:
    names: dict[str, str] = {}
    sources = config.get("candidate_sources") or []

    if "positions_kr_alpha" in sources:
        pos_path = data_dir / "positions.csv"
        if pos_path.exists():
            for p in load_positions(pos_path):
                if p.asset_group == "kr_alpha" and p.ticker not in {"CASH", "PORTFOLIO"}:
                    t = normalize_ticker(p.ticker)
                    names[t] = p.name or t

    if "alpha_shortlist" in sources:
        for fname in ("alpha_shortlist.csv", "alpha_candidates.csv"):
            path = output_dir / fname
            if path.exists():
                df = pd.read_csv(path, dtype=str, keep_default_na=False)
                for r in df.to_dict(orient="records"):
                    t = normalize_ticker(str(r.get("ticker", "")))
                    if t:
                        names.setdefault(t, str(r.get("name", t)))

    for src, fname in (
        ("hakedaka_primary_hunt", "hakedaka_primary_hunt_list.csv"),
        ("hakedaka_preliminary_hunt", "hakedaka_preliminary_hunt_list.csv"),
    ):
        if src in sources:
            path = output_dir / fname
            if path.exists():
                df = pd.read_csv(path, dtype=str, keep_default_na=False)
                for r in df.to_dict(orient="records"):
                    t = normalize_ticker(str(r.get("ticker", "")))
                    if t:
                        names.setdefault(t, str(r.get("name", t)))

    max_n = int(config.get("max_candidates", 120))
    if len(names) > max_n:
        return dict(list(names.items())[:max_n])
    return names


def _load_dart_events(output_dir: Path, ticker: str, as_of: str, lookback_days: int) -> list[dict[str, str]]:
    path = output_dir / "hakedaka_dart_events.csv"
    if not path.exists():
        return []
    as_of_dt = _parse_date(as_of) or datetime.now()
    cutoff = as_of_dt - timedelta(days=lookback_days)
    events: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if normalize_ticker(row.get("ticker", "")) != ticker:
                continue
            ed = _parse_date(row.get("event_date", ""))
            if ed and ed >= cutoff:
                events.append(row)
    return events


def _score_catalyst(
    events: list[dict[str, str]],
    config: dict[str, Any],
) -> tuple[int, str, str, bool, list[str]]:
    missing: list[str] = []
    if not events:
        missing.append("dart_events")
        return 0, "none", "No recent DART/disclosure catalyst", False, missing

    kw = config.get("catalyst_keywords") or {}
    denial_kw = config.get("denial_keywords") or []
    has_denial = False
    best_type = "none"
    best_score = 0
    best_title = ""

    for ev in events:
        title = str(ev.get("report_title", ""))
        types = str(ev.get("event_types", ""))
        combined = f"{title} {types}".lower()

        for d in denial_kw:
            if d.lower() in combined or d in title:
                has_denial = True
                break

        for ctype, words in kw.items():
            hit = sum(1 for w in words if w.lower() in combined or w in title)
            if hit:
                raw = min(25, 10 + hit * 5)
                if ctype in {"ma_tender", "buyback"}:
                    raw = min(25, raw + 5)
                if raw > best_score:
                    best_score = raw
                    best_type = ctype
                    best_title = title.strip()[:80]

    if has_denial:
        return 0, best_type or "denied", f"Official denial/rumor rebuttal — {best_title}", True, missing

    cap = int((config.get("score_caps") or {}).get("catalyst_max", 25))
    return min(best_score, cap), best_type, best_title or "Recent disclosure activity", False, missing


def _volume_ratio(px: dict[str, Any], history: list[dict[str, Any]]) -> float | None:
    tv20 = float(px.get("trading_value_20d") or 0)
    tv60 = float(px.get("trading_value_60d") or 0)
    if tv20 > 0 and tv60 > 0:
        daily_20 = tv20 / 20.0
        daily_60 = tv60 / 60.0
        if daily_60 > 0:
            return round(daily_20 / daily_60, 2)
    if len(history) >= 5:
        try:
            recent = [float(h.get("trading_value_20d") or 0) for h in history[-5:]]
            base = [float(h.get("trading_value_20d") or 0) for h in history[:-5]]
            r_avg = sum(recent) / max(len(recent), 1)
            b_avg = sum(base) / max(len(base), 1) if base else 0
            if b_avg > 0:
                return round(r_avg / b_avg, 2)
        except (TypeError, ValueError):
            pass
    return None


def _score_volume(
    px: dict[str, Any],
    history: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[int, float | None, list[str]]:
    missing: list[str] = []
    ratio = _volume_ratio(px, history)
    if ratio is None:
        missing.append("volume_ratio")
        return 0, None, missing

    vol_cfg = config.get("volume") or {}
    e3_min = float(vol_cfg.get("e3_min_ratio", 3.0))
    e2_min = float(vol_cfg.get("e2_min_ratio", 1.8))
    cap = int((config.get("score_caps") or {}).get("volume_max", 20))

    if ratio >= e3_min:
        score = cap
    elif ratio >= e2_min:
        score = int(cap * 0.65)
    elif ratio >= 1.2:
        score = int(cap * 0.35)
    else:
        score = 0
    return score, ratio, missing


def _score_price_action(px: dict[str, Any], config: dict[str, Any]) -> tuple[int, float | None, float | None]:
    close = float(px.get("close") or 0)
    high52 = float(px.get("high_52w") or 0)
    dist = float(px.get("distance_from_52w_high") or 0)
    ret1m = float(px.get("return_1m") or 0)
    ret3m = float(px.get("return_3m") or 0)
    cap = int((config.get("score_caps") or {}).get("price_action_max", 20))

    if close <= 0:
        return 0, None, None

    support = round(close * 0.93, 2)
    breakout = None
    score = 0

    if dist >= 0.95:
        score += int(cap * 0.5)
        breakout = close
    elif dist >= 0.85 and ret1m > 0.05:
        score += int(cap * 0.75)
        breakout = close
    elif ret1m > 0.08 and ret3m < 0:
        score += int(cap * 0.6)
        breakout = close
    elif ret1m > 0.03:
        score += int(cap * 0.3)

    if high52 > 0 and close >= high52 * 0.98:
        breakout = high52
        score = cap

    return min(score, cap), breakout, support


def _score_moving_average(px: dict[str, Any], config: dict[str, Any]) -> int:
    ret1m = float(px.get("return_1m") or 0)
    ret3m = float(px.get("return_3m") or 0)
    cap = int((config.get("score_caps") or {}).get("moving_average_max", 15))
    score = 0
    if ret1m > 0 and ret3m < 0:
        score += int(cap * 0.7)
    elif ret1m > ret3m > -0.1:
        score += int(cap * 0.45)
    elif ret1m > 0:
        score += int(cap * 0.25)
    return min(score, cap)


def _score_flow(px: dict[str, Any], config: dict[str, Any]) -> int:
    cap = int((config.get("score_caps") or {}).get("flow_max", 10))
    ret1m = float(px.get("return_1m") or 0)
    vol = float(px.get("volatility_60d") or 0)
    if ret1m > 0.05 and vol < 0.05:
        return cap
    if ret1m > 0:
        return int(cap * 0.4)
    return 0


def _risk_penalty(
    *,
    has_denial: bool,
    volume_ratio: float | None,
    catalyst_score: int,
    px: dict[str, Any],
    config: dict[str, Any],
) -> int:
    cap = int((config.get("score_caps") or {}).get("risk_penalty_max", -30))
    penalty = 0
    if has_denial:
        penalty -= 25
    if catalyst_score == 0:
        penalty -= 8
    vol = float(px.get("volatility_60d") or 0)
    if vol > 0.08:
        penalty -= 10
    elif vol > 0.06:
        penalty -= 5
    if volume_ratio is not None and volume_ratio < 1.0:
        penalty -= 5
    return max(cap, penalty)


def _grade_from_score(total: int, thresholds: dict[str, Any]) -> EarlyGrade:
    if total <= int(thresholds.get("e0_max", 39)):
        return "E0"
    if total <= int(thresholds.get("e1_max", 54)):
        return "E1"
    if total <= int(thresholds.get("e2_max", 69)):
        return "E2"
    if total <= int(thresholds.get("e3_max", 84)):
        return "E3"
    return "E4"


def _apply_grade_caps(
    grade: EarlyGrade,
    *,
    catalyst_score: int,
    volume_ratio: float | None,
    has_denial: bool,
    config: dict[str, Any],
) -> EarlyGrade:
    if has_denial:
        return "E0"
    min_cat = int(config.get("min_catalyst_for_e3", 10))
    if config.get("weak_catalyst_e3_cap", True) and catalyst_score < min_cat:
        if grade in {"E3", "E4"}:
            return "E2"
    if volume_ratio is None and grade in {"E3", "E4"}:
        return "E2"
    vol_cfg = config.get("volume") or {}
    if volume_ratio is not None and volume_ratio < float(vol_cfg.get("e3_min_ratio", 3.0)):
        if grade == "E3":
            return "E2"
    return grade


def _stop_and_invalidation(
    close: float,
    support: float | None,
    config: dict[str, Any],
) -> tuple[float | None, str]:
    if close <= 0:
        return None, "No price — stop undefined"
    pct = float((config.get("stop_rules") or {}).get("pct_below_entry", 0.07))
    stop = round(close * (1 - pct), 2)
    if support and support < close:
        stop = round(min(stop, support), 2)
    inv = (
        f"Exit if close < {stop} (-7% from entry or support break); "
        "volume fade; breakout failure; official denial; no follow-through 3-5 sessions"
    )
    return stop, inv


def _pilot_action(
    grade: EarlyGrade,
    stop_level: float | None,
    config: dict[str, Any],
) -> tuple[str, float, str]:
    fr = config.get("pilot_fractions") or {}
    abs_max = float(fr.get("absolute_max", 0.25))

    if grade == "E0":
        return "noise", 0.0, "No action"
    if grade == "E1":
        return "watch", 0.0, "Observe only — no pilot entry"
    if grade == "E4":
        return "confirmation_candidate", 0.0, "Escalate to Confirmation Engine — no early pilot add"
    if stop_level is None:
        return "watch", 0.0, "stop_level missing — pilot_entry blocked"

    if grade == "E2":
        frac = min(float(fr.get("e2", 0.10)), abs_max)
        return "pilot_entry_10", frac, f"Pilot up to {frac:.0%} of target alpha weight"
    if grade == "E3":
        frac = min(float(fr.get("e3_max", 0.25)), abs_max)
        return "pilot_entry_20_25", frac, f"Pilot up to {frac:.0%} of target alpha weight (volume confirmed)"
    return "watch", 0.0, "Ungraded"


def _confidence(grade: EarlyGrade, catalyst_score: int, volume_ratio: float | None) -> str:
    if grade in {"E0", "E1"}:
        return "low"
    if grade == "E2":
        return "medium" if catalyst_score >= 10 else "low-medium"
    if grade == "E3":
        return "medium-high" if volume_ratio and volume_ratio >= 3 else "medium"
    return "high"


def score_early_alpha_ticker(
    *,
    ticker: str,
    name: str,
    as_of: str,
    px: dict[str, Any] | None,
    events: list[dict[str, str]],
    config: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
) -> EarlyAlphaSignal:
    missing: list[str] = []
    if not px:
        missing.append("price")
        return EarlyAlphaSignal(
            ticker=ticker, name=name, date=as_of, total_score=0, early_grade="E0",
            catalyst_type="none", catalyst_summary="", catalyst_score=0,
            volume_score=0, price_action_score=0, moving_average_score=0, flow_score=0,
            risk_penalty=0, volume_ratio=None, price_breakout_level=None,
            support_level=None, stop_level=None,
            invalidation_condition="No price data",
            allowed_action="noise", allowed_position_fraction=0.0,
            confidence="low", reason="Missing price", missing_data=missing,
        )

    cat_score, cat_type, cat_summary, has_denial, cat_missing = _score_catalyst(events, config)
    missing.extend(cat_missing)

    vol_score, vol_ratio, vol_missing = _score_volume(px, history or [], config)
    missing.extend(vol_missing)

    pa_score, breakout, support = _score_price_action(px, config)
    ma_score = _score_moving_average(px, config)
    flow_score = _score_flow(px, config)
    risk = _risk_penalty(
        has_denial=has_denial,
        volume_ratio=vol_ratio,
        catalyst_score=cat_score,
        px=px,
        config=config,
    )

    total = max(0, min(100, cat_score + vol_score + pa_score + ma_score + flow_score + risk))
    thresholds = config.get("grade_thresholds") or {}
    grade = _grade_from_score(total, thresholds)
    grade = _apply_grade_caps(
        grade,
        catalyst_score=cat_score,
        volume_ratio=vol_ratio,
        has_denial=has_denial,
        config=config,
    )

    close = float(px.get("close") or 0)
    stop, invalidation = _stop_and_invalidation(close, support, config)
    action, frac, action_reason = _pilot_action(grade, stop, config)

    chase = ""
    if breakout and close > 0:
        chase = f"Do not chase above {round(breakout * 1.05, 2)} (+5% from breakout)"

    confirm = ""
    if grade == "E4":
        confirm = "QVM grade A/B + trend confirmation + volume sustain → Confirmation Engine full size"
    elif grade in {"E2", "E3"}:
        confirm = "Upgrade when Confirmation Engine Buy-allowed + Alpha gate GREEN"

    reason_parts = [
        f"catalyst={cat_score}",
        f"volume={vol_score}",
        f"price={pa_score}",
        f"ma={ma_score}",
        f"flow={flow_score}",
        f"risk={risk}",
        action_reason,
    ]

    return EarlyAlphaSignal(
        ticker=ticker,
        name=name,
        date=as_of,
        total_score=total,
        early_grade=grade,
        catalyst_type=cat_type,
        catalyst_summary=cat_summary,
        catalyst_score=cat_score,
        volume_score=vol_score,
        price_action_score=pa_score,
        moving_average_score=ma_score,
        flow_score=flow_score,
        risk_penalty=risk,
        volume_ratio=vol_ratio,
        price_breakout_level=breakout,
        support_level=support,
        stop_level=stop,
        invalidation_condition=invalidation,
        allowed_action=action,
        allowed_position_fraction=frac,
        confidence=_confidence(grade, cat_score, vol_ratio),
        reason=" · ".join(reason_parts),
        missing_data=sorted(set(missing)),
        confirmation_trigger=confirm,
        do_not_chase_zone=chase,
    )


def build_early_alpha_decision(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or load_early_alpha_config(data_dir)
    candidates = _load_candidate_universe(data_dir, output_dir, cfg)
    prices = _load_prices(data_dir)
    lookback = int(cfg.get("dart_lookback_days", 30))

    signals: list[EarlyAlphaSignal] = []
    for ticker, name in sorted(candidates.items()):
        px = prices.get(ticker)
        events = _load_dart_events(output_dir, ticker, as_of, lookback)
        history = _load_price_history_recent(data_dir, ticker)
        sig = score_early_alpha_ticker(
            ticker=ticker,
            name=name,
            as_of=as_of,
            px=px,
            events=events,
            config=cfg,
            history=history,
        )
        signals.append(sig)

    signals.sort(key=lambda s: (-s.total_score, s.ticker))
    pilot = [s for s in signals if s.allowed_action.startswith("pilot_entry")]
    watch = [s for s in signals if s.early_grade == "E1"]
    confirm = [s for s in signals if s.early_grade == "E4"]

    return {
        "phase": "Early-Alpha-v0.1",
        "mode": "shadow_pilot_only",
        "execution_authority": "none",
        "affects_trade_actions": False,
        "affects_final_execution": False,
        "disclaimer": EARLY_ALPHA_DISCLAIMER,
        "as_of": as_of,
        "candidate_count": len(signals),
        "pilot_entry_count": len(pilot),
        "watch_count": len(watch),
        "confirmation_candidate_count": len(confirm),
        "signals": [s.to_row() for s in signals],
        "top_pilot": [s.to_row() for s in pilot[:5]],
        "top_watch": [s.to_row() for s in watch[:5]],
    }


from src.report.display_format import shadow_opportunity_action_label


def build_early_alpha_brief_md(decision: dict[str, Any]) -> str:
    lines = [
        "# Early Alpha Brief (v0.1 — shadow pilot only)",
        "",
        f"> {decision.get('disclaimer', EARLY_ALPHA_DISCLAIMER)}",
        "",
        f"- **As of**: {decision.get('as_of', '—')}",
        f"- **Candidates**: {decision.get('candidate_count', 0)} · "
        f"pilot {decision.get('pilot_entry_count', 0)} · "
        f"watch {decision.get('watch_count', 0)} · "
        f"confirmation {decision.get('confirmation_candidate_count', 0)}",
        "",
        "## Top shadow pilot candidates (execution prohibited)",
        "",
        "| Ticker | Score | Grade | Action | Pilot frac | Stop | Catalyst |",
        "|--------|-------|-------|--------|------------|------|----------|",
    ]
    for row in decision.get("top_pilot") or []:
        lines.append(
            f"| {row.get('ticker')} | {row.get('total_score')} | {row.get('early_grade')} | "
            f"{shadow_opportunity_action_label(str(row.get('allowed_action', '')))} | {row.get('allowed_position_fraction')} | "
            f"{row.get('stop_level')} | {str(row.get('catalyst_summary', ''))[:40]} |"
        )
    if not decision.get("top_pilot"):
        lines.append("| — | — | — | — | — | — | — |")

    lines.extend([
        "",
        "## Rules reminder",
        "",
        "- Early signal ≠ confirmation buy",
        "- Pilot max = 25% of target alpha weight per ticker",
        "- stop_level required for pilot_entry",
        "- E4 → Confirmation Engine only",
        "",
    ])
    return "\n".join(lines)


def write_early_alpha_outputs(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision = build_early_alpha_decision(data_dir, output_dir, as_of=as_of, config=config)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "early_alpha_decision.json"
    json_path.write_text(json.dumps(decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    csv_path = output_dir / "early_alpha_signals.csv"
    rows = decision.get("signals") or []
    if rows:
        fieldnames = list(rows[0].keys())
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    else:
        csv_path.write_text("ticker,name,date,total_score,early_grade\n", encoding="utf-8-sig")

    md_path = output_dir / "early_alpha_brief.md"
    md_path.write_text(build_early_alpha_brief_md(decision) + "\n", encoding="utf-8")

    return decision
