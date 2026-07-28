"""CLI: Method B compass backtest — does not alter src/compass/ or data/ ops files."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Compass Method B external long-history backtest")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "backtest")
    parser.add_argument("--n-trials", type=int, default=16)
    args = parser.parse_args()

    from src.backtest.compass_method_b import run_method_b_backtest

    result = run_method_b_backtest(
        args.data_dir,
        args.output_dir,
        n_trials=args.n_trials,
    )
    print(json.dumps(
        {
            "output_dir": result["output_dir"],
            "panel": {
                "start": result["data_notes"].get("panel_start"),
                "end": result["data_notes"].get("panel_end"),
                "rows": result["data_notes"].get("panel_rows"),
                "judgment_start": result["data_notes"].get("judgment_start"),
            },
            "excess_ann": result["perf_summary"].get("excess_ann"),
            "dsr_excess": result["stats"]["dsr_excess"].get("dsr"),
            "regime_flips": result["stats"]["cycles"].get("regime_flips"),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
