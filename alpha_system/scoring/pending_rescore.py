"""Persist pending CECS rescore review signals for the home action queue."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_PATH = Path("data/pending_rescore_reviews.json")


def pending_path(root: Path | None = None) -> Path:
    if root is None:
        return DEFAULT_PATH
    return root / "data" / "pending_rescore_reviews.json"


def load_pending(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or DEFAULT_PATH
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = raw.get("items") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict) and not x.get("dismissed")]


def upsert_pending(
    item: Mapping[str, Any],
    *,
    path: Path | None = None,
) -> None:
    p = path or DEFAULT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, Any]] = []
    meta: dict[str, Any] = {}
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                meta = {k: v for k, v in raw.items() if k != "items"}
                existing = list(raw.get("items") or [])
            elif isinstance(raw, list):
                existing = list(raw)
        except (OSError, json.JSONDecodeError):
            existing = []
    key = str(item.get("key") or "")
    out: list[dict[str, Any]] = []
    replaced = False
    for old in existing:
        if key and old.get("key") == key:
            out.append(dict(item))
            replaced = True
        else:
            out.append(old)
    if not replaced:
        out.append(dict(item))
    payload = {
        **meta,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "items": out,
    }
    _atomic_write(p, payload)


def dismiss_pending(key: str, *, path: Path | None = None) -> None:
    p = path or DEFAULT_PATH
    items = []
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            items = list((raw.get("items") if isinstance(raw, dict) else raw) or [])
        except (OSError, json.JSONDecodeError):
            return
    for it in items:
        if it.get("key") == key:
            it["dismissed"] = True
            it["dismissed_at"] = date.today().isoformat()
    _atomic_write(
        p,
        {
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "items": items,
        },
    )


def queue_payloads_from_pending(
    path: Path | None = None,
) -> list[dict[str, Any]]:
    return load_pending(path)


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    fd, tmp_name = None, None
    try:
        fd, tmp_name = _mktemp(path)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            fd = None
        os.replace(tmp_name, path)
        tmp_name = None
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_name and os.path.exists(tmp_name):
            os.remove(tmp_name)


def _mktemp(path: Path) -> tuple[int, str]:
    import tempfile

    fd, name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    return fd, name
