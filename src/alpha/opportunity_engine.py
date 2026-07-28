"""Alpha Opportunity Engine v0.2 — general movement-timing shadow layer."""
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
from src.alpha.opportunity_shared import (
    grade_from_score,
    load_price_history,
    load_prices_map,
    parse_date,
    pilot_action,
    stop_and_invalidation,
    volume_ratio,
)

OPPORTUNITY_DISCLAIMER = (
    "Alpha Opportunity v0.2 is shadow pilot-entry only. It detects when quality/alpha "
    "candidates begin to move — not confirmation buy permission. Does not modify "
    "trade_actions or final_execution_decision."
)

OpportunityGrade = str

E3_SIGNAL_LABELS = (
    "volume_3x",
    "box_breakout_60d",
    "ma_recovery",
    "flow_proxy",
    "earnings_improvement",
    "sector_rs",
    "value_shareholder",
)


@dataclass
class OpportunitySignal:
    ticker: str
    name: str
    date: str
    sector: str
    total_score: int
    opportunity_grade: OpportunityGrade
    volume_score: int
    price_structure_score: int
    fundamental_momentum_score: int
    flow_score: int
    valuation_rerating_score: int
    sector_momentum_score: int
    risk_penalty: int
    catalyst_type: str
    catalyst_summary: str
    catalyst_denied: bool
    volume_ratio: float | None
    price_breakout_level: float | None
    support_level: float | None
    stop_level: float | None
    e3_composite_count: int
    e3_signals_met: list[str] = field(default_factory=list)
    e3_signals_missing: list[str] = field(default_factory=list)
    missing_confirmation: str = ""
    invalidation_condition: str = ""
    allowed_action: str = "noise"
    allowed_position_fraction: float = 0.0
    confidence: str = "low"
    reason: str = ""
    missing_data: list[str] = field(default_factory=list)
    confirmation_trigger: str = ""
    do_not_chase_zone: str = ""
    pilot_only: bool = True

    def to_row(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "date": self.date,
            "sector": self.sector,
            "total_score": self.total_score,
            "opportunity_grade": self.opportunity_grade,
            "volume_score": self.volume_score,
            "price_structure_score": self.price_structure_score,
            "fundamental_momentum_score": self.fundamental_momentum_score,
            "flow_score": self.flow_score,
            "valuation_rerating_score": self.valuation_rerating_score,
            "sector_momentum_score": self.sector_momentum_score,
            "risk_penalty": self.risk_penalty,
            "catalyst_type": self.catalyst_type,
            "catalyst_summary": self.catalyst_summary,
            "catalyst_denied": self.catalyst_denied,
            "volume_ratio": self.volume_ratio if self.volume_ratio is not None else "",
            "price_breakout_level": self.price_breakout_level or "",
            "support_level": self.support_level or "",
            "stop_level": self.stop_level or "",
            "e3_composite_count": self.e3_composite_count,
            "e3_signals_met": ";".join(self.e3_signals_met),
            "e3_signals_missing": ";".join(self.e3_signals_missing),
            "missing_confirmation": self.missing_confirmation,
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

    def to_breakdown_row(self) -> dict[str, Any]:
        caps = {
            "volume": 20,
            "price_structure": 20,
            "fundamental_momentum": 20,
            "flow": 15,
            "valuation_rerating": 15,
            "sector_momentum": 10,
            "risk": -30,
        }
        blockers: list[str] = []
        if self.opportunity_grade == "E0":
            blockers.append("score_too_low")
        if self.opportunity_grade == "E1":
            blockers.append("watch_only")
        if self.volume_ratio is None and self.opportunity_grade in {"E3", "E4"}:
            blockers.append("volume_data_missing")
        if self.e3_composite_count < 3 and self.opportunity_grade in {"E3", "E4"}:
            blockers.append("e3_composite_insufficient")
        if self.allowed_action.startswith("pilot_entry") and not self.stop_level:
            blockers.append("stop_level_missing")
        if self.catalyst_denied:
            blockers.append("catalyst_denied")

        return {
            "ticker": self.ticker,
            "name": self.name,
            "date": self.date,
            "sector": self.sector,
            "opportunity_grade": self.opportunity_grade,
            "total_score": self.total_score,
            "allowed_action": self.allowed_action,
            "allowed_position_fraction": self.allowed_position_fraction,
            "volume_score": self.volume_score,
            "volume_cap": caps["volume"],
            "price_structure_score": self.price_structure_score,
            "price_structure_cap": caps["price_structure"],
            "fundamental_momentum_score": self.fundamental_momentum_score,
            "fundamental_momentum_cap": caps["fundamental_momentum"],
            "flow_score": self.flow_score,
            "flow_cap": caps["flow"],
            "valuation_rerating_score": self.valuation_rerating_score,
            "valuation_rerating_cap": caps["valuation_rerating"],
            "sector_momentum_score": self.sector_momentum_score,
            "sector_momentum_cap": caps["sector_momentum"],
            "risk_penalty": self.risk_penalty,
            "risk_cap": caps["risk"],
            "e3_composite_count": self.e3_composite_count,
            "e3_signals_met": ";".join(self.e3_signals_met),
            "e3_signals_missing": ";".join(self.e3_signals_missing),
            "catalyst_type": self.catalyst_type,
            "catalyst_denied": self.catalyst_denied,
            "missing_confirmation": self.missing_confirmation,
            "pilot_blockers": ";".join(blockers) if blockers else "",
            "missing_data": ";".join(self.missing_data),
            "reason": self.reason,
        }


def load_opportunity_config(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "opportunity_engine_config.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_sector_map(data_dir: Path) -> dict[str, str]:
    path = data_dir / "universe.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return {
        normalize_ticker(str(r.get("ticker", ""))): str(r.get("sector", "") or "unknown")
        for r in df.to_dict(orient="records")
        if normalize_ticker(str(r.get("ticker", "")))
    }


def _load_alpha_meta(output_dir: Path) -> dict[str, dict[str, Any]]:
    path = output_dir / "alpha_candidates.csv"
    if not path.exists():
        return {}
    meta: dict[str, dict[str, Any]] = {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for r in df.to_dict(orient="records"):
        t = normalize_ticker(str(r.get("ticker", "")))
        if not t:
            continue
        try:
            meta[t] = {
                "name": str(r.get("name", t)),
                "sector": str(r.get("sector", "unknown") or "unknown"),
                "total_score": float(r.get("total_score") or 0),
                "quality_score": float(r.get("quality_score") or 0),
                "valuation_score": float(r.get("valuation_score") or 0),
                "momentum_score": float(r.get("momentum_score") or 0),
                "shareholder_return_score": float(r.get("shareholder_return_score") or 0),
                "grade": str(r.get("grade", "")),
            }
        except (TypeError, ValueError):
            continue
    return meta


def _load_fundamentals_map(data_dir: Path) -> dict[str, dict[str, Any]]:
    path = data_dir / "fundamentals.csv"
    if not path.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for r in df.to_dict(orient="records"):
        t = normalize_ticker(str(r.get("ticker", "")))
        if t:
            out[t] = r
    return out


def _add_csv_tickers(
    path: Path,
    names: dict[str, dict[str, str]],
    *,
    sector_map: dict[str, str],
) -> None:
    if not path.exists():
        return
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for r in df.to_dict(orient="records"):
        t = normalize_ticker(str(r.get("ticker", "")))
        if not t:
            continue
        names.setdefault(
            t,
            {
                "name": str(r.get("name", t)),
                "sector": str(r.get("sector") or sector_map.get(t, "unknown") or "unknown"),
            },
        )


def _unusual_volume_tickers(
    prices: dict[str, dict[str, Any]],
    data_dir: Path,
    top_n: int,
) -> list[str]:
    scored: list[tuple[float, str]] = []
    for ticker, px in prices.items():
        history = load_price_history(data_dir, ticker, n=60)
        ratio = volume_ratio(px, history)
        if ratio is not None and ratio >= 1.0:
            scored.append((ratio, ticker))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t for _, t in scored[:top_n]]


def _sector_momentum_tickers(
    alpha_meta: dict[str, dict[str, Any]],
    per_sector: int,
) -> list[str]:
    by_sector: dict[str, list[tuple[float, str]]] = {}
    for ticker, m in alpha_meta.items():
        sector = str(m.get("sector", "unknown") or "unknown")
        mom = float(m.get("momentum_score") or 0)
        by_sector.setdefault(sector, []).append((mom, ticker))
    out: list[str] = []
    for sector in sorted(by_sector):
        leaders = sorted(by_sector[sector], key=lambda x: (-x[0], x[1]))[:per_sector]
        out.extend(t for _, t in leaders)
    return out


def _quality_value_tickers(alpha_meta: dict[str, dict[str, Any]], top_n: int) -> list[str]:
    ranked = sorted(
        alpha_meta.items(),
        key=lambda kv: (-float(kv[1].get("total_score") or 0), kv[0]),
    )
    return [t for t, _ in ranked[:top_n]]


def load_opportunity_universe(
    data_dir: Path,
    output_dir: Path,
    config: dict[str, Any],
) -> dict[str, dict[str, str]]:
    sources = set(config.get("candidate_sources") or [])
    sector_map = _load_sector_map(data_dir)
    alpha_meta = _load_alpha_meta(output_dir)
    prices = load_prices_map(data_dir)
    names: dict[str, dict[str, str]] = {}

    if "positions_kr_alpha" in sources:
        pos_path = data_dir / "positions.csv"
        if pos_path.exists():
            for p in load_positions(pos_path):
                if p.asset_group == "kr_alpha" and p.ticker not in {"CASH", "PORTFOLIO"}:
                    t = normalize_ticker(p.ticker)
                    names[t] = {
                        "name": p.name or t,
                        "sector": sector_map.get(t, "unknown"),
                    }

    if "alpha_shortlist" in sources:
        _add_csv_tickers(output_dir / "alpha_shortlist.csv", names, sector_map=sector_map)

    if "alpha_candidates_top" in sources or "alpha_candidates" in sources:
        _add_csv_tickers(output_dir / "alpha_candidates.csv", names, sector_map=sector_map)

    if "alpha_portfolio_proposal" in sources:
        _add_csv_tickers(output_dir / "alpha_portfolio_proposal.csv", names, sector_map=sector_map)

    for src, fname in (
        ("hakedaka_primary_hunt", "hakedaka_primary_hunt_list.csv"),
        ("hakedaka_preliminary_hunt", "hakedaka_preliminary_hunt_list.csv"),
    ):
        if src in sources:
            _add_csv_tickers(output_dir / fname, names, sector_map=sector_map)

    qv_n = int(config.get("quality_value_top_n", 80))
    if "quality_value_top" in sources:
        for t in _quality_value_tickers(alpha_meta, qv_n):
            m = alpha_meta.get(t, {})
            names.setdefault(
                t,
                {"name": str(m.get("name", t)), "sector": str(m.get("sector", "unknown"))},
            )

    per_sector = int(config.get("sector_leaders_per_sector", 2))
    if "sector_momentum_leaders" in sources:
        for t in _sector_momentum_tickers(alpha_meta, per_sector):
            m = alpha_meta.get(t, {})
            names.setdefault(
                t,
                {"name": str(m.get("name", t)), "sector": str(m.get("sector", "unknown"))},
            )

    uv_n = int(config.get("unusual_volume_top_n", 40))
    if "unusual_volume" in sources:
        for t in _unusual_volume_tickers(prices, data_dir, uv_n):
            names.setdefault(t, {"name": t, "sector": sector_map.get(t, "unknown")})

    max_n = int(config.get("max_candidates", 200))
    if len(names) > max_n:
        return dict(list(names.items())[:max_n])
    return names


def _load_dart_events(
    output_dir: Path,
    ticker: str,
    as_of: str,
    lookback_days: int,
) -> list[dict[str, str]]:
    path = output_dir / "hakedaka_dart_events.csv"
    if not path.exists():
        return []
    as_of_dt = parse_date(as_of) or datetime.now()
    cutoff = as_of_dt - timedelta(days=lookback_days)
    events: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if normalize_ticker(row.get("ticker", "")) != ticker:
                continue
            ed = parse_date(row.get("event_date", ""))
            if ed and ed >= cutoff:
                events.append(row)
    return events


def _catalyst_metadata(
    events: list[dict[str, str]],
    config: dict[str, Any],
) -> tuple[str, str, bool, list[str]]:
    missing: list[str] = []
    if not events:
        missing.append("dart_events")
        return "none", "No recent DART/disclosure catalyst", False, missing

    kw = config.get("catalyst_keywords") or {}
    denial_kw = config.get("denial_keywords") or []
    has_denial = False
    best_type = "none"
    best_hits = 0
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
            if hit > best_hits:
                best_hits = hit
                best_type = ctype
                best_title = title.strip()[:80]

    if has_denial:
        ctype = "denied" if best_type == "none" else best_type
        return ctype, f"Official denial/rumor rebuttal — {best_title}", True, missing

    if best_hits == 0:
        return "none", "Recent disclosure activity (unclassified)", False, missing
    return best_type, best_title or "Recent disclosure activity", False, missing


def _score_volume_pillar(
    px: dict[str, Any],
    history: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[int, float | None, list[str]]:
    missing: list[str] = []
    ratio = volume_ratio(px, history)
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
    elif ratio >= float(vol_cfg.get("unusual_min_ratio", 1.5)):
        score = int(cap * 0.4)
    elif ratio >= 1.2:
        score = int(cap * 0.25)
    else:
        score = 0
    return score, ratio, missing


def _box_breakout_60d(
    close: float,
    history: list[dict[str, Any]],
) -> tuple[bool, float | None]:
    if close <= 0 or len(history) < 20:
        return False, None
    try:
        highs = [float(h.get("close") or 0) for h in history if float(h.get("close") or 0) > 0]
    except (TypeError, ValueError):
        return False, None
    if len(highs) < 10:
        return False, None
    box_high = max(highs[:-1]) if len(highs) > 1 else max(highs)
    if box_high <= 0:
        return False, None
    if close >= box_high * 1.005:
        return True, round(box_high, 2)
    return False, round(box_high, 2)


def _score_price_structure(
    px: dict[str, Any],
    history: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[int, float | None, float | None]:
    close = float(px.get("close") or 0)
    high52 = float(px.get("high_52w") or 0)
    dist = float(px.get("distance_from_52w_high") or 0)
    ret1m = float(px.get("return_1m") or 0)
    ret3m = float(px.get("return_3m") or 0)
    cap = int((config.get("score_caps") or {}).get("price_structure_max", 20))

    if close <= 0:
        return 0, None, None

    support = round(close * 0.93, 2)
    breakout = None
    score = 0
    box_hit, box_level = _box_breakout_60d(close, history)

    if box_hit:
        score += int(cap * 0.55)
        breakout = close
    if dist >= 0.95:
        score += int(cap * 0.35)
        breakout = close
    elif dist >= 0.85 and ret1m > 0.05:
        score += int(cap * 0.5)
        breakout = close
    elif ret1m > 0.08 and ret3m < 0:
        score += int(cap * 0.45)
        breakout = close
    elif ret1m > 0.03:
        score += int(cap * 0.2)

    if high52 > 0 and close >= high52 * 0.98:
        breakout = high52
        score = cap
    elif box_level and breakout is None and box_hit:
        breakout = box_level

    return min(score, cap), breakout, support


def _score_fundamental_momentum(
    fund: dict[str, Any] | None,
    px: dict[str, Any],
    config: dict[str, Any],
) -> tuple[int, list[str]]:
    missing: list[str] = []
    cap = int((config.get("score_caps") or {}).get("fundamental_momentum_max", 20))
    score = 0

    if fund:
        try:
            eyoy = fund.get("earnings_yoy", "")
            if eyoy not in ("", None):
                ey = float(eyoy)
                if ey > 0.15:
                    score += int(cap * 0.7)
                elif ey > 0:
                    score += int(cap * 0.45)
                elif ey > -0.1:
                    score += int(cap * 0.15)
            else:
                missing.append("earnings_yoy")
        except (TypeError, ValueError):
            missing.append("earnings_yoy")
    else:
        missing.append("fundamentals")

    ret1m = float(px.get("return_1m") or 0)
    ret3m = float(px.get("return_3m") or 0)
    if ret1m > ret3m > -0.05:
        score += int(cap * 0.25)

    return min(score, cap), missing


def _score_flow_pillar(px: dict[str, Any], config: dict[str, Any]) -> int:
    cap = int((config.get("score_caps") or {}).get("flow_max", 15))
    ret1m = float(px.get("return_1m") or 0)
    ret3m = float(px.get("return_3m") or 0)
    vol = float(px.get("volatility_60d") or 0)
    if ret1m > 0.06 and vol < 0.05:
        return cap
    if ret1m > 0.03 and ret3m <= 0:
        return int(cap * 0.65)
    if ret1m > 0:
        return int(cap * 0.35)
    return 0


def _flow_proxy_met(px: dict[str, Any]) -> bool:
    ret1m = float(px.get("return_1m") or 0)
    vol = float(px.get("volatility_60d") or 0)
    return ret1m > 0.04 and vol < 0.06


def _score_valuation_rerating(
    alpha: dict[str, Any] | None,
    px: dict[str, Any],
    config: dict[str, Any],
) -> tuple[int, list[str]]:
    missing: list[str] = []
    cap = int((config.get("score_caps") or {}).get("valuation_rerating_max", 15))
    score = 0

    if alpha:
        v = float(alpha.get("valuation_score") or 0)
        q = float(alpha.get("quality_score") or 0)
        if v >= 60 and q >= 50:
            score = cap
        elif v >= 50:
            score = int(cap * 0.65)
        elif v >= 40:
            score = int(cap * 0.35)
    else:
        missing.append("alpha_valuation")

    dist = float(px.get("distance_from_52w_high") or 0)
    if dist < 0.75 and score < cap:
        score = min(cap, score + int(cap * 0.2))

    return min(score, cap), missing


def _sector_avg_momentum(
    sector: str,
    alpha_meta: dict[str, dict[str, Any]],
) -> float | None:
    vals = [
        float(m.get("momentum_score") or 0)
        for m in alpha_meta.values()
        if str(m.get("sector", "unknown")) == sector
    ]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _score_sector_momentum(
    sector: str,
    px: dict[str, Any],
    alpha: dict[str, Any] | None,
    alpha_meta: dict[str, dict[str, Any]],
    config: dict[str, Any],
) -> int:
    cap = int((config.get("score_caps") or {}).get("sector_momentum_max", 10))
    ret1m = float(px.get("return_1m") or 0)
    sector_avg = _sector_avg_momentum(sector, alpha_meta)
    ticker_mom = float(alpha.get("momentum_score") or 0) if alpha else ret1m * 100

    if sector_avg is not None and ticker_mom > sector_avg + 5:
        return cap
    if ret1m > 0.05:
        return int(cap * 0.6)
    if ticker_mom > 55:
        return int(cap * 0.4)
    return 0


def _risk_penalty_opportunity(
    *,
    catalyst_denied: bool,
    volume_ratio: float | None,
    px: dict[str, Any],
    config: dict[str, Any],
) -> int:
    cap = int((config.get("score_caps") or {}).get("risk_penalty_max", -30))
    penalty = 0
    if catalyst_denied:
        penalty += int(config.get("denial_risk_penalty", -12))
    vol = float(px.get("volatility_60d") or 0)
    if vol > 0.08:
        penalty -= 10
    elif vol > 0.06:
        penalty -= 5
    if volume_ratio is not None and volume_ratio < 1.0:
        penalty -= 5
    ret1m = float(px.get("return_1m") or 0)
    if ret1m < -0.1:
        penalty -= 8
    return max(cap, penalty)


def _ma_recovery_met(px: dict[str, Any]) -> bool:
    ret1m = float(px.get("return_1m") or 0)
    ret3m = float(px.get("return_3m") or 0)
    dist = float(px.get("distance_from_52w_high") or 0)
    return (ret1m > 0 and ret3m < 0) or (ret1m > 0.05 and dist > 0.7)


def _earnings_improvement_met(fund: dict[str, Any] | None) -> bool:
    if not fund:
        return False
    try:
        ey = fund.get("earnings_yoy", "")
        return ey not in ("", None) and float(ey) > 0
    except (TypeError, ValueError):
        return False


def _sector_rs_met(
    sector: str,
    px: dict[str, Any],
    alpha: dict[str, Any] | None,
    alpha_meta: dict[str, dict[str, Any]],
) -> bool:
    ret1m = float(px.get("return_1m") or 0)
    sector_avg = _sector_avg_momentum(sector, alpha_meta)
    ticker_mom = float(alpha.get("momentum_score") or 0) if alpha else None
    if sector_avg is not None and ticker_mom is not None:
        return ticker_mom >= sector_avg
    return ret1m > 0.03


def _value_shareholder_met(alpha: dict[str, Any] | None) -> bool:
    if not alpha:
        return False
    v = float(alpha.get("valuation_score") or 0)
    sr = float(alpha.get("shareholder_return_score") or 0)
    return v >= 50 and sr >= 50


def _eval_e3_composite(
    *,
    px: dict[str, Any],
    history: list[dict[str, Any]],
    fund: dict[str, Any] | None,
    alpha: dict[str, Any] | None,
    sector: str,
    alpha_meta: dict[str, dict[str, Any]],
    volume_ratio: float | None,
    config: dict[str, Any],
) -> tuple[int, list[str], list[str]]:
    vol_cfg = config.get("volume") or {}
    e3_vol = float(vol_cfg.get("e3_min_ratio", 3.0))
    close = float(px.get("close") or 0)
    box_hit, _ = _box_breakout_60d(close, history)

    checks: dict[str, bool] = {
        "volume_3x": volume_ratio is not None and volume_ratio >= e3_vol,
        "box_breakout_60d": box_hit,
        "ma_recovery": _ma_recovery_met(px),
        "flow_proxy": _flow_proxy_met(px),
        "earnings_improvement": _earnings_improvement_met(fund),
        "sector_rs": _sector_rs_met(sector, px, alpha, alpha_meta),
        "value_shareholder": _value_shareholder_met(alpha),
    }
    met = [k for k in E3_SIGNAL_LABELS if checks.get(k)]
    missing = [k for k in E3_SIGNAL_LABELS if not checks.get(k)]
    return len(met), met, missing


def _apply_opportunity_grade_caps(
    grade: OpportunityGrade,
    *,
    e3_count: int,
    volume_ratio: float | None,
    config: dict[str, Any],
) -> OpportunityGrade:
    e3_cfg = config.get("e3_composite") or {}
    min_signals = int(e3_cfg.get("min_signals", 3))
    require_vol = bool(e3_cfg.get("require_volume_for_e3", True))
    vol_cfg = config.get("volume") or {}
    e3_vol = float(vol_cfg.get("e3_min_ratio", 3.0))

    if grade in {"E3", "E4"}:
        if e3_count < min_signals:
            return "E2"
        if require_vol and volume_ratio is None:
            return "E2"
        if require_vol and volume_ratio is not None and volume_ratio < e3_vol and grade == "E3":
            return "E2"
    return grade


def _confidence_opportunity(
    grade: OpportunityGrade,
    e3_count: int,
    volume_ratio: float | None,
) -> str:
    if grade in {"E0", "E1"}:
        return "low"
    if grade == "E2":
        return "medium" if e3_count >= 2 else "low-medium"
    if grade == "E3":
        return "medium-high" if volume_ratio and volume_ratio >= 3 else "medium"
    return "high"


def _missing_confirmation_text(grade: OpportunityGrade, e3_count: int) -> str:
    if grade in {"E0", "E1"}:
        return "Score insufficient — Confirmation Engine not applicable"
    if grade == "E4":
        return "Escalate to Confirmation Engine for full-size permission"
    parts = ["Confirmation Engine Buy-allowed", "Alpha gate GREEN"]
    if e3_count < 3:
        parts.append(f"E3 composite needs {3 - e3_count} more signal(s)")
    parts.append("volume sustain 3-5 sessions")
    return " + ".join(parts)


def _pilot_fraction_e3(grade: OpportunityGrade, e3_count: int, config: dict[str, Any]) -> float | None:
    if grade != "E3":
        return None
    fr = config.get("pilot_fractions") or {}
    abs_max = float(fr.get("absolute_max", 0.25))
    e3_min = float(fr.get("e3_min", 0.20))
    e3_max = float(fr.get("e3_max", 0.25))
    frac = e3_max if e3_count >= 4 else e3_min
    return min(frac, abs_max)


def score_opportunity_ticker(
    *,
    ticker: str,
    name: str,
    sector: str,
    as_of: str,
    px: dict[str, Any] | None,
    events: list[dict[str, str]],
    config: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
    fund: dict[str, Any] | None = None,
    alpha: dict[str, Any] | None = None,
    alpha_meta: dict[str, dict[str, Any]] | None = None,
) -> OpportunitySignal:
    missing: list[str] = []
    hist = history or []
    meta = alpha_meta or {}

    if not px:
        missing.append("price")
        return OpportunitySignal(
            ticker=ticker,
            name=name,
            date=as_of,
            sector=sector,
            total_score=0,
            opportunity_grade="E0",
            volume_score=0,
            price_structure_score=0,
            fundamental_momentum_score=0,
            flow_score=0,
            valuation_rerating_score=0,
            sector_momentum_score=0,
            risk_penalty=0,
            catalyst_type="none",
            catalyst_summary="",
            catalyst_denied=False,
            volume_ratio=None,
            price_breakout_level=None,
            support_level=None,
            stop_level=None,
            e3_composite_count=0,
            missing_confirmation="Missing price — no opportunity assessment",
            invalidation_condition="No price data",
            allowed_action="noise",
            allowed_position_fraction=0.0,
            confidence="low",
            reason="Missing price",
            missing_data=missing,
        )

    cat_type, cat_summary, cat_denied, cat_missing = _catalyst_metadata(events, config)
    missing.extend(cat_missing)
    if cat_denied:
        cat_type = "none" if cat_type == "denied" else f"{cat_type}_denied"

    vol_score, vol_ratio, vol_missing = _score_volume_pillar(px, hist, config)
    missing.extend(vol_missing)

    ps_score, breakout, support = _score_price_structure(px, hist, config)
    fm_score, fm_missing = _score_fundamental_momentum(fund, px, config)
    missing.extend(fm_missing)
    flow_score = _score_flow_pillar(px, config)
    val_score, val_missing = _score_valuation_rerating(alpha, px, config)
    missing.extend(val_missing)
    sec_score = _score_sector_momentum(sector, px, alpha, meta, config)

    risk = _risk_penalty_opportunity(
        catalyst_denied=cat_denied,
        volume_ratio=vol_ratio,
        px=px,
        config=config,
    )

    pillar_total = vol_score + ps_score + fm_score + flow_score + val_score + sec_score + risk
    total = max(0, min(100, pillar_total))

    e3_count, e3_met, e3_missing = _eval_e3_composite(
        px=px,
        history=hist,
        fund=fund,
        alpha=alpha,
        sector=sector,
        alpha_meta=meta,
        volume_ratio=vol_ratio,
        config=config,
    )

    thresholds = config.get("grade_thresholds") or {}
    grade = grade_from_score(total, thresholds)
    grade = _apply_opportunity_grade_caps(
        grade,
        e3_count=e3_count,
        volume_ratio=vol_ratio,
        config=config,
    )

    close = float(px.get("close") or 0)
    stop, invalidation = stop_and_invalidation(close, support, config)
    action, frac, action_reason = pilot_action(grade, stop, config)

    if grade == "E3":
        e3_frac = _pilot_fraction_e3(grade, e3_count, config)
        if e3_frac is not None and stop is not None:
            frac = e3_frac
            action = "pilot_entry_20_25"
            action_reason = f"Pilot up to {frac:.0%} of target alpha weight (E3 composite)"

    chase = ""
    if breakout and close > 0:
        chase = f"Do not chase above {round(breakout * 1.05, 2)} (+5% from breakout)"

    confirm = ""
    if grade == "E4":
        confirm = "QVM grade A/B + trend confirmation + volume sustain → Confirmation Engine full size"
    elif grade in {"E2", "E3"}:
        confirm = "Upgrade when Confirmation Engine Buy-allowed + Alpha gate GREEN"

    reason_parts = [
        f"volume={vol_score}",
        f"price_structure={ps_score}",
        f"fundamental={fm_score}",
        f"flow={flow_score}",
        f"valuation={val_score}",
        f"sector={sec_score}",
        f"risk={risk}",
        f"e3_composite={e3_count}/7",
        f"catalyst_meta={cat_type}",
        action_reason,
    ]

    return OpportunitySignal(
        ticker=ticker,
        name=name,
        date=as_of,
        sector=sector,
        total_score=total,
        opportunity_grade=grade,
        volume_score=vol_score,
        price_structure_score=ps_score,
        fundamental_momentum_score=fm_score,
        flow_score=flow_score,
        valuation_rerating_score=val_score,
        sector_momentum_score=sec_score,
        risk_penalty=risk,
        catalyst_type=cat_type,
        catalyst_summary=cat_summary,
        catalyst_denied=cat_denied,
        volume_ratio=vol_ratio,
        price_breakout_level=breakout,
        support_level=support,
        stop_level=stop,
        e3_composite_count=e3_count,
        e3_signals_met=e3_met,
        e3_signals_missing=e3_missing,
        missing_confirmation=_missing_confirmation_text(grade, e3_count),
        invalidation_condition=invalidation,
        allowed_action=action,
        allowed_position_fraction=frac,
        confidence=_confidence_opportunity(grade, e3_count, vol_ratio),
        reason=" · ".join(reason_parts),
        missing_data=sorted(set(missing)),
        confirmation_trigger=confirm,
        do_not_chase_zone=chase,
    )


def build_opportunity_decision(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or load_opportunity_config(data_dir)
    universe = load_opportunity_universe(data_dir, output_dir, cfg)
    prices = load_prices_map(data_dir)
    alpha_meta = _load_alpha_meta(output_dir)
    fundamentals = _load_fundamentals_map(data_dir)
    lookback = int(cfg.get("dart_lookback_days", 30))

    signals: list[OpportunitySignal] = []
    for ticker, info in sorted(universe.items()):
        px = prices.get(ticker)
        events = _load_dart_events(output_dir, ticker, as_of, lookback)
        history = load_price_history(data_dir, ticker, n=60)
        sig = score_opportunity_ticker(
            ticker=ticker,
            name=info.get("name", ticker),
            sector=info.get("sector", "unknown"),
            as_of=as_of,
            px=px,
            events=events,
            config=cfg,
            history=history,
            fund=fundamentals.get(ticker),
            alpha=alpha_meta.get(ticker),
            alpha_meta=alpha_meta,
        )
        signals.append(sig)

    signals.sort(key=lambda s: (-s.total_score, s.ticker))
    pilot = [s for s in signals if s.allowed_action.startswith("pilot_entry")]
    watch = [s for s in signals if s.opportunity_grade == "E1"]
    confirm = [s for s in signals if s.opportunity_grade == "E4"]

    return {
        "phase": "Alpha-Opportunity-v0.2",
        "mode": "shadow_pilot_only",
        "execution_authority": cfg.get("execution_authority", "none"),
        "affects_trade_actions": cfg.get("affects_trade_actions", False),
        "affects_final_execution": cfg.get("affects_final_execution", False),
        "disclaimer": OPPORTUNITY_DISCLAIMER,
        "as_of": as_of,
        "candidate_count": len(signals),
        "pilot_entry_count": len(pilot),
        "watch_count": len(watch),
        "confirmation_candidate_count": len(confirm),
        "signals": [s.to_row() for s in signals],
        "top_pilot": [s.to_row() for s in pilot[:5]],
        "top_watch": [s.to_row() for s in watch[:5]],
        "breakdown": [s.to_breakdown_row() for s in signals],
    }


from src.report.display_format import shadow_opportunity_action_label


def build_opportunity_brief_md(decision: dict[str, Any]) -> str:
    lines = [
        "# Alpha Opportunity Brief (v0.2 — shadow pilot only)",
        "",
        f"> {decision.get('disclaimer', OPPORTUNITY_DISCLAIMER)}",
        "",
        f"- **As of**: {decision.get('as_of', '—')}",
        f"- **Candidates**: {decision.get('candidate_count', 0)} · "
        f"pilot {decision.get('pilot_entry_count', 0)} · "
        f"watch {decision.get('watch_count', 0)} · "
        f"confirmation {decision.get('confirmation_candidate_count', 0)}",
        "",
        "## Top shadow pilot candidates (execution prohibited)",
        "",
        "| Ticker | Score | Grade | Action | Pilot frac | Stop | E3 | Missing confirmation |",
        "|--------|-------|-------|--------|------------|------|----|----------------------|",
    ]
    for row in decision.get("top_pilot") or []:
        lines.append(
            f"| {row.get('ticker')} | {row.get('total_score')} | {row.get('opportunity_grade')} | "
            f"{shadow_opportunity_action_label(str(row.get('allowed_action', '')))} | {row.get('allowed_position_fraction')} | "
            f"{row.get('stop_level')} | {row.get('e3_composite_count')} | "
            f"{str(row.get('missing_confirmation', ''))[:50]} |"
        )
    if not decision.get("top_pilot"):
        lines.append("| — | — | — | — | — | — | — | — |")

    lines.extend([
        "",
        "## Top watch (E1)",
        "",
        "| Ticker | Score | E3 met | Catalyst | Do-not-chase |",
        "|--------|-------|--------|----------|--------------|",
    ])
    for row in decision.get("top_watch") or []:
        lines.append(
            f"| {row.get('ticker')} | {row.get('total_score')} | "
            f"{row.get('e3_signals_met', '')[:30]} | "
            f"{str(row.get('catalyst_summary', ''))[:35]} | "
            f"{str(row.get('do_not_chase_zone', ''))[:30]} |"
        )
    if not decision.get("top_watch"):
        lines.append("| — | — | — | — | — |")

    lines.extend([
        "",
        "## Rules reminder",
        "",
        "- Opportunity signal ≠ confirmation buy",
        "- Catalyst is metadata only — denial does not force E0",
        "- E3 requires 3+ composite signals (volume, breakout, flow, earnings, sector, value)",
        "- Pilot max = 25% of target alpha weight per ticker",
        "- stop_level required for pilot_entry",
        "- E4 → Confirmation Engine only",
        "",
    ])
    return "\n".join(lines)


def write_opportunity_outputs(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision = build_opportunity_decision(data_dir, output_dir, as_of=as_of, config=config)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "opportunity_decision.json"
    payload = {k: v for k, v in decision.items() if k != "breakdown"}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    csv_path = output_dir / "opportunity_signals.csv"
    rows = decision.get("signals") or []
    if rows:
        fieldnames = list(rows[0].keys())
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    else:
        csv_path.write_text(
            "ticker,name,date,total_score,opportunity_grade\n",
            encoding="utf-8-sig",
        )

    breakdown_path = output_dir / "opportunity_reason_breakdown.csv"
    breakdown_rows = decision.get("breakdown") or []
    if breakdown_rows:
        bd_fields = list(breakdown_rows[0].keys())
        with breakdown_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=bd_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(breakdown_rows)
    else:
        breakdown_path.write_text("ticker,opportunity_grade,total_score\n", encoding="utf-8-sig")

    md_path = output_dir / "opportunity_brief.md"
    md_path.write_text(build_opportunity_brief_md(decision) + "\n", encoding="utf-8")

    return decision
