from __future__ import annotations

import json
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from src.validation.system_health import run_system_health, write_health_report
from src.field_normalize import normalize_sector, normalize_ticker_export, sanitize_json_value

EXPORT_SCHEMA_VERSION = "1.0"

CROSS_VALIDATION_PROMPT = """# Multi-Asset Trigger Portfolio — AI 교차 검증 요청

당신은 **규칙 기반 포트폴리오 운용 시스템**의 독립 검증자입니다. 아래 JSON 번들을 근거로만 판단하세요. 추측·일반론 금지.

## 검증 항목

1. **데이터 충분성**
   - `health_report`: fail/warn 항목이 투자 판단에 치명적인지
   - Compass Tier1 필드( kospi, vix, usdkrw 등 ) 결측·0값
   - Alpha fundamentals/prices 커버리지

2. **나침반·레짐 논리**
   - `compass_regime`: score_breakdown과 computed_regime/applied_regime 일관성
   - manual override가 있다면 타당한지

3. **TAA/SAA**
   - `asset_group_targets` vs `gpt_context.kr_alpha_meta` 예산 정합
   - 레짐에 맞는 방어/공격 tilt인지

4. **Alpha Screener**
   - top_candidates 팩터·등급이 excluded_summary와 모순 없는지
   - holdings_review TRIM/REPLACE 권고 근거
   - `alpha_grade_b_universe` / `alpha_top30_scored` / `alpha_replace_candidates` 검토:
     1. B등급 30개 중 현재 보유/타깃과 겹치는 종목은?
     2. Replace-review 후보의 대체 후보가 충분히 합리적인가?
     3. Top 30 중 섹터 쏠림이 있는가?
     4. Actual Buy Allowed=0인데 후보 리스트를 매수 신호로 오해할 표현이 있는가?
     5. kr_alpha hard stop 초과 상태에서 신규 알파 후보가 buy로 표시되지 않는가?
   - `alpha_screening_meta.buy_permission_status`와 모든 후보 `buy_permission` 일치 여부

5. **실행 제약**
   - `action_constraints`, data_gate RED/YELLOW 시 매매 허용 여부
   - trade_actions / portfolio gap과 충돌 없는지

6. **Alpha v2 Shadow**
   - `alpha_v2_final_5_8` / `alpha_v2_top30` 검토:
     1. Alpha v2 후보가 기존 알파 후보보다 품질이 좋은가?
     2. KOSDAQ 후보가 과도하게 많지 않은가?
     3. 연기금/외국인 수급이 후보 선정에 과도하게 반영되지 않았는가?
     4. Buy Watch가 Buy Permission으로 오해될 표현이 있는가?
     5. Actual Buy Allowed=0인데 신규매수처럼 보이는 문구가 있는가?
     6. Trim Watch 후보의 수급 악화가 명확한가?
     7. Profit Sweep 후보가 SAA 자본보존 철학과 일치하는가?
     8. KOSDAQ Shadow 후보가 실전 후보처럼 표시되지 않았는가?
   - `alpha_v2_policy_notes`에 "Flow signal is not buy permission" 포함 여부

## 출력 형식

```
## 종합 판정: PASS | WARN | FAIL

### 데이터
- ...

### 레짐·배분
- ...

### Alpha
- ...

### 실행 리스크
- ...

### 권고 (사람 승인 전)
- ...
```
"""


from src.report.io_utils import read_output_json


class ExportBundleValidationError(RuntimeError):
    """Export blocked — bundle artifacts fail pre-export gate."""

    def __init__(self, failures: list[str], *, details: dict[str, Any] | None = None):
        self.failures = failures
        self.details = details or {}
        super().__init__("; ".join(failures))


