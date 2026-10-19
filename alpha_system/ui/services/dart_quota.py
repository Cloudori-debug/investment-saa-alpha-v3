"""OpenDART daily call budget — soft stop before 020 hard fail.

Official guide: status 020 when request limit exceeded (often ~10k–20k/day
per key; exact cap varies). Mid-session full reloads burn the budget.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# Soft ceiling leaves headroom under typical personal-key caps.
DEFAULT_DAILY_SOFT_LIMIT = 8_000
QUOTA_FILENAME = "dart_api_quota.json"


def quota_path(data_dir: Path) -> Path:
    return Path(data_dir) / "local" / QUOTA_FILENAME


@dataclass
class DartQuota:
    day: str
    calls: int = 0
    soft_limit: int = DEFAULT_DAILY_SOFT_LIMIT
    by_path: dict[str, int] | None = None

    def remaining(self) -> int:
        return max(0, int(self.soft_limit) - int(self.calls))

    def can_call(self, n: int = 1) -> bool:
        return self.remaining() >= max(1, int(n))

    def record(self, path: str = "", n: int = 1) -> None:
        self.calls = int(self.calls) + max(1, int(n))
        bucket = self.by_path if self.by_path is not None else {}
        key = str(path or "unknown")
        bucket[key] = int(bucket.get(key) or 0) + max(1, int(n))
        self.by_path = bucket

    def status_line(self) -> str:
        return (
            f"DART 호출 {self.calls}/{self.soft_limit} "
            f"(잔여 {self.remaining()} · 일 {self.day})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "calls": int(self.calls),
            "soft_limit": int(self.soft_limit),
            "by_path": dict(self.by_path or {}),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }


def load_quota(
    data_dir: Path,
    *,
    soft_limit: int = DEFAULT_DAILY_SOFT_LIMIT,
    today: date | None = None,
) -> DartQuota:
    day = (today or date.today()).isoformat()
    path = quota_path(data_dir)
    if not path.exists():
        return DartQuota(day=day, soft_limit=soft_limit)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return DartQuota(day=day, soft_limit=soft_limit)
    if not isinstance(raw, dict) or str(raw.get("day") or "") != day:
        return DartQuota(day=day, soft_limit=soft_limit)
    return DartQuota(
        day=day,
        calls=int(raw.get("calls") or 0),
        soft_limit=int(raw.get("soft_limit") or soft_limit),
        by_path=dict(raw.get("by_path") or {}),
    )


def save_quota(data_dir: Path, quota: DartQuota) -> Path:
    path = quota_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(quota.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
