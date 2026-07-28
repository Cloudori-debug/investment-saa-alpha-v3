from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_refresh.dart_document_fetch import load_cached_document_text
from src.value_list.hakedaka_catalyst_evidence import (
    CATALYST_EVIDENCE_DISCLAIMER,
    CATALYST_EVIDENCE_FIELDS,
    _confidence_distribution,
    rebuild_treasury_precision,
    write_updated_treasury_events,
)
from src.value_list.hakedaka_evidence_enrichment import EVIDENCE_DISCLAIMER, build_hakedaka_top10_evidence_pack
from src.value_list.hakedaka_manual_verification_queue import (
    SHAREHOLDER_RETURN_FIELDS,
    TOP_CANDIDATE_VERIFICATION_FIELDS,
    build_shareholder_return_rows,
    build_top_candidate_verification_rows,
    write_csv,
)
from src.value_list.hakedaka_treasury_extraction import enrich_event_row, extract_catalyst_from_body

CALIBRATION_DISCLAIMER = (
    "Shadow diagnostic only. Calibrated catalyst evidence is not buy/sell advice. "
    "Execution authority remains v1.0.2 trade_actions/allowed_actions only."
)

CALIBRATION_EXTRA_FIELDS = [
    "parse_suspect",
    "sanity_reasons",
    "buyback_amount_to_market_cap",
    "share_count_to_market_cap",
    "extraction_confidence_raw",
]

CATALYST_EVIDENCE_FIELDS_CALIBRATED = CATALYST_EVIDENCE_FIELDS + [
    f for f in CALIBRATION_EXTRA_FIELDS if f not in CATALYST_EVIDENCE_FIELDS
]

WATCHLIST_FIELDS = [
    "ticker", "name", "event_type", "confidence",
    "shareholder_return_yield", "hakedaka_score", "hakedaka_rank",
    "reason_not_top15", "watch_reason",
    "shadow_only", "execution_authority",
]


