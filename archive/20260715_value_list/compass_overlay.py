from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.value_list.ticker_registry import load_integration_config


def write_hakedaka_compass_overlay(data_dir: Path, output_dir: Path) -> Path | None:
    """SAA/TAA·나침반 JSON에 하케다카 kr_alpha 교차검증 메모 병합."""
    cfg = load_integration_config(data_dir)
    if not cfg.get("enabled", True) or not (cfg.get("compass") or {}).get("annotate_kr_alpha", True):
        return None

    ver_path = output_dir / "hakedaka_dart_verification.csv"
    macro_path = output_dir / "macro_scenario.json"
    shortlist_path = output_dir / "alpha_shortlist.csv"
    scores_path = output_dir / "hakedaka_scores.csv"

    verified_a: list[dict] = []
    if ver_path.exists():
        vdf = pd.read_csv(ver_path, dtype=str)
        verified_a = vdf[
            (vdf["grade"] == "A")
            & (vdf["verification_status"].isin(["verified", "partial"]))
        ].head(8).to_dict("records")

    macro = {}
    if macro_path.exists():
        macro = json.loads(macro_path.read_text(encoding="utf-8"))
    sid = macro.get("scenario_id", "reform_delay")
    compass_cfg = cfg.get("compass") or {}
    note_key = {
        "reform_success": "reform_success_note",
        "reform_delay": "reform_delay_note",
        "stress_failure": "stress_note",
    }.get(sid, "reform_delay_note")
    stance_note = str(compass_cfg.get(note_key, ""))

    overlap: list[dict] = []
    if shortlist_path.exists() and scores_path.exists():
        sl = pd.read_csv(shortlist_path, dtype=str)
        hk = pd.read_csv(scores_path, dtype=str)
        hk_tickers = set(hk["ticker"].astype(str).str.zfill(6))
        for _, row in sl.iterrows():
            t = str(row.get("ticker", "")).zfill(6)
            if t in hk_tickers:
                overlap.append({
                    "ticker": t,
                    "name": row.get("name", ""),
                    "alpha_score": row.get("total_score", ""),
                    "in_hakedaka": row.get("in_hakedaka", "true"),
                })

    overlay = {
        "macro_scenario_id": sid,
        "hakedaka_stance": macro.get("hakedaka_stance", "track"),
        "stance_note": stance_note,
        "dart_verified_a_count": len(verified_a),
        "alpha_shortlist_overlap": len(overlap),
        "top_verified_a": [
            {"ticker": r.get("ticker"), "name": r.get("name"), "dart_signal": r.get("dart_signal")}
            for r in verified_a[:5]
        ],
        "kr_alpha_cross_candidates": overlap[:8],
        "integration_hint": (
            "kr_alpha 슬롯 검토 시 QVM 숏리스트 ∩ 하케다카 A·DART verified 우선 교차검증. "
            "실행은 Execution Scope·dry-run 준수."
        ),
    }

    out_path = output_dir / "hakedaka_compass_overlay.json"
    out_path.write_text(json.dumps(overlay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    regime_path = output_dir / "compass_regime.json"
    if regime_path.exists():
        regime = json.loads(regime_path.read_text(encoding="utf-8"))
        regime["hakedaka_overlay"] = overlay
        regime_path.write_text(json.dumps(regime, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    alloc_path = output_dir / "target_asset_allocation.csv"
    if alloc_path.exists():
        alloc = pd.read_csv(alloc_path, dtype=str)
        if "asset_group" in alloc.columns and "kr_alpha" in alloc["asset_group"].astype(str).values:
            note_path = output_dir / "hakedaka_taa_note.md"
            lines = [
                "# 하케다카 × kr_alpha (TAA 참고)",
                "",
                f"- 거시 시나리오: **{macro.get('label', sid)}**",
                f"- {stance_note}",
                f"- DART verified A등급: {len(verified_a)}종",
                f"- 알파 숏리스트 overlap: {len(overlap)}종",
                "",
                "## 교차 후보",
            ]
            for item in overlap[:8]:
                lines.append(f"- {item.get('name')} ({item.get('ticker')}) — QVM {item.get('alpha_score')}")
            if not overlap:
                lines.append("- (overlap 없음 — 알파 풀·하케다카 티커·재무 확인)")
            lines.extend(["", overlay["integration_hint"]])
            note_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return out_path
