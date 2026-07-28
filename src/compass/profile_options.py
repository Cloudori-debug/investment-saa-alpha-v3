"""SAA 프로필 — 단일 운용 (defensive_balanced)."""

from __future__ import annotations

DEFAULT_PROFILE = "defensive_balanced"

# 레거시 CLI·스크립트 호환 (모두 defensive_balanced로 resolve)
PROFILE_CLI_CHOICES: list[str] = [
    "defensive_balanced",
    "balanced",
    "conservative",
    "growth",
    "qvm_sr",
    "capital_preservation",
    "active_growth",
]
