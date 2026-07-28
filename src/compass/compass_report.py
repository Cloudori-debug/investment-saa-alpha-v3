from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.compass.action_labels import COMPASS_ACTION_FOOTNOTE, group_action_display_label
from src.compass.regime_json import build_regime_json_payload
from src.compass.models import (
    CompassResult,
    GroupGapRow,
    P0_LIMITATIONS,
    PortfolioAllocation,
    TargetMismatchWarning,
)

_DIRECTION_ARROWS: dict[str, str] = {
    "N": "↑",
    "NE": "↗",
    "E": "→",
    "SE": "↘",
    "S": "↓",
    "SW": "↙",
    "W": "←",
    "NW": "↖",
}


def _score_bar(score: float, width: int = 20) -> str:
    center = width // 2
    pos = int(round((score + 1) / 2 * width))
    pos = max(0, min(width - 1, pos))
    chars = ["·"] * width
    chars[center] = "│"
    chars[pos] = "●"
    return "".join(chars) + f" ({score:+.2f})"


def write_compass_report(
    path: Path,
    compass: CompassResult,
    allocation: PortfolioAllocation,
    *,
    group_gaps: list[GroupGapRow] | None = None,
    mismatch_warnings: list[TargetMismatchWarning] | None = None,
    generated_targets: list | None = None,
    tier2_used: bool = False,
    generated_at: str | None = None,
) -> None:
    arrow = _DIRECTION_ARROWS.get(compass.compass_direction, "·")
    ts = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# 시장·레짐 나침반 리포트 (P0 v1.0)",
        "",
        f"- 기준일: {compass.date}",
        f"- 생성: {ts}",
        f"- 스키마: v1.0",
        f"- Tier2 매크로: **{'적용' if tier2_used else '미적용'}**",
        "",
        "## 1. 나침반 요약",
        "",
        "```",
        "        N (회복)",
        "         ↑",
        "    NW ← · → NE",
        "         ↓",
        "        S (수축)",
        "",
        f"  현재 방향: {compass.compass_direction} {arrow}",
        "```",
        "",
        f"**{compass.compass_summary}**",
        "",
        "| 항목 | 값 | 신뢰도 |",
        "|------|-----|--------|",
        f"| 시장 국면 (산출) | **{compass.market_phase.value}** | {compass.phase_confidence:.0%} |",
        f"| 리스크 레짐 (산출) | **{compass.computed_regime.value}** | {compass.regime_confidence:.0%} |",
        f"| 적용 레짐 (TAA) | **{compass.applied_regime.value}** | — |",
        f"| Data Gate | **{compass.data_gate}** | — |",
        f"| 실행 레벨 | **{compass.execution_level}** | — |",
    ]
    if compass.manual_regime:
        lines.append(f"| 수동 입력 레짐 | {compass.manual_regime} | — |")
    if compass.override.active:
        lines.extend([
            "",
            "### Override 로그",
            f"- active: **{compass.override.active}**",
            f"- reason: {compass.override.reason or '—'}",
            f"- timestamp: {compass.override.timestamp or '—'}",
        ])

    lines.extend([
        "",
        "## 2. 4축 신호",
        "",
        "| 축 | 점수 | 시각화 | 상세 |",
        "|----|-----:|--------|------|",
    ])
    for sig in compass.signals:
        lines.append(
            f"| {sig.label} | {sig.score:+.2f} | `{_score_bar(sig.score)}` | {sig.detail} |"
        )

    lines.extend([
        "",
        "## 3. Score Breakdown",
        "",
        "| 축 | 지표 | 기여도 | 상세 |",
        "|----|------|-------:|------|",
    ])
    for item in compass.score_breakdown:
        lines.append(
            f"| {item.axis} | {item.indicator} | {item.contribution:+.2f} | {item.detail or '—'} |"
        )

    lines.extend([
        "",
        "## 4. SAA + TAA 자산군 목표비중",
        "",
        f"프로필: **{allocation.profile}** | 합계: **{allocation.total_weight:.1f}%**",
        "",
        "| 자산군 | SAA | phase | regime | raw | **final** | min | max |",
        "|--------|----:|------:|-------:|----:|----------:|----:|----:|",
    ])
    for g in allocation.groups:
        lines.append(
            f"| {g.asset_group} | {g.saa_weight:.1f}% | {g.phase_tilt:+.1f}%p | {g.regime_tilt:+.1f}%p | "
            f"{g.raw_target:.1f}% | **{g.final_target:.1f}%** | {g.min_weight:.0f}% | {g.max_weight:.0f}% |"
        )

    if group_gaps:
        lines.extend([
            "",
            "## 5. 자산군 Gap & 실행 판단",
            "",
            "| 자산군 | 현재 | 목표 | Gap | Action | 사유 |",
            "|--------|-----:|-----:|----:|--------|------|",
        ])
        for g in group_gaps:
            lines.append(
                f"| {g.asset_group} | {g.current:.1f}% | {g.target:.1f}% | {g.gap:+.1f}%p | "
                f"**{group_action_display_label(g.action, gap=g.gap)}** | {g.reason} |"
            )
        lines.extend(["", COMPASS_ACTION_FOOTNOTE, ""])

    section = 6 if group_gaps else 5
    if generated_targets:
        lines.extend([
            "",
            f"## {section}. 자동 생성 종목 Target (`generated_target_portfolio.csv`)",
            "",
            "| ticker | name | group | target% |",
            "|--------|------|-------|--------:|",
        ])
        for t in generated_targets[:12]:
            lines.append(f"| {t.ticker} | {t.name} | {t.asset_group} | {t.target_weight:.1f}% |")
        if len(generated_targets) > 12:
            lines.append(f"| … | +{len(generated_targets) - 12} more | | |")
        section += 1

    if mismatch_warnings:
        lines.extend([
            "",
            f"## {section}. 참고: 원본 `target_portfolio.csv` vs 자산군 목표",
            "",
            "> **실행·Gap 계산에는 `generated_target_portfolio.csv` 사용** (합계 100%).",
            "> 아래는 **수동 템플릿**(`data/target_portfolio.csv`) 상대비중과 나침반 자산군 목표 차이입니다.",
            "> `current_vs_target` 합계가 100%이면 실행 기준은 정상입니다.",
            "",
            "| 자산군 | 템플릿 종목 합 | 나침반 target | 차이 |",
            "|--------|---------------:|-------------:|-----:|",
        ])
        for w in mismatch_warnings:
            lines.append(
                f"| {w.asset_group} | {w.ticker_target_sum:.1f}% | {w.allocation_target:.1f}% | {w.diff:+.1f}%p |"
            )
        section += 1

    lines.extend(["", f"## {section}. 운용 메모", ""])
    for note in allocation.notes:
        lines.append(f"- {note}")

    lines.extend([
        "",
        f"## {section + 1}. 한계 (P0)",
        "",
    ])
    for lim in P0_LIMITATIONS:
        lines.append(f"- {lim}")

    lines.extend([
        "",
        f"## {section + 2}. 레짐별 행동 가이드",
        "",
        _regime_action_guide(compass.applied_regime.value),
        "",
        "> P0 v1.0 — 규칙 기반 자산군 목표비중 생성기. 투자 권유가 아닙니다.",
    ])

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _regime_action_guide(regime: str) -> str:
    guides = {
        "RISK_ON": (
            "- 베타·알파 점진 확대, 현금 축소\n"
            "- 목표 비중 접근 우선\n"
            "- kr_alpha 위성 비중 소폭 확대 가능"
        ),
        "YELLOW_STABLE": (
            "- SAA 유지, 트리거 기반 분할 매수\n"
            "- 급격한 비중 변경 자제\n"
            "- 현금·채권 버퍼 유지"
        ),
        "CAUTION": (
            "- TAA 방어 tilt 적용\n"
            "- 신규 베타 매수 제한, 기존 보유 Hold\n"
            "- 금·달러 헤지 점검"
        ),
        "RISK_OFF": (
            "- 현금·단기채 비중 확대, 알파·베타 축소\n"
            "- Trim은 반등 시에만, 매수 대기\n"
            "- VIX 30 돌파 시 Risk defense"
        ),
        "CRISIS": (
            "- Level 0~1: 거래 최소화, 방어 우선\n"
            "- 분할 매수는 crisis_zone 트리거 확인 후\n"
            "- kr_alpha 신규 진입 중단"
        ),
    }
    return guides.get(regime, "- SAA 기준 유지")


def write_compass_json(
    path: Path,
    compass: CompassResult,
    allocation: PortfolioAllocation,
    *,
    mismatch_warnings: list[TargetMismatchWarning] | None = None,
    generated_at: str | None = None,
    tier2_used: bool = False,
) -> None:
    ts = generated_at or datetime.now(timezone.utc).isoformat()
    payload = build_regime_json_payload(
        compass,
        allocation,
        mismatch_warnings=mismatch_warnings,
        generated_at=ts,
        tier2_used=tier2_used,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
