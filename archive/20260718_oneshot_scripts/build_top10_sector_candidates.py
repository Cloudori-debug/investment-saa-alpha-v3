"""Build top10 sector unknown list and manual mapping candidates."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.alpha.alpha_pipeline import run_alpha_pipeline
from src.alpha.top10_sector_candidate import format_top10_sector_candidate_report_lines


def main() -> int:
    data_dir = ROOT / "data"
    output_dir = ROOT / "outputs"
    run_alpha_pipeline(data_dir, output_dir, write_outputs=True)
    review_path = output_dir / "top10_sector_candidate_review.json"
    if not review_path.exists():
        print("FAIL: top10_sector_candidate_review.json not created")
        return 1
    meta = json.loads(review_path.read_text(encoding="utf-8"))
    print("\n".join(format_top10_sector_candidate_report_lines(meta)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
