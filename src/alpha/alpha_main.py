from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.alpha.alpha_pipeline import run_alpha_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="KOSPI Alpha Screener")
    root = Path(__file__).resolve().parents[2]
    parser.add_argument("--data-dir", type=Path, default=root / "data")
    parser.add_argument("--output-dir", type=Path, default=root / "outputs")
    parser.add_argument("--as-of", type=str, default=None)
    args = parser.parse_args(argv)

    try:
        out = run_alpha_pipeline(args.data_dir, args.output_dir, as_of=args.as_of)
        r = out.result
        print(f"Alpha Screener | as_of={r.as_of} | gate={r.data_gate}")
        print(f"Candidates: {len(r.candidates)} | Excluded: {len(r.excluded)} | Holdings: {len(r.holdings_review)}")
        print(f"Outputs: {args.output_dir.resolve()}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
