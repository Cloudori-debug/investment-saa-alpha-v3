from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.report.publish import patch_acceptance_and_sync_exports, publish_report_exports


def test_publish_report_exports_writes_brief_and_bundle(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    data = tmp_path / "data"
    out.mkdir()
    data.mkdir()
    (out / "run_manifest.json").write_text(json.dumps({"run_id": "r1"}), encoding="utf-8")
    (out / "final_execution_decision.json").write_text(
        json.dumps({"as_of": "2026-06-26", "run_id": "r1", "system_status": "GREEN", "data_gate": "GREEN"}),
        encoding="utf-8",
    )
    (out / "acceptance_report.json").write_text(
        json.dumps({"overall": "GREEN", "items": []}),
        encoding="utf-8",
    )

    with patch("src.validation.ai_export.run_system_health") as mock_health:
        mock_health.return_value.as_of = "2026-06-26"
        mock_health.return_value.to_dict.return_value = {"overall": "GREEN"}

        brief, bundle = publish_report_exports(
            out, data, as_of="2026-06-26", run_id="r1", include_health=False,
        )

    assert (out / "daily_brief.json").exists()
    assert (out / "ai_export_bundle.json").exists()
    assert bundle["daily_brief"]["run_id"] == "r1"
    assert brief["report_version"] == "v2.0"
