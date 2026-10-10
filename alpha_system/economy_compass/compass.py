"""Assemble economy compass view from regime signal — no file writes to target."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from alpha_system.economy_compass.history import FrequencyTable, frequency_for_stage
from alpha_system.economy_compass.sleeves import (
    SleeveBand,
    alpha_envelope_line,
    sleeve_bands_for_stage,
)
from alpha_system.economy_signal import EconomySignal, SignalInput


@dataclass(frozen=True)
class MetricSleeveHint:
    key: str
    title: str
    stress_label: str
    sleeve_implication: str


@dataclass(frozen=True)
class CompassView:
    stage: Optional[int]
    stage_label: str
    alpha_line: str
    sleeves: tuple[SleeveBand, ...]
    frequency: FrequencyTable
    metric_hints: tuple[MetricSleeveHint, ...]
    regime_warning: str
    kr_link: str


_STRESS = {0: "여유", 1: "주의", 2: "긴축"}

_SLEEVE_IMPL: dict[str, dict[int, str]] = {
    "hy_oas": {
        0: "신용 안정 → 주식 여유 · 현금 최소.",
        1: "신용 주의 → 주식 축소·현금↑ Review.",
        2: "신용 경색 → 주식↓ · 현금·국채·금 우선.",
    },
    "real_us": {
        0: "할인 부담 작음 → 주식·장기채 상대 우호.",
        1: "실질금리↑ → 성장주·듀레이션 부담.",
        2: "할인 압력 큼 → 주식↓ · 현금·단기 우대.",
    },
    "fed_hike": {
        0: "정책금리 압박 약함.",
        1: "소폭 긴축 → 레버리지·테마 주의.",
        2: "빠른 인상 → 위험자산 줄임 · 빚 기반 AI 과열 경계.",
    },
    "boj_hike": {
        0: "엔·글로벌 유동성 압박 약함.",
        1: "글로벌 긴축 배경으로 주의.",
        2: "유동성 부담 → 주식·환 민감 자산 신중.",
    },
    "curve": {
        0: "정상 곡선 → 침체 경고 약함.",
        1: "평탄·약한 역전 → 불확실성↑.",
        2: "역전 깊음 → 방어 슬리브·현금 우선.",
    },
}

_TITLES = {
    "hy_oas": "하이일드 스프레드",
    "real_us": "미국 10년 실질금리",
    "fed_hike": "연준 금리 3개월",
    "boj_hike": "일본 콜금리 3개월",
    "curve": "미국 장단기 금리차",
}


def _metric_hints(inputs: Sequence[SignalInput]) -> tuple[MetricSleeveHint, ...]:
    out: list[MetricSleeveHint] = []
    for item in inputs:
        key = str(item.key or "")
        if key not in _SLEEVE_IMPL:
            continue
        score = item.score
        if score is None:
            impl = "데이터 없음 · 이 지표는 스킵(fail-open)."
            stress = "—"
        else:
            try:
                s = int(score)
            except (TypeError, ValueError):
                s = 1
            impl = _SLEEVE_IMPL[key].get(s, "")
            stress = _STRESS.get(s, "—")
        out.append(
            MetricSleeveHint(
                key=key,
                title=_TITLES.get(key, item.label or key),
                stress_label=stress,
                sleeve_implication=impl,
            )
        )
    return tuple(out)


def build_compass(signal: EconomySignal | None) -> CompassView:
    """Pure view model from cached economy signal."""
    if signal is None:
        return CompassView(
            stage=None,
            stage_label="",
            alpha_line="—",
            sleeves=(),
            frequency=frequency_for_stage(None),
            metric_hints=(),
            regime_warning="다시 계산으로 국면을 만드세요.",
            kr_link="포트폴리오 ③ 최종 제안·노른자 대기 (자동 편입 없음)",
        )
    stage = signal.stage
    sleeves = tuple(sleeve_bands_for_stage(stage))
    warn = ""
    if stage is not None and int(stage) >= 4:
        warn = (
            "긴축·방어 구간 · 기술 생존 ≠ 주가 · "
            "빚·금리로 부푼 AI·테마 추격 자제 · 자동매도 없음."
        )
    elif stage is not None and int(stage) == 3:
        warn = "중립 · 품질(노른자)만 · 레버리지·테마 과열 주의."
    return CompassView(
        stage=stage,
        stage_label=str(signal.stage_label or ""),
        alpha_line=alpha_envelope_line(
            stage, float(signal.equity_share), float(signal.cash_share)
        ),
        sleeves=sleeves,
        frequency=frequency_for_stage(stage),
        metric_hints=_metric_hints(signal.inputs or []),
        regime_warning=warn,
        kr_link="포트폴리오 ③ 최종 제안·노른자 대기 · 나침반이 순위·target을 바꾸지 않음",
    )