def _read_json(path: Path) -> dict | list | None:
    """Deprecated: use read_output_json for dict outputs."""
    data = read_output_json(path) if path.suffix == ".json" else None
    if data is not None:
        return data
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def build_ai_export_bundle(
    data_dir: Path,
    output_dir: Path,
    *,
    include_health: bool = True,
    daily_brief: dict[str, Any] | None = None,
    health_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """GPT 교차 검증용 통합 번들. 요약은 daily_brief 우선."""
    from src.report.io_utils import read_output_json

    if health_report is not None:
        health_dict = health_report
        as_of = str(health_dict.get("as_of") or "")
    elif include_health:
        disk_health = read_output_json(output_dir / "system_health.json")
        if disk_health:
            health_dict = disk_health
            as_of = str(disk_health.get("as_of") or "")
        else:
            health = run_system_health(data_dir, output_dir)
            health_dict = health.to_dict()
            as_of = health.as_of
            write_health_report(health, output_dir / "system_health.json")
    else:
        disk_health = read_output_json(output_dir / "system_health.json") or {}
        health_dict = disk_health
        as_of = str(disk_health.get("as_of") or "")
    manifest = read_output_json(output_dir / "run_manifest.json")
    acceptance_report = read_output_json(output_dir / "acceptance_report.json")
    if daily_brief is None:
        daily_brief = read_output_json(output_dir / "daily_brief.json")

    from src.decision_logger import get_decision_log_tails
    from src.alpha.target_write_audit import get_last_target_write_audit

    log_tails = get_decision_log_tails(output_dir / "decision_log.jsonl")
    write_audit = get_last_target_write_audit(output_dir)
    tg_hash = ""
    if acceptance_report:
        for item in acceptance_report.get("items") or []:
            if isinstance(item, dict) and item.get("name") == "target_portfolio_guard":
                tg_hash = str((item.get("detail") or {}).get("current_hash") or "")
                break
        tg_hash = tg_hash or str(acceptance_report.get("target_hash") or "")

    from src.alpha_shadow_policy import load_alpha_shadow_flags, resolve_alpha_v02_shadow_doc

    shadow_flags = load_alpha_shadow_flags(data_dir)
    _v02_doc, v02_status, _ = resolve_alpha_v02_shadow_doc(
        output_dir,
        data_dir=data_dir,
        run_id=(manifest or {}).get("run_id") or (daily_brief or {}).get("run_id"),
    )

    bundle: dict[str, Any] = {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "run_id": (manifest or {}).get("run_id") or (daily_brief or {}).get("run_id"),
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "target_hash": tg_hash or str((health_dict.get("meta") or {}).get("target_hash") or ""),
        "alpha_v0_2_enabled": shadow_flags["v0_2_enabled"],
        "alpha_v0_2_status": v02_status,
        "daily_brief": daily_brief,
        "acceptance": acceptance_report,
        "validation_prompt": CROSS_VALIDATION_PROMPT,
        "health_report": health_dict,
        "gpt_context": read_output_json(output_dir / "gpt_context.json"),
        "compass_regime": read_output_json(output_dir / "compass_regime.json"),
        "decision_log_last": log_tails.get("last_bundle_reconciliation") or log_tails.get("last_line"),
        "last_target_write_audit": write_audit or log_tails.get("last_target_write_audit"),
        "last_bundle_reconciliation": log_tails.get("last_bundle_reconciliation"),
        "last_execution_decision": log_tails.get("last_execution_decision"),
        "reports": {
            "compass_report_md": _read_text(output_dir / "compass_report.md"),
            "alpha_report_md": _read_text(output_dir / "alpha_report.md"),
            "trigger_alerts_md": _read_text(output_dir / "trigger_alerts.md"),
            "daily_report_md": _read_text(output_dir / "daily_report.md"),
        },
        "report_clarity_validation": read_output_json(output_dir / "report_clarity_validation.json"),
        "tables_summary": _tables_summary(output_dir, slim=bool(daily_brief)),
        "exposure_lookthrough": read_output_json(output_dir / "exposure_lookthrough.json"),
        "data_inputs_snapshot": _inputs_snapshot(data_dir),
        "limitations": [
            "자동매매·증권사 API 없음",
            "GPT Report v2.0: daily_brief.json 우선, tables_summary는 보조",
            "foreign_flow·국채10Y: PyKRX 실패 시 수동/Tier2 fallback",
        ],
    }
    consistency = read_output_json(output_dir / "bundle_consistency_validation.json")
    if consistency:
        bundle["bundle_consistency_validation"] = consistency

    from src.validation.alpha_export_lists import build_alpha_export_sections

    bundle.update(build_alpha_export_sections(data_dir, output_dir))

    from src.alpha_v2_gate import build_alpha_v2_export_sections

    bundle.update(build_alpha_v2_export_sections(output_dir))

    shadow_hist = read_output_json(output_dir / "history" / "shadow_history_last.json") or {}
    shadow_summary = shadow_hist.get("last_summary") or {}
    if not shadow_summary and (output_dir / "history" / "shadow_daily_summary.csv").exists():
        import csv
        with (output_dir / "history" / "shadow_daily_summary.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
            if rows:
                shadow_summary = rows[-1]
    brief_shadow = (daily_brief or {}).get("shadow_history") or {}
    bundle["shadow_history"] = {
        "shadow_history_updated": bool(
            brief_shadow.get("alpha_v2_shadow_history_updated")
            or shadow_summary.get("alpha_v2_shadow_history_updated")
        ),
        "alpha_v2_history_rows_appended": brief_shadow.get("alpha_v2_rows_appended", 0),
        "flow_history_rows_appended": brief_shadow.get("flow_rows_appended", 0),
        "shadow_daily_summary_latest": shadow_summary,
        "buy_watch_count": brief_shadow.get("buy_watch_count") or shadow_summary.get("buy_watch_count", 0),
        "trim_watch_held_count": brief_shadow.get("trim_watch_held_count")
        or shadow_summary.get("trim_watch_held_count", 0),
        "trim_watch_informational_count": brief_shadow.get("trim_watch_informational_count")
        or shadow_summary.get("trim_watch_informational_count", 0),
        "new_kosdaq_candidates_count": brief_shadow.get("new_kosdaq_candidates_count")
        or shadow_summary.get("new_kosdaq_candidates_count", 0),
        "fresh_flow_ratio": brief_shadow.get("fresh_flow_ratio") or shadow_summary.get("fresh_flow_ratio"),
        "target_write_occurred": False,
    }
    return bundle


def _last_decision_log(path: Path) -> dict | None:
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return None
    return json.loads(lines[-1])


def _dataframe_records_for_export(df) -> list[dict[str, Any]]:
    import pandas as pd

    out = df.copy()
    for col in out.columns:
        if col == "ticker":
            out[col] = out[col].map(normalize_ticker_export)
        elif col == "sector":
            out[col] = out[col].map(normalize_sector)
    out = out.where(pd.notna(out), None)
    records = out.to_dict(orient="records")
    return [sanitize_json_value(rec) for rec in records]


def _tables_summary(output_dir: Path, *, slim: bool = False) -> dict[str, Any]:
    import pandas as pd

    if slim:
        csv_files = {
            "holdings_review": "holdings_review.csv",
            "current_vs_target": "current_vs_target.csv",
        }
    else:
        csv_files = {
            "target_asset_allocation": "target_asset_allocation.csv",
            "portfolio_gap": "portfolio_gap.csv",
            "trade_actions": "trade_actions.csv",
            "alpha_candidates_top10": "alpha_candidates.csv",
            "holdings_review": "holdings_review.csv",
            "current_vs_target": "current_vs_target.csv",
        }
    summary: dict[str, Any] = {}
    if slim:
        summary["_note"] = "요약은 daily_brief 참조 — holdings/current_vs_target만 포함"
    for key, fname in csv_files.items():
        path = output_dir / fname
        if not path.exists():
            summary[key] = None
            continue
        dtype: dict[str, str] | None = None
        if fname in {"alpha_candidates.csv", "holdings_review.csv", "trade_actions.csv", "current_vs_target.csv"}:
            dtype = {"ticker": str}
        df = pd.read_csv(path, dtype=dtype)
        if key == "alpha_candidates_top10":
            df = df.head(10)
        summary[key] = _dataframe_records_for_export(df)
    return summary


def _inputs_snapshot(data_dir: Path) -> dict[str, Any]:
    from src.data_loader import load_market_indicators_bundle

    snap: dict[str, Any] = {}
    mi = data_dir / "market_indicators.csv"
    if mi.exists():
        bundle = load_market_indicators_bundle(mi)
        snap.update(bundle.to_export_dict())
    t2 = data_dir / "macro_tier2.csv"
    if t2.exists():
        import pandas as pd

        snap["macro_tier2_latest"] = pd.read_csv(t2, dtype=str).iloc[-1].to_dict()
    for name in ("universe.csv", "fundamentals.csv", "prices.csv"):
        p = data_dir / name
        if p.exists():
            import pandas as pd

            df = pd.read_csv(p, dtype=str)
            snap[f"{name}_row_count"] = len(df)
    return snap


def write_ai_export_json(bundle: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = sanitize_json_value(bundle)
    path.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def sync_export_clarity_artifacts(output_dir: Path) -> None:
    """Attach daily_report + clarity validation to ai_export_bundle after pipeline end."""
    bundle_path = output_dir / "ai_export_bundle.json"
    if not bundle_path.exists():
        return
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    if not isinstance(bundle, dict):
        return
    reports = bundle.setdefault("reports", {})
    daily = _read_text(output_dir / "daily_report.md")
    if daily:
        reports["daily_report_md"] = daily
    clarity = read_output_json(output_dir / "report_clarity_validation.json")
    if clarity:
        bundle["report_clarity_validation"] = clarity
    vf = read_output_json(output_dir / "validation_findings.json")
    if vf:
        bundle["validation_findings"] = vf
    write_ai_export_json(bundle, bundle_path)


def validate_export_bundle_readiness(
    data_dir: Path,
    output_dir: Path,
    *,
    bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pre-export gate — all target hashes, clarity, run_id must pass."""
    from src.alpha.target_write_audit import get_last_target_write_audit
    from src.report.execution_metrics import validate_report_clarity
    from src.validation.bundle_consistency import verify_bundle_snapshot_alignment

    failures: list[str] = []
    alignment = verify_bundle_snapshot_alignment(output_dir)
    if not alignment.get("aligned"):
        failures.extend(f"bundle_consistency: {i}" for i in alignment.get("issues") or [])

    consistency_doc = read_output_json(output_dir / "bundle_consistency_validation.json") or {}
    if consistency_doc and not consistency_doc.get("pass"):
        failures.append("bundle_consistency_validation.pass is false")

    clarity = read_output_json(output_dir / "report_clarity_validation.json")
    if clarity is None:
        clarity = validate_report_clarity(output_dir)
        (output_dir / "report_clarity_validation.json").write_text(
            json.dumps(clarity, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if not clarity.get("pass"):
        for item in clarity.get("failures") or []:
            failures.append(f"report_clarity: {item}")

    write_audit = get_last_target_write_audit(output_dir)
    if write_audit.get("target_write_allowed") and not write_audit.get("run_id"):
        failures.append("target_write_audit.run_id is null")

    bundle = bundle or read_output_json(output_dir / "ai_export_bundle.json") or {}
    if bundle.get("last_target_write_audit") is None and write_audit:
        bundle["last_target_write_audit"] = write_audit
    if bundle.get("decision_log_last", {}).get("event") == "target_write_audit":
        failures.append("decision_log_last must not be target_write_audit alone — reconcile before export")

    acc_hash = str((bundle.get("acceptance") or {}).get("target_hash") or "")
    health_hash = str((bundle.get("health_report") or {}).get("meta", {}).get("target_hash") or "")
    for item in (bundle.get("acceptance") or {}).get("items") or []:
        if isinstance(item, dict) and item.get("name") == "target_portfolio_guard":
            health_hash = health_hash or str((item.get("detail") or {}).get("current_hash") or "")
            acc_hash = acc_hash or str((item.get("detail") or {}).get("current_hash") or "")
    root_hash = str(bundle.get("target_hash") or "")
    canonical = alignment.get("target_hash") or health_hash or root_hash
    if canonical and acc_hash and not _export_hash_matches(canonical, acc_hash):
        failures.append(
            f"acceptance target_hash mismatch in bundle: {acc_hash[:12]} vs {canonical[:12]}"
        )

    daily_md = (bundle.get("reports") or {}).get("daily_report_md") or ""
    if daily_md and canonical:
        from src.validation.bundle_consistency import _extract_daily_report_target_hash

        d_hash = _extract_daily_report_target_hash(daily_md)
        if d_hash and not _export_hash_matches(canonical, d_hash):
            failures.append(
                f"daily_report target hash mismatch: {d_hash[:12]} vs {canonical[:12]}"
            )

    return {
        "pass": not failures,
        "failures": failures,
        "alignment": alignment,
        "clarity": clarity,
        "target_write_audit": write_audit,
    }


def _export_hash_matches(canonical: str, other: str) -> bool:
    if not canonical or not other:
        return True
    c, o = canonical.lower(), other.lower()
    if c == o:
        return True
    n = min(len(c), len(o), 12)
    return c[:n] == o[:n]


def prepare_export_bundle_existing_only(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Build export bundle from existing outputs — no reconcile, no data refresh."""
    from src.report.execution_metrics import validate_report_clarity

    manifest = read_output_json(output_dir / "run_manifest.json") or {}
    final = read_output_json(output_dir / "final_execution_decision.json") or {}
    if not manifest.get("run_id") and not final:
        raise ExportBundleValidationError(
            ["run_manifest.json or final_execution_decision.json required for bundle_only"],
        )

    clarity = validate_report_clarity(output_dir)
    (output_dir / "report_clarity_validation.json").write_text(
        json.dumps(clarity, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    sync_export_clarity_artifacts(output_dir)

    bundle = build_ai_export_bundle(data_dir, output_dir, include_health=False)
    gate = validate_export_bundle_readiness(data_dir, output_dir, bundle=bundle)
    bundle["export_bundle_validation"] = gate
    bundle["bundle_only"] = True
    bundle["note"] = "Bundle Only: existing outputs used, no recalculation."
    write_ai_export_json(bundle, output_dir / "ai_export_bundle.json")

    gate_path = output_dir / "export_bundle_validation.json"
    gate_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not gate["pass"]:
        raise ExportBundleValidationError(gate["failures"], details=gate)
    return bundle


def prepare_export_bundle(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Reconcile artifacts, refresh reports, validate, then build export bundle."""
    from src.report.execution_metrics import validate_report_clarity
    from src.validation.bundle_consistency import (
        reconcile_bundle_artifacts,
        refresh_daily_report_authoritative,
        resolve_pipeline_run_id,
    )

    manifest = read_output_json(output_dir / "run_manifest.json") or {}
    run_id = str(manifest.get("run_id") or resolve_pipeline_run_id(output_dir) or "")
    if not run_id:
        raise ExportBundleValidationError(
            ["run_manifest.json missing run_id — run full pipeline before export"],
        )
    final = read_output_json(output_dir / "final_execution_decision.json") or {}
    as_of = str(final.get("as_of") or manifest.get("as_of") or "")

    reconcile_bundle_artifacts(
        data_dir,
        output_dir,
        run_id=run_id,
        as_of=as_of or datetime.now().date().isoformat(),
        target_restore_meta={"restored": False},
        post_target_write_refresh=True,
    )
    refresh_daily_report_authoritative(output_dir, data_dir)
    sync_export_clarity_artifacts(output_dir)

    clarity = validate_report_clarity(output_dir)
    (output_dir / "report_clarity_validation.json").write_text(
        json.dumps(clarity, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    bundle = build_ai_export_bundle(data_dir, output_dir, include_health=False)
    gate = validate_export_bundle_readiness(data_dir, output_dir, bundle=bundle)
    bundle["export_bundle_validation"] = gate
    write_ai_export_json(bundle, output_dir / "ai_export_bundle.json")

    if not gate["pass"]:
        gate_path = output_dir / "export_bundle_validation.json"
        gate_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise ExportBundleValidationError(gate["failures"], details=gate)

    gate_path = output_dir / "export_bundle_validation.json"
    gate_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return bundle


def build_export_zip(bundle: dict[str, Any]) -> bytes:
    buf = BytesIO()
    clean = sanitize_json_value(bundle)
    payload = json.dumps(clean, ensure_ascii=False, indent=2, allow_nan=False)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ai_export_bundle.json", payload)
        zf.writestr("validation_prompt.md", bundle.get("validation_prompt", ""))
        health = clean.get("health_report")
        if health:
            zf.writestr("system_health.json", json.dumps(health, ensure_ascii=False, indent=2, allow_nan=False))
        for key, content in (bundle.get("reports") or {}).items():
            if content:
                zf.writestr(f"reports/{key}.md", content)
        clarity = clean.get("report_clarity_validation")
        if clarity:
            zf.writestr(
                "report_clarity_validation.json",
                json.dumps(clarity, ensure_ascii=False, indent=2, allow_nan=False),
            )
        consistency = clean.get("bundle_consistency_validation")
        if consistency:
            zf.writestr(
                "bundle_consistency_validation.json",
                json.dumps(consistency, ensure_ascii=False, indent=2, allow_nan=False),
            )
        export_gate = clean.get("export_bundle_validation")
        if export_gate:
            zf.writestr(
                "export_bundle_validation.json",
                json.dumps(export_gate, ensure_ascii=False, indent=2, allow_nan=False),
            )
        daily = (clean.get("reports") or {}).get("daily_report_md")
        if daily:
            zf.writestr("daily_report.md", daily)
    return buf.getvalue()
