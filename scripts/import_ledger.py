"""Import ledger from SAA-Alpha-Backup folder or zip."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from alpha_system.ui.services.ops_assistant_pack import restore_ops_backup_any


def main() -> int:
    p = argparse.ArgumentParser(description="Import SAA Alpha ledger backup")
    p.add_argument("path", type=Path, help="Backup folder or .zip")
    p.add_argument("--root", type=Path, default=_ROOT)
    p.add_argument("--no-overwrite", action="store_true")
    args = p.parse_args()
    result = restore_ops_backup_any(
        args.root,
        args.path,
        overwrite=not args.no_overwrite,
    )
    print(f"restored={len(result.get('restored', []))} skipped={len(result.get('skipped', []))}")
    for rel in result.get("restored", [])[:30]:
        print(f"  + {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
