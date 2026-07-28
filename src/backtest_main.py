from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.backtest.regime_backtest import run_regime_backtest, write_backtest_outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="레짐·자산군 배분 백테스트")
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--data-dir", type=Path, default=root / "data")
    parser.add_argument("--output-dir", type=Path, default=root / "outputs")
    parser.add_argument("--profile", default=None)
    args = parser.parse_args(argv)

    try:
        result = run_regime_backtest(args.data_dir, profile=args.profile)
        write_backtest_outputs(result, args.output_dir)
        print(f"Backtest: {len(result.rows)} days, regime changes={result.regime_changes}")
        print(f"Output: {args.output_dir.resolve()}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
