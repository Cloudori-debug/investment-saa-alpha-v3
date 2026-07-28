#!/usr/bin/env python3
"""Phase 4h-1 — Catalyst Extraction Calibration (shadow only)."""
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
    parser = argparse.ArgumentParser(description="Hakedaka catalyst calibration (shadow only)")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--top-n", type=int, default=15)
    args = parser.parse_args(argv)

    from src.value_list.hakedaka_catalyst_calibration_runner import run_hakedaka_catalyst_calibration

    report = run_hakedaka_catalyst_calibration(
        args.data_dir, args.output_dir, as_of=args.as_of or date.today().isoformat(), top_n=args.top_n,
    )
    out = args.output_dir / "hakedaka_phase4h1_run.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report.get("summary") or {}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