def _load_mcap(data_dir: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    path = data_dir / "prices.csv"
    if not path.exists():
        return out
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for _, row in df.iterrows():
        try:
            out[str(row["ticker"]).zfill(6)] = float(row.get("market_cap") or 0)
        except (TypeError, ValueError):
            pass
    return out


def _load_score_ranks(output_dir: Path, *, top_n: int = 15) -> tuple[dict[str, float], dict[str, int], set[str]]:
    path = output_dir / "hakedaka_catalyst_scores.csv"
    scores: dict[str, float] = {}
    ranks: dict[str, int] = {}
    top_tickers: set[str] = set()
    if not path.exists():
        return scores, ranks, top_tickers
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    score_col = "hakedaka_total_score" if "hakedaka_total_score" in df.columns else "total_score"
    df[score_col] = pd.to_numeric(df[score_col], errors="coerce").fillna(0)
    df = df.sort_values(score_col, ascending=False).reset_index(drop=True)
    for i, row in df.iterrows():
        t = str(row["ticker"]).zfill(6)
        scores[t] = float(row[score_col])
        ranks[t] = int(i) + 1
    top_tickers = set(df.head(top_n)["ticker"].astype(str).str.zfill(6))
    return scores, ranks, top_tickers


def recalibrate_catalyst_evidence(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from src.value_list.hakedaka_catalyst_evidence import _load_treasury_events

    events = _load_treasury_events(output_dir)
    mcap_by = _load_mcap(data_dir)
    evidence_rows: list[dict[str, Any]] = []
    updated_events: list[dict[str, Any]] = []

    for row in events:
        ticker = str(row.get("ticker", "")).zfill(6)
        name = str(row.get("name", ticker))
        rcept = str(row.get("source_url_or_receipt_no", "")).strip()
        event_type = str(row.get("event_type", ""))
        body = load_cached_document_text(output_dir, ticker=ticker, rcept_no=rcept) if rcept else None
        mcap = mcap_by.get(ticker)

        if body:
            catalyst = extract_catalyst_from_body(body, event_type, market_cap=mcap)
            enriched = enrich_event_row(row, body_text=body)
        else:
            title = str(row.get("source_report_name", "")) + " " + str(row.get("text_evidence", ""))
            catalyst = extract_catalyst_from_body(title, event_type, market_cap=mcap)
            enriched = enrich_event_row(row)

        enriched["parse_suspect"] = catalyst.get("parse_suspect", False)
        enriched["extraction_confidence"] = catalyst.get("extraction_confidence", "low")
        enriched["treasury_event_confidence"] = catalyst.get("extraction_confidence", "low")
        updated_events.append(enriched)

        evidence_rows.append({
            "as_of": as_of,
            "ticker": ticker,
            "name": name,
            "receipt_no": rcept,
            "event_date": str(row.get("event_date", "")),
            "event_type": event_type,
            "document_fetch_ok": bool(body),
            "document_path": str(row.get("document_path", "")),
            "buyback_announced_amount": catalyst.get("buyback_announced_amount"),
            "buyback_announced_shares": catalyst.get("buyback_announced_shares"),
            "cancellation_announced_amount": catalyst.get("cancellation_announced_amount"),
            "cancellation_announced_shares": catalyst.get("cancellation_announced_shares"),
            "cancellation_completed_amount": catalyst.get("cancellation_completed_amount"),
            "cancellation_completed_shares": catalyst.get("cancellation_completed_shares"),
            "buyback_period_start": catalyst.get("buyback_period_start", ""),
            "buyback_period_end": catalyst.get("buyback_period_end", ""),
            "board_resolution_date": catalyst.get("board_resolution_date", ""),
            "completion_status": catalyst.get("completion_status", ""),
            "purpose": catalyst.get("purpose", ""),
            "extraction_confidence": catalyst.get("extraction_confidence", "low"),
            "missing_reason": catalyst.get("missing_reason", ""),
            "text_sample": (body or str(row.get("source_report_name", "")))[:200],
            "parse_suspect": catalyst.get("parse_suspect", False),
            "sanity_reasons": catalyst.get("sanity_reasons", ""),
            "buyback_amount_to_market_cap": catalyst.get("buyback_amount_to_market_cap"),
            "share_count_to_market_cap": catalyst.get("share_count_to_market_cap"),
            "extraction_confidence_raw": catalyst.get("extraction_confidence_raw", ""),
        })
    return evidence_rows, updated_events


def build_catalyst_watchlist(
    data_dir: Path,
    output_dir: Path,
    evidence_rows: list[dict[str, Any]],
    *,
    top_n: int = 15,
    min_return_yield: float = 3.0,
) -> list[dict[str, Any]]:
    scores, ranks, top_tickers = _load_score_ranks(output_dir, top_n=top_n)
    shr_by: dict[str, float] = {}
    shr_path = output_dir / "hakedaka_shareholder_return.csv"
    if shr_path.exists():
        df = pd.read_csv(shr_path, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            try:
                shr_by[str(row["ticker"]).zfill(6)] = float(row.get("shareholder_return_yield") or 0)
            except (TypeError, ValueError):
                pass

    by_ticker: dict[str, dict[str, Any]] = {}
    for ev in evidence_rows:
        conf = str(ev.get("extraction_confidence", "low"))
        if conf not in ("high", "medium") or ev.get("parse_suspect"):
            continue
        t = str(ev["ticker"]).zfill(6)
        rank = ranks.get(t, 999)
        if t in top_tickers:
            continue
        prev = by_ticker.get(t)
        conf_rank = {"high": 3, "medium": 2, "needs_review": 1, "low": 0}
        if prev and conf_rank.get(str(prev.get("confidence")), 0) >= conf_rank.get(conf, 0):
            continue
        shr = shr_by.get(t, 0)
        watch_reasons = ["catalyst_confidence_outside_top15"]
        if shr >= min_return_yield:
            watch_reasons.append("meaningful_shareholder_return_yield")
        if rank > top_n:
            watch_reasons.append("event_found_score_rank_low")
        by_ticker[t] = {
            "ticker": t,
            "name": ev.get("name", t),
            "event_type": ev.get("event_type", ""),
            "confidence": conf,
            "shareholder_return_yield": shr if shr else "",
            "hakedaka_score": scores.get(t, ""),
            "hakedaka_rank": rank if rank < 999 else "",
            "reason_not_top15": f"rank={rank} (top{top_n}_cutoff={top_n})",
            "watch_reason": ";".join(watch_reasons),
            "shadow_only": True,
            "execution_authority": "none",
        }

    rows = sorted(by_ticker.values(), key=lambda r: (-float(r.get("shareholder_return_yield") or 0), r.get("hakedaka_rank") or 999))
    return rows


def _confidence_distribution_calibrated(rows: list[dict[str, Any]]) -> dict[str, int]:
    dist: dict[str, int] = {"high": 0, "medium": 0, "low": 0, "needs_review": 0}
    for r in rows:
        conf = str(r.get("extraction_confidence", "low"))
        if conf not in dist:
            conf = "low"
        dist[conf] += 1
    return dist


def run_hakedaka_catalyst_calibration(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
    top_n: int = 15,
) -> dict[str, Any]:
    """Phase 4h-1 — Catalyst Extraction Calibration (shadow only)."""
    as_of_date = as_of or date.today().isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)

    conf_before = _confidence_distribution_calibrated([])
    old_path = output_dir / "hakedaka_catalyst_evidence.json"
    if old_path.exists():
        try:
            old = json.loads(old_path.read_text(encoding="utf-8"))
            conf_before = _confidence_distribution_calibrated(old.get("rows") or [])
        except (json.JSONDecodeError, OSError):
            pass

    evidence_rows, updated_events = recalibrate_catalyst_evidence(data_dir, output_dir, as_of=as_of_date)
    if updated_events:
        write_updated_treasury_events(output_dir, updated_events)
        rebuild_treasury_precision(data_dir, output_dir, as_of=as_of_date)

    write_csv(output_dir / "hakedaka_catalyst_evidence.csv", CATALYST_EVIDENCE_FIELDS_CALIBRATED, evidence_rows)
    cat_json = {
        "as_of": as_of_date,
        "mode": "shadow_catalyst_evidence_calibrated",
        "disclaimer": CALIBRATION_DISCLAIMER,
        "row_count": len(evidence_rows),
        "confidence_distribution": _confidence_distribution_calibrated(evidence_rows),
        "parse_suspect_count": sum(1 for r in evidence_rows if r.get("parse_suspect")),
        "rows": evidence_rows,
    }
    (output_dir / "hakedaka_catalyst_evidence.json").write_text(
        json.dumps(cat_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    shr_rows = build_shareholder_return_rows(data_dir, output_dir, as_of=as_of_date)
    write_csv(output_dir / "hakedaka_shareholder_return.csv", SHAREHOLDER_RETURN_FIELDS, shr_rows)

    watchlist = build_catalyst_watchlist(data_dir, output_dir, evidence_rows, top_n=top_n)
    write_csv(output_dir / "hakedaka_catalyst_watchlist.csv", WATCHLIST_FIELDS, watchlist)

    top_ver = build_top_candidate_verification_rows(data_dir, output_dir, as_of=as_of_date, top_n=top_n)
    write_csv(output_dir / "hakedaka_top_candidate_verification.csv", TOP_CANDIDATE_VERIFICATION_FIELDS, top_ver)

    build_hakedaka_top10_evidence_pack(data_dir, output_dir, as_of=as_of_date)

    conf_after = _confidence_distribution_calibrated(evidence_rows)
    regression = {
        "komeron_017890": _regression_check("017890"),
        "shinil_002700": _regression_check("002700"),
    }

    report: dict[str, Any] = {
        "as_of": as_of_date,
        "mode": "shadow_only",
        "phase": "4h-1",
        "disclaimer": CALIBRATION_DISCLAIMER,
        "summary": {
            "confidence_before": conf_before,
            "confidence_after": conf_after,
            "parse_suspect_count": sum(1 for r in evidence_rows if r.get("parse_suspect")),
            "watchlist_count": len(watchlist),
            "shareholder_manual_review_count": sum(1 for r in shr_rows if r.get("manual_review_required")),
            "regression_samples": regression,
        },
        "watchlist_top5": watchlist[:5],
    }
    (output_dir / "hakedaka_phase4h1_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return report


def _regression_check(ticker: str) -> dict[str, Any]:
    from src.value_list.hakedaka_catalyst_calibration import (
        REGRESSION_KOMERON_BODY,
        REGRESSION_SHINIL_BODY,
    )

    if ticker == "017890":
        cat = extract_catalyst_from_body(REGRESSION_KOMERON_BODY, "treasury_cancel")
        sh = cat.get("cancellation_announced_shares")
        return {
            "pass": sh == 600_000.0 and sh != 1.0 and not cat.get("parse_suspect"),
            "shares": sh,
            "amount": cat.get("cancellation_announced_amount"),
            "confidence": cat.get("extraction_confidence"),
            "parse_suspect": cat.get("parse_suspect"),
        }
    if ticker == "002700":
        cat = extract_catalyst_from_body(REGRESSION_SHINIL_BODY, "treasury_acquire")
        amt = cat.get("buyback_announced_amount")
        sh = cat.get("buyback_announced_shares")
        return {
            "pass": amt == 1_999_361_000.0 and sh == 1_651_000.0 and cat.get("extraction_confidence") == "high",
            "amount": amt,
            "shares": sh,
            "confidence": cat.get("extraction_confidence"),
            "parse_suspect": cat.get("parse_suspect"),
        }
    return {"pass": False}
