from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.backtest.alpha_backtest import run_alpha_lite_backtest, write_alpha_backtest_outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alpha Lite 백테스트 (quintile + top-N 검증)")
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--data-dir", type=Path, default=root / "data")
    parser.add_argument("--output-dir", type=Path, default=root / "outputs")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help="Use only the last N unique history dates (optional).",
    )
    args = parser.parse_args(argv)

    try:
        result = run_alpha_lite_backtest(
            args.data_dir,
            top_n=args.top_n,
            lookback_days=args.lookback_days,
        )
        write_alpha_backtest_outputs(result, args.output_dir)
        print(
            f"Alpha BT: scored_days={len(result.scored_dates)} "
            f"price_history_days={len(result.dates)} quality={result.sample_quality} "
            f"top{result.top_n}_gross_excess={result.top_n_excess:.2%} "
            f"net_excess={result.top_n_excess_net:.2%} monotonic={result.monotonic}"
        )
        print(f"Output: {args.output_dir.resolve()}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
