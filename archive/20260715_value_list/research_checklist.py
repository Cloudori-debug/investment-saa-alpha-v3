from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.settings.user_secrets import credential_status
from src.value_list.macro_scenarios import evaluate_macro_scenario
from src.value_list.dart_disclosure import load_hakedaka_dart_signals


@dataclass
class ResearchCheckItem:
    id: str
    label: str
    status: str
    detail: str
    category: str


def _load_ac(output_dir: Path) -> dict[str, Any]:
    final_path = output_dir / "final_execution_decision.json"
    if final_path.exists():
        f = json.loads(final_path.read_text(encoding="utf-8"))
        return {
            "execution_scope": f.get("execution_scope", "—"),
            "alpha_approval": f.get("alpha_approval", "—"),
            "dry_run_days": int(f.get("dry_run_days", 0)),
            "overall": f.get("system_status") or f.get("overall", "YELLOW"),
        }
    p = output_dir / "acceptance_report.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _load_hakedaka(output_dir: Path) -> list[dict]:
    import pandas as pd

    p = output_dir / "hakedaka_scores.csv"
    if not p.exists():
        return []
    return pd.read_csv(p, dtype=str).to_dict("records")


def build_research_checklist(data_dir: Path, output_dir: Path) -> list[ResearchCheckItem]:
    ac = _load_ac(output_dir)
    macro = evaluate_macro_scenario(data_dir, output_dir)
    cred = credential_status(data_dir)
    dart = load_hakedaka_dart_signals(data_dir)
    rows = _load_hakedaka(output_dir)
    scope = str(ac.get("execution_scope", "—"))
    dry = int(ac.get("dry_run_days", 0))

    items: list[ResearchCheckItem] = []

    items.append(ResearchCheckItem(
        "RC-M1",
        "거시 시나리오 — 스트레스 아님",
        "pass" if macro.scenario_id != "stress_failure" else "warn",
        f"{macro.label} · {', '.join(macro.drivers[:3])}",
        "macro",
    ))
    items.append(ResearchCheckItem(
        "RC-M2",
        "PwC 채널 — 사모신용·신용 경색 경계",
        "warn" if macro.scenario_id == "stress_failure" or macro.score_stress >= 4 else "pass",
        "고변동·조정 국면에서 private credit 전염 경계 (미국 은행 자본 리포트 맥락)",
        "macro",
    ))
    items.append(ResearchCheckItem(
        "RC-D1",
        "DART API 자격",
        "pass" if cred.get("dart") else "fail",
        "자동 공시 스캔 가능" if cred.get("dart") else "설정 → API 키 필요",
        "data",
    ))

    dart_tickers = dart.get("tickers") or {}
    scanned = len(dart_tickers)
    top = [r for r in rows if str(r.get("ticker", "")).zfill(6) in dart_tickers][:15]
    strong = sum(1 for t, v in dart_tickers.items() if v.get("signal") == "strong")
    weak = sum(1 for t, v in dart_tickers.items() if v.get("signal") == "weak")

    items.append(ResearchCheckItem(
        "RC-D2",
        f"DART 자동 스캔 ({scanned}종)",
        "pass" if scanned >= 30 else "warn" if scanned else "fail",
        f"as_of {dart.get('as_of', '—')} · 소각공시 {strong} · 취득/처분 위주 {weak}",
        "data",
    ))

    a_rows = [r for r in rows if str(r.get("grade", "")) == "A" and str(r.get("ticker", ""))]
    a_with_cancel = sum(
        1 for r in a_rows
        if (dart_tickers.get(str(r.get("ticker", "")).zfill(6), {}) or {}).get("cancel_disclosure")
    )
    items.append(ResearchCheckItem(
        "RC-H1",
        "A등급 소각·환원 공시 (DART)",
        "pass" if a_rows and a_with_cancel >= max(1, len(a_rows) // 4) else "warn",
        f"A등급 {len(a_rows)}종 중 소각키워드 공시 {a_with_cancel}종",
        "hakedaka",
    ))

    ocf_pos = 0
    for r in rows[:20]:
        try:
            if float(r.get("market_score") or 0) >= 60:
                ocf_pos += 1
        except (TypeError, ValueError):
            pass
    items.append(ResearchCheckItem(
        "RC-H2",
        "상위 종목 재무·밸류에이션 데이터",
        "pass" if ocf_pos >= 5 else "warn",
        f"상위 20종 중 market_score≥60: {ocf_pos}종 (PBR·배당·PER 프록시)",
        "hakedaka",
    ))

    overlap = sum(1 for r in rows if str(r.get("in_alpha_shortlist", "")).lower() == "true")
    items.append(ResearchCheckItem(
        "RC-H3",
        "하케다카 ↔ QVM 알파 overlap",
        "pass" if overlap >= 1 else "warn",
        f"숏리스트 overlap {overlap}종 — 교차검증용",
        "hakedaka",
    ))

    items.append(ResearchCheckItem(
        "RC-X1",
        "실행 scope — kr_alpha 매수 가능 여부",
        "fail" if scope == "NO_TRADE" else "warn" if scope == "ETF_ONLY" else "pass",
        f"scope={scope} · alpha={ac.get('alpha_approval', '—')}",
        "execution",
    ))

    items.append(ResearchCheckItem(
        "RC-X2",
        f"dry-run 누적 ({dry}/10)",
        "pass" if dry >= 10 else "warn",
        "10영업일 전까지 소액·ETF만" if dry < 10 else "실운용 재평가 가능",
        "execution",
    ))

    w_in_top = sum(1 for r in rows[:15] if str(r.get("grade", "")) == "W")
    items.append(ResearchCheckItem(
        "RC-X3",
        "상위 15종 W·복잡도 필터",
        "pass" if w_in_top <= 3 else "warn",
        f"상위 15 중 W등급 {w_in_top}종 — 소액·분산 원칙",
        "execution",
    ))

    return items


def write_research_checklist(data_dir: Path, output_dir: Path) -> Path:
    items = build_research_checklist(data_dir, output_dir)
    payload = {
        "schema_version": "1.0",
        "items": [
            {"id": i.id, "label": i.label, "status": i.status, "detail": i.detail, "category": i.category}
            for i in items
        ],
        "summary": {
            "pass": sum(1 for i in items if i.status == "pass"),
            "warn": sum(1 for i in items if i.status == "warn"),
            "fail": sum(1 for i in items if i.status == "fail"),
        },
    }
    path = output_dir / "research_checklist.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Research Checklist (자동)",
        "",
        "> PwC·DOCX·하케다카 근거문서 교차검증 — **실행 신호 아님**",
        "",
    ]
    icon = {"pass": "✅", "warn": "⚠️", "fail": "❌"}
    for i in items:
        lines.append(f"- {icon.get(i.status, '·')} **{i.label}** — {i.detail}")
    (output_dir / "research_checklist.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
