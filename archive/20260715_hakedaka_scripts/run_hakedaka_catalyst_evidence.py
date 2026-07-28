#!/usr/bin/env python3
"""Phase 4h — DART Document Body Fetch & Catalyst Evidence (shadow only).

Usage:
  python scripts/run_hakedaka_catalyst_evidence.py
  python scripts/run_hakedaka_catalyst_evidence.py --no-fetch
  python scripts/run_hakedaka_catalyst_evidence.py --top-n 15
"""
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
    parser = argparse.ArgumentParser(description="Hakedaka catalyst evidence extraction (shadow only)")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--no-fetch", action="store_true", help="Skip DART document fetch (cache/re-extract only)")
    parser.add_argument("--no-cache", action="store_true", help="Ignore cached document bodies")
    parser.add_argument("--top-n", type=int, default=15)
    args = parser.parse_args(argv)

    as_of = args.as_of or date.today().isoformat()
    from src.settings.user_secrets import apply_secrets_to_env

    apply_secrets_to_env(args.data_dir)

    from src.value_list.hakedaka_catalyst_evidence import run_hakedaka_catalyst_evidence

    report = run_hakedaka_catalyst_evidence(
        args.data_dir,
        args.output_dir,
        as_of=as_of,
        fetch_documents=not args.no_fetch,
        use_cache=not args.no_cache,
        top_n=args.top_n,
    )
    out_path = args.output_dir / "hakedaka_phase4h_run.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report.get("summary") or {}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
