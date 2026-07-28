from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.value_list.hakedaka_evidence_enrichment import (
    EVIDENCE_DISCLAIMER,
    _missing_critical,
    _why_not_actionable,
)
from src.value_list.hakedaka_manual_overrides import apply_manual_to_fundamentals, load_manual_overrides
from src.value_list.hakedaka_treasury_extraction import enrich_event_row
from src.value_list.ticker_registry import hakedaka_meta_by_ticker, resolve_hakedaka_registry

MANUAL_VERIFICATION_DISCLAIMER = (
    "Shadow diagnostic only. Manual verification queue is not buy/sell advice. "
    "Execution authority remains v1.0.2 trade_actions/allowed_actions only."
)

PHASE4G_EVENT_EXTRA_FIELDS = [
    "completion_status",
    "treasury_event_confidence",
]

SHAREHOLDER_RETURN_FIELDS = [
    "as_of", "ticker", "name",
    "buyback_amount_to_market_cap",
    "cancellation_amount_to_market_cap",
    "treasury_share_ratio",
    "dividend_yield",
    "shareholder_return_yield",
    "treasury_event_confidence",
    "manual_review_required",
    "missing_reason",
]

NAV_MANUAL_QUEUE_FIELDS = [
    "ticker", "name", "current_pbr", "market_cap",
    "listed_subsidiary_candidate", "required_manual_fields",
    "suggested_source", "priority", "reason",
]

TOP_CANDIDATE_VERIFICATION_FIELDS = [
    "as_of", "ticker", "name", "hakedaka_total_score", "data_quality_score", "hunt_tier",
    "financial_verified", "net_cash_verified", "treasury_verified", "nav_verified",
    "governance_verified", "forward_return_started",
    "actionable_blocker", "verification_status",
]


def _f(val: Any) -> float | None:
    if val in (None, ""):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _load_mcap_by_ticker(data_dir: Path) -> dict[str, float]:
    mcap_by: dict[str, float] = {}
    px_path = data_dir / "prices.csv"
    if not px_path.exists():
        return mcap_by
    df = pd.read_csv(px_path, dtype=str, keep_default_na=False)
    for _, row in df.iterrows():
        try:
            mcap_by[str(row["ticker"]).zfill(6)] = float(row.get("market_cap") or 0)
        except (TypeError, ValueError):
            pass
    return mcap_by


def _load_pbr_by_ticker(data_dir: Path) -> dict[str, float]:
    pbr_by: dict[str, float] = {}
    from src.value_list.hakedaka_fundamentals import load_hakedaka_fundamentals

    for ticker, fund in load_hakedaka_fundamentals(data_dir).items():
        pbr = _f(fund.get("asset_value_discount_proxy"))
        if pbr is not None and pbr > 0:
            pbr_by[ticker] = pbr
    return pbr_by


def reanalyze_treasury_events_csv(output_dir: Path, *, as_of: str) -> dict[str, Any]:
    """Re-analyze text_only treasury events with improved extraction."""
    from src.value_list.hakedaka_treasury_events import TREASURY_CSV_FIELDS_EXTENDED

    events_path = output_dir / "hakedaka_treasury_events.csv"
    if not events_path.exists():
        return {"events": 0, "skipped": "no_events_csv"}

    fieldnames = list(TREASURY_CSV_FIELDS_EXTENDED)
    for f in PHASE4G_EVENT_EXTRA_FIELDS:
        if f not in fieldnames:
            fieldnames.append(f)

    df = pd.read_csv(events_path, dtype=str, keep_default_na=False)
    enriched: list[dict[str, Any]] = []
    before_low = after_high = after_medium = 0

    for _, row in df.iterrows():
        raw = dict(row)
        if str(raw.get("extraction_confidence", "")) in ("text_only", "low", ""):
            before_low += 1
        out = enrich_event_row(raw)
        conf = str(out.get("treasury_event_confidence", "low"))
        if conf == "high":
            after_high += 1
        elif conf == "medium":
            after_medium += 1
        for key in fieldnames:
            if key not in out:
                out[key] = ""
        enriched.append(out)

    with events_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(enriched)

    with_confidence = sum(
        1 for r in enriched
        if str(r.get("treasury_event_confidence", "")) in ("high", "medium")
    )
    return {
        "as_of": as_of,
        "events": len(enriched),
        "text_only_before": before_low,
        "confidence_high": after_high,
        "confidence_medium": after_medium,
        "confidence_high_or_medium": with_confidence,
        "treasury_precision_coverage_pct": round(with_confidence / len(enriched) * 100, 1) if enriched else 0,
    }


