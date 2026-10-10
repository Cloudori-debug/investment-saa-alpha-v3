"""Forest-level defense checklist by economy stage — Review-only display.

Does not write target_portfolio.csv, change QVM ranks, or place orders.
Complements stage_playbook (alpha equity/cash sleeve) with whole-net-worth reminders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from alpha_system.ui.services.economy_playbook import TodoCard


@dataclass(frozen=True)
class ForestChecklist:
    """Operator reminders outside the KR equity sleeve."""

    stage: Optional[int]
    tone: str  # ok | wait | bad | off
    title: str
    focus: str
    cards: tuple[TodoCard, ...]

    @property
    def bullets(self) -> tuple[str, ...]:
        return tuple(c.body for c in self.cards)


def stage_forest_checklist(stage: int | None) -> ForestChecklist:
    """Map economy ladder → cash / bonds / gold / quality waitlist checks."""
    if stage is None:
        return ForestChecklist(
            stage=None,
            tone="off",
            title="단계 없음",
            focus="다시 계산 후 확인",
            cards=(
                TodoCard(
                    "재산 전체",
                    "금리·신용 단계를 만든 뒤, 현금·채권·금·해외도 같이 보세요.",
                ),
                TodoCard(
                    "알림만",
                    "순위·target·자동매매는 없습니다.",
                ),
            ),
        )
    s = int(stage)
    if s <= 2:
        return ForestChecklist(
            stage=s,
            tone="ok",
            title="숲 · 불리기 여유",
            focus="주식 밖은 최소 버퍼 · 대기열만",
            cards=(
                TodoCard("현금 버퍼", "현금·단기예금은 최소 버퍼만 두어도 됩니다."),
                TodoCard(
                    "국채 · 금",
                    "무리하게 늘리지 말고, 목표가 비중에 가깝게만.",
                ),
                TodoCard(
                    "노른자 대기",
                    "포트 「편입하지 않음」고Q = 조정 때 볼 목록으로 메모.",
                ),
                TodoCard(
                    "해외 · 환",
                    "가끔만 점검 · 추격 매수는 주식 품질과 같이.",
                ),
            ),
        )
    if s == 3:
        return ForestChecklist(
            stage=s,
            tone="wait",
            title="숲 · 방어 점검",
            focus="현금·국채·금 · 노른자만",
            cards=(
                TodoCard(
                    "현금 · 예금",
                    "단기채·예금 합이 너무 얇지 않은지 확인.",
                ),
                TodoCard(
                    "한국 국채",
                    "우량채 비중 Review · 해외채권은 환율 리스크 신중.",
                ),
                TodoCard(
                    "금",
                    "인플레·환율 불안 때만 소량 · 과매수 추격 금지.",
                ),
                TodoCard(
                    "리츠 · HY",
                    "고위험 신용·리츠는 보류·축소 쪽을 먼저.",
                ),
                TodoCard(
                    "주식 · 노른자",
                    "품질만 · 위 「지금 할 일」과 같이 Review.",
                ),
            ),
        )
    if s == 4:
        return ForestChecklist(
            stage=s,
            tone="bad",
            title="숲 · 방어 우선",
            focus="탄약 · 신규 중단",
            cards=(
                TodoCard(
                    "탄약 두껍게",
                    "현금·단기채를 재산 전체 %로 다시 적으세요.",
                ),
                TodoCard(
                    "국채 듀레이션",
                    "금리·둔화 신호를 본 뒤에만 Review.",
                ),
                TodoCard(
                    "금 상한",
                    "꼬리 헤지 상한 안에서 유지 여부만.",
                ),
                TodoCard(
                    "주식 신규 중단",
                    "한국·해외 신규 기본 중단 · 노른자 목록만 유지.",
                ),
                TodoCard(
                    "레버리지 제외",
                    "변동금리·약한 재무·테마 레버리지는 제외.",
                ),
            ),
        )
    return ForestChecklist(
        stage=s,
        tone="bad",
        title="숲 · 생존·유동성",
        focus="현금 우대 · 추격 금지",
        cards=(
            TodoCard(
                "생존 우선",
                "생활비·단기 유동성을 최우선으로.",
            ),
            TodoCard(
                "위험자산 ↓",
                "주식 합산 비중을 숲 %로 확인·축소 Review.",
            ),
            TodoCard(
                "대기만",
                "노른자 목록 유지 · 실행은 단계 하향 후·분할·월말.",
            ),
            TodoCard(
                "추격 금지",
                "HY·커브 악화 시 추격 매수 하지 마세요.",
            ),
            TodoCard(
                "회복 전 보류",
                "단계 하향 전까지 비중 확대는 보류.",
            ),
        ),
    )
