from __future__ import annotations

import csv
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_refresh.dart_client import RateLimiter
from src.data_refresh.dart_document_fetch import fetch_or_load_document, load_cached_document_text
from src.value_list.hakedaka_evidence_enrichment import (
    EVIDENCE_DISCLAIMER,
    build_hakedaka_top10_evidence_pack,
)
from src.value_list.hakedaka_manual_verification_queue import (
    SHAREHOLDER_RETURN_FIELDS,
    TOP_CANDIDATE_VERIFICATION_FIELDS,
    build_shareholder_return_rows,
    build_top_candidate_verification_rows,
    write_csv,
)
from src.value_list.hakedaka_treasury_extraction import enrich_event_row, extract_catalyst_from_body

CATALYST_EVIDENCE_DISCLAIMER = (
    "Shadow diagnostic only. Catalyst evidence is not buy/sell advice. "
    "Execution authority remains v1.0.2 trade_actions/allowed_actions only."
)

CATALYST_EVIDENCE_FIELDS = [
    "as_of", "ticker", "name", "receipt_no", "event_date", "event_type",
    "document_fetch_ok", "document_path",
    "buyback_announced_amount", "buyback_announced_shares",
    "cancellation_announced_amount", "cancellation_announced_shares",
    "cancellation_completed_amount", "cancellation_completed_shares",
    "buyback_period_start", "buyback_period_end",
    "board_resolution_date", "completion_status", "purpose",
    "extraction_confidence", "missing_reason", "text_sample",
]

