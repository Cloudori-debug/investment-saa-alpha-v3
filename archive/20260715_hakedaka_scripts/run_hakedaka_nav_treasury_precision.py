#!/usr/bin/env python3
"""Phase 4f — Hakedaka NAV & Treasury Precision (shadow only).

Usage:
  python scripts/run_hakedaka_nav_treasury_precision.py
  python scripts/run_hakedaka_nav_treasury_precision.py --force-fundamentals --rescan-treasury
  python scripts/run_hakedaka_nav_treasury_precision.py --skip-treasury --skip-fundamentals
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
    parser = argparse.ArgumentParser(description="Hakedaka NAV & Treasury Precision (shadow only)")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    parser.add_argument("--as-of", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--force-fundamentals", action="store_true", help="DART fundamentals 강제 enrich")
    parser.add_argument("--rescan-treasury", action="store_true", help="Treasury events DART rescan")
    parser.add_argument("--skip-fundamentals", action="store_true", help="Fundamentals enrich 생략")
    parser.add_argument("--skip-treasury", action="store_true", help="Treasury rescan 생략")
    args = parser.parse_args(argv)

    as_of = args.as_of or date.today().isoformat()
    from src.settings.user_secrets import apply_secrets_to_env

    apply_secrets_to_env(args.data_dir)

    from src.value_list.hakedaka_nav_treasury_precision import run_hakedaka_nav_treasury_precision

    report = run_hakedaka_nav_treasury_precision(
        args.data_dir,
        args.output_dir,
        as_of=as_of,
        force_fundamentals=args.force_fundamentals and not args.skip_fundamentals,
        rescan_treasury=args.rescan_treasury and not args.skip_treasury,
    )
    summary_path = args.output_dir / "hakedaka_phase4f_run.json"
    summary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report.get("summary") or {}, ensure_ascii=False, indent=2))
    if report.get("manual_override_warnings"):
        print("WARN manual overrides:", report["manual_override_warnings"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