def build_shareholder_return_rows(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
) -> list[dict[str, Any]]:
    from src.value_list.hakedaka_fundamentals import load_hakedaka_fundamentals

    funds = load_hakedaka_fundamentals(data_dir)
    mcap_by = _load_mcap_by_ticker(data_dir)
    registry = {
        str(r["ticker"]).zfill(6): str(r.get("name", ""))
        for r in resolve_hakedaka_registry(data_dir) if r.get("ticker")
    }
    events_by: dict[str, list[dict[str, Any]]] = {}
    ev_path = output_dir / "hakedaka_treasury_events.csv"
    if ev_path.exists():
        df = pd.read_csv(ev_path, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            t = str(row["ticker"]).zfill(6)
            events_by.setdefault(t, []).append(dict(row))

    rows: list[dict[str, Any]] = []
    for ticker, name in sorted(registry.items()):
        fund = funds.get(ticker, {})
        mcap = mcap_by.get(ticker) or 0
        events = events_by.get(ticker, [])
        buybacks = [e for e in events if "acquire" in str(e.get("event_type", ""))]
        cancels = [e for e in events if "cancel" in str(e.get("event_type", ""))]

        buy_amt = None
        cancel_amt = None
        best_conf = "low"
        missing: list[str] = []

        def _event_conf(event: dict[str, Any]) -> str:
            return str(event.get("extraction_confidence") or event.get("treasury_event_confidence") or "low")

        for e in events:
            c = _event_conf(e)
            rank = {"high": 3, "medium": 2, "needs_review": 1, "low": 0}
            if rank.get(c, 0) > rank.get(best_conf, 0):
                best_conf = c

        if buybacks:
            latest = buybacks[0]
            buy_amt = _f(latest.get("buyback_announced_amount") or latest.get("announced_amount"))
        if cancels:
            latest_c = cancels[0]
            cancel_amt = _f(
                latest_c.get("cancellation_announced_amount")
                or latest_c.get("cancellation_amount")
            )

        treasury_ratio = _f(fund.get("treasury_share_ratio"))
        div_yield = _f(fund.get("shareholder_return_yield"))
        if div_yield is None:
            payout = _f(fund.get("payout_ratio"))
            if payout is not None and payout > 0:
                div_yield = round(payout / 100, 4)

        buy_to_mcap = round(buy_amt / mcap * 100, 4) if buy_amt and mcap > 0 else None
        cancel_to_mcap = round(cancel_amt / mcap * 100, 4) if cancel_amt and mcap > 0 else None

        parts: list[float] = []
        if buy_to_mcap is not None:
            parts.append(buy_to_mcap)
        if cancel_to_mcap is not None:
            parts.append(cancel_to_mcap)
        if div_yield is not None:
            parts.append(div_yield * 100 if div_yield < 1 else div_yield)

        shr_yield = round(sum(parts), 4) if parts else None
        manual_review = shr_yield is None or best_conf in ("low", "needs_review")

        if buy_to_mcap is None and buybacks:
            missing.append("buyback_amount_to_mcap")
        if cancel_to_mcap is None and cancels:
            missing.append("cancellation_amount_to_mcap")
        if treasury_ratio is None:
            missing.append("treasury_share_ratio")
        if div_yield is None:
            missing.append("dividend_yield")

        rows.append({
            "as_of": as_of,
            "ticker": ticker,
            "name": name,
            "buyback_amount_to_market_cap": buy_to_mcap,
            "cancellation_amount_to_market_cap": cancel_to_mcap,
            "treasury_share_ratio": treasury_ratio,
            "dividend_yield": div_yield,
            "shareholder_return_yield": shr_yield,
            "treasury_event_confidence": best_conf,
            "manual_review_required": manual_review,
            "missing_reason": ";".join(missing),
        })
    return rows


def build_nav_manual_review_queue(
    data_dir: Path,
    output_dir: Path,
) -> list[dict[str, Any]]:
    meta_by = hakedaka_meta_by_ticker(data_dir)
    pbr_by = _load_pbr_by_ticker(data_dir)
    mcap_by = _load_mcap_by_ticker(data_dir)
    manual = load_manual_overrides(data_dir)
    scores: dict[str, float] = {}
    score_path = output_dir / "hakedaka_catalyst_scores.csv"
    if score_path.exists():
        df = pd.read_csv(score_path, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            t = str(row["ticker"]).zfill(6)
            scores[t] = _f(row.get("hakedaka_total_score")) or 0

    nav_path = output_dir / "hakedaka_nav_proxy.json"
    nav_by: dict[str, dict[str, Any]] = {}
    if nav_path.exists():
        try:
            doc = json.loads(nav_path.read_text(encoding="utf-8"))
            for r in doc.get("rows") or []:
                nav_by[str(r.get("ticker", "")).zfill(6)] = r
        except (json.JSONDecodeError, OSError):
            pass

    candidates: list[dict[str, Any]] = []
    for ticker, meta in meta_by.items():
        gid = int(meta.get("group_id", 0))
        nav_row = nav_by.get(ticker, {})
        is_holding = gid == 1 or "holding_company_discount" in str(meta.get("candidate_groups", ""))
        has_manual = bool(manual.get(ticker))
        nav_source = str(nav_row.get("source", ""))
        if not is_holding and not nav_row:
            continue
        if has_manual and nav_row.get("listed_subsidiary_ticker"):
            continue
        score = scores.get(ticker, 0)
        pbr = pbr_by.get(ticker)
        mcap = mcap_by.get(ticker)
        priority = 1
        if score >= 70:
            priority = 1
        elif score >= 65:
            priority = 2
        elif gid == 1:
            priority = 2
        else:
            priority = 3
        if nav_source == "pbr_proxy":
            priority = min(priority, 2)

        reason_parts = []
        if gid == 1:
            reason_parts.append("holding_company_discount group")
        if nav_source == "pbr_proxy":
            reason_parts.append("PBR proxy only — true NAV discount unverified")
        if not has_manual:
            reason_parts.append("no manual override")

        candidates.append({
            "ticker": ticker,
            "name": str(meta.get("name", ticker)),
            "current_pbr": pbr,
            "market_cap": mcap,
            "listed_subsidiary_candidate": str(manual.get(ticker, {}).get("listed_subsidiary_ticker", "")),
            "required_manual_fields": (
                "listed_subsidiary_ticker,ownership_pct,subsidiary_market_value,"
                "ownership_adjusted_value,holding_company_nav_discount_override"
            ),
            "suggested_source": "DART major shareholder report; company IR; subsidiary listing",
            "priority": priority,
            "reason": "; ".join(reason_parts),
            "_score": score,
        })

    candidates.sort(key=lambda r: (r["priority"], -r["_score"]))
    for r in candidates:
        r.pop("_score", None)
    return candidates[:15]


def _load_top_candidates(output_dir: Path, *, n: int = 15) -> pd.DataFrame:
    path = output_dir / "hakedaka_catalyst_scores.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    score_col = "hakedaka_total_score" if "hakedaka_total_score" in df.columns else "total_score"
    df[score_col] = pd.to_numeric(df[score_col], errors="coerce").fillna(0)
    return df.sort_values(score_col, ascending=False).head(n)


def build_top_candidate_verification_rows(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    top_n: int = 15,
) -> list[dict[str, Any]]:
    from src.value_list.hakedaka_fundamentals import load_hakedaka_fundamentals
    from src.value_list.dart_disclosure import load_hakedaka_dart_signals

    top = _load_top_candidates(output_dir, n=top_n)
    if top.empty:
        return []

    manual = load_manual_overrides(data_dir)
    funds_raw = load_hakedaka_fundamentals(data_dir)
    dart_doc = load_hakedaka_dart_signals(data_dir)
    dart_by = dart_doc.get("tickers") or {}
    meta_by = hakedaka_meta_by_ticker(data_dir)
    nav_path = output_dir / "hakedaka_nav_proxy.json"
    nav_by: dict[str, dict[str, Any]] = {}
    if nav_path.exists():
        try:
            doc = json.loads(nav_path.read_text(encoding="utf-8"))
            for r in doc.get("rows") or []:
                nav_by[str(r.get("ticker", "")).zfill(6)] = r
        except (json.JSONDecodeError, OSError):
            pass

    events_by: dict[str, list[dict[str, Any]]] = {}
    ev_path = output_dir / "hakedaka_treasury_events.csv"
    if ev_path.exists():
        df_ev = pd.read_csv(ev_path, dtype=str, keep_default_na=False)
        for _, row in df_ev.iterrows():
            t = str(row["ticker"]).zfill(6)
            events_by.setdefault(t, []).append(dict(row))

    rows: list[dict[str, Any]] = []
    score_col = "hakedaka_total_score" if "hakedaka_total_score" in top.columns else "total_score"
    fwd_cols = ("forward_return_5d", "forward_return_20d", "forward_return_60d", "forward_return_120d")

    for _, row in top.iterrows():
        ticker = str(row["ticker"]).zfill(6)
        name = str(row.get("name", ticker))
        fund = apply_manual_to_fundamentals(funds_raw.get(ticker), manual.get(ticker))
        dart = dart_by.get(ticker, {})
        meta = meta_by.get(ticker, {})
        treasury = events_by.get(ticker, [])
        missing = _missing_critical(fund)

        fin_count = sum(
            1 for k in ("operating_cash_flow", "free_cash_flow", "debt_ratio", "net_cash")
            if fund.get(k) not in (None, "")
        )
        financial_verified = fin_count >= 3
        net_cash_verified = fund.get("net_cash") not in (None, "")

        treasury_verified = any(
            str(e.get("treasury_event_confidence", "")) in ("high", "medium")
            for e in treasury
        ) or bool(fund.get("treasury_share_ratio"))

        nav_row = nav_by.get(ticker, {})
        nav_manual = manual.get(ticker, {})
        nav_verified = bool(
            nav_manual.get("holding_company_nav_discount_override")
            or nav_manual.get("listed_subsidiary_ticker")
        )
        if not nav_verified and int(meta.get("group_id", 0)) != 1:
            nav_verified = True  # not applicable for non-holding

        governance_verified = bool(
            dart.get("cancel_disclosure")
            or dart.get("return_disclosure")
            or fund.get("governance_event_flag")
            or nav_manual.get("activist_event_override")
        )

        forward_return_started = any(
            str(row.get(c, "")).strip() not in ("", "nan")
            for c in fwd_cols if c in row.index
        )

        quality_score = float(row.get("data_quality_score") or 0)
        hunt_tier = str(row.get("hunt_tier") or "preliminary")
        shr_verified = treasury_verified
        blocker = _why_not_actionable(
            quality_score=quality_score,
            missing=missing,
            financial_safety_verified=financial_verified,
            shareholder_return_verified=shr_verified,
            hunt_tier=hunt_tier,
        )

        if hunt_tier == "actionable_candidate" and quality_score >= 75 and financial_verified:
            status = "actionable_blocked_shadow"
        elif financial_verified and net_cash_verified and quality_score >= 60:
            status = "verified"
        else:
            status = "preliminary"

        rows.append({
            "as_of": as_of,
            "ticker": ticker,
            "name": name,
            "hakedaka_total_score": float(row.get(score_col) or 0),
            "data_quality_score": quality_score,
            "hunt_tier": hunt_tier,
            "financial_verified": financial_verified,
            "net_cash_verified": net_cash_verified,
            "treasury_verified": treasury_verified,
            "nav_verified": nav_verified,
            "governance_verified": governance_verified,
            "forward_return_started": forward_return_started,
            "actionable_blocker": blocker,
            "verification_status": status,
        })
    return rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def run_hakedaka_manual_verification_queue(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
    top_n: int = 15,
) -> dict[str, Any]:
    """Phase 4g — Treasury & NAV Manual Verification Queue (shadow only)."""
    from src.value_list.hakedaka_nav_treasury_precision import (
        build_treasury_precision_rows,
        merge_treasury_events_with_precision,
        write_treasury_precision_csv,
    )

    as_of_date = as_of or date.today().isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)

    treasury_reanalysis = reanalyze_treasury_events_csv(output_dir, as_of=as_of_date)
    treasury_rows = build_treasury_precision_rows(data_dir, output_dir, as_of=as_of_date)
    write_treasury_precision_csv(output_dir, treasury_rows)
    merge_treasury_events_with_precision(output_dir, treasury_rows)

    shr_rows = build_shareholder_return_rows(data_dir, output_dir, as_of=as_of_date)
    write_csv(output_dir / "hakedaka_shareholder_return.csv", SHAREHOLDER_RETURN_FIELDS, shr_rows)

    nav_queue = build_nav_manual_review_queue(data_dir, output_dir)
    write_csv(output_dir / "hakedaka_nav_manual_review_queue.csv", NAV_MANUAL_QUEUE_FIELDS, nav_queue)

    top_ver = build_top_candidate_verification_rows(
        data_dir, output_dir, as_of=as_of_date, top_n=top_n,
    )
    write_csv(output_dir / "hakedaka_top_candidate_verification.csv", TOP_CANDIDATE_VERIFICATION_FIELDS, top_ver)

    ticker_precision = sum(
        1 for r in treasury_rows
        if r.get("treasury_share_ratio") not in (None, "")
        or r.get("buyback_announced_shares") not in (None, "")
        or r.get("cancellation_announced_shares") not in (None, "")
    )
    event_precision = treasury_reanalysis.get("confidence_high_or_medium", 0)
    event_total = treasury_reanalysis.get("events", 0) or 1
    shr_manual = sum(1 for r in shr_rows if r.get("manual_review_required"))

    verified_count = sum(1 for r in top_ver if r.get("verification_status") == "verified")
    actionable_blocked = sum(1 for r in top_ver if "actionable" in str(r.get("verification_status", "")))
    blockers = [r.get("actionable_blocker", "") for r in top_ver[:5]]

    report: dict[str, Any] = {
        "as_of": as_of_date,
        "mode": "shadow_only",
        "phase": "4g",
        "disclaimer": MANUAL_VERIFICATION_DISCLAIMER,
        "evidence_disclaimer": EVIDENCE_DISCLAIMER,
        "summary": {
            "treasury_event_confidence_coverage_pct": round(event_precision / event_total * 100, 1),
            "treasury_precision_ticker_coverage_pct": round(ticker_precision / len(treasury_rows) * 100, 1)
            if treasury_rows else 0,
            "shareholder_return_manual_review_count": shr_manual,
            "nav_manual_queue_count": len(nav_queue),
            "top_candidate_count": len(top_ver),
            "verified_candidate_count": verified_count,
            "actionable_blocked_count": actionable_blocked,
            "forward_return_started_count": sum(1 for r in top_ver if r.get("forward_return_started")),
        },
        "treasury_reanalysis": treasury_reanalysis,
        "top_blockers_sample": blockers,
        "nav_queue_top5": nav_queue[:5],
    }
    (output_dir / "hakedaka_phase4g_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return report
