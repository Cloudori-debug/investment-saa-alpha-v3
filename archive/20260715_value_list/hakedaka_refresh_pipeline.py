from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from src.data_refresh.tier_h import ensure_tier_h_prices, refresh_tier_h_snapshot
from src.value_list.dart_disclosure import scan_hakedaka_dart_events
from src.value_list.hakedaka_data_quality import write_hakedaka_data_quality_report
from src.value_list.hakedaka_fundamentals import enrich_hakedaka_fundamentals, tier_h_fundamentals_is_due
from src.value_list.hakedaka_evidence_enrichment import run_hakedaka_evidence_enrichment
from src.value_list.ticker_registry import resolve_hakedaka_registry


def run_hakedaka_data_refresh(
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
    force_dart: bool = True,
    force_fundamentals: bool = False,
) -> dict[str, Any]:
    """Phase 4b — Tier H 가격·DART·재무·품질 리포트 (shadow only)."""
    as_of_date = as_of or date.today().isoformat()
    tickers = [
        str(r["ticker"]).zfill(6)
        for r in resolve_hakedaka_registry(data_dir)
        if r.get("ticker")
    ]
    report: dict[str, Any] = {"as_of": as_of_date, "mode": "shadow_only", "steps": {}}

    fetch_prices = os.environ.get("PYTEST_CURRENT_TEST") is None
    tier_h = ensure_tier_h_prices(data_dir, as_of_date, fetch_missing=fetch_prices)
    report["steps"]["tier_h_prices"] = {
        "required": tier_h.required_count,
        "coverage_pct": tier_h.coverage_pct,
        "added": tier_h.added[:12],
        "failed": tier_h.failed[:12],
    }

    dart_result: dict[str, Any] = {"skipped": "pytest"}
    if fetch_prices:
        try:
            dart_result = scan_hakedaka_dart_events(
                data_dir,
                output_dir,
                tickers,
                as_of=as_of_date,
                lookback_days=90,
                force_rescan=force_dart,
            )
        except Exception as exc:
            dart_result = {"error": str(exc)}
    report["steps"]["dart_events"] = dart_result

    fund_result: dict[str, Any] = {"ran": False}
    if fetch_prices and (force_fundamentals or tier_h_fundamentals_is_due(data_dir, as_of_date)):
        try:
            fr = enrich_hakedaka_fundamentals(
                data_dir, tickers, as_of=as_of_date, force=force_fundamentals,
            )
            fund_result = {"ran": fr.ran, "enriched": fr.enriched, "skipped": fr.skipped, "reason": fr.reason}
        except Exception as exc:
            fund_result = {"error": str(exc)}
    report["steps"]["hakedaka_fundamentals"] = fund_result

    quality = write_hakedaka_data_quality_report(
        data_dir,
        output_dir,
        as_of=as_of_date,
        tier_h_coverage_pct=tier_h.coverage_pct,
    )
    report["steps"]["data_quality"] = quality

    evidence = run_hakedaka_evidence_enrichment(
        data_dir,
        output_dir,
        as_of=as_of_date,
        force_fundamentals=force_fundamentals,
        build_evidence_pack=False,
        fetch_treasury=fetch_prices,
    )
    report["steps"]["evidence_enrichment"] = evidence.get("steps", {})
    return report
