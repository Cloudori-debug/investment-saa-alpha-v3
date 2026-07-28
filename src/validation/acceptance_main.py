from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.validation.acceptance_check import run_acceptance_check, write_acceptance_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="운용 승인 기준 (AC) 검증")
    root = Path(__file__).resolve().parents[2]
    parser.add_argument("--data-dir", type=Path, default=root / "data")
    parser.add_argument("--output-dir", type=Path, default=root / "outputs")
    args = parser.parse_args(argv)

    report = run_acceptance_check(args.data_dir, args.output_dir)
    out_path = args.output_dir / "acceptance_report.json"
    write_acceptance_report(report, out_path)
    print(f"Acceptance: {report.overall} -> {out_path}")
    print(report.operational_verdict)
    return 0 if report.overall != "RED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
