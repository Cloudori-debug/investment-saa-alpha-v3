"""v3 hygiene prune — journal / local backups / optional cache.

Does NOT touch: target_portfolio.csv, exit_targets.yaml, universe, config yaml.
Default is dry-run; pass --apply to write.
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / "data" / "alpha_system_journal.jsonl"
JOURNAL_ARCHIVE = ROOT / "data" / "local" / "journal_archive"
BACKUP_DIR = ROOT / "data" / "local" / "backups"
CACHE_DIR = ROOT / "data" / "cache"
PRICES_HISTORY = ROOT / "data" / "prices_history.csv"

DEFAULT_KEEP_LINES = 200
DEFAULT_KEEP_BACKUPS = 3


def _archive_journal(*, keep: int, apply: bool) -> str:
    if not JOURNAL.exists():
        return "journal: missing (skip)"
    lines = JOURNAL.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    n = len(lines)
    if n <= keep:
        return f"journal: {n} lines ≤ keep={keep} (no trim)"
    old, new = lines[:-keep], lines[-keep:]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = JOURNAL_ARCHIVE / f"alpha_system_journal_{stamp}.jsonl"
    msg = f"journal: archive {len(old)} lines → {dest.relative_to(ROOT)} · keep {len(new)}"
    if not apply:
        return msg + " [dry-run]"
    JOURNAL_ARCHIVE.mkdir(parents=True, exist_ok=True)
    dest.write_text("".join(old), encoding="utf-8")
    JOURNAL.write_text("".join(new), encoding="utf-8")
    return msg + " [applied]"


def _prune_backups(*, keep: int, apply: bool) -> str:
    if not BACKUP_DIR.is_dir():
        return "backups: no data/local/backups (skip)"
    zips = sorted(BACKUP_DIR.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    drop = zips[keep:]
    if not drop:
        return f"backups: {len(zips)} zip(s) ≤ keep={keep}"
    names = ", ".join(p.name for p in drop)
    msg = f"backups: remove {len(drop)} older → keep {keep} ({names})"
    if not apply:
        return msg + " [dry-run]"
    for p in drop:
        p.unlink(missing_ok=True)
    return msg + " [applied]"


def _clear_cache(*, apply: bool) -> str:
    if not CACHE_DIR.is_dir():
        return "cache: missing (skip)"
    files = list(CACHE_DIR.rglob("*"))
    n = sum(1 for p in files if p.is_file())
    msg = f"cache: clear {n} file(s) under data/cache/"
    if not apply:
        return msg + " [dry-run]"
    shutil.rmtree(CACHE_DIR, ignore_errors=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return msg + " [applied]"


def _drop_prices_history(*, apply: bool) -> str:
    if not PRICES_HISTORY.exists():
        return "prices_history: missing (skip)"
    kb = PRICES_HISTORY.stat().st_size / 1024
    msg = f"prices_history: delete {kb:.0f} KB (regenerate via refresh)"
    if not apply:
        return msg + " [dry-run]"
    PRICES_HISTORY.unlink()
    return msg + " [applied]"


def main() -> int:
    ap = argparse.ArgumentParser(description="v3 hygiene prune (safe defaults)")
    ap.add_argument("--apply", action="store_true", help="write changes (default dry-run)")
    ap.add_argument("--keep-journal", type=int, default=DEFAULT_KEEP_LINES)
    ap.add_argument("--keep-backups", type=int, default=DEFAULT_KEEP_BACKUPS)
    ap.add_argument("--cache", action="store_true", help="also clear data/cache/")
    ap.add_argument(
        "--prices-history",
        action="store_true",
        help="also delete data/prices_history.csv (regenerable)",
    )
    args = ap.parse_args()

    print(f"root={ROOT}")
    print(f"mode={'APPLY' if args.apply else 'DRY-RUN'}")
    print(_archive_journal(keep=args.keep_journal, apply=args.apply))
    print(_prune_backups(keep=args.keep_backups, apply=args.apply))
    if args.cache:
        print(_clear_cache(apply=args.apply))
    else:
        print("cache: skipped (pass --cache to clear)")
    if args.prices_history:
        print(_drop_prices_history(apply=args.apply))
    else:
        print("prices_history: kept (pass --prices-history to delete)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
