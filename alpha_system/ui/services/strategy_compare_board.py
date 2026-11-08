"""전략 비교 카탈로그 · Lab KPI 집계 (Review-only · target 불변)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from alpha_system.shadow.household_alloc_lab import load_recipes, load_report


@dataclass(frozen=True)
class StrategyCard:
    id: str
    group: str  # individual | momentum | static
    label: str
    what: str
    rules: str
    dont: str
    universe: str
    source: str = ""
    composition: tuple[str, ...] = ()
    # kpi
    cagr: float | None = None
    max_drawdown: float | None = None
    total_ret: float | None = None
    n_days: int = 0
    kpi_note: str = ""
    kpi_ok: bool = False
    # False = 개별주 Soft 등 · ETF Lab CAGR과 나란히 순위 매기지 않음
    comparable: bool = True


@dataclass
class StrategyCompareBoard:
    cards: list[StrategyCard] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    report_as_of: str = ""
    writes_target: bool = False
    review_only: bool = True


_SOFT_WHAT = (
    "개별주 계량(퀀트) · Q/V Soft 통과분만 제안. "
    "감·애널 추종이 아니라 바닥·유동성 규칙."
)
_SOFT_RULES = (
    "중기 Lab floors_equal_wide · r6/r1 바닥 · top_n · "
    "월(주) 리밸 Shadow · Core에 score_m 없음."
)
_SOFT_DONT = "올웨더·듀얼과 비중 합산 집행 금지 · target 자동·자동주문 없음."

_SHORT_WHAT = (
    "알파 안 모멘텀 퀀트 위성 · 가계 전량 동적배분(DAA) 대체가 아님."
)
_SHORT_RULES = "60일∧120일 추세 · score_m · 단기 장부 분리 · 중기 Core 불변."
_SHORT_DONT = "중기 Soft에 score_m 혼합 · 단기→중기 전량 이관 금지."

_DUAL_WHAT = (
    "Antonacci GEM 정석 근사 · 12M 상대→절대로 ETF 전량 교체."
)
_DUAL_RULES = (
    "월 리밸 · 상대(미국 vs EAFE) 승자 → "
    "절대(승자>달러단기)면 승자 · 아니면 미종합채 · 국내 ETF 대리."
)
_DUAL_DONT = (
    "코스피/유로50단독/배당30 · 레버리지 · Soft와 한 점수 합산 · target 기입."
)


def _pct_pair(cagr: float | None, mdd: float | None) -> str:
    if cagr is None and mdd is None:
        return "—"
    c = "—" if cagr is None else f"{100.0 * float(cagr):+.1f}%"
    m = "—" if mdd is None else f"{100.0 * float(mdd):.1f}%"
    return f"{c} / {m}"


def _soft_ref_kpi(total: float | None, mdd: float | None, n_days: int) -> str:
    """총수익·MDD·표본일만 · 연율 CAGR 표기 금지."""
    if total is None and mdd is None:
        return "—"
    t = "—" if total is None else f"총수익 {100.0 * float(total):+.1f}%"
    m = "—" if mdd is None else f"MDD {100.0 * float(mdd):.1f}%"
    d = f"{n_days}일" if n_days else "표본—"
    return f"{t} · {m} · {d} · 비교금지"


def _load_strategy_yaml(root: Path) -> dict[str, Any]:
    path = Path(root) / "data" / "strategy_portfolio.yaml"
    if not path.is_file():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _soft_card(root: Path) -> StrategyCard:
    y = _load_strategy_yaml(root)
    mid = y.get("mid") if isinstance(y.get("mid"), dict) else {}
    kpi = mid.get("kpi") if isinstance(mid.get("kpi"), dict) else {}
    total = kpi.get("total_net_ret")
    mdd = kpi.get("max_drawdown")
    n_days = int(kpi.get("n_days") or 0)
    label = str(mid.get("label") or "floors_equal_wide")
    # Soft는 ETF Lab과 기간·유니버스가 다름 → CAGR 연율화·순위 비교 금지
    ok = total is not None and mdd is not None
    op = mid.get("operating") if isinstance(mid.get("operating"), dict) else {}
    top_n = mid.get("top_n") if mid.get("top_n") is not None else op.get("top_n")
    base_note = str(kpi.get("note") or "strategy_portfolio mid.kpi · 개별주 Soft Lab")
    return StrategyCard(
        id="mid_soft",
        group="individual",
        label=f"중기 Soft · {label}",
        what=_SOFT_WHAT,
        rules=_SOFT_RULES,
        dont=_SOFT_DONT,
        universe="코스피/코스닥 개별주 · Soft 통과분",
        source=str(mid.get("engine") or "qv_soft"),
        composition=(
            "포트폴리오 › 오늘 매매 › 중기 Soft 제안",
            f"top_n={top_n}",
            f"r6={mid.get('r6_floor')} · r1={mid.get('r1_floor')}",
        ),
        cagr=None,
        max_drawdown=float(mdd) if mdd is not None else None,
        total_ret=float(total) if total is not None else None,
        n_days=n_days,
        kpi_note=(
            f"{base_note} · ETF Lab과 비교금지(짧은 표본·개별주)"
        ),
        kpi_ok=ok,
        comparable=False,
    )


def _short_card(root: Path) -> StrategyCard:
    y = _load_strategy_yaml(root)
    short = y.get("short") if isinstance(y.get("short"), dict) else {}
    # optional local short lab report
    cagr = mdd = total = None
    n_days = 0
    note = str(short.get("note") or "")
    ok = False
    for rel in (
        Path("data") / "local" / "short_profit_lab_report.json",
        Path("data") / "shadow_short_profit_lab_report.json",
    ):
        path = Path(root) / rel
        if not path.is_file():
            continue
        try:
            import json

            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(raw, dict):
            continue
        total = raw.get("total_net_ret")
        mdd = raw.get("max_drawdown")
        n_days = int(raw.get("n_days") or 0)
        ok = total is not None
        note = str(raw.get("note") or note or "short lab report")
        break
    return StrategyCard(
        id="short_momentum",
        group="momentum",
        label="단기 모멘텀 위성",
        what=_SHORT_WHAT,
        rules=_SHORT_RULES,
        dont=_SHORT_DONT,
        universe="단기 장부 · score_m 위성",
        source=str(short.get("engine") or "short_trend_60_120_score_m"),
        composition=(
            "포트 › 단기 모멘텀 접기",
            "60∧120 · score_m",
        ),
        cagr=None,
        max_drawdown=float(mdd) if mdd is not None else None,
        total_ret=float(total) if total is not None else None,
        n_days=n_days,
        kpi_note=(
            f"{note} · ETF Lab과 비교금지"
            if note
            else "단기 Lab 리포트 없으면 KPI 공란 · ETF와 비교금지"
        ),
        kpi_ok=ok,
        comparable=False,
    )


def _household_cards(root: Path) -> list[StrategyCard]:
    try:
        recipes = load_recipes(root)
    except (OSError, ValueError):
        return []
    report = load_report(root) or {}
    by_id: dict[str, dict[str, Any]] = {}
    for row in report.get("strategies") or []:
        if isinstance(row, dict) and row.get("id"):
            by_id[str(row["id"])] = row
    out: list[StrategyCard] = []
    for st in recipes.get("strategies") or []:
        if not isinstance(st, dict):
            continue
        sid = str(st.get("id") or "")
        kind = str(st.get("kind") or "")
        name = str(st.get("name_ko") or sid)
        source = str(st.get("source") or "")
        if kind == "dual_momentum":
            group = "momentum"
            what, rules, dont = _DUAL_WHAT, _DUAL_RULES, _DUAL_DONT
            comp = [
                f"공격 {o.get('name')} ({o.get('ticker')})"
                for o in (st.get("offensive") or [])
                if isinstance(o, dict)
            ]
            comp.append(f"현금 {st.get('cash_name')} ({st.get('cash_ticker')})")
            comp.append(f"안전 {st.get('safe_name')} ({st.get('safe_ticker')})")
            universe = "국내 상장 ETF · 듀얼모멘텀 근사"
        else:
            group = "static"
            what = "정적 배분(규칙 퀀트) · 비중 고정 후 정기 리밸."
            rules = f"리밸 {st.get('rebalance') or 'annual_jan'} · 국내 ETF 차용."
            dont = "레버리지·인버스 · Soft와 합산 집행 · target 자동."
            comp = [
                f"{sl.get('pct')}% {sl.get('name')} ({sl.get('ticker')})"
                for sl in (st.get("sleeves") or [])
                if isinstance(sl, dict)
            ]
            universe = "국내 상장 ETF · 가계 본체 후보"
        row = by_id.get(sid) or {}
        out.append(
            StrategyCard(
                id=sid,
                group=group,
                label=name,
                what=what,
                rules=rules,
                dont=dont,
                universe=universe,
                source=source,
                composition=tuple(comp),
                cagr=row.get("cagr"),
                max_drawdown=row.get("max_drawdown"),
                total_ret=row.get("total_ret"),
                n_days=int(row.get("n_days") or 0),
                kpi_note=(
                    "가계 Lab 리포트"
                    if row.get("ok")
                    else str(row.get("reason") or "Lab 미실행 · 전략 비교에서 재계산")
                ),
                kpi_ok=bool(row.get("ok")),
            )
        )
    return out


def build_strategy_compare_board(root: Path) -> StrategyCompareBoard:
    root = Path(root)
    cards = [_soft_card(root), _short_card(root), *_household_cards(root)]
    report = load_report(root) or {}
    caveats = [
        "중기 Soft·단기(미산출)는 참고만 · ETF Lab CAGR과 순위 비교 금지",
        "비교 대상=국내 ETF 정적·듀얼모멘텀 Lab만",
        "Review-only · Soft·target 자동변경 없음",
        "가계 Lab은 국내 ETF 대리 · 원문 미국 성과와 다를 수 있음",
    ]
    for c in report.get("caveats") or []:
        if c and str(c) not in caveats:
            caveats.append(str(c))
    return StrategyCompareBoard(
        cards=cards,
        caveats=caveats,
        report_as_of=str(report.get("as_of") or ""),
        writes_target=False,
        review_only=True,
    )


def group_labels() -> dict[str, str]:
    return {
        "individual": "개별 퀀트",
        "momentum": "모멘텀 퀀트",
        "static": "정적 배분",
    }


def radio_options(board: StrategyCompareBoard) -> list[tuple[str, str]]:
    """(id, display label with group prefix)."""
    gl = group_labels()
    opts: list[tuple[str, str]] = []
    for c in board.cards:
        prefix = gl.get(c.group, c.group)
        opts.append((c.id, f"{prefix} · {c.label}"))
    return opts


def find_card(board: StrategyCompareBoard, sid: str) -> StrategyCard | None:
    for c in board.cards:
        if c.id == sid:
            return c
    return board.cards[0] if board.cards else None


def compare_table_rows(board: StrategyCompareBoard) -> list[dict[str, str]]:
    gl = group_labels()
    rows = []
    for c in board.cards:
        if not c.comparable:
            perf = _soft_ref_kpi(c.total_ret, c.max_drawdown, c.n_days)
            if c.id == "short_momentum" and not c.kpi_ok:
                perf = "—"
            kpi_lab = "참고·비교금지" if c.kpi_ok else "미산출"
        else:
            perf = _pct_pair(c.cagr, c.max_drawdown)
            kpi_lab = "OK" if c.kpi_ok else "미산출"
        rows.append(
            {
                "구분": gl.get(c.group, c.group),
                "전략": c.label,
                "유니버스": c.universe.split("·")[0].strip(),
                "성과": perf,
                "KPI": kpi_lab,
                "비고": (c.kpi_note or "")[:72],
            }
        )
    return rows


def _card_kpi_bits(card: StrategyCard) -> tuple[str, str, str]:
    """(kpi_text, kpi_title, chip_class)."""
    if card.comparable:
        return (
            _pct_pair(card.cagr, card.max_drawdown),
            "Lab CAGR / MDD",
            "pf-sc-chip-ok" if card.kpi_ok else "pf-sc-chip-mute",
        )
    return (
        _soft_ref_kpi(card.total_ret, card.max_drawdown, card.n_days),
        "참고 · ETF와 비교금지",
        "pf-sc-chip-ref",
    )


def card_detail_html(card: StrategyCard) -> str:
    from html import escape

    def e(x: object) -> str:
        return escape(str(x or ""))

    comp = "".join(f"<li>{e(x)}</li>" for x in card.composition) or "<li>—</li>"
    kpi, kpi_title, _chip = _card_kpi_bits(card)
    return (
        '<div class="pf-strat-card">'
        f'<div class="pf-hh-k">{e(card.label)}</div>'
        f'<div class="pf-strat-sec"><b>무엇인가</b><p>{e(card.what)}</p></div>'
        f'<div class="pf-strat-sec"><b>규칙</b><p>{e(card.rules)}</p></div>'
        f'<div class="pf-strat-sec"><b>구성</b><ul>{comp}</ul></div>'
        f'<div class="pf-strat-sec"><b>{e(kpi_title)}</b>'
        f"<p>{e(kpi)} · {e(card.kpi_note)}</p></div>"
        f'<div class="pf-strat-sec"><b>하지 않음</b><p>{e(card.dont)}</p></div>'
        f'<div class="pf-hh-tip">출처 · {e(card.source)} · {e(card.universe)}</div>'
        "</div>"
    )


def card_tile_html(card: StrategyCard) -> str:
    """한눈 갤러리용 타일 · 탭/라디오 없이 전부 표시."""
    from html import escape

    def e(x: object) -> str:
        return escape(str(x or ""))

    gl = group_labels()
    kpi, kpi_title, chip_cls = _card_kpi_bits(card)
    chip = "비교가능" if card.comparable else "비교금지"
    status = "OK" if card.kpi_ok else "미산출"
    comp_bits = " · ".join(str(x) for x in card.composition[:4]) or "—"
    tone = {
        "individual": "pf-sc-tile-ind",
        "momentum": "pf-sc-tile-mom",
        "static": "pf-sc-tile-static",
    }.get(card.group, "")
    return (
        f'<article class="pf-sc-tile {tone}" data-id="{e(card.id)}">'
        f'<div class="pf-sc-tile-top">'
        f'<span class="pf-sc-group">{e(gl.get(card.group, card.group))}</span>'
        f'<span class="pf-sc-chip {chip_cls}">{e(chip)} · {e(status)}</span>'
        f"</div>"
        f'<h3 class="pf-sc-tile-title">{e(card.label)}</h3>'
        f'<div class="pf-sc-kpi" title="{e(kpi_title)}">{e(kpi)}</div>'
        f'<p class="pf-sc-what">{e(card.what)}</p>'
        f'<div class="pf-sc-block"><b>규칙</b><span>{e(card.rules)}</span></div>'
        f'<div class="pf-sc-block"><b>구성</b><span>{e(comp_bits)}</span></div>'
        f'<div class="pf-sc-block pf-sc-dont"><b>하지 않음</b>'
        f"<span>{e(card.dont)}</span></div>"
        f'<div class="pf-sc-foot">{e(card.universe)}</div>'
        "</article>"
    )


def compare_overview_html(board: StrategyCompareBoard) -> str:
    """순위·참고를 한 표로 · Soft는 비교금지 표시."""
    from html import escape

    def e(x: object) -> str:
        return escape(str(x or ""))

    rows = compare_table_rows(board)
    if not rows:
        return (
            '<div class="pf-sc-overview pf-sc-overview-empty">'
            "전략 없음"
            "</div>"
        )
    body = []
    for r in rows:
        ref = "pf-sc-row-ref" if "비교금지" in str(r.get("KPI") or "") or "비교금지" in str(
            r.get("성과") or ""
        ) else ""
        body.append(
            f'<tr class="{ref}">'
            f'<td>{e(r.get("구분"))}</td>'
            f'<td class="pf-sc-td-name">{e(r.get("전략"))}</td>'
            f'<td>{e(r.get("유니버스"))}</td>'
            f'<td class="pf-sc-td-perf">{e(r.get("성과"))}</td>'
            f'<td>{e(r.get("KPI"))}</td>'
            f'<td class="pf-sc-td-note">{e(r.get("비고"))}</td>'
            f"</tr>"
        )
    asof = f' · Lab as_of {e(board.report_as_of)}' if board.report_as_of else ""
    return (
        '<div class="pf-sc-overview" role="region" aria-label="전략 한눈 비교">'
        '<div class="pf-sc-overview-h">'
        f"<span>한눈 비교표{asof}</span>"
        '<span class="pf-sc-overview-hint">'
        "회색 행=Soft·단기 참고(순위 단정 금지) · 나머지=ETF Lab"
        "</span>"
        "</div>"
        '<div class="pf-sc-table-wrap">'
        '<table class="pf-sc-table">'
        "<thead><tr>"
        "<th>구분</th><th>전략</th><th>유니버스</th>"
        "<th>성과</th><th>KPI</th><th>비고</th>"
        "</tr></thead>"
        f'<tbody>{"".join(body)}</tbody>'
        "</table></div></div>"
    )


def strategy_gallery_html(board: StrategyCompareBoard) -> str:
    """그룹별 타일 그리드 · 모드 전환 없음."""
    from html import escape

    gl = group_labels()
    order = ("individual", "momentum", "static")
    by: dict[str, list[StrategyCard]] = {k: [] for k in order}
    for c in board.cards:
        by.setdefault(c.group, []).append(c)
    sections: list[str] = []
    for g in order:
        cards = by.get(g) or []
        if not cards:
            continue
        tiles = "".join(card_tile_html(c) for c in cards)
        sections.append(
            f'<section class="pf-sc-sec" aria-label="{escape(gl.get(g, g))}">'
            f'<div class="pf-sc-sec-h">{escape(gl.get(g, g))} · {len(cards)}</div>'
            f'<div class="pf-sc-grid">{tiles}</div>'
            f"</section>"
        )
    # leftover groups
    for g, cards in by.items():
        if g in order or not cards:
            continue
        tiles = "".join(card_tile_html(c) for c in cards)
        sections.append(
            f'<section class="pf-sc-sec">'
            f'<div class="pf-sc-sec-h">{escape(g)} · {len(cards)}</div>'
            f'<div class="pf-sc-grid">{tiles}</div>'
            f"</section>"
        )
    if not sections:
        return '<div class="pf-sc-gallery-empty">전략 카드 없음</div>'
    return (
        '<div class="pf-sc-gallery" role="region" aria-label="전략 카드 전부">'
        + "".join(sections)
        + "</div>"
    )


__all__ = [
    "StrategyCard",
    "StrategyCompareBoard",
    "build_strategy_compare_board",
    "card_detail_html",
    "card_tile_html",
    "compare_overview_html",
    "compare_table_rows",
    "find_card",
    "group_labels",
    "radio_options",
    "strategy_gallery_html",
]
