from __future__ import annotations

from pathlib import Path

from src.value_list.compass_overlay import write_hakedaka_compass_overlay
from src.value_list.dart_prep import prepare_hakedaka_dart_pipeline
from src.value_list.dart_verification import run_hakedaka_dart_verification
from src.value_list.macro_scenarios import write_macro_scenario
from src.value_list.pipeline import run_hakedaka_tracker
from src.value_list.research_checklist import write_research_checklist
from src.value_list.ticker_registry import resolve_hakedaka_registry
from src.settings.user_secrets import credential_status


def _research_progress(label: str) -> None:
    import os
    import sys

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        print(f"    · 하케다카: {label}...", flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(f"    · hakedaka: {label}...".encode(enc, errors="replace").decode(enc), flush=True)


def run_research_automation(data_dir: Path, output_dir: Path) -> None:
    """하케다카 DART 검증·추적·거시·체크리스트·배분 오버레이 자동 실행."""
    output_dir.mkdir(parents=True, exist_ok=True)
    _research_progress("레지스트리")
    tickers = [
        str(r["ticker"]).zfill(6)
        for r in resolve_hakedaka_registry(data_dir)
        if r.get("ticker")
    ]

    ver_csv = output_dir / "hakedaka_dart_verification.csv"
    if not ver_csv.exists():
        prepare_hakedaka_dart_pipeline(data_dir, output_dir)
    elif credential_status(data_dir).get("dart"):
        run_hakedaka_dart_verification(data_dir, output_dir, tickers)

    _research_progress("DART 검증·트래커")
    run_hakedaka_tracker(data_dir, output_dir)
    write_macro_scenario(data_dir, output_dir)

    from src.value_list.hakedaka_refresh_pipeline import run_hakedaka_data_refresh

    as_of = ""
    macro_path = output_dir / "macro_scenario.json"
    if macro_path.exists():
        import json

        as_of = str(json.loads(macro_path.read_text(encoding="utf-8")).get("as_of", ""))[:10]
    if not as_of:
        from datetime import date

        as_of = date.today().isoformat()

    _research_progress("데이터 리프레시")
    run_hakedaka_data_refresh(data_dir, output_dir, as_of=as_of, force_dart=True)

    _research_progress("리레이팅·증거")
    from src.value_list.rerating_screener import write_hakedaka_rerating_outputs
    write_hakedaka_rerating_outputs(data_dir, output_dir, as_of=as_of)

    from src.value_list.hakedaka_evidence_enrichment import run_hakedaka_evidence_enrichment
    run_hakedaka_evidence_enrichment(
        data_dir, output_dir, as_of=as_of, build_evidence_pack=True, fetch_treasury=False,
    )

    from src.value_list.hakedaka_coverage_audit import write_hakedaka_coverage_audit

    write_hakedaka_coverage_audit(data_dir, output_dir, as_of=as_of)

    from src.value_list.hakedaka_nav_treasury_precision import run_hakedaka_nav_treasury_precision
    run_hakedaka_nav_treasury_precision(
        data_dir, output_dir, as_of=as_of, force_fundamentals=False, rescan_treasury=False,
    )

    from src.value_list.hakedaka_manual_verification_queue import run_hakedaka_manual_verification_queue
    run_hakedaka_manual_verification_queue(data_dir, output_dir, as_of=as_of)

    _research_progress("촉매·캘리브레이션")
    from src.value_list.hakedaka_catalyst_evidence import run_hakedaka_catalyst_evidence
    import os
    run_hakedaka_catalyst_evidence(
        data_dir, output_dir, as_of=as_of,
        fetch_documents=not os.environ.get("PYTEST_CURRENT_TEST"),
    )

    from src.value_list.hakedaka_catalyst_calibration_runner import run_hakedaka_catalyst_calibration
    run_hakedaka_catalyst_calibration(data_dir, output_dir, as_of=as_of)

    from src.value_list.hakedaka_forward_return_tracker import run_hakedaka_forward_return_tracking
    run_hakedaka_forward_return_tracking(data_dir, output_dir, as_of=as_of)

    _research_progress("체크리스트·오버레이")
    write_research_checklist(data_dir, output_dir)
    write_hakedaka_compass_overlay(data_dir, output_dir)
