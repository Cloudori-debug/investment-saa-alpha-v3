"""교체 나침반 — live bearing from exit-step rules (Review-only).

Needle points to what the operator should do about holdings vs proposal.
Does not place orders or write target_portfolio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Sequence

Bearing = Literal["hold", "trim", "cash", "replace", "missing"]

# Compass degrees: 0 = North (유지), clockwise
BEARING_DEG: dict[Bearing, float] = {
    "hold": 0.0,
    "trim": 300.0,  # NW — 줄이기
    "cash": 60.0,  # NE — 환금
    "replace": 180.0,  # South — 전량·교체
    "missing": 240.0,  # SW — 목표없음
}

BEARING_KO: dict[Bearing, str] = {
    "hold": "유지",
    "trim": "줄이기",
    "cash": "환금",
    "replace": "전량·교체",
    "missing": "목표없음",
}

BEARING_HINT: dict[Bearing, str] = {
    "hold": "보유 유지 · 순위만 바뀐 것은 교체 아님",
    "trim": "목표가 근접 · ¼만 줄여 자리 확보 후 신규 검토",
    "cash": "목표가 도달 · 절반 환금 후 남는 예산으로만 신규",
    "replace": "제안 탈락·논지·타임캡 · 전량 후 신규 분할매수",
    "missing": "목표가 먼저 · 교체보다 E 게이트",
}

STEP_EVIDENCE_KO: dict[str, str] = {
    "S0": "논지·하드 규칙 훼손 — 전량 환금 검토 (익절 스텝 S0)",
    "S2a": "실보유가 이번 주 제안 북에 없음 — 제안 탈락·로테이션 (S2a)",
    "S2c": "목표가 도달 후 N주 동안 목표가 미갱신 — 타임캡 전량 (S2c)",
    "S1": "현재가(또는 PBR)가 목표가에 도달 — 수량 절반 환금 (S1)",
    "Sprox": "목표가 근접도 70% 이상·미도달 — ¼(25%) 줄이기 (S근접)",
    "E": "익절 목표가 YAML 없음 — E 게이트에서 목표가 먼저",
    "DATA": "목표가는 있으나 가격·PBR 데이터 없음 — 신호 무효",
    "HOLD": "위 규칙에 해당 없음 — 유지 (순위만 변동해도 교체 아님)",
}


def evidence_lines_for_row(row: Any, *, in_proposal: bool | None = None) -> list[str]:
    """Operator-facing evidence bullets for one ops holding."""
    extra = getattr(row, "extra", None) or {}
    kind = str(getattr(row, "ops_signal", "") or "hold")
    step = str(extra.get("ops_step_id") or ("HOLD" if kind == "hold" else ""))
    lines: list[str] = []
    lines.append(f"판정: {getattr(row, 'ops_signal_label', None) or kind}")
    if step:
        lines.append(f"규칙: {STEP_EVIDENCE_KO.get(step, step)} ({step})")
    detail = str(getattr(row, "ops_signal_detail", None) or "").strip()
    if detail:
        lines.append(f"요약: {detail}")
    rationale = str(extra.get("ops_rationale") or "").strip()
    if rationale and rationale != detail:
        lines.append(f"근거 메모: {rationale}")
    prox = extra.get("ops_proximity_pct")
    if prox is not None:
        try:
            lines.append(f"목표가 근접도: {float(prox):.1f}% (100%=도달)")
        except (TypeError, ValueError):
            pass
    trim = getattr(row, "ops_trim_pct", None)
    if trim is not None:
        lines.append(f"권고 비중 조정: {trim}%")
    if in_proposal is not None:
        lines.append(
            "제안 북: 포함" if in_proposal else "제안 북: 미포함 (탈락 후보)"
        )
    # Position facts
    w = getattr(row, "weight_pct", None)
    if w is not None:
        try:
            lines.append(f"실비중: {float(w):.2f}%")
        except (TypeError, ValueError):
            pass
    avg = getattr(row, "avg_price", None)
    cur = getattr(row, "current_price", None)
    if avg is not None or cur is not None:
        bits = []
        if avg is not None:
            bits.append(f"평단 {avg:,.0f}" if isinstance(avg, (int, float)) else f"평단 {avg}")
        if cur is not None:
            bits.append(f"현재 {cur:,.0f}" if isinstance(cur, (int, float)) else f"현재 {cur}")
        lines.append(" · ".join(bits))
    rem = getattr(row, "remaining_upside_pct", None)
    if rem is not None:
        try:
            lines.append(f"목표가까지 남은 상승: {float(rem):+.1f}%")
        except (TypeError, ValueError):
            pass
    tgt_detail = str(getattr(row, "target_detail", None) or "").strip()
    if tgt_detail:
        lines.append(f"목표가: {tgt_detail}")
    lines.append("자동매매·target 자동 변경 없음 · 사람 집행")
    return lines


# Higher = stronger pull on portfolio needle
_PRIORITY: dict[str, int] = {
    "S0": 100,
    "S2a": 90,
    "S2c": 85,
    "S1": 70,
    "Sprox": 50,
    "E": 40,
    "DATA": 20,
    "HOLD": 0,
}


@dataclass(frozen=True)
class RotationNeedleItem:
    ticker: str
    name: str
    bearing: Bearing
    step_id: str
    label: str
    detail: str
    priority: int


@dataclass(frozen=True)
class RotationCompass:
    bearing: Bearing
    degrees: float
    title_ko: str
    hint: str
    items: tuple[RotationNeedleItem, ...]
    replace_count: int
    trim_or_cash_count: int
    hold_count: int
    summary: str


def _bearing_from_row(row: Any) -> tuple[Bearing, str, int]:
    kind = str(getattr(row, "ops_signal", "") or "hold")
    extra = getattr(row, "extra", None) or {}
    step = str(extra.get("ops_step_id") or "")
    if kind == "exit_full":
        return "replace", step or "S2a", _PRIORITY.get(step or "S2a", 90)
    if kind == "cash_half":
        return "cash", step or "S1", _PRIORITY.get(step or "S1", 70)
    if kind == "trim":
        return "trim", step or "Sprox", _PRIORITY.get(step or "Sprox", 50)
    if kind == "missing":
        return "missing", step or "E", _PRIORITY.get("E", 40)
    return "hold", step or "HOLD", 0


def build_rotation_compass(
    ops_rows: Sequence[Any],
    *,
    proposal_tickers: set[str] | None = None,
) -> RotationCompass:
    """Build live compass from ops holdings (signals already attached)."""
    del proposal_tickers  # membership already baked into ops_signal via S2a
    items: list[RotationNeedleItem] = []
    for r in ops_rows:
        tk = str(getattr(r, "ticker", "") or "").zfill(6)
        if not tk.strip("0"):
            continue
        # Skip non-alpha noise if weight ~0
        w = getattr(r, "weight_pct", None)
        try:
            if w is not None and float(w) <= 0.05:
                continue
        except (TypeError, ValueError):
            pass
        bearing, step, pri = _bearing_from_row(r)
        items.append(
            RotationNeedleItem(
                ticker=tk,
                name=str(getattr(r, "name", None) or tk),
                bearing=bearing,
                step_id=step,
                label=str(getattr(r, "ops_signal_label", None) or BEARING_KO[bearing]),
                detail=str(getattr(r, "ops_signal_detail", None) or ""),
                priority=pri,
            )
        )

    if not items:
        return RotationCompass(
            bearing="hold",
            degrees=0.0,
            title_ko=BEARING_KO["hold"],
            hint="알파 보유 없음 · 후보는 표에서 · 교체 불필요",
            items=(),
            replace_count=0,
            trim_or_cash_count=0,
            hold_count=0,
            summary="바늘: 유지 · 보유 없음",
        )

    top = max(items, key=lambda x: x.priority)
    # If all priority 0, hold
    bearing: Bearing = top.bearing if top.priority > 0 else "hold"
    # Tie-break: if any replace, prefer replace for portfolio needle
    if any(i.bearing == "replace" for i in items):
        bearing = "replace"
    elif any(i.bearing == "cash" for i in items):
        bearing = "cash"
    elif any(i.bearing == "trim" for i in items):
        bearing = "trim"
    elif any(i.bearing == "missing" for i in items):
        bearing = "missing"

    replace_n = sum(1 for i in items if i.bearing == "replace")
    trim_cash_n = sum(1 for i in items if i.bearing in ("trim", "cash"))
    hold_n = sum(1 for i in items if i.bearing == "hold")

    return RotationCompass(
        bearing=bearing,
        degrees=BEARING_DEG[bearing],
        title_ko=BEARING_KO[bearing],
        hint=BEARING_HINT[bearing],
        items=tuple(sorted(items, key=lambda x: (-x.priority, x.ticker))),
        replace_count=replace_n,
        trim_or_cash_count=trim_cash_n,
        hold_count=hold_n,
        summary=(
            f"바늘: {BEARING_KO[bearing]} · "
            f"전량·교체 {replace_n} · 줄이기/환금 {trim_cash_n} · 유지 {hold_n}"
        ),
    )


def compass_svg_html(degrees: float, *, size: int = 220) -> str:
    """Inline SVG dial + needle (CSS rotate). degrees: 0=north."""
    # SVG y-down: rotate so 0° points up
    rot = degrees
    r = size // 2 - 8
    cx = cy = size // 2
    return f"""
