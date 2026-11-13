"""계좌 이분 할 일 · 역발상 Soft 게이트 — Review-only.

합산 주문·target·API 없음. docs/ACCOUNT_SPLIT_OPS_SPEC.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from typing import Any, Sequence

from alpha_system.proposal_chart import norm_ticker
from alpha_system.ui.services.strategy_candidates_board import (
    ACCOUNT_BUDGET_PCT,
    ACCOUNT_LABEL_KO,
    ACCOUNT_PENSION,
    ACCOUNT_TAXABLE,
    OPS_STACK_BUDGET_PCT,
    PARK_TICKER,
    StrategyCandidatesBundle,
    attach_ops_stack_portfolio_pct,
)

DAY_BUY_CAP_PCT = 33.0
GATE_PASS = "pass"
GATE_HOLD = "hold"
GATE_FAIL = "fail"


@dataclass(frozen=True)
class ChecklistItem:
    account_id: str
    strategy_id: str
    title_ko: str
    cadence_ko: str
    done_when_ko: str
    tickers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContrarianGateStep:
    id: str
    label_ko: str
    status: str  # pass | hold | fail
    detail_ko: str


@dataclass
class AccountOpsChecklist:
    pension_items: list[ChecklistItem] = field(default_factory=list)
    taxable_items: list[ChecklistItem] = field(default_factory=list)
    gate_steps: list[ContrarianGateStep] = field(default_factory=list)
    gate_verdict: str = GATE_HOLD  # pass | hold | fail
    gate_line_ko: str = ""
    account_budget_pct: dict[str, float] = field(default_factory=dict)
    aux: Any = None  # ContrarianSoftAux | None · 순환 import 회피
    review_only: bool = True
    writes_target: bool = False
    note_ko: str = (
        "합산 집행 금지 · target 자동 없음 · 역발상=관찰·분할 · HTS·연금은 사람"
    )


def _tickers_for(bundle: StrategyCandidatesBundle, sid: str) -> tuple[str, ...]:
    out: list[str] = []
    for c in bundle.by_strategy.get(sid) or []:
        tk = norm_ticker(c.ticker)
        if tk and tk not in out:
            out.append(tk)
    return tuple(out)


def _soft_equity_tickers(bundle: StrategyCandidatesBundle) -> tuple[str, ...]:
    """단기채 파킹 제외 Soft 종목."""
    out: list[str] = []
    for c in bundle.by_strategy.get("mid_soft") or []:
        tk = norm_ticker(c.ticker)
        if not tk or tk == PARK_TICKER:
            continue
        if tk not in out:
            out.append(tk)
    return tuple(out)


def build_account_todos(
    bundle: StrategyCandidatesBundle,
) -> tuple[list[ChecklistItem], list[ChecklistItem]]:
    """연금 / 일반 오늘 할 일."""
    attach_ops_stack_portfolio_pct(bundle)
    soft_tks = _soft_equity_tickers(bundle)
    short_tks = tuple(
        tk
        for tk in _tickers_for(bundle, "short_momentum")
        if tk != PARK_TICKER
    )
    dual_tks = tuple(
        tk
        for tk in _tickers_for(bundle, "dual_momentum")
        if tk != PARK_TICKER
    )
    static_tks = _tickers_for(bundle, "static_book")

    pension = [
        ChecklistItem(
            account_id=ACCOUNT_PENSION,
            strategy_id="static_book",
            title_ko="정적 본체 · 나침반적합",
            cadence_ko="연 1회·밴드",
            done_when_ko=(
                "증권·연금 앱에서 비중만 복원 · Soft와 한 주문 금지 · "
                f"가계 {OPS_STACK_BUDGET_PCT['static_book']:g}%"
            ),
            tickers=static_tks[:8],
        ),
        ChecklistItem(
            account_id=ACCOUNT_PENSION,
            strategy_id="dual_momentum",
            title_ko="듀얼 GEM · 월 픽",
            cadence_ko="월",
            done_when_ko=(
                "픽 1종만 앱 밖 집행 · Soft와 합산 금지 · "
                f"가계 {OPS_STACK_BUDGET_PCT['dual_momentum']:g}%"
                + (
                    f" · 현재 {', '.join(dual_tks[:3])}"
                    if dual_tks
                    else " · 픽 없으면 파킹"
                )
            ),
            tickers=dual_tks[:3],
        ),
    ]
    taxable = [
        ChecklistItem(
            account_id=ACCOUNT_TAXABLE,
            strategy_id="mid_soft",
            title_ko="중기 Soft · 일반 HTS",
            cadence_ko="확인① 후",
            done_when_ko=(
                "Soft 통과만 · 하루≤33% · 미집행=단기채 파킹 · "
                f"가계 {OPS_STACK_BUDGET_PCT['mid_soft']:g}%"
                + (
                    f" · 후보 {', '.join(soft_tks[:5])}"
                    if soft_tks
                    else " · Soft 공집합→파킹"
                )
            ),
            tickers=soft_tks[:5],
        ),
        ChecklistItem(
            account_id=ACCOUNT_TAXABLE,
            strategy_id="short_momentum",
            title_ko="단기 Soft · 위성",
            cadence_ko="위성",
            done_when_ko=(
                "중기 전량과 섞지 않음 · "
                f"가계 {OPS_STACK_BUDGET_PCT['short_momentum']:g}%"
                + (
                    f" · {', '.join(short_tks[:3])}"
                    if short_tks
                    else " · 공집합→파킹"
                )
            ),
            tickers=short_tks[:3],
        ),
    ]
    return pension, taxable


def build_contrarian_gate_steps(
    *,
    soft_equity_n: int = 0,
    observe_deep_or_precise: bool | None = None,
    logic_or_essence_ok: bool | None = None,
    gieop_gate: str | None = None,
    fear_tone: str | None = None,
    fear_as_buy_signal: bool = False,
    day_buy_pct: float | None = None,
    soft_funded_from_pension: bool = False,
) -> list[ContrarianGateStep]:
    """역발상 Soft 체인 · None 입력=미확인(hold)."""
    steps: list[ContrarianGateStep] = []

    # 1 저P 티어 ≠ 매수
    if observe_deep_or_precise is None:
        steps.append(
            ContrarianGateStep(
                "low_pbr_tier",
                "저P 티어≠매수",
                GATE_HOLD,
                "관찰 보드 미확인 · 심층·정밀만 후보 · Soft 자동편입 없음",
            )
        )
    elif observe_deep_or_precise:
        steps.append(
            ContrarianGateStep(
                "low_pbr_tier",
                "저P 티어≠매수",
                GATE_PASS,
                "심층·정밀 관찰 후보 · 매수 단정 아님",
            )
        )
    else:
        steps.append(
            ContrarianGateStep(
                "low_pbr_tier",
                "저P 티어≠매수",
                GATE_FAIL,
                "심층·정밀 아님 · Soft 매수 Review 보류",
            )
        )

    # 2 Soft∩논리/본질
    if logic_or_essence_ok is None:
        st = GATE_PASS if soft_equity_n > 0 else GATE_HOLD
        detail = (
            f"Soft 주식 {soft_equity_n}종 · 논리·본질은 해부/보드로 재확인"
            if soft_equity_n > 0
            else "Soft 주식 없음 · 논리·본질 미확인"
        )
        steps.append(
            ContrarianGateStep(
                "soft_logic",
                "Soft∩논리·본질",
                st,
                detail,
            )
        )
    elif logic_or_essence_ok:
        steps.append(
            ContrarianGateStep(
                "soft_logic",
                "Soft∩논리·본질",
                GATE_PASS,
                "논리·본질 Soft 통과 · 거시 점수 비가산",
            )
        )
    else:
        steps.append(
            ContrarianGateStep(
                "soft_logic",
                "Soft∩논리·본질",
                GATE_FAIL,
                "논리·본질 미통과 · Soft 매수 금지",
            )
        )

    # 3 기업해부
    g = str(gieop_gate or "").strip().upper()
    if not g:
        steps.append(
            ContrarianGateStep(
                "gieop",
                "기업해부",
                GATE_HOLD,
                "해부 판정 없음 · HOLD≠보유 권고 · PASS 전 매수 보류",
            )
        )
    elif g == "PASS":
        steps.append(
            ContrarianGateStep(
                "gieop",
                "기업해부",
                GATE_PASS,
                "해부 PASS · Review-only",
            )
        )
    elif g == "HOLD":
        steps.append(
            ContrarianGateStep(
                "gieop",
                "기업해부",
                GATE_HOLD,
                "해부 HOLD=조사 보류 · 보유 권고 아님",
            )
        )
    else:
        steps.append(
            ContrarianGateStep(
                "gieop",
                "기업해부",
                GATE_FAIL,
                f"해부 {g} · Soft 매수 금지",
            )
        )

    # 4 Fear · 나침반 — 허가증 아님 · Fear ⇏ Buy (contrarian-soft-gate-theory)
    tone = str(fear_tone or "").strip().lower()
    if fear_as_buy_signal:
        steps.append(
            ContrarianGateStep(
                "fear",
                "Fear·나침반",
                GATE_FAIL,
                "Fear≠매수 허가 · 트리거로 쓰면 FAIL · 사이즈↓·대기·파킹만",
            )
        )
    elif not tone:
        steps.append(
            ContrarianGateStep(
                "fear",
                "Fear·나침반",
                GATE_HOLD,
                "Fear Soft 미확인 · 매수 트리거로 쓰지 않음",
            )
        )
    elif tone == "hot":
        steps.append(
            ContrarianGateStep(
                "fear",
                "Fear·나침반",
                GATE_HOLD,
                "Fear hot · Soft 사이즈↓ · 공포매수 금지",
            )
        )
    else:
        steps.append(
            ContrarianGateStep(
                "fear",
                "Fear·나침반",
                GATE_PASS,
                "Fear=자세만 · 매수 트리거 아님",
            )
        )

    # 5 분할 하루≤33%
    if day_buy_pct is None:
        steps.append(
            ContrarianGateStep(
                "day_cap",
                "분할 하루≤33%",
                GATE_PASS,
                f"기본 상한 {DAY_BUY_CAP_PCT:g}% · 원금메우기·전량바닥 금지",
            )
        )
    elif float(day_buy_pct) <= DAY_BUY_CAP_PCT + 1e-9:
        steps.append(
            ContrarianGateStep(
                "day_cap",
                "분할 하루≤33%",
                GATE_PASS,
                f"오늘 {float(day_buy_pct):g}% ≤ {DAY_BUY_CAP_PCT:g}%",
            )
        )
    else:
        steps.append(
            ContrarianGateStep(
                "day_cap",
                "분할 하루≤33%",
                GATE_FAIL,
                f"오늘 {float(day_buy_pct):g}% > {DAY_BUY_CAP_PCT:g}% · 보류",
            )
        )

    # 6 계좌=일반만
    if soft_funded_from_pension:
        steps.append(
            ContrarianGateStep(
                "account",
                "계좌=일반만",
                GATE_FAIL,
                "연금·ISA 예산으로 Soft 채우기 금지",
            )
        )
    else:
        steps.append(
            ContrarianGateStep(
                "account",
                "계좌=일반만",
                GATE_PASS,
                f"Soft는 일반({ACCOUNT_BUDGET_PCT[ACCOUNT_TAXABLE]:g}%) · "
                f"연금({ACCOUNT_BUDGET_PCT[ACCOUNT_PENSION]:g}%)과 분리",
            )
        )

    return steps


def _verdict_from_steps(steps: Sequence[ContrarianGateStep]) -> tuple[str, str]:
    if any(s.status == GATE_FAIL for s in steps):
        bad = next(s for s in steps if s.status == GATE_FAIL)
        return GATE_FAIL, f"역발상 게이트 실패 · {bad.label_ko} · 대기·파킹"
    if any(s.status == GATE_HOLD for s in steps):
        held = [s.label_ko for s in steps if s.status == GATE_HOLD]
        return (
            GATE_HOLD,
            "역발상 게이트 보류 · " + " · ".join(held[:3]) + " · 매수 배지 없음",
        )
    return GATE_PASS, "역발상 게이트 통과 · 일반 Soft 매수 Review · 하루≤33%"


def build_account_ops_checklist(
    bundle: StrategyCandidatesBundle | None = None,
    *,
    observe_deep_or_precise: bool | None = None,
    logic_or_essence_ok: bool | None = None,
    gieop_gate: str | None = None,
    fear_tone: str | None = None,
    fear_as_buy_signal: bool = False,
    day_buy_pct: float | None = None,
    soft_funded_from_pension: bool = False,
    fear_available_n: int | None = None,
    fear_missing_n: int | None = None,
    blocker_n: int | None = None,
    unknown_n: int | None = None,
    pass_value: bool | None = None,
) -> AccountOpsChecklist:
    """계좌 할 일 + 역발상 게이트 + 보조지표."""
    from alpha_system.ui.services.contrarian_soft_aux import (
        build_contrarian_soft_aux,
    )

    b = bundle or StrategyCandidatesBundle(as_of="", market="")
    attach_ops_stack_portfolio_pct(b)
    pension, taxable = build_account_todos(b)
    soft_n = len(_soft_equity_tickers(b))
    steps = build_contrarian_gate_steps(
        soft_equity_n=soft_n,
        observe_deep_or_precise=observe_deep_or_precise,
        logic_or_essence_ok=logic_or_essence_ok,
        gieop_gate=gieop_gate,
        fear_tone=fear_tone,
        fear_as_buy_signal=fear_as_buy_signal,
        day_buy_pct=day_buy_pct,
        soft_funded_from_pension=soft_funded_from_pension,
    )
    verdict, line = _verdict_from_steps(steps)
    # 허가 문구를 역할 라벨로 명확화
    from alpha_system.ui.services.contrarian_soft_aux import gate_role_label

    line = gate_role_label(verdict) + " · " + line.split(" · ", 1)[-1]
    aux = build_contrarian_soft_aux(
        gate_verdict=verdict,
        gate_steps=steps,
        fear_available_n=fear_available_n,
        fear_missing_n=fear_missing_n,
        gieop_gate=gieop_gate,
        blocker_n=blocker_n,
        unknown_n=unknown_n,
        logic_ok=logic_or_essence_ok,
        pass_value=pass_value,
    )
    return AccountOpsChecklist(
        pension_items=list(pension),
        taxable_items=list(taxable),
        gate_steps=list(steps),
        gate_verdict=verdict,
        gate_line_ko=line,
        account_budget_pct=dict(
            b.account_budget_pct or ACCOUNT_BUDGET_PCT
        ),
        aux=aux,
        review_only=True,
        writes_target=False,
    )


def _items_html(title: str, items: Sequence[ChecklistItem], budget: float) -> str:
    rows = []
    for it in items:
        tks = ", ".join(it.tickers) if it.tickers else "—"
        rows.append(
            "<li>"
            f"<strong>{escape(it.title_ko)}</strong>"
            f" <span class=\"pf-env-muted\">({escape(it.cadence_ko)})</span>"
            f"<div class=\"pf-env-muted\">{escape(it.done_when_ko)}</div>"
            f"<div class=\"pf-env-muted\">티커 {escape(tks)}</div>"
            "</li>"
        )
    body = "".join(rows) or "<li class=\"pf-env-muted\">할 일 없음</li>"
    return (
        f'<div class="pf-acct-col">'
        f'<div class="pf-acct-h">{escape(title)} · 가계 {budget:g}%</div>'
        f"<ul class=\"pf-acct-ul\">{body}</ul>"
        f"</div>"
    )


def _gate_html(checklist: AccountOpsChecklist) -> str:
    chips = []
    for s in checklist.gate_steps:
        cls = {
            GATE_PASS: "pf-gate-pass",
            GATE_HOLD: "pf-gate-hold",
            GATE_FAIL: "pf-gate-fail",
        }.get(s.status, "pf-gate-hold")
        mark = {"pass": "O", "hold": "△", "fail": "X"}.get(s.status, "△")
        chips.append(
            f'<span class="pf-gate-chip {cls}" title="{escape(s.detail_ko)}">'
            f"{escape(mark)} {escape(s.label_ko)}</span>"
        )
    aux_html = ""
    if checklist.aux is not None:
        from alpha_system.ui.services.contrarian_soft_aux import aux_meters_html

        aux_html = aux_meters_html(checklist.aux)
    return (
        '<div class="pf-acct-gate">'
        f'<div class="pf-acct-gate-line">{escape(checklist.gate_line_ko)}</div>'
        f'<div class="pf-acct-gate-chips">{"".join(chips)}</div>'
        f"{aux_html}"
        "</div>"
    )


def account_ops_checklist_html(checklist: AccountOpsChecklist) -> str:
    """유니버스용 HTML."""
    pen_b = float(
        checklist.account_budget_pct.get(
            ACCOUNT_PENSION, ACCOUNT_BUDGET_PCT[ACCOUNT_PENSION]
        )
    )
    tax_b = float(
        checklist.account_budget_pct.get(
            ACCOUNT_TAXABLE, ACCOUNT_BUDGET_PCT[ACCOUNT_TAXABLE]
        )
    )
    style = (
        "<style>"
        ".pf-acct-ops{margin:0.6rem 0 0.85rem;padding:0.55rem 0.65rem;"
        "border:1px solid #d8dee8;border-radius:6px;background:#f7f9fc}"
        ".pf-acct-ops-k{font-weight:700;margin-bottom:0.35rem}"
        ".pf-acct-row{display:flex;gap:0.75rem;flex-wrap:wrap}"
        ".pf-acct-col{flex:1 1 14rem;min-width:12rem}"
        ".pf-acct-h{font-weight:650;margin-bottom:0.25rem}"
        ".pf-acct-ul{margin:0;padding-left:1.1rem}"
        ".pf-acct-ul li{margin:0.25rem 0}"
        ".pf-acct-gate{margin-top:0.55rem;padding-top:0.45rem;"
        "border-top:1px dashed #c5cedb}"
        ".pf-acct-gate-line{font-weight:600;margin-bottom:0.3rem}"
        ".pf-gate-chip{display:inline-block;margin:0.15rem 0.25rem 0 0;"
        "padding:0.12rem 0.4rem;border-radius:4px;font-size:0.85rem}"
        ".pf-gate-pass{background:#d8f0d8;color:#1a5c1a}"
        ".pf-gate-hold{background:#fff3cd;color:#6b5200}"
        ".pf-gate-fail{background:#f8d4d4;color:#7a1f1f}"
        ".pf-acct-tip{margin-top:0.4rem;font-size:0.85rem;color:#556}"
        "</style>"
    )
    return (
        f'<div class="pf-acct-ops" role="region">'
        f"{style}"
        '<div class="pf-acct-ops-k">오늘 계좌별 할 일 · 역발상 Soft 게이트</div>'
        '<div class="pf-acct-row">'
        + _items_html(
            ACCOUNT_LABEL_KO[ACCOUNT_PENSION],
            checklist.pension_items,
            pen_b,
        )
        + _items_html(
            ACCOUNT_LABEL_KO[ACCOUNT_TAXABLE],
            checklist.taxable_items,
            tax_b,
        )
        + "</div>"
        + _gate_html(checklist)
        + f'<div class="pf-acct-tip">{escape(checklist.note_ko)}</div>'
        "</div>"
    )


__all__ = [
    "ACCOUNT_BUDGET_PCT",
    "AccountOpsChecklist",
    "ChecklistItem",
    "ContrarianGateStep",
    "DAY_BUY_CAP_PCT",
    "account_ops_checklist_html",
    "build_account_ops_checklist",
    "build_account_todos",
    "build_contrarian_gate_steps",
]
