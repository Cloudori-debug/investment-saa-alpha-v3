"""기업해부(박홍기) · 저PBR 관찰 데스크 — 포트폴리오 부착 (Review-only).

알파 Soft/QVM과 점수 합산 금지 · target 불변.
시작하기.html · 내조사 초안은 로컬 기업해부 폴더로 연다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any, Sequence

from alpha_system.proposal_chart import norm_ticker
from alpha_system.screen_book import normalize_market

# Soft×보유 교차 → 오늘 매매 Review (점수·target 불변)
PORT_MAINTAIN = "maintain"
PORT_BUY_REVIEW = "buy_review"
PORT_SELL_REVIEW = "sell_review"
PORT_PARK = "park"

PORT_ACTION_KO = {
    PORT_MAINTAIN: "유지·해부확인",
    PORT_BUY_REVIEW: "사 Review",
    PORT_SELL_REVIEW: "팔 Review",
    PORT_PARK: "대기·파킹",
}

PORT_ACTION_HINT = {
    PORT_MAINTAIN: "Soft∩보유 · 해부만 보강 · Soft 점수 불변",
    PORT_BUY_REVIEW: "Soft 제안만 · 해부 PASS 후 하루≤33% · target 사람만",
    PORT_SELL_REVIEW: "보유만·Soft 밖 · 전량/환금 Review",
    PORT_PARK: "Soft·보유 둘 다 아님 · Soft 될 때까지 편입 금지",
}

OBSERVE_REL = Path("data") / "local"
DEFAULT_GIEOP_ROOT = Path(r"C:\Cursor\investment\Gieop_Haebu_R4_3")
PATHS_REL = Path("data") / "local" / "gieop_paths.json"


@dataclass(frozen=True)
class GieopPathBundle:
    root: Path
    start_html: Path
    drafts_dir: Path

    @property
    def start_ok(self) -> bool:
        return self.start_html.is_file()

    @property
    def drafts_ok(self) -> bool:
        return self.drafts_dir.is_dir()


@dataclass
class ObserveUiRow:
    ticker: str
    name: str
    tier: str
    observe_score: int
    judgment_ko: str
    next_action_ko: str
    pbr_press: float | None
    pass_value: bool
    crash_flag: bool
    in_soft: bool
    gics: str = ""


@dataclass
class GieopObserveUiBoard:
    available: bool
    market: str
    as_of: str
    model_version: str
    counts: dict[str, int] = field(default_factory=dict)
    deep_pick: list[ObserveUiRow] = field(default_factory=list)
    watch_top: list[ObserveUiRow] = field(default_factory=list)
    note: str = ""
    path: str = ""


@dataclass(frozen=True)
class PortfolioBridgeRow:
    ticker: str
    name: str
    tier: str
    in_soft: bool
    in_held: bool
    port_action: str
    action_ko: str
    hint_ko: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "tier": self.tier,
            "in_soft": self.in_soft,
            "in_held": self.in_held,
            "port_action": self.port_action,
            "action_ko": self.action_ko,
            "hint_ko": self.hint_ko,
        }


@dataclass
class PortfolioBridgeBoard:
    rows: list[PortfolioBridgeRow] = field(default_factory=list)
    n_buy: int = 0
    n_maintain: int = 0
    n_sell: int = 0
    n_park: int = 0
    review_only: bool = True
    writes_target: bool = False

    def summary_line_ko(self) -> str:
        if not self.rows:
            return "기업해부 심층 × Soft: 심층 후보 없음"
        return (
            f"기업해부 심층 × Soft: 사 {self.n_buy} · 유지 {self.n_maintain} · "
            f"팔 {self.n_sell} · 대기 {self.n_park}"
        )


def classify_port_action(*, in_soft: bool, in_held: bool) -> str:
    """Soft×보유 → port_action · Soft/QVM 점수와 무관."""
    if in_soft and in_held:
        return PORT_MAINTAIN
    if in_soft and not in_held:
        return PORT_BUY_REVIEW
    if (not in_soft) and in_held:
        return PORT_SELL_REVIEW
    return PORT_PARK


def build_portfolio_bridge(
    deep_pick: Sequence[ObserveUiRow],
    *,
    soft_tickers: Sequence[str] | None = None,
    held_tickers: Sequence[str] | None = None,
) -> PortfolioBridgeBoard:
    soft = {
        norm_ticker(t)
        for t in (soft_tickers or [])
        if norm_ticker(t) and norm_ticker(t) != "000000"
    }
    held = {
        norm_ticker(t)
        for t in (held_tickers or [])
        if norm_ticker(t) and norm_ticker(t) != "000000"
    }
    rows: list[PortfolioBridgeRow] = []
    n_buy = n_maintain = n_sell = n_park = 0
    for r in deep_pick:
        tk = norm_ticker(r.ticker)
        if not tk:
            continue
        in_soft = tk in soft
        in_held = tk in held
        action = classify_port_action(in_soft=in_soft, in_held=in_held)
        if action == PORT_BUY_REVIEW:
            n_buy += 1
        elif action == PORT_MAINTAIN:
            n_maintain += 1
        elif action == PORT_SELL_REVIEW:
            n_sell += 1
        else:
            n_park += 1
        rows.append(
            PortfolioBridgeRow(
                ticker=tk,
                name=str(r.name or tk),
                tier=str(r.tier or ""),
                in_soft=in_soft,
                in_held=in_held,
                port_action=action,
                action_ko=PORT_ACTION_KO.get(action, action),
                hint_ko=PORT_ACTION_HINT.get(action, ""),
            )
        )
    return PortfolioBridgeBoard(
        rows=rows,
        n_buy=n_buy,
        n_maintain=n_maintain,
        n_sell=n_sell,
        n_park=n_park,
    )


def portfolio_bridge_html(bridge: PortfolioBridgeBoard) -> str:
    """심층 × Soft×보유 교차표 · target 쓰기 없음."""
    if not bridge.rows:
        return (
            '<div class="pf-gieop-bridge">'
            '<div class="pf-gieop-watch-title">포트 연결</div>'
            '<p class="pf-gieop-idle">심층 후보 없음 · 관찰 갱신 후 Soft×보유 교차</p>'
            "</div>"
        )
    body = ""
    for r in bridge.rows:
        soft_ko = "예" if r.in_soft else "아니오"
        held_ko = "예" if r.in_held else "아니오"
        body += (
            "<tr>"
            f"<td>{_esc(r.name)}</td><td>{_esc(r.ticker)}</td>"
            f"<td>{_esc(r.tier)}</td>"
            f"<td>{soft_ko}</td><td>{held_ko}</td>"
            f"<td><span class='pf-gieop-tag pf-gieop-act-{_esc(r.port_action)}'>"
            f"{_esc(r.action_ko)}</span></td>"
            f"<td>{_esc(r.hint_ko)}</td>"
            "</tr>"
        )
    return (
        '<div class="pf-gieop-bridge">'
        '<div class="pf-gieop-watch-title">포트 연결 · Soft×보유 → 팔·유지·사 Review</div>'
        f'<div class="pf-gieop-counts">{_esc(bridge.summary_line_ko())}</div>'
        '<table class="pf-gieop-table"><thead><tr>'
        "<th>종목</th><th>코드</th><th>티어</th><th>Soft</th><th>보유</th>"
        "<th>할 일</th><th>힌트</th>"
        "</tr></thead><tbody>"
        f"{body}</tbody></table>"
        '<p class="pf-gieop-note">Review-only · Soft·target 자동기입 없음 · 주문은 사람·HTS</p>'
        "</div>"
    )


def resolve_gieop_paths(root: Path) -> GieopPathBundle:
    """로컬 기업해부 루트 · data/local/gieop_paths.json 으로 덮어쓰기 가능."""
    base = DEFAULT_GIEOP_ROOT
    cfg = Path(root) / PATHS_REL
    if cfg.is_file():
        try:
            raw = json.loads(cfg.read_text(encoding="utf-8"))
            cand = Path(str(raw.get("gieop_root") or "")).expanduser()
            if cand.is_dir():
                base = cand
        except Exception:  # noqa: BLE001
            pass
    return GieopPathBundle(
        root=base,
        start_html=base / "시작하기.html",
        drafts_dir=base / "내조사",
    )


def observe_json_path(root: Path, market: str) -> Path:
    mkt = normalize_market(market) or "KOSPI"
    mkt_u = str(mkt).upper()
    if not mkt_u.startswith("KOS"):
        mkt_u = "KOSPI"
    return Path(root) / OBSERVE_REL / f"krx_low_pbr_observe_{mkt_u}.json"


def _row_from_dict(d: dict[str, Any]) -> ObserveUiRow | None:
    tk = norm_ticker(d.get("ticker"))
    if not tk:
        return None
    pbr = d.get("pbr_press")
    try:
        pbr_f = float(pbr) if pbr not in (None, "") else None
    except (TypeError, ValueError):
        pbr_f = None
    return ObserveUiRow(
        ticker=tk,
        name=str(d.get("name") or tk),
        tier=str(d.get("tier") or ""),
        observe_score=int(d.get("observe_score") or 0),
        judgment_ko=str(d.get("judgment_ko") or ""),
        next_action_ko=str(d.get("next_action_ko") or ""),
        pbr_press=pbr_f,
        pass_value=bool(d.get("pass_value")),
        crash_flag=bool(d.get("crash_flag")),
        in_soft=bool(d.get("in_soft")),
        gics=str(d.get("gics") or ""),
    )


def load_observe_ui_board(root: Path, *, market: str = "KOSPI") -> GieopObserveUiBoard:
    path = observe_json_path(root, market)
    if not path.is_file():
        mkt = normalize_market(market) or "KOSPI"
        return GieopObserveUiBoard(
            available=False,
            market=str(mkt).upper(),
            as_of="",
            model_version="",
            note="관찰 보드 없음 · 아래「저PBR 관찰 갱신」실행",
            path=str(path),
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return GieopObserveUiBoard(
            available=False,
            market="KOSPI",
            as_of="",
            model_version="",
            note="관찰 JSON 읽기 실패",
            path=str(path),
        )
    deep: list[ObserveUiRow] = []
    for item in raw.get("deep_pick") or []:
        if isinstance(item, dict):
            r = _row_from_dict(item)
            if r:
                deep.append(r)
    watch: list[ObserveUiRow] = []
    for item in raw.get("rows") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("tier") or "") != "정밀관찰":
            continue
        r = _row_from_dict(item)
        if r:
            watch.append(r)
        if len(watch) >= 8:
            break
    counts = raw.get("counts") if isinstance(raw.get("counts"), dict) else {}
    return GieopObserveUiBoard(
        available=True,
        market=str(raw.get("market") or "KOSPI"),
        as_of=str(raw.get("as_of") or ""),
        model_version=str(raw.get("model_version") or ""),
        counts={str(k): int(v) for k, v in counts.items()},
        deep_pick=deep,
        watch_top=watch,
        note=str(raw.get("note") or ""),
        path=str(path),
    )


def refresh_observe_board(
    root: Path,
    *,
    market: str = "KOSPI",
    soft_tickers: Sequence[str] | None = None,
    write_drafts: bool = True,
) -> GieopObserveUiBoard:
    from alpha_system.review.krx_low_pbr_observe import (
        build_observe_board,
        save_board,
        write_deep_drafts,
    )

    paths = resolve_gieop_paths(root)
    board = build_observe_board(
        root,
        market=market,
        soft_tickers=soft_tickers or [],
        deep_pick_n=3,
    )
    save_board(board, root)
    if write_drafts and paths.drafts_ok:
        tmpl = Path(r"C:\Users\이동준\Downloads\이름 없는 조사_기준일미정_수정1.json")
        write_deep_drafts(
            board,
            dest_dir=paths.drafts_dir,
            template_path=tmpl if tmpl.is_file() else None,
        )
    return load_observe_ui_board(root, market=market)


def open_path(target: Path) -> str:
    """Windows에서 파일/폴더 열기 · 실패 시 경로 문자열 반환."""
    target = Path(target)
    try:
        os.startfile(str(target))  # type: ignore[attr-defined]
        return ""
    except AttributeError:
        return str(target)
    except OSError as exc:
        return f"{target} · {exc}"


def _esc(v: object) -> str:
    return escape(str(v or ""), quote=True)


def observe_board_html(board: GieopObserveUiBoard) -> str:
    if not board.available:
        return (
            f'<div class="pf-gieop-block"><p class="pf-gieop-idle">'
            f"{_esc(board.note)}</p></div>"
        )
    count_bits = " · ".join(
        f"{_esc(k)} {int(v)}" for k, v in sorted(board.counts.items())
    )
    cards: list[str] = []
    for r in board.deep_pick:
        tags = []
        if r.pass_value:
            tags.append("논리가치")
        if r.in_soft:
            tags.append("Soft")
        if r.crash_flag:
            tags.append("낙폭주의")
        if r.pbr_press is not None:
            tags.append(f"공표PBR {r.pbr_press:.2f}")
        tag_html = "".join(
            f'<span class="pf-gieop-tag">{_esc(t)}</span>' for t in tags
        )
        cards.append(
            "<div class='pf-gieop-card pf-gieop-deep'>"
            f"<div class='pf-gieop-head'><span class='pf-gieop-tier'>{_esc(r.tier)}</span>"
            f"<span class='pf-gieop-name'>{_esc(r.name)}</span>"
            f"<span class='pf-gieop-tk'>{_esc(r.ticker)}</span></div>"
            f"<div class='pf-gieop-tags'>{tag_html}</div>"
            f"<p class='pf-gieop-judge'>{_esc(r.judgment_ko)}</p>"
            f"<p class='pf-gieop-next'>{_esc(r.next_action_ko)}</p>"
            "</div>"
        )
    watch_rows = ""
    for r in board.watch_top:
        watch_rows += (
            "<tr>"
            f"<td>{_esc(r.name)}</td><td>{_esc(r.ticker)}</td>"
            f"<td>{int(r.observe_score)}</td>"
            f"<td>{_esc((r.judgment_ko or '')[:48])}</td>"
            "</tr>"
        )
    watch_tbl = ""
    if watch_rows:
        watch_tbl = (
            "<div class='pf-gieop-watch'>"
            "<div class='pf-gieop-watch-title'>정밀관찰 상위</div>"
            "<table class='pf-gieop-table'><thead><tr>"
            "<th>종목</th><th>코드</th><th>점수</th><th>판단</th>"
            "</tr></thead><tbody>"
            f"{watch_rows}</tbody></table></div>"
        )
    return (
        f'<div class="pf-gieop-block">'
        f'<div class="pf-gieop-meta">{_esc(board.market)} · as_of {_esc(board.as_of)}'
        f" · {_esc(board.model_version)}</div>"
        f'<div class="pf-gieop-counts">{count_bits}</div>'
        f'<div class="pf-gieop-grid">{"".join(cards)}</div>'
        f"{watch_tbl}"
        f'<p class="pf-gieop-note">{_esc(board.note)}</p>'
        "</div>"
    )


def run_observe_pipe(
    root: Path,
    *,
    market: str,
    soft_rows: Sequence[object] | None = None,
    soft_tickers: Sequence[str] | None = None,
    held_tickers: Sequence[str] | None = None,
) -> dict[str, Any]:
    """저PBR 갱신 → 알파 시드 → 정량커버 · Soft·target 불변."""
    from alpha_system.ui.services.gieop_alpha_seed import (
        collect_alpha_gieop_candidates,
        seed_alpha_to_gieop,
    )
    from alpha_system.ui.services.gieop_fusion_desk import refresh_quant_on_drafts

    soft_tks = [
        norm_ticker(t)
        for t in (soft_tickers or ())
        if norm_ticker(t)
    ]
    if not soft_tks:
        soft_tks = [
            norm_ticker(getattr(r, "ticker", None))
            for r in (soft_rows or ())
            if norm_ticker(getattr(r, "ticker", None))
        ]
    held_tks = [
        norm_ticker(t)
        for t in (held_tickers or ())
        if norm_ticker(t)
    ]
    refresh_observe_board(
        root,
        market=market,
        soft_tickers=soft_tks,
        write_drafts=True,
    )
    seeded = seed_alpha_to_gieop(
        Path(root),
        market=market,
        soft_rows=list(soft_rows or []),
        held_tickers=held_tks,
        include_value_only=True,
        value_only_max=5,
    )
    alpha_board = collect_alpha_gieop_candidates(
        Path(root),
        market=market,
        soft_rows=list(soft_rows or []),
        held_tickers=held_tks,
        include_value_only=True,
        value_only_max=5,
    )
    qres = refresh_quant_on_drafts(
        Path(root),
        market=market,
        candidates=alpha_board.candidates,
    )
    return {
        "seed_new": len(seeded.written),
        "seed_skip": len(seeded.skipped),
        "quant_n": len(qres.get("updated") or []),
        "quant_hi": qres.get("n_hi", 0),
        "quant_mid": qres.get("n_mid", 0),
        "quant_lo": qres.get("n_lo", 0),
    }