<div class="rot-compass" style="width:{size}px;margin:0 auto;text-align:center;">
<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}"
     xmlns="http://www.w3.org/2000/svg" aria-label="교체 나침반">
  <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="currentColor"
          stroke-opacity="0.25" stroke-width="2"/>
  <circle cx="{cx}" cy="{cy}" r="6" fill="currentColor"/>
  <text x="{cx}" y="22" text-anchor="middle" font-size="12" fill="currentColor">유지</text>
  <text x="{size - 14}" y="{cy + 4}" text-anchor="end" font-size="11" fill="currentColor">환금</text>
  <text x="{cx}" y="{size - 10}" text-anchor="middle" font-size="12" fill="currentColor">전량·교체</text>
  <text x="14" y="{cy + 4}" text-anchor="start" font-size="11" fill="currentColor">줄이기</text>
  <g style="transform:rotate({rot}deg);transform-origin:{cx}px {cy}px;
            transition:transform 0.6s ease;">
    <polygon points="{cx},28 {cx - 9},{cy + 8} {cx + 9},{cy + 8}"
             fill="currentColor"/>
    <line x1="{cx}" y1="{cy}" x2="{cx}" y2="{size - 36}"
          stroke="currentColor" stroke-opacity="0.35" stroke-width="2"/>
  </g>
</svg>
</div>
"""
