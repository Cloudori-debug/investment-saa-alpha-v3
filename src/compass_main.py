from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.compass.compass_pipeline import run_compass_pipeline
from src.data_loader import load_positions, load_target_portfolio


from src.compass.profile_options import PROFILE_CLI_CHOICES

PROFILE_CHOICES = PROFILE_CLI_CHOICES


def run_compass(
    data_dir: Path,
    output_dir: Path,
    *,
    profile: str | None = None,
) -> int:
    positions = None
    targets = None
    pos_path = data_dir / "positions.csv"
    tgt_path = data_dir / "target_portfolio.csv"
    if pos_path.exists():
        positions = load_positions(pos_path)
    if tgt_path.exists():
        targets = load_target_portfolio(tgt_path)

    result = run_compass_pipeline(
        data_dir,
        output_dir,
        profile=profile,
        positions=positions,
        ticker_targets=targets,
        template_targets=targets,
        auto_decompose=True,
    )

    print(f"Compass: {result.compass.compass_direction} | Phase: {result.compass.market_phase.value}")
    print(f"Regime: applied={result.compass.applied_regime.value} computed={result.compass.computed_regime.value}")
    print(f"Profile: {result.allocation.profile} | Tier2: {result.tier2_used}")
    if result.generated_targets:
        print(f"Generated targets: {len(result.generated_targets)} tickers")
    if result.mismatch_warnings:
        print(f"Mismatch warnings: {len(result.mismatch_warnings)}")
    print(f"Outputs: {output_dir.resolve()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="시장·레짐 나침반 P0 v1.0+")
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--data-dir", type=Path, default=root / "data")
    parser.add_argument("--output-dir", type=Path, default=root / "outputs")
    parser.add_argument("--profile", choices=PROFILE_CHOICES, default=None)
    args = parser.parse_args(argv)

    try:
        return run_compass(args.data_dir, args.output_dir, profile=args.profile)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
