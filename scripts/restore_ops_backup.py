"""CLI: restore SAA 알파 운용 비서 backup zip into this repo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from alpha_system.ui.services.ops_assistant_pack import restore_ops_backup_zip


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore ops assistant backup zip")
    parser.add_argument("zip_path", type=Path, help="Path to saa_ops_assistant_backup_*.zip")
    parser.add_argument(
        "--root",
        type=Path,
        default=_ROOT,
        help="Repo root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Skip files that already exist",
    )
    args = parser.parse_args()
    result = restore_ops_backup_zip(
        args.root,
        args.zip_path,
        overwrite=not args.no_overwrite,
    )
    print(f"restored={len(result['restored'])} skipped={len(result['skipped'])}")
    for rel in result["restored"][:20]:
        print(f"  + {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
