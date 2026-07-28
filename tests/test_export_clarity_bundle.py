"""AI export bundle includes clarity validation artifacts."""
from __future__ import annotations

import json
from pathlib import Path

from src.validation.ai_export import build_export_zip, sync_export_clarity_artifacts, write_ai_export_json


def test_export_zip_includes_daily_report_and_clarity(tmp_path: Path) -> None:
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "daily_report.md").write_text("## 최종 실행 권위\n- **Actual Buy Allowed**: 0\n", encoding="utf-8")
    clarity = {"pass": True, "failures": []}
    (out / "report_clarity_validation.json").write_text(json.dumps(clarity), encoding="utf-8")
    bundle = {
        "export_schema_version": "1.0",
        "reports": {"daily_report_md": (out / "daily_report.md").read_text(encoding="utf-8")},
        "report_clarity_validation": clarity,
        "validation_prompt": "",
    }
    write_ai_export_json(bundle, out / "ai_export_bundle.json")
    sync_export_clarity_artifacts(out)
    updated = json.loads((out / "ai_export_bundle.json").read_text(encoding="utf-8"))
    assert updated.get("report_clarity_validation", {}).get("pass") is True
    assert "daily_report_md" in updated.get("reports", {})
    zbytes = build_export_zip(updated)
    import zipfile
    from io import BytesIO
    with zipfile.ZipFile(BytesIO(zbytes)) as zf:
        names = set(zf.namelist())
    assert "daily_report.md" in names
    assert "report_clarity_validation.json" in names


def test_watch_signal_label_not_buy_signal() -> None:
    from src.trigger_conditions import evaluate_asset_triggers, build_trigger_context
    from src.config import load_trigger_rules
    from src.models import MarketIndicators, TriggerAlert, TriggerStatus
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    market = MarketIndicators(
        date="2026-06-29", kospi=8471, kospi_recent_high=9114, vix=18.6, usdkrw=1540, regime="YELLOW_STABLE",
    )
    rules = load_trigger_rules(root / "data" / "trigger_rules.yaml")
    ctx = build_trigger_context(
        market, rules,
        [TriggerAlert(key="kospi_pullback", label="KOSPI Pullback", status=TriggerStatus.ACTIVE, detail="")],
        asset_group_gaps={"domestic_beta": {"target": 5.0, "current": 0.0, "gap": 5.0}},
    )
    alerts = evaluate_asset_triggers(ctx)
    domestic = next(a for a in alerts if a.key == "asset_buy_domestic_beta")
    assert domestic.status == TriggerStatus.ACTIVE
    assert "watch signal" in domestic.label
    assert "buy signal" not in domestic.label
    assert domestic.detail.startswith("watch_condition:")
