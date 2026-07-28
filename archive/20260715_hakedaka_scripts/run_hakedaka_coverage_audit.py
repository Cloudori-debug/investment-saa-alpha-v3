#!/usr/bin/env python3
"""Phase 4d — Hakedaka Coverage Audit & Enrichment Runbook (shadow only).

Usage:
  python scripts/run_hakedaka_coverage_audit.py
  python scripts/run_hakedaka_coverage_audit.py --force-fundamentals --write-runbook
  python scripts/run_hakedaka_coverage_audit.py --lookback-days 90 --top-n-evidence 10
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hakedaka coverage audit runbook (shadow only)")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    parser.add_argument("--as-of", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--force-fundamentals", action="store_true", help="DART fundamentals 강제 enrich")
    parser.add_argument("--lookback-days", type=int, default=90, help="Treasury event lookback days")
    parser.add_argument("--top-n-evidence", type=int, default=10, help="Manual review queue size")
    parser.add_argument("--write-runbook", action="store_true", help="hakedaka_coverage_runbook.md 생성")
    parser.add_argument("--skip-treasury", action="store_true", help="Treasury rescan 생략")
    args = parser.parse_args(argv)

    as_of = args.as_of or date.today().isoformat()
    from src.settings.user_secrets import apply_secrets_to_env

    apply_secrets_to_env(args.data_dir)

    from src.value_list.hakedaka_coverage_audit import (
        run_hakedaka_coverage_audit_pipeline,
        write_coverage_runbook_markdown,
        write_hakedaka_coverage_audit,
    )

    report: dict = {"as_of": as_of, "exit_code": 0}
    try:
        pipeline = run_hakedaka_coverage_audit_pipeline(
            args.data_dir,
            args.output_dir,
            as_of=as_of,
            force_fundamentals=args.force_fundamentals,
            lookback_days=args.lookback_days,
            top_n_evidence=args.top_n_evidence,
            fetch_treasury=not args.skip_treasury,
        )
        report["pipeline"] = pipeline
    except Exception as exc:
        report["pipeline_error"] = str(exc)
        try:
            audit = write_hakedaka_coverage_audit(
                args.data_dir,
                args.output_dir,
                as_of=as_of,
                top_n_review=args.top_n_evidence,
            )
            report["coverage_audit_fallback"] = audit.get("coverage")
        except Exception as inner:
            report["coverage_audit_fallback_error"] = str(inner)
            report["exit_code"] = 1

    audit_path = args.output_dir / "hakedaka_coverage_audit.json"
    if audit_path.exists():
        audit_doc = json.loads(audit_path.read_text(encoding="utf-8"))
        if args.write_runbook:
            rb = write_coverage_runbook_markdown(args.output_dir, audit_doc)
            report["runbook_path"] = str(rb)
        report["coverage"] = audit_doc.get("coverage")
        report["target_warnings"] = audit_doc.get("target_warnings")
        report["below_target"] = audit_doc.get("below_target")
        if audit_doc.get("below_target"):
            print("WARN: coverage below target - shadow diagnostic only, no execution impact")
            for w in audit_doc.get("target_warnings") or []:
                print(f"  WARN {w.get('metric')}: {w.get('actual_pct')}% < {w.get('target_pct')}%")

    summary_path = args.output_dir / "hakedaka_coverage_audit_run.json"
    summary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report.get("coverage") or {}, ensure_ascii=False, indent=2))
    return int(report.get("exit_code", 0))


if __name__ == "__main__":
    raise SystemExit(main())
