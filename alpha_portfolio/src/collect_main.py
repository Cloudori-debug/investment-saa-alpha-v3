from __future__ import annotations

import argparse
import sys
from datetime import date

from src.collect.pykrx_collector import run_collect


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PyKRX universe + price_snapshot collector")
    parser.add_argument("--as-of", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument(
        "--scope",
        choices=["holdings", "liquid", "all"],
        default=None,
        help="holdings=보유+fundamentals+target (기본)",
    )
    args = parser.parse_args(argv)

    try:
        result = run_collect(as_of=args.as_of, scope=args.scope)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"as_of       : {result.as_of}")
    print(f"scope       : {result.scope}")
    print(f"universe    : {result.universe_count}")
    print(f"snapshot    : {result.snapshot_count}")
    for k, v in result.paths.items():
        print(f"  {k}: {v}")
    for w in result.warnings:
        print(f"  WARN: {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
