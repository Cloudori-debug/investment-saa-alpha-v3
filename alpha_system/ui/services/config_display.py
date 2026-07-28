"""Config field classification for settings page."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from alpha_system.loader import load_raw_yaml
from alpha_system.schema import AlphaSystemConfig, ConfigTodoError

Category = Literal["locked", "confirmed", "todo"]


@dataclass(frozen=True)
class ConfigFieldRow:
    path: str
    value: Any
    category: Category
    note: str = ""


LOCKED_PREFIXES = (
    "version",
    "purpose",
    "hard_rules",
    "tranches.",
    "capital.",
    "benchmark",
)

TODO_NULL_PATHS = {
    "scoring.score_cutoff",
    "exit.thesis_damage_exit",
    "exit.score_below_cutoff_action",
    "exit.target_valuation_exit",
    "exit.window_end_portfolio_action",
    "thesis_damage_event_ids",
}


def _flatten(obj: Any, prefix: str = "") -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, (dict, list)) and v and not isinstance(v, list):
                rows.extend(_flatten(v, p))
            else:
                rows.append((p, v))
    else:
        rows.append((prefix, obj))
    return rows


def _is_todo(path: str, value: Any) -> bool:
    if path in TODO_NULL_PATHS:
        return value is None or value == [] or value == ""
    if value is None:
        return True
    if isinstance(value, list) and len(value) == 0 and "event_ids" not in path:
        return path.endswith("_ids") or path in TODO_NULL_PATHS
    return False


def _is_locked(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in LOCKED_PREFIXES)


def classify_config(cfg_path) -> tuple[list[ConfigFieldRow], list[str]]:
    raw = load_raw_yaml(cfg_path)
    try:
        AlphaSystemConfig.model_validate(raw)
        validation_ok = True
        todo_errors: list[str] = []
    except ConfigTodoError as exc:
        validation_ok = False
        todo_errors = [str(exc)]
    except Exception as exc:
        validation_ok = False
        todo_errors = [str(exc)]

    rows: list[ConfigFieldRow] = []
    for path, value in _flatten(raw):
        if _is_todo(path, value):
            cat: Category = "todo"
            note = "가동 전 확정 필요"
        elif _is_locked(path):
            cat = "locked"
            note = "스키마 검증 대상"
        else:
            cat = "confirmed"
            note = ""
        rows.append(ConfigFieldRow(path=path, value=value, category=cat, note=note))
    return rows, todo_errors if not validation_ok else []
