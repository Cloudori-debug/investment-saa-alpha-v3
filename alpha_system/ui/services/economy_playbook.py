"""Economy-stage playbook + holdings↔proposal gap (Review-only).

Does not write target_portfolio.csv, change QVM ranks, or place orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence


@dataclass(frozen=True)
class TodoCard:
    """One visual action tile: short label + detail."""

    label: str
    body: str


@dataclass(frozen=True)
class StagePlaybook:
    """Fixed operator checklist for the current equity/cash stage."""

    stage: Optional[int]
    tone: str  # ok | wait | bad | off
    title: str
    equity_pct: Optional[float]
    cash_pct: Optional[float]
    cards: tuple[TodoCard, ...]

    @property
    def equity_cash(self) -> str:
        if self.equity_pct is None or self.cash_pct is None:
            return "—"
        return (
            f"개별주 {int(round(self.equity_pct))}% / "
            f"단기채 {int(round(self.cash_pct))}%"
        )

    @property
    def bullets(self) -> tuple[str, ...]:
        return tuple(c.body for c in self.cards)


@dataclass(frozen=True)
class GapName:
    ticker: str
    name: str


@dataclass(frozen=True)
class HoldingsProposalGap:
    held_not_proposed: list[GapName] = field(default_factory=list)
    proposed_not_held: list[GapName] = field(default_factory=list)
    overlap: list[GapName] = field(default_factory=list)

    @property
    def has_gaps(self) -> bool:
        return bool(self.held_not_proposed or self.proposed_not_held)

    @property
    def no_books(self) -> bool:
        return not self.held_not_proposed and not self.proposed_not_held and not self.overlap


def _norm_ticker(raw: object) -> str:
    text = str(raw or "").strip()
    if text.isdigit():
        return text.zfill(6)
    return text


def stage_playbook(stage: int | None) -> StagePlaybook:
    """High-rate / credit ladder → plain Korean to-dos (no auto trade)."""
    if stage is None:
        return StagePlaybook(
            stage=None,
            tone="off",
            title="단계 없음",
            equity_pct=None,
            cash_pct=None,
            cards=(
                TodoCard(
                    "다시 계산",
                    "금리·신용 단계를 만든 뒤 단기채 비중을 맞추세요.",
                ),
                TodoCard(
                    "자동 없음",
                    "종목 순위와 target 파일은 바꾸지 않습니다.",
                ),
            ),
        )
    s = int(stage)
    if s <= 1:
        return StagePlaybook(
            stage=s,
            tone="ok",
            title="기본 · 공격 여유",
            equity_pct=90.0,
            cash_pct=10.0,
            cards=(
                TodoCard("단기채 버퍼", "기본 버퍼(약 10%)만 유지해도 됩니다."),
                TodoCard(
                    "중기 Review",
                    "Q/SR·게이트·하케다카 통과 제안만 보세요.",
                ),
                TodoCard(
                    "단기 추격",
                    "모멘텀은 배지·vol 예산을 확인한 뒤.",
                ),
            ),
        )
    if s == 2:
        return StagePlaybook(
            stage=s,
            tone="ok",
            title="조금 줄임",
            equity_pct=75.0,
            cash_pct=25.0,
            cards=(
                TodoCard(
                    "단기채 ↑",
                    "단기채를 약 25%까지 올려 맞출지 Review.",
                ),
                TodoCard(
                    "중기 신규",
                    "품질·환원 우선 · 테마만 센 종목은 보류.",
                ),
                TodoCard(
                    "단기 보수",
                    "신규·추격은 평소보다 보수적으로.",
                ),
            ),
        )
    if s == 3:
        return StagePlaybook(
            stage=s,
            tone="wait",
            title="고금리 중립 · 할 일",
            equity_pct=60.0,
            cash_pct=40.0,
            cards=(
                TodoCard(
                    "단기채 ~40%",
                    "전체 봉투의 단기채·현금을 ~40%에 가깝게 맞출지 Review.",
                ),
                TodoCard(
                    "중기 · 품질만",
                    "Q·SR·게이트·하케다카·목표가 여유 있는 종목만.",
                ),
                TodoCard(
                    "보유 ∉ 제안",
                    "보유인데 최종 제안 밖이면 교체·축소를 종목별로 검토.",
                ),
                TodoCard(
                    "단기 줄이기",
                    "모멘텀 추격·반등 단타는 줄이기.",
                ),
                TodoCard(
                    "사람 실행",
                    "자동매도·target 자동기입 없음 · 현금·단기채에서 실행.",
                ),
            ),
        )
    if s == 4:
        return StagePlaybook(
            stage=s,
            tone="bad",
            title="방어 · 할 일",
            equity_pct=40.0,
            cash_pct=60.0,
            cards=(
                TodoCard(
                    "단기채 ~60%",
                    "단기채·현금을 ~60%까지 두껍게 맞출지 Review.",
                ),
                TodoCard(
                    "중기 신규 중단",
                    "신규는 기본 중단 · 보유는 게이트·목표가부터 정리.",
                ),
                TodoCard(
                    "5단계 감시",
                    "HY·커브가 더 악화되면 현금 우대(5단계)로 한 단계 더.",
                ),
                TodoCard(
                    "단기 위성",
                    "예산·교체 배지를 우선 확인.",
                ),
            ),
        )
    return StagePlaybook(
        stage=s,
        tone="bad",
        title="현금 우대 · 할 일",
        equity_pct=20.0,
        cash_pct=80.0,
        cards=(
            TodoCard(
                "위험자산 ↓",
                "비중을 크게 줄이고 단기채·현금을 우선 Review.",
            ),
            TodoCard(
                "신규 보류",
                "중기·단기 신규는 사실상 보류 · 생존·유동성 우선.",
            ),
            TodoCard(
                "단계 재확인",
                "HY 급등·커브 깊은 역전이 같이 있으면 이 단계가 맞는지 재확인.",
            ),
            TodoCard(
                "추격 자제",
                "회복 신호(HY 안정·단계 하향) 전까지 추격 매수 자제.",
            ),
        ),
    )


def _name_map(rows: Iterable[object]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in rows:
        tk = _norm_ticker(getattr(row, "ticker", None))
        if not tk:
            continue
        name = str(getattr(row, "name", None) or "").strip() or tk
        out[tk] = name
    return out


def holdings_proposal_gap(
    held_rows: Sequence[object] | None,
    proposal_rows: Sequence[object] | None,
) -> HoldingsProposalGap:
    """Compare ops holdings vs final proposal (eligible) tickers."""
    held_map = _name_map(held_rows or ())
    prop_map = _name_map(proposal_rows or ())
    held = set(held_map)
    prop = set(prop_map)
    overlap = sorted(held & prop)
    held_only = sorted(held - prop)
    prop_only = sorted(prop - held)
    return HoldingsProposalGap(
        held_not_proposed=[GapName(t, held_map[t]) for t in held_only],
        proposed_not_held=[GapName(t, prop_map[t]) for t in prop_only],
        overlap=[GapName(t, held_map.get(t) or prop_map.get(t) or t) for t in overlap],
    )
