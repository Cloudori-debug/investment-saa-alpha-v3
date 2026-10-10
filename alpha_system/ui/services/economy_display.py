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

# key → stress score → what this reading means for equity/cash (plain Korean).
METRIC_READING: dict[str, dict[int, str]] = {
    "hy_oas": {
        0: "신용 시장이 안정으로 읽힙니다. 가산이 낮을수록 부도 우려가 작고, 위험자산에 우호적입니다.",
        1: "회사채 가산이 중간입니다. 신용 스트레스가 커지기 시작한 구간으로 주식 비중을 조금 줄일 근거가 됩니다.",
        2: "고위험 회사채가 비싸져 신용 경색 신호입니다. 위험자산보다 현금·단기채를 늘리는 쪽으로 읽습니다.",
    },
    "real_us": {
        0: "실질금리가 낮아 할인 부담이 작습니다. 주식·장기채 가격에 상대적으로 우호적입니다.",
        1: "실질금리가 올라 할인율이 센 편입니다. 성장주·장기자산에 부담이 쌓이는 구간입니다.",
        2: "물가 제외 장기금리가 높아 자산 할인 압력이 큽니다. 주식 비중을 줄이는 긴축 신호로 칩니다.",
    },
    "fed_hike": {
        0: "최근 3개월 인상이 없거나 인하 쪽입니다. 정책금리 압박은 약합니다.",
        1: "소폭 인상입니다. 급격한 쇼크는 아니지만 유동성·할인율에 주의가 붙습니다.",
        2: "짧은 기간에 금리를 많이 올렸습니다. 긴축 속도가 센 구간으로 주식 비중을 줄일 근거입니다.",
    },
    "boj_hike": {
        0: "일본 정책금리가 최근 3개월 그대로이거나 내린 쪽입니다. 엔·글로벌 유동성 압박은 약합니다.",
        1: "일본도 소폭 인상 중입니다. 단독 쇼크보다는 글로벌 긴축 배경으로 주의합니다.",
        2: "일본 금리가 짧은 기간에 크게 올랐습니다. 엔화·글로벌 유동성에 부담이 큰 구간입니다.",
    },
    "curve": {
        0: "장기금리가 단기보다 높아 정상 곡선입니다. 침체 경고로 쓰는 역전은 아닙니다.",
        1: "장단기가 비슷하거나 약한 역전입니다. 경기·정책 불확실성이 커진 구간으로 읽습니다.",
        2: "단기금리가 장기보다 높은 역전입니다. 침체·금융 스트레스 가능성이 커진 신호로 칩니다.",
    },
}

# Display range + scoring thresholds (same cuts as economy_signal.score_*).
# segments: ordered (end_value, tone) covering lo→hi; last end should be hi.
METRIC_SLIDER: dict[str, dict[str, object]] = {
    "hy_oas": {
        "lo": 100.0,
        "hi": 700.0,
        "ticks": ((350.0, "350"), (500.0, "500")),
        "segments": ((350.0, "ok"), (500.0, "wait"), (700.0, "bad")),
        "fmt": "bp",
    },
    "real_us": {
        "lo": -0.5,
        "hi": 4.0,
        "ticks": ((1.0, "1%"), (2.0, "2%")),
        "segments": ((1.0, "ok"), (2.0, "wait"), (4.0, "bad")),
        "fmt": "%",
    },
    "fed_hike": {
        "lo": -0.50,
        "hi": 1.00,
        "ticks": ((0.0, "0"), (0.25, "+0.25")),
        "segments": ((0.0, "ok"), (0.25, "wait"), (1.00, "bad")),
        "fmt": "%p",
    },
    "boj_hike": {
        "lo": -0.50,
        "hi": 1.00,
        "ticks": ((0.0, "0"), (0.25, "+0.25")),
        "segments": ((0.0, "ok"), (0.25, "wait"), (1.00, "bad")),
        "fmt": "%p",
    },
    "curve": {
        "lo": -1.50,
        "hi": 1.50,
        "ticks": ((-0.20, "−0.2"), (0.20, "+0.2")),
        "segments": ((-0.20, "bad"), (0.20, "wait"), (1.50, "ok")),
        "fmt": "%p",
    },
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


def metric_reading(item: SignalInput) -> str:
    """Plain-language reading for the current value / stress band."""
    if item.score is None:
        return "이 지표는 아직 없어 단계 계산에 넣지 않습니다."
    band = METRIC_READING.get(item.key, {})
    text = band.get(int(item.score), "")
    if text:
        return text
    label = stress_label(item.score)
    return f"현재 배지는 {label}입니다. 개별주·단기채 단계를 올릴지 내릴지 참고만 합니다."


def _slider_pct(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    raw = (value - lo) / (hi - lo) * 100.0
    return max(0.0, min(100.0, raw))


def metric_slider(item: SignalInput) -> dict[str, object] | None:
    """Horizontal bar: current position + threshold ticks (scoring cuts)."""
    spec = METRIC_SLIDER.get(item.key)
    if spec is None or item.value is None:
        return None
    lo = float(spec["lo"])
    hi = float(spec["hi"])
    pct = _slider_pct(float(item.value), lo, hi)
    ticks: list[dict[str, object]] = []
    for cut, label in spec["ticks"]:  # type: ignore[misc]
        ticks.append({"pct": round(_slider_pct(float(cut), lo, hi), 2), "label": str(label)})
    segments: list[dict[str, object]] = []
    cursor = lo
    for end, tone in spec["segments"]:  # type: ignore[misc]
        end_f = float(end)
        start_pct = _slider_pct(cursor, lo, hi)
        end_pct = _slider_pct(end_f, lo, hi)
        width = max(0.0, end_pct - start_pct)
        if width > 0:
            segments.append({"width": round(width, 2), "tone": str(tone)})
        cursor = end_f
    return {
        "pct": round(pct, 2),
        "tone": stress_tone(item.score),
        "ticks": ticks,
        "segments": segments,
        "clamped": float(item.value) < lo or float(item.value) > hi,
    }


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


def metric_rows(signal: EconomySignal, *, today: date | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in signal.inputs:
        rows.append(
            {
                "key": item.key,
                "title": metric_title(item),
                "hint": metric_hint(item),
                "reading": metric_reading(item),
                "value": format_metric_value(item),
                "stress": stress_label(item.score),
                "tone": stress_tone(item.score),
                "as_of": format_as_of(item.as_of, today=today),
                "slider": metric_slider(item),
            }
        )
    return rows
