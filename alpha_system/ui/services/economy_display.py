"""Economy signal screen copy — hide FRED ticker soup from the operator."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Mapping

from alpha_system.economy_signal import STAGES, EconomySignal, SignalInput

KST = timezone(timedelta(hours=9))

STRESS_LABEL = {0: "여유", 1: "주의", 2: "긴축"}

# key → (short name, one-line meaning). Series codes stay in `key` only.
METRIC_COPY: dict[str, tuple[str, str]] = {
    "hy_oas": ("하이일드 스프레드", "회사채가 국채보다 얼마나 비싼지"),
    "real_us": ("미국 10년 실질금리", "물가를 뺀 장기 금리"),
    "fed_hike": ("연준 금리 3개월", "최근 올린 폭"),
    "boj_hike": ("일본 콜금리 3개월", "월간 통계라 며칠~몇 달 늦을 수 있음"),
    "curve": ("미국 장단기 금리차", "10년물에서 2년물을 뺀 값"),
}

_SERIES_NOTES = {
    "dff",
    "dfii10",
    "t10y2y",
    "irstci01jpm156n",
    "bamlh0a0hym2",
    "hy oas",
    "신용 스프레드",
}


def stress_label(score: int | None) -> str:
    if score is None:
        return "없음"
    return STRESS_LABEL.get(int(score), "없음")


def stress_tone(score: int | None) -> str:
    if score is None:
        return "off"
    if int(score) <= 0:
        return "ok"
    if int(score) == 1:
        return "wait"
    return "bad"


def format_fetched_at(raw: str, *, today: date | None = None) -> str:
    del today
    text = (raw or "").strip()
    if not text:
        return ""
    stamp = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(stamp)
    except ValueError:
        return text[:16].replace("T", " ")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(KST)
    return local.strftime("%Y-%m-%d %H:%M")


def format_as_of(raw: str, *, today: date | None = None) -> str:
    text = (raw or "").strip()[:10]
    if not text:
        return ""
    try:
        day = date.fromisoformat(text)
    except ValueError:
        return text
    now = today or date.today()
    age = (now - day).days
    if age >= 40:
        return f"{text} · 지연"
    return text


def format_metric_value(item: SignalInput) -> str:
    if item.value is None:
        return "—"
    unit = (item.unit or "").strip()
    val = item.value
    if item.key in {"fed_hike", "boj_hike"}:
        if abs(val) < 1e-9:
            return "변동 없음"
        sign = "+" if val > 0 else ""
        return f"{sign}{val:g}{unit}"
    if item.key == "curve":
        sign = "+" if val > 0 else ""
        return f"{sign}{val:g}{unit}"
    if unit == "bp":
        return f"{val:g} bp"
    if unit == "%":
        return f"{val:g}%"
    return f"{val:g} {unit}".strip()


def metric_title(item: SignalInput) -> str:
    pair = METRIC_COPY.get(item.key)
    return pair[0] if pair else item.label


def metric_hint(item: SignalInput) -> str:
    pair = METRIC_COPY.get(item.key)
    hint = pair[1] if pair else ""
    note = (item.note or "").strip()
    low = note.lower()
    if note and not any(token in low for token in _SERIES_NOTES) and "수준" not in note:
        return note
    if item.key == "fed_hike" and "DFF 수준" in note:
        rest = note.replace("DFF 수준", "").strip()
        if rest:
            return f"기준금리 {rest}%"
    if item.key == "boj_hike" and ("IRSTCI" in note or "수준" in note):
        return METRIC_COPY["boj_hike"][1]
    return hint


def hero_copy(signal: EconomySignal) -> Mapping[str, str]:
    cap = max(int(signal.known), 0) * 2
    scoreline = ""
    if signal.known:
        scoreline = f"긴축 {signal.tightening} / {cap}"
    if signal.stage is None:
        return {
            "kicker": "단계 없음",
            "title": "기본 비중 유지",
            "equity": "90%",
            "cash": "10%",
            "why": signal.detail or "지표가 부족합니다.",
            "scoreline": scoreline,
        }
    return {
        "kicker": f"{signal.stage}단계",
        "title": signal.stage_label or "",
        "equity": f"{signal.equity_share:.0%}",
        "cash": f"{signal.cash_share:.0%}",
        "why": "사람이 현금·단기채에서 맞춥니다.",
        "scoreline": scoreline,
    }


def ladder_rows(current: int | None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for stage, eq, cash, label in STAGES:
        rows.append(
            {
                "stage": stage,
                "label": label,
                "equity": f"{eq:.0%}",
                "cash": f"{cash:.0%}",
                "current": current is not None and stage == current,
            }
        )
    return rows


def metric_rows(signal: EconomySignal, *, today: date | None = None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in signal.inputs:
        rows.append(
            {
                "title": metric_title(item),
                "hint": metric_hint(item),
                "value": format_metric_value(item),
                "stress": stress_label(item.score),
                "tone": stress_tone(item.score),
                "as_of": format_as_of(item.as_of, today=today),
            }
        )
    return rows
