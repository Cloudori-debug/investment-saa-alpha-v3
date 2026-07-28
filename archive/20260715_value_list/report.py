from __future__ import annotations

from pathlib import Path

from src.value_list.scorer import HakedakaScoreRow


def write_hakedaka_report(rows: list[HakedakaScoreRow], path: Path) -> None:
    a_count = sum(1 for r in rows if r.grade == "A")
    core = [r for r in rows if r.priority_bucket == "핵심"]
    held = [r for r in rows if r.in_positions]
    overlap = [r for r in rows if r.in_alpha_shortlist]

    lines = [
        "# 하케다카 리스트 — 2026 자사주 소각·저평가 50종",
        "",
        "> PDF 투자 해석·우선순위 점수 + 시스템 QVM/재무 오버레이. **실행 신호 아님** — Research-only.",
        "",
        f"- 종목 수: **{len(rows)}** · A등급: **{a_count}** · 핵심 버킷: **{len(core)}**",
        f"- 보유 overlap: **{len(held)}** · 알파 숏리스트 overlap: **{len(overlap)}**",
        "",
        "## 상위 15 (추적 점수)",
        "",
        "| Rank | Ticker | Name | Group | Grade | 추적점수 | PDF | QVM | 정합 | DART | PBR | 보유 | 알파 |",
        "|-----:|--------|------|-------|-------|--------:|----:|----:|-----:|:----:|----:|:----:|:----:|",
    ]
    for r in rows[:15]:
        lines.append(
            f"| {r.rank} | {r.ticker or '—'} | {r.name} | {r.group_id} | {r.grade} | "
            f"{r.tracking_score:.1f} | {r.pdf_total:.0f} | "
            f"{r.alpha_score if r.alpha_score is not None else '—'} | "
            f"{r.alignment_score if r.alignment_score is not None else '—'} | "
            f"{r.dart_signal if r.dart_signal != 'unknown' else '—'} | "
            f"{r.pbr if r.pbr is not None else '—'} | "
            f"{'✓' if r.in_positions else ''} | {'✓' if r.in_alpha_shortlist else ''} |"
        )

    lines.extend([
        "",
        "## A-우선검토 (PDF)",
        "",
    ])
    for r in rows:
        if r.grade == "A":
            lines.append(
                f"- **{r.name}** ({r.ticker or '?'}) — 추적 {r.tracking_score:.1f} · "
                f"{r.invest_type} · {r.horizon_short}/{r.horizon_mid}/{r.horizon_long}"
            )

    lines.extend([
        "",
        "## W-관찰전용 / 구조 복잡 (저비중)",
        "",
    ])
    for r in rows:
        if r.grade == "W" or r.complexity == "높음":
            note = r.memo or r.invest_type
            lines.append(f"- {r.name} ({r.ticker or '?'}) — {note}")

    lines.extend([
        "",
        "## 점수 구성",
        "",
        "- **thesis_score**: PDF 등급·기간·그룹·복잡도 (40%)",
        "- **alpha_score**: QVM-SR 숏리스트/후보 점수 (30%, 있을 때)",
        "- **market_score**: PBR·PER·배당 (15%, 재무 있을 때)",
        "- **alignment_score**: DART 소각·환원 공시 + OCF·PBR (15%, 자동)",
        "",
        "> 매수 전: 자동 DART 스캔은 보조 신호. 공시 원문·주총 안건은 별도 확인.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
