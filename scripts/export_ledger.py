"""Export ledger to SAA-Alpha-Backup folder (USB carry kit half #2)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from alpha_system.ui.services.ops_assistant_pack import create_ops_backup_folder


def main() -> int:
    p = argparse.ArgumentParser(description="Export SAA Alpha ledger backup folder")
    p.add_argument("--root", type=Path, default=_ROOT)
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Destination folder (default: dist/CARRY/02_SAA-Alpha-Backup)",
    )
    p.add_argument("--with-secrets", action="store_true")
    p.add_argument("--with-market-cache", action="store_true")
    args = p.parse_args()
    out = args.out or (args.root / "dist" / "CARRY" / "02_SAA-Alpha-Backup")
    result = create_ops_backup_folder(
        args.root,
        dest_dir=out,
        include_optional_data=bool(args.with_market_cache),
        include_secrets=bool(args.with_secrets),
    )
    print(f"OK folder={result.path}")
    print(f"included={len(result.included)} missing={len(result.missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
