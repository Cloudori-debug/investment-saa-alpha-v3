from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.report.export_daily_brief import (
    build_daily_report_v2_sections,
    export_daily_brief,
    write_daily_brief,
)
from src.report.io_utils import read_output_json
from src.validation.ai_export import build_ai_export_bundle, write_ai_export_json


def publish_report_exports(
    output_dir: Path,
    data_dir: Path,
    *,
    as_of: str,
    run_id: str,
    include_health: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """GPT Report v2.0 brief + AI export bundle — 단일 진입점 (중복 생성 방지)."""
    brief = export_daily_brief(output_dir, as_of=as_of, run_id=run_id, data_dir=data_dir)
    write_daily_brief(output_dir / "daily_brief.json", brief)
    bundle = build_ai_export_bundle(
        data_dir,
        output_dir,
        include_health=include_health,
        daily_brief=brief,
    )
    write_ai_export_json(bundle, output_dir / "ai_export_bundle.json")
    return brief, bundle


def patch_acceptance_and_sync_exports(
    output_dir: Path,
    acceptance: Any,
    *,
    as_of: str,
    run_id: str,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """AC-08 갱신 후 brief·bundle 메타만 동기화 (전체 bundle 재빌드 없음)."""
    from src.validation.acceptance_check import _check_ai_export, write_acceptance_report

    acceptance.items = [
        _check_ai_export(output_dir) if item.id == "AC-08" else item
        for item in acceptance.items
    ]
    write_acceptance_report(acceptance, output_dir / "acceptance_report.json")

    if data_dir is not None:
        from src.report.authoritative_status import sync_acceptance_authoritative_scope_fields

        sync_acceptance_authoritative_scope_fields(data_dir, output_dir)

    brief = export_daily_brief(output_dir, as_of=as_of, run_id=run_id, data_dir=data_dir)
    write_daily_brief(output_dir / "daily_brief.json", brief)

    bundle_path = output_dir / "ai_export_bundle.json"
    if bundle_path.exists():
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        if isinstance(bundle, dict):
            bundle["daily_brief"] = brief
            acc = read_output_json(output_dir / "acceptance_report.json")
            if acc:
                bundle["acceptance"] = acc
            write_ai_export_json(bundle, bundle_path)

    return brief


__all__ = [
    "build_daily_report_v2_sections",
    "export_daily_brief",
    "patch_acceptance_and_sync_exports",
    "publish_report_exports",
    "write_daily_brief",
]
