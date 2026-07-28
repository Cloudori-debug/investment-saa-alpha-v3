"""Alpha Opportunity Analytics v0.3 — probability, lifetime, type, post-analysis, failure DB."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.alpha.opportunity_shared import load_prices_map, parse_date
from src.data_refresh.external_market import business_days_between
from src.data_refresh.price_store import normalize_ticker

ANALYTICS_DISCLAIMER = (
    "Opportunity Analytics v0.3 is shadow learning only. Probability and expected alpha are "
    "heuristic until the failure database matures. Does not modify trade_actions or execution."
)

GRADE_RANK = {"E0": 0, "E1": 1, "E2": 2, "E3": 3, "E4": 4}


def load_analytics_config(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "opportunity_analytics_config.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def classify_opportunity_type(row: dict[str, Any]) -> str:
    """Classify opportunity into one of six archetypes."""
    ps = int(row.get("price_structure_score") or 0)
    vol = int(row.get("volume_score") or 0)
    fm = int(row.get("fundamental_momentum_score") or 0)
    val = int(row.get("valuation_rerating_score") or 0)
    flow = int(row.get("flow_score") or 0)
    cat = str(row.get("catalyst_type") or "none")
    e3_met = str(row.get("e3_signals_met") or "")

    if cat in {"buyback", "dividend", "ma_tender"} and val >= 8:
        return "re_rating"
    if "box_breakout" in e3_met or (ps >= 14 and vol >= 12):
        return "breakout"
    if "ma_recovery" in e3_met and fm >= 8:
        return "recovery"
    if fm >= 12 and int(row.get("sector_momentum_score") or 0) >= 5:
        return "momentum"
    if val >= 10 and vol >= 6 and ps < 10:
        return "value_awakening"
    if ps >= 8 and int(row.get("risk_penalty") or 0) <= -10:
        return "turnaround"
    if vol >= ps:
        return "momentum"
    if val >= fm:
        return "value_awakening"
    return "recovery"


def _type_defaults(cfg: dict[str, Any], opp_type: str) -> dict[str, float]:
    defaults = (cfg.get("type_defaults") or {}).get(opp_type) or {}
    return {
        "expected_alpha_pct": float(defaults.get("expected_alpha_pct", 12.0)),
        "expected_holding_days": float(defaults.get("expected_holding_days", 90)),
        "base_success_rate_pct": float(defaults.get("base_success_rate_pct", 50.0)),
    }


def estimate_success_probability(
    row: dict[str, Any],
    *,
    opportunity_age_days: int,
    cfg: dict[str, Any],
    historical_rate: float | None = None,
) -> float:
    score = int(row.get("total_score") or 0)
    grade = str(row.get("opportunity_grade") or "E0")
    e3 = int(row.get("e3_composite_count") or 0)
    base = min(85.0, max(12.0, (score - 35) * 1.15))
    base += GRADE_RANK.get(grade, 0) * 4
    base += min(8, e3 * 2)
    if int(row.get("risk_penalty") or 0) < -15:
        base -= 8
    decay = float(cfg.get("age_decay_per_week", 3.0))
    base -= (opportunity_age_days // 7) * decay
    opp_type = row.get("opportunity_type") or classify_opportunity_type(row)
    td = _type_defaults(cfg, str(opp_type))
    model_prob = (base + td["base_success_rate_pct"]) / 2
    if historical_rate is not None:
        w = float(cfg.get("historical_blend_weight", 0.35))
        model_prob = (1 - w) * model_prob + w * historical_rate
    return round(max(5.0, min(92.0, model_prob)), 1)


def estimate_expected_alpha(
    row: dict[str, Any],
    opp_type: str,
    cfg: dict[str, Any],
    success_prob: float,
) -> float:
    td = _type_defaults(cfg, opp_type)
    score_factor = int(row.get("total_score") or 50) / 100.0
    prob_factor = success_prob / 100.0
    raw = td["expected_alpha_pct"] * score_factor * (0.5 + 0.5 * prob_factor)
    return round(max(2.0, min(35.0, raw)), 1)


def _ledger_path(output_dir: Path, cfg: dict[str, Any]) -> Path:
    return output_dir / str(cfg.get("ledger_path", "opportunity_signal_ledger.jsonl"))


def load_ledger(output_dir: Path, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    path = _ledger_path(output_dir, cfg)
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _active_key(ticker: str, opp_type: str) -> str:
    return f"{normalize_ticker(ticker)}|{opp_type}"


def update_ledger_from_signals(
    signals: list[dict[str, Any]],
    *,
    as_of: str,
    output_dir: Path,
    cfg: dict[str, Any],
    prices: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Append/update ledger for E1+ signals; return enriched rows with age."""
    min_grade = str(cfg.get("min_grade_to_track", "E1"))
    min_rank = GRADE_RANK.get(min_grade, 1)
    existing = load_ledger(output_dir, cfg)
    closed = [e for e in existing if e.get("status") == "closed"]
    active: dict[str, dict[str, Any]] = {}
    for e in existing:
        if e.get("status") == "active":
            active[_active_key(str(e.get("ticker", "")), str(e.get("opportunity_type", "")))] = dict(e)

    enriched: list[dict[str, Any]] = []

    for row in signals:
        grade = str(row.get("opportunity_grade") or "E0")
        opp_type = classify_opportunity_type(row)
        ticker = normalize_ticker(str(row.get("ticker", "")))
        if GRADE_RANK.get(grade, 0) < min_rank:
            enriched.append({
                **row,
                "opportunity_type": opp_type,
                "opportunity_age_days": 0,
                "first_seen_date": "",
            })
            continue

        key = _active_key(ticker, opp_type)
        px = prices.get(ticker, {})
        signal_price = float(px.get("close") or 0) or None

        if key in active:
            entry = active[key]
            first = str(entry.get("first_seen_date", as_of))
            age = business_days_between(first, as_of[:10])
            entry["last_seen_date"] = as_of
            entry["last_grade"] = grade
            entry["last_score"] = int(row.get("total_score") or 0)
            entry["opportunity_age_days"] = age
            if GRADE_RANK.get(grade, 0) > GRADE_RANK.get(str(entry.get("peak_grade", "E0")), 0):
                entry["peak_grade"] = grade
                entry["peak_score"] = int(row.get("total_score") or 0)
            active[key] = entry
            enriched.append({
                **row,
                "opportunity_type": opp_type,
                "opportunity_age_days": age,
                "first_seen_date": first,
                "signal_id": entry.get("signal_id"),
                "signal_price": entry.get("signal_price"),
            })
        else:
            signal_id = f"{ticker}|{opp_type}|{as_of}"
            entry = {
                "signal_id": signal_id,
                "ticker": ticker,
                "name": row.get("name"),
                "opportunity_type": opp_type,
                "first_seen_date": as_of,
                "last_seen_date": as_of,
                "first_grade": grade,
                "last_grade": grade,
                "peak_grade": grade,
                "first_score": int(row.get("total_score") or 0),
                "last_score": int(row.get("total_score") or 0),
                "peak_score": int(row.get("total_score") or 0),
                "signal_price": signal_price,
                "status": "active",
                "outcome": None,
                "actual_pilot_entry": False,
                "opportunity_age_days": 0,
            }
            active[key] = entry
            enriched.append({
                **row,
                "opportunity_type": opp_type,
                "opportunity_age_days": 0,
                "first_seen_date": as_of,
                "signal_id": signal_id,
                "signal_price": signal_price,
            })

    path = _ledger_path(output_dir, cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for entry in closed:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        for key, entry in active.items():
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    out_map = {
        (normalize_ticker(str(r.get("ticker", ""))), r.get("opportunity_type", "")): r
        for r in enriched
    }
    final: list[dict[str, Any]] = []
    for row in signals:
        ticker = normalize_ticker(str(row.get("ticker", "")))
        opp_type = classify_opportunity_type(row)
        key = (ticker, opp_type)
        if key in out_map:
            final.append(out_map[key])
        else:
            final.append({**row, "opportunity_type": opp_type, "opportunity_age_days": 0, "first_seen_date": ""})
    return final


def _load_price_series(data_dir: Path, ticker: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for fname in ("prices_history.csv", "prices.csv"):
        path = data_dir / fname
        if not path.exists():
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        sub = df[df["ticker"].map(normalize_ticker) == ticker].copy()
        if not sub.empty:
            frames.append(sub)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    return out


def _forward_return_pct(series: pd.DataFrame, start: str, horizon_days: int, as_of: str) -> float | None:
    if series.empty:
        return None
    start_dt = parse_date(start)
    if not start_dt:
        return None
    sub = series[series["date"] >= pd.Timestamp(start_dt)]
    if sub.empty:
        return None
    start_row = sub.iloc[0]
    start_price = float(start_row["close"])
    if start_price <= 0:
        return None
    end_target = start_dt + pd.Timedelta(days=int(horizon_days * 1.45))
    as_of_dt = parse_date(as_of) or start_dt
    window = sub[sub["date"] <= min(pd.Timestamp(end_target), pd.Timestamp(as_of_dt))]
    if len(window) < 2:
        return None
    end_price = float(window.iloc[-1]["close"])
    return round((end_price / start_price - 1) * 100, 2)


def _mfe_mae_pct(series: pd.DataFrame, start: str, as_of: str) -> tuple[float | None, float | None]:
    if series.empty:
        return None, None
    start_dt = parse_date(start)
    as_of_dt = parse_date(as_of)
    if not start_dt or not as_of_dt:
        return None, None
    sub = series[(series["date"] >= pd.Timestamp(start_dt)) & (series["date"] <= pd.Timestamp(as_of_dt))]
    if sub.empty:
        return None, None
    start_price = float(sub.iloc[0]["close"])
    if start_price <= 0:
        return None, None
    closes = sub["close"].astype(float)
    mfe = round((closes.max() / start_price - 1) * 100, 2)
    mae = round((closes.min() / start_price - 1) * 100, 2)
    return mfe, mae


def infer_failure_reasons(entry: dict[str, Any], row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    ret60 = entry.get("forward_return_60d")
    mfe = entry.get("mfe_pct")
    mae = entry.get("mae_pct")
    age = int(entry.get("opportunity_age_days") or 0)
    if ret60 is not None and float(ret60) < 0 and float(row.get("volume_ratio") or 0) < 1.2:
        reasons.append("volume_fade")
    if mfe is not None and mae is not None and float(mfe) < 3 and float(mae) < -5:
        reasons.append("fake_breakout")
    if int(row.get("fundamental_momentum_score") or 0) < 5 and ret60 is not None and float(ret60) < 0:
        reasons.append("earnings_not_reflected")
    if int(row.get("flow_score") or 0) < 4:
        reasons.append("flow_reversal")
    if int(row.get("sector_momentum_score") or 0) < 3:
        reasons.append("sector_weakness")
    if age > 28 and ret60 is not None and float(ret60) < 2:
        reasons.append("time_decay")
    return reasons or ["unclassified"]


def run_post_analysis(
    ledger: list[dict[str, Any]],
    signals_by_ticker: dict[str, dict[str, Any]],
    *,
    data_dir: Path,
    as_of: str,
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    horizons = cfg.get("post_analysis_horizons_days") or [30, 60, 90]
    success_thr = float(cfg.get("success_threshold_pct", 5.0))
    fail_thr = float(cfg.get("failure_threshold_pct", -7.0))
    rows: list[dict[str, Any]] = []

    for entry in ledger:
        if entry.get("status") == "closed":
            rows.append(entry)
            continue
        ticker = normalize_ticker(str(entry.get("ticker", "")))
        first = str(entry.get("first_seen_date", ""))
        age = business_days_between(first, as_of[:10]) if first else 0
        entry = {**entry, "opportunity_age_days": age}
        series = _load_price_series(data_dir, ticker)
        mfe, mae = _mfe_mae_pct(series, first, as_of)
        entry["mfe_pct"] = mfe
        entry["mae_pct"] = mae
        for h in horizons:
            ret = _forward_return_pct(series, first, h, as_of)
            entry[f"forward_return_{h}d"] = ret

        sig_row = signals_by_ticker.get(ticker, {})
        ret60 = entry.get("forward_return_60d")
        if ret60 is not None and age >= 60:
            if float(ret60) >= success_thr:
                entry["outcome"] = "success"
                entry["status"] = "closed"
            elif float(ret60) <= fail_thr:
                entry["outcome"] = "failure"
                entry["status"] = "closed"
                entry["failure_reasons"] = infer_failure_reasons(entry, sig_row)
        rows.append(entry)
    return rows


def build_failure_database(
    post_rows: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    closed = [r for r in post_rows if r.get("outcome") in {"success", "failure"}]
    by_type: dict[str, dict[str, Any]] = {}
    reason_counts: dict[str, int] = {}

    for r in closed:
        t = str(r.get("opportunity_type", "unknown"))
        bucket = by_type.setdefault(t, {"success": 0, "failure": 0, "total": 0})
        bucket["total"] += 1
        if r.get("outcome") == "success":
            bucket["success"] += 1
        else:
            bucket["failure"] += 1
            for reason in r.get("failure_reasons") or []:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1

    type_stats = {}
    for t, b in by_type.items():
        rate = round(100.0 * b["success"] / b["total"], 1) if b["total"] else None
        type_stats[t] = {**b, "success_rate_pct": rate}

    total = len(closed)
    successes = sum(1 for r in closed if r.get("outcome") == "success")
    return {
        "schema_version": "0.3",
        "mode": "shadow_learning_only",
        "total_closed": total,
        "success_count": successes,
        "failure_count": total - successes,
        "overall_success_rate_pct": round(100.0 * successes / total, 1) if total else None,
        "by_opportunity_type": type_stats,
        "failure_reason_counts": reason_counts,
        "note": "Rates stabilize after ~30+ closed signals per type",
    }


def enrich_signals_with_analytics(
    signals: list[dict[str, Any]],
    *,
    cfg: dict[str, Any],
    failure_db: dict[str, Any],
) -> list[dict[str, Any]]:
    type_rates = {
        k: v.get("success_rate_pct")
        for k, v in (failure_db.get("by_opportunity_type") or {}).items()
        if v.get("success_rate_pct") is not None
    }
    enriched: list[dict[str, Any]] = []
    for row in signals:
        opp_type = str(row.get("opportunity_type") or classify_opportunity_type(row))
        age = int(row.get("opportunity_age_days") or 0)
        hist = type_rates.get(opp_type)
        prob = estimate_success_probability(row, opportunity_age_days=age, cfg=cfg, historical_rate=hist)
        exp_alpha = estimate_expected_alpha(row, opp_type, cfg, prob)
        td = _type_defaults(cfg, opp_type)
        holding = int(td["expected_holding_days"])
        if age > 14:
            holding = max(30, holding - age // 2)
        enriched.append({
            **row,
            "opportunity_type": opp_type,
            "success_probability_pct": prob,
            "expected_alpha_pct": exp_alpha,
            "expected_holding_days": holding,
            "probability_source": "historical_blend" if hist is not None else "heuristic_model",
        })
    return enriched


def write_opportunity_analytics(
    data_dir: Path,
    output_dir: Path,
    decision: dict[str, Any],
    *,
    as_of: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or load_analytics_config(data_dir)
    prices = load_prices_map(data_dir)
    signals = list(decision.get("signals") or [])

    tracked = update_ledger_from_signals(signals, as_of=as_of, output_dir=output_dir, cfg=cfg, prices=prices)
    ledger = load_ledger(output_dir, cfg)
    sig_map = {normalize_ticker(str(s.get("ticker", ""))): s for s in tracked}
    post_rows = run_post_analysis(ledger, sig_map, data_dir=data_dir, as_of=as_of, cfg=cfg)
    failure_db = build_failure_database(post_rows, cfg)
    enriched = enrich_signals_with_analytics(tracked, cfg=cfg, failure_db=failure_db)

    # Rewrite ledger with post-analysis updates
    ledger_path = _ledger_path(output_dir, cfg)
    with ledger_path.open("w", encoding="utf-8") as handle:
        for entry in post_rows:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    output_dir.mkdir(parents=True, exist_ok=True)
    analytics = {
        "phase": "Alpha-Opportunity-Analytics-v0.3",
        "mode": "shadow_learning_only",
        "disclaimer": ANALYTICS_DISCLAIMER,
        "as_of": as_of,
        "failure_database": failure_db,
        "active_signals": sum(1 for r in post_rows if r.get("status") == "active"),
        "closed_signals": failure_db.get("total_closed", 0),
        "statistics_validated": failure_db.get("total_closed", 0) >= 30,
        "probability_note": (
            "heuristic — not statistically validated (closed < 30)"
            if failure_db.get("total_closed", 0) < 30
            else "historical blend available"
        ),
        "top_pilot_analytics": [
            r for r in enriched if str(r.get("allowed_action", "")).startswith("pilot_entry")
        ][:8],
    }
    (output_dir / "opportunity_analytics.json").write_text(
        json.dumps(analytics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    (output_dir / "opportunity_failure_database.json").write_text(
        json.dumps(failure_db, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    if enriched:
        fields = list(enriched[0].keys())
        with (output_dir / "opportunity_signals.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(enriched)

    post_fields = [
        "signal_id", "ticker", "name", "opportunity_type", "first_seen_date", "last_seen_date",
        "opportunity_age_days", "first_grade", "peak_grade", "signal_price", "status", "outcome",
        "mfe_pct", "mae_pct", "forward_return_30d", "forward_return_60d", "forward_return_90d",
        "failure_reasons", "actual_pilot_entry",
    ]
    with (output_dir / "opportunity_post_analysis.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=post_fields, extrasaction="ignore")
        writer.writeheader()
        for row in post_rows:
            out = dict(row)
            if isinstance(out.get("failure_reasons"), list):
                out["failure_reasons"] = ";".join(out["failure_reasons"])
            writer.writerow(out)

    breakdown = []
    for row in enriched:
        breakdown.append({
            "ticker": row.get("ticker"),
            "opportunity_grade": row.get("opportunity_grade"),
            "opportunity_type": row.get("opportunity_type"),
            "total_score": row.get("total_score"),
            "success_probability_pct": row.get("success_probability_pct"),
            "expected_alpha_pct": row.get("expected_alpha_pct"),
            "expected_holding_days": row.get("expected_holding_days"),
            "opportunity_age_days": row.get("opportunity_age_days"),
            "allowed_action": row.get("allowed_action"),
            "pilot_blocked_reason": row.get("pilot_blocked_reason", ""),
            "e3_signals_missing": row.get("e3_signals_missing"),
            "missing_confirmation": row.get("missing_confirmation"),
        })
    if breakdown:
        with (output_dir / "opportunity_reason_breakdown.csv").open(
            "w", encoding="utf-8-sig", newline="",
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(breakdown[0].keys()))
            writer.writeheader()
            writer.writerows(breakdown)

    return analytics
