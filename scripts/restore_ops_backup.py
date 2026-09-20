"""CLI: restore 코스피 알파 스크리너 backup zip OR backup folder."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from alpha_system.ui.services.ops_assistant_pack import restore_ops_backup_any


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore ops assistant backup (zip or folder)")
    parser.add_argument("path", type=Path, help="Backup zip or SAA-Alpha-Backup folder")
    parser.add_argument("--root", type=Path, default=_ROOT)
    parser.add_argument("--no-overwrite", action="store_true")
    args = parser.parse_args()
    result = restore_ops_backup_any(
        args.root,
        args.path,
        overwrite=not args.no_overwrite,
    )
    print(f"restored={len(result.get('restored', []))} skipped={len(result.get('skipped', []))}")
    for rel in result.get("restored", [])[:20]:
        print(f"  + {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
