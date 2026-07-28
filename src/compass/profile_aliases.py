from __future__ import annotations

from typing import Any

PROFILE_CANONICAL: dict[str, list[str]] = {
    "defensive_balanced": [
        "balanced",
        "conservative",
        "growth",
        "qvm_sr",
        "capital_preservation",
        "active_growth",
    ],
}

_LEGACY_TO_CANONICAL: dict[str, str] = {
    alias: canonical for canonical, aliases in PROFILE_CANONICAL.items() for alias in aliases
}


def resolve_profile_name(profiles: dict[str, Any], name: str | None = None) -> str:
    default = profiles.get("default_profile", "defensive_balanced")
    raw = name or default
    aliases: dict[str, str] = profiles.get("profile_aliases", {})
    if raw in aliases:
        return aliases[raw]
    if raw in _LEGACY_TO_CANONICAL:
        return _LEGACY_TO_CANONICAL[raw]
    if raw in profiles.get("profiles", {}):
        return raw
    raise ValueError(f"unknown SAA profile: {raw}")


def canonical_profile_name(name: str) -> str:
    return _LEGACY_TO_CANONICAL.get(name, name)