PHASE4H_EVENT_EXTRA = [
    "board_resolution_date", "purpose", "body_extraction_used", "document_path",
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


def _load_treasury_events(output_dir: Path) -> list[dict[str, Any]]:
    path = output_dir / "hakedaka_treasury_events.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return [dict(row) for _, row in df.iterrows()]


def _treasury_precision_pct(output_dir: Path) -> float:
    path = output_dir / "hakedaka_treasury_precision.csv"
    if not path.exists():
        return 0.0
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if df.empty:
        return 0.0
    n = sum(
        1 for _, row in df.iterrows()
        if str(row.get("treasury_share_ratio", "")).strip()
        or str(row.get("buyback_announced_shares", "")).strip()
        or str(row.get("cancellation_announced_shares", "")).strip()
    )
    return round(n / len(df) * 100, 1)


def _confidence_distribution(rows: list[dict[str, Any]]) -> dict[str, int]:
    dist: dict[str, int] = {"high": 0, "medium": 0, "low": 0, "needs_review": 0}
    for r in rows:
        conf = str(r.get("extraction_confidence", "low"))
        if conf not in dist:
            conf = "low"
        dist[conf] += 1
    return dist


def process_catalyst_evidence(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str,
    fetch_documents: bool = True,
    use_cache: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Fetch DART bodies and extract catalyst evidence for treasury events."""
    events = _load_treasury_events(output_dir)
    if not events:
        return [], [], {"events": 0, "skipped": "no_treasury_events"}

    limiter = RateLimiter(min_interval_sec=0.15)
    fetch_fail_reasons: dict[str, int] = {}
    mcap_by = _load_mcap(data_dir)
    evidence_rows: list[dict[str, Any]] = []
    fetch_ok = fetch_fail = 0
    updated_events: list[dict[str, Any]] = []

    for row in events:
        ticker = str(row.get("ticker", "")).zfill(6)
        name = str(row.get("name", ticker))
        rcept = str(row.get("source_url_or_receipt_no", "")).strip()
        event_type = str(row.get("event_type", ""))

        body_text = ""
        doc_path: Path | None = None
        fetch_reason = ""
        fetch_ok_flag = False

        if rcept:
            cached = load_cached_document_text(output_dir, ticker=ticker, rcept_no=rcept) if use_cache else None
            if cached:
                body_text = cached
                fetch_ok_flag = True
                fetch_ok += 1
                rcept_clean = re.sub(r"\D", "", rcept)
                doc_path = output_dir / "dart_documents" / "hakedaka" / f"{ticker}_{rcept_clean}.txt"
            elif fetch_documents:
                try:
                    body_text, fetch_reason, doc_path = fetch_or_load_document(
                        output_dir,
                        ticker=ticker,
                        rcept_no=rcept,
                        data_dir=data_dir,
                        limiter=limiter,
                        use_cache=False,
                    )
                    fetch_ok_flag = bool(body_text)
                    if fetch_ok_flag:
                        fetch_ok += 1
                    else:
                        fetch_fail += 1
                        key = fetch_reason.split(":")[0] if fetch_reason else "unknown"
                        fetch_fail_reasons[key] = fetch_fail_reasons.get(key, 0) + 1
                except Exception as exc:
                    fetch_reason = f"fetch_exception:{exc}"
                    fetch_fail += 1
                    fetch_fail_reasons["fetch_exception"] = fetch_fail_reasons.get("fetch_exception", 0) + 1
            else:
                fetch_reason = "fetch_skipped"
        elif not rcept:
            fetch_reason = "missing_receipt_no"
            fetch_fail += 1
            fetch_fail_reasons["missing_receipt_no"] = fetch_fail_reasons.get("missing_receipt_no", 0) + 1

        if body_text:
            enriched = enrich_event_row(row, body_text=body_text)
            catalyst = extract_catalyst_from_body(
                body_text, event_type, market_cap=mcap_by.get(ticker),
            )
        else:
            enriched = enrich_event_row(row)
            catalyst = extract_catalyst_from_body(
                str(row.get("source_report_name", "")) + " " + str(row.get("text_evidence", "")),
                event_type,
                market_cap=mcap_by.get(ticker),
            )
            if fetch_reason:
                prev = str(enriched.get("missing_reason", "")).strip()
                enriched["missing_reason"] = f"{prev};document:{fetch_reason}".strip(";")

        if doc_path:
            enriched["document_path"] = str(doc_path)

        updated_events.append(enriched)

        miss_parts = [str(catalyst.get("missing_reason", "")).strip()]
        if fetch_reason:
            miss_parts.append(f"document:{fetch_reason}")

        evidence_rows.append({
            "as_of": as_of,
            "ticker": ticker,
            "name": name,
            "receipt_no": rcept,
            "event_date": str(row.get("event_date", "")),
            "event_type": event_type,
            "document_fetch_ok": fetch_ok_flag,
            "document_path": str(doc_path) if doc_path else "",
            "buyback_announced_amount": catalyst.get("buyback_announced_amount") or enriched.get("buyback_announced_amount"),
            "buyback_announced_shares": catalyst.get("buyback_announced_shares") or enriched.get("buyback_announced_shares"),
            "cancellation_announced_amount": catalyst.get("cancellation_announced_amount") or enriched.get("cancellation_announced_amount"),
            "cancellation_announced_shares": catalyst.get("cancellation_announced_shares") or enriched.get("cancellation_announced_shares"),
            "cancellation_completed_amount": catalyst.get("cancellation_completed_amount") or enriched.get("cancellation_completed_amount"),
            "cancellation_completed_shares": catalyst.get("cancellation_completed_shares") or enriched.get("cancellation_completed_shares"),
            "buyback_period_start": catalyst.get("buyback_period_start") or enriched.get("buyback_period_start", ""),
            "buyback_period_end": catalyst.get("buyback_period_end") or enriched.get("buyback_period_end", ""),
            "board_resolution_date": catalyst.get("board_resolution_date", ""),
            "completion_status": catalyst.get("completion_status", enriched.get("completion_status", "")),
            "purpose": catalyst.get("purpose", ""),
            "extraction_confidence": catalyst.get("extraction_confidence", enriched.get("treasury_event_confidence", "low")),
            "missing_reason": ";".join(p for p in miss_parts if p),
            "text_sample": (body_text or str(row.get("source_report_name", "")))[:200],
        })

    stats = {
        "events": len(events),
        "documents_fetched_ok": fetch_ok,
        "documents_fetch_failed": fetch_fail,
        "fetch_fail_reasons": fetch_fail_reasons,
        "confidence_distribution": _confidence_distribution(evidence_rows),
    }
    return evidence_rows, updated_events, stats


def write_updated_treasury_events(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    from src.value_list.hakedaka_treasury_events import TREASURY_CSV_FIELDS_EXTENDED

    fieldnames = list(TREASURY_CSV_FIELDS_EXTENDED)
    for f in PHASE4H_EVENT_EXTRA + ["board_resolution_date", "purpose"]:
        if f not in fieldnames:
            fieldnames.append(f)

    path = output_dir / "hakedaka_treasury_events.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in fieldnames:
                if key not in out:
                    out[key] = ""
            writer.writerow(out)


def rebuild_treasury_precision(data_dir: Path, output_dir: Path, *, as_of: str) -> None:
    from src.value_list.hakedaka_nav_treasury_precision import (
        build_treasury_precision_rows,
        merge_treasury_events_with_precision,
        write_treasury_precision_csv,
    )

    rows = build_treasury_precision_rows(data_dir, output_dir, as_of=as_of)
    write_treasury_precision_csv(output_dir, rows)
    merge_treasury_events_with_precision(output_dir, rows)


def _attach_catalyst_to_evidence_pack(output_dir: Path) -> None:
    """Add catalyst_evidence_detail to existing evidence pack candidates."""
    pack_path = output_dir / "hakedaka_top10_evidence_pack.json"
    cat_path = output_dir / "hakedaka_catalyst_evidence.json"
    if not pack_path.exists() or not cat_path.exists():
        return
    try:
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        cat_doc = json.loads(cat_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for row in cat_doc.get("rows") or []:
        t = str(row.get("ticker", "")).zfill(6)
        by_ticker.setdefault(t, []).append(row)

    for cand in pack.get("candidates") or []:
        ticker = str(cand.get("ticker", "")).zfill(6)
        events = by_ticker.get(ticker, [])
        cand["catalyst_evidence_detail"] = events[:5]
        if events:
            best = max(events, key=lambda e: {"high": 3, "medium": 2, "low": 1}.get(
                str(e.get("extraction_confidence", "low")), 0,
            ))
            cand.setdefault("treasury_precision_summary", {})["body_extraction_confidence"] = best.get(
                "extraction_confidence",
            )

    pack_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_hakedaka_catalyst_evidence(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
    fetch_documents: bool = True,
    use_cache: bool = True,
    top_n: int = 15,
) -> dict[str, Any]:
    """Phase 4h — DART Document Body Fetch & Catalyst Evidence (shadow only)."""
    from src.settings.user_secrets import apply_secrets_to_env

    as_of_date = as_of or date.today().isoformat()
    apply_secrets_to_env(data_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    in_pytest = os.environ.get("PYTEST_CURRENT_TEST") is not None
    if in_pytest:
        fetch_documents = False

    precision_before = _treasury_precision_pct(output_dir)
    conf_before = {"high": 0, "medium": 0, "low": 0}
    for row in _load_treasury_events(output_dir):
        c = str(row.get("treasury_event_confidence", row.get("extraction_confidence", "low")))
        if c in conf_before:
            conf_before[c] += 1

    evidence_rows, updated_events, fetch_stats = process_catalyst_evidence(
        data_dir, output_dir, as_of=as_of_date,
        fetch_documents=fetch_documents, use_cache=use_cache,
    )

    if updated_events:
        write_updated_treasury_events(output_dir, updated_events)
        rebuild_treasury_precision(data_dir, output_dir, as_of=as_of_date)

    write_csv(output_dir / "hakedaka_catalyst_evidence.csv", CATALYST_EVIDENCE_FIELDS, evidence_rows)
    cat_json = {
        "as_of": as_of_date,
        "mode": "shadow_catalyst_evidence",
        "disclaimer": CATALYST_EVIDENCE_DISCLAIMER,
        "row_count": len(evidence_rows),
        "fetch_stats": fetch_stats,
        "confidence_distribution": _confidence_distribution(evidence_rows),
        "rows": evidence_rows,
    }
    (output_dir / "hakedaka_catalyst_evidence.json").write_text(
        json.dumps(cat_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )

    shr_rows = build_shareholder_return_rows(data_dir, output_dir, as_of=as_of_date)
    write_csv(output_dir / "hakedaka_shareholder_return.csv", SHAREHOLDER_RETURN_FIELDS, shr_rows)

    top_ver = build_top_candidate_verification_rows(
        data_dir, output_dir, as_of=as_of_date, top_n=top_n,
    )
    write_csv(output_dir / "hakedaka_top_candidate_verification.csv", TOP_CANDIDATE_VERIFICATION_FIELDS, top_ver)

    build_hakedaka_top10_evidence_pack(data_dir, output_dir, as_of=as_of_date)
    _attach_catalyst_to_evidence_pack(output_dir)

    precision_after = _treasury_precision_pct(output_dir)
    conf_after = _confidence_distribution(evidence_rows)
    shr_manual = sum(1 for r in shr_rows if r.get("manual_review_required"))
    examples = sorted(
        evidence_rows,
        key=lambda r: {"high": 3, "medium": 2, "low": 1}.get(str(r.get("extraction_confidence", "low")), 0),
        reverse=True,
    )[:3]

    report: dict[str, Any] = {
        "as_of": as_of_date,
        "mode": "shadow_only",
        "phase": "4h",
        "disclaimer": CATALYST_EVIDENCE_DISCLAIMER,
        "evidence_disclaimer": EVIDENCE_DISCLAIMER,
        "summary": {
            "documents_fetched_ok": fetch_stats.get("documents_fetched_ok", 0),
            "documents_fetch_failed": fetch_stats.get("documents_fetch_failed", 0),
            "confidence_distribution": conf_after,
            "confidence_before": conf_before,
            "treasury_precision_before_pct": precision_before,
            "treasury_precision_after_pct": precision_after,
            "shareholder_manual_review_count": shr_manual,
            "top_catalyst_examples": examples,
            "verified_top15_count": sum(1 for r in top_ver if r.get("verification_status") == "verified"),
            "treasury_verified_top15_count": sum(1 for r in top_ver if r.get("treasury_verified")),
        },
        "fetch_stats": fetch_stats,
    }
    (output_dir / "hakedaka_phase4h_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return report
