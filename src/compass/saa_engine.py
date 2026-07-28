from __future__ import annotations

from pathlib import Path
from typing import Any

from src.compass.profile_aliases import resolve_profile_name
from src.config import load_yaml


def load_saa_profiles(path: Path) -> dict[str, Any]:
    return load_yaml(path)


def get_saa_weights(profiles: dict[str, Any], profile_name: str | None = None) -> dict[str, float]:
    name = resolve_profile_name(profiles, profile_name)
    profile = profiles.get("profiles", {}).get(name)
    if not profile:
        raise ValueError(f"unknown SAA profile: {name}")
    groups = profile.get("groups", {})
    total = sum(float(v) for v in groups.values())
    if abs(total - 100) > 0.5:
        raise ValueError(f"SAA profile '{name}' weights sum to {total}, expected 100")
    return {str(k): float(v) for k, v in groups.items()}


def get_group_bounds(profiles: dict[str, Any], profile_name: str | None = None) -> dict[str, dict[str, float]]:
    name = resolve_profile_name(profiles, profile_name)
    profile = profiles.get("profiles", {}).get(name, {})
    bounds = profile.get("group_bounds", {})
    return {
        str(group): {"min": float(b.get("min", 0)), "max": float(b.get("max", 100))}
        for group, b in bounds.items()
    }
