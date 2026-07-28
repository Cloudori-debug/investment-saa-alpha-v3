from __future__ import annotations

import json
from pathlib import Path

from src.data_loader import load_market_indicators


def field_stale_days(data_dir: Path | None, field: str, *, max_ok: int = 2) -> tuple[bool, int]:
    """Returns (is_stale, stale_business_days). provenance 없으면 stale=True."""
    if data_dir is None:
        return False, 0
    path = data_dir / "market_data_provenance.json"
    if not path.exists():
        return True, 99
    prov = json.loads(path.read_text(encoding="utf-8"))
    meta = (prov.get("fields") or {}).get(field)
    if not meta:
        return True, 99
    stale = int(meta.get("stale_business_days", 99))
    return stale > max_ok, stale


def max_stale_business_days(data_dir: Path) -> int | None:
    path = data_dir / "market_data_provenance.json"
    if not path.exists():
        return None
    fields = (json.loads(path.read_text(encoding="utf-8")).get("fields") or {})
    if not fields:
        return None
    return max(int(v.get("stale_business_days", 0)) for v in fields.values())


def audit_market_data_consistency(data_dir: Path) -> dict[str, object]:
    """market_indicators 기준일 vs provenance·필드 value_date 정합 (schema v2)."""
    from src.validation.market_indicator_schema import (
        load_normalized_provenance,
        market_mixed_blocker_fields,
    )

    issues: list[str] = []
    market_date: str | None = None
    mi_path = data_dir / "market_indicators.csv"
    if mi_path.exists():
        try:
            market_date = load_market_indicators(mi_path).date
        except ValueError:
            issues.append("market_indicators.csv 파싱 실패")

    prov_path = data_dir / "market_data_provenance.json"
    prov_as_of: str | None = None
    field_dates: dict[str, str] = {}
    schema_mixed: list[str] = []
    if not prov_path.exists():
        issues.append("market_data_provenance.json 없음")
    else:
        normalized = load_normalized_provenance(data_dir)
        if normalized:
            prov_as_of = str(normalized.get("as_of") or "")
            fields = normalized.get("fields") or {}
            schema_mixed = market_mixed_blocker_fields(fields)
            for name, meta in fields.items():
                vd = str(meta.get("value_date") or meta.get("last_updated") or "")
                if vd:
                    field_dates[name] = vd
            if schema_mixed:
                issues.append(f"schema mixed fields: {', '.join(schema_mixed)}")
        else:
            issues.append("market_data_provenance.json 파싱 실패")

    if market_date and prov_as_of and market_date != prov_as_of:
        issues.append(
            f"기준일 참고: market_indicators={market_date}, provenance.as_of={prov_as_of} "
            f"(KR/US calendar lag 허용)"
        )

    stale_max = max_stale_business_days(data_dir)
    reanalysis_required = bool(
        schema_mixed
        or (stale_max is not None and stale_max > 2)
    )

    return {
        "market_date": market_date,
        "provenance_as_of": prov_as_of,
        "field_last_updated": field_dates,
        "field_value_dates": field_dates,
        "schema_mixed_fields": schema_mixed,
        "max_stale_business_days": stale_max,
        "issues": issues,
        "reanalysis_required": reanalysis_required,
    }
