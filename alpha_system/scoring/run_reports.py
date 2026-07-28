"""CLI helpers for §7.2 reports (no fake correlation numbers)."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

from alpha_system.scoring.correlation import (
    analyze_factor_correlation,
    write_correlation_report,
)
from alpha_system.scoring.overlap import write_overlap_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="alpha_system scoring reports")
    parser.add_argument(
        "--overlap-out",
        type=Path,
        default=Path("docs/ALPHA_SYSTEM_CECS_T2_OVERLAP_REPORT.md"),
    )
    parser.add_argument(
        "--corr-out",
        type=Path,
        default=Path("docs/ALPHA_SYSTEM_FACTOR_CORRELATION_REPORT.md"),
    )
    parser.add_argument(
        "--factors-csv",
        type=Path,
        default=None,
        help="Optional CSV with seven factor columns; omit → correlation SKIPPED report",
    )
    parser.add_argument("--as-of", type=str, default=None)
    args = parser.parse_args(argv)

    write_overlap_report(args.overlap_out)

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    df = None
    if args.factors_csv is not None:
        df = pd.read_csv(args.factors_csv)
    report = analyze_factor_correlation(df, as_of=as_of)
    write_correlation_report(report, args.corr_out)
    print(f"overlap → {args.overlap_out}")
    print(f"correlation status={report.status} → {args.corr_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
