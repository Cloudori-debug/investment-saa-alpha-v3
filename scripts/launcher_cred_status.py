"""Print DART/KRX credential status for launcher menu (bat-safe, no inline -c)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.settings.user_secrets import credential_status  # noqa: E402


def main() -> int:
    s = credential_status(ROOT / "data")
    dart = "OK" if s["dart"] else "MISSING"
    krx = "OK" if s["krx"] else "MISSING"
    print(f" API  DART: {dart}  | KRX: {krx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
