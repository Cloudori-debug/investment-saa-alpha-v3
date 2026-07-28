"""CLI: create SAA 알파 운용 비서 backup zip (format / other PC)."""

from __future__ import annotations

import argparse
from pathlib import Path

from alpha_system.ui.services.ops_assistant_pack import create_ops_backup_zip


def main() -> int:
    parser = argparse.ArgumentParser(description="Create ops assistant backup zip")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repo root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Destination directory (default: data/local/backups)",
    )
    parser.add_argument(
        "--with-secrets",
        action="store_true",
        help="Include data/local/user_secrets.json (USB encrypt recommended)",
    )
    parser.add_argument(
        "--no-optional-data",
        action="store_true",
        help="Skip prices/fundamentals/alpha_scores caches",
    )
    args = parser.parse_args()
    result = create_ops_backup_zip(
        args.root,
        dest_dir=args.out_dir,
        include_optional_data=not args.no_optional_data,
        include_secrets=bool(args.with_secrets),
    )
    print(f"OK {result.path}")
    print(f"included={len(result.included)} missing={len(result.missing)}")
    if args.with_secrets:
        print("WARNING: secrets included — do not share this zip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
