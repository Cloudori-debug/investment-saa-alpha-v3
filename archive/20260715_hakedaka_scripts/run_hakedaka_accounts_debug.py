#!/usr/bin/env python3
"""Phase 4e — DART Accounts Fetch Debug (shadow only).

Usage:
  python scripts/run_hakedaka_accounts_debug.py --force --save-raw --write-summary
  python scripts/run_hakedaka_accounts_debug.py --sample-size 5 --years 2026,2025,2024
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
    parser = argparse.ArgumentParser(description="DART accounts fetch debug (shadow only)")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--sample-size", type=int, default=5)
    parser.add_argument("--force", action="store_true", help="fallback enrich + coverage audit refresh")
    parser.add_argument("--years", type=str, default="", help="comma-separated bsns_year list")
    parser.add_argument("--save-raw", action="store_true", help="save raw JSON samples for failures")
    parser.add_argument("--write-summary", action="store_true", help="write dart_accounts_debug_summary.json")
    args = parser.parse_args(argv)

    years: list[str] | None = None
    if args.years.strip():
        years = [y.strip() for y in args.years.split(",") if y.strip()]

    from src.value_list.dart_accounts_debug import run_dart_accounts_debug

    report = run_dart_accounts_debug(
        args.data_dir,
        args.output_dir,
        as_of=args.as_of or date.today().isoformat(),
        sample_size=args.sample_size,
        force=args.force,
        years=years,
        save_raw=args.save_raw,
        write_summary=args.write_summary or True,
    )
    summary = report.get("summary") or {}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary.get("dominant_failure_category"):
        print(
            f"dominant: {summary['dominant_failure_category']} -> "
            f"{summary.get('recommended_next_action', '')}"
        )
    return 0 if report.get("dart_credentials", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
