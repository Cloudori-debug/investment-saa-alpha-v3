from __future__ import annotations

import math
from typing import Any


def normalize_sector(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, float) and math.isnan(value):
        return "unknown"
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return "unknown"
    return text


def normalize_ticker_export(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value.is_integer():
            value = int(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    if text.isdigit():
        return text.zfill(6)
    return text


def normalize_sector_fields_in_record(record: dict[str, Any]) -> dict[str, Any]:
    if "sector" in record:
        record = {**record, "sector": normalize_sector(record.get("sector"))}
    return record


def normalize_sector_fields_in_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_sector_fields_in_record(dict(r)) for r in records]


def sanitize_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, dict):
        return {str(k): sanitize_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_json_value(v) for v in value]
    if isinstance(value, (str, int, bool)):
        return value
    if hasattr(value, "item"):
        try:
            return sanitize_json_value(value.item())
        except (TypeError, ValueError):
            pass
    return str(value)
