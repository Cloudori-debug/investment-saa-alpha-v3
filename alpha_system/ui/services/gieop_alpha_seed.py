"""알파 투자 후보 → 기업해부(박홍기) 능동 평가 시드 (Review-only).

Soft 제안·논리가치 통과분을 기업해부 초안으로 보낸다.
Soft/QVM 점수·target_portfolio 자동기입 없음.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Sequence

from alpha_system.proposal_chart import norm_ticker
from alpha_system.screen_book import normalize_market
from alpha_system.ui.services.gieop_observe_board import (
    resolve_gieop_paths,
)

MODEL_VERSION = "gieop-alpha-seed-v1"
OUT_REL = Path("data") / "local"
TEMPLATE_DEFAULT = Path(
    r"C:\Users\이동준\Downloads\이름 없는 조사_기준일미정_수정1.json"
)

SRC_SOFT = "soft"
SRC_SOFT_VALUE = "soft_value"
SRC_VALUE = "value_only"
SRC_HELD_SOFT = "held_soft"

SRC_KO = {
    SRC_SOFT: "Soft제안",
    SRC_SOFT_VALUE: "Soft∩논리가치",
    SRC_VALUE: "논리가치만",
    SRC_HELD_SOFT: "보유∩Soft",
}


@dataclass(frozen=True)
class AlphaGieopCandidate:
    ticker: str
    name: str
    sector: str
    source: str
    logic_label_ko: str
    in_soft: bool
    in_held: bool
    pass_value: bool
    market_cap: float | None = None

    @property
    def source_ko(self) -> str:
        return SRC_KO.get(self.source, self.source)


@dataclass
class AlphaGieopSeedBoard:
    market: str
    as_of: str
    candidates: list[AlphaGieopCandidate] = field(default_factory=list)
    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    note: str = (
        "알파 후보 → 기업해부 초안 · Soft·target 불변 · Review-only"
    )
    writes_target: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "as_of": self.as_of,
            "model_version": MODEL_VERSION,
            "evaluated_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "n_candidates": len(self.candidates),
            "candidates": [
                {
                    "ticker": c.ticker,
                    "name": c.name,
                    "sector": c.sector,
                    "source": c.source,
                    "source_ko": c.source_ko,
                    "logic_label_ko": c.logic_label_ko,
                    "in_soft": c.in_soft,
                    "in_held": c.in_held,
                    "pass_value": c.pass_value,
                    "market_cap": c.market_cap,
                }
                for c in self.candidates
            ],
            "written": list(self.written),
            "skipped": list(self.skipped),
            "note": self.note,
            "writes_target": False,
            "charter": {
                "proposal_mode": "pure_qvm",
                "target_portfolio_written": False,
                "soft_score_unchanged": True,
            },
        }


def _clean(raw: object) -> str:
    return str(raw or "").strip()


def _load_tasks(template_path: Path | None) -> list[dict[str, Any]]:
    path = Path(template_path) if template_path else TEMPLATE_DEFAULT
    if path.is_file():
        try:
            tasks = json.loads(path.read_text(encoding="utf-8")).get("tasks")
            if isinstance(tasks, list) and tasks:
                return list(tasks)
        except Exception:  # noqa: BLE001
            pass
    return [
        {
            "id": f"P{i:02d}",
            "status": "NOT_STARTED",
            "reason": "",
            "source_ids": [],
            "fact_ids": [],
            "calculation_ids": [],
            "counterevidence": "",
            "next_action": "",
            "review_required": False,
        }
        for i in range(1, 51)
    ]


def _existing_draft_tickers(dest_dir: Path) -> set[str]:
    """내조사 파일명·project_id에서 이미 시드된 티커."""
    out: set[str] = set()
    if not dest_dir.is_dir():
        return out
    for p in dest_dir.glob("*.json"):
        stem = p.stem
        # …_005880_기준일… / PROJECT-…-005880
        for part in stem.replace("-", "_").split("_"):
            if part.isdigit() and len(part) == 6:
                out.add(part)
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            meta = raw.get("meta") if isinstance(raw, dict) else None
            if isinstance(meta, dict):
                tk = norm_ticker(meta.get("ticker"))
                if tk:
                    out.add(tk)
            pid = str(raw.get("project_id") or "") if isinstance(raw, dict) else ""
            for part in pid.replace("-", "_").split("_"):
                if part.isdigit() and len(part) == 6:
                    out.add(part)
        except Exception:  # noqa: BLE001
            continue
    return out


def collect_alpha_gieop_candidates(
    root: Path,
    *,
    market: str = "KOSPI",
    soft_rows: Sequence[Any] | None = None,
    held_tickers: Sequence[str] | None = None,
    include_value_only: bool = True,
    value_only_max: int = 5,
) -> AlphaGieopSeedBoard:
    """Soft 제안 + Soft∩논리 + (옵션) 논리만 상위 N."""
    from alpha_system.review.monopoly_value_screen import build_value_screen

    root = Path(root)
    mkt = normalize_market(market) or "KOSPI"
    mkt_u = str(mkt).upper()
    if not mkt_u.startswith("KOS"):
        mkt_u = "KOSPI"

    held = {
        norm_ticker(t)
        for t in (held_tickers or [])
        if norm_ticker(t) and norm_ticker(t) != "000000"
    }

    value_by: dict[str, Any] = {}
    as_of = ""
    try:
        vboard = build_value_screen(root, market=mkt_u)
        as_of = str(vboard.price_as_of or "")
        value_by = {norm_ticker(r.ticker): r for r in vboard.rows}
    except Exception:  # noqa: BLE001
        value_by = {}

    by_tk: dict[str, AlphaGieopCandidate] = {}

    def _upsert(
        *,
        ticker: str,
        name: str,
        sector: str,
        source: str,
        in_soft: bool,
        prefer: bool = False,
    ) -> None:
        tk = norm_ticker(ticker)
        if not tk:
            return
        vr = value_by.get(tk)
        pass_v = bool(getattr(vr, "pass_value", False)) if vr else False
        logic = ""
        if vr:
            logic = str(getattr(vr, "logic_label_ko", "") or "")
            if not logic and pass_v:
                bits = []
                if getattr(vr, "pass_absolute", False):
                    bits.append("절대저P")
                if getattr(vr, "pass_sector_rel", False):
                    bits.append("섹터할인")
                if getattr(vr, "pass_quality", False):
                    bits.append("퀄OK")
                logic = "·".join(bits) if bits else "논리가치"
        nm = _clean(name) or (
            _clean(getattr(vr, "name", "")) if vr else ""
        ) or tk
        sec = _clean(sector) or (
            _clean(getattr(vr, "sector", "")) if vr else ""
        )
        mcap = getattr(vr, "market_cap", None) if vr else None
        in_held = tk in held
        # Soft∩가치면 source 승격
        src = source
        if in_soft and pass_v and source in {SRC_SOFT, SRC_HELD_SOFT}:
            src = SRC_SOFT_VALUE
        cand = AlphaGieopCandidate(
            ticker=tk,
            name=nm,
            sector=sec,
            source=src,
            logic_label_ko=logic or ("Soft 제안" if in_soft else ""),
            in_soft=in_soft,
            in_held=in_held,
            pass_value=pass_v,
            market_cap=float(mcap) if mcap is not None else None,
        )
        prev = by_tk.get(tk)
        if prev is None or prefer:
            by_tk[tk] = cand
        elif src == SRC_SOFT_VALUE and prev.source != SRC_SOFT_VALUE:
            by_tk[tk] = cand

    for r in soft_rows or []:
        tk = norm_ticker(getattr(r, "ticker", None))
        if not tk:
            continue
        in_held = tk in held
        _upsert(
            ticker=tk,
            name=str(getattr(r, "name", "") or ""),
            sector=str(getattr(r, "sector", "") or ""),
            source=SRC_HELD_SOFT if in_held else SRC_SOFT,
            in_soft=True,
            prefer=True,
        )

    if include_value_only:
        value_only = [
            r
            for r in value_by.values()
            if getattr(r, "pass_value", False)
            and norm_ticker(r.ticker) not in by_tk
        ]
        value_only.sort(
            key=lambda x: (
                0 if getattr(x, "pass_quality", False) else 1,
                0 if getattr(x, "pass_absolute", False) else 1,
                0 if getattr(x, "pass_sector_rel", False) else 1,
                1 if getattr(x, "crash_flag", False) else 0,
                norm_ticker(x.ticker),
            )
        )
        for r in value_only[: max(0, int(value_only_max))]:
            _upsert(
                ticker=r.ticker,
                name=str(r.name or ""),
                sector=str(r.sector or ""),
                source=SRC_VALUE,
                in_soft=False,
            )

    # Soft∩가치 우선 · Soft · 논리만
    order = {SRC_SOFT_VALUE: 0, SRC_HELD_SOFT: 1, SRC_SOFT: 2, SRC_VALUE: 3}
    cands = sorted(
        by_tk.values(),
        key=lambda c: (
            order.get(c.source, 9),
            0 if c.pass_value else 1,
            c.ticker,
        ),
    )
    return AlphaGieopSeedBoard(
        market=mkt_u,
        as_of=as_of,
        candidates=cands,
    )


def write_alpha_gieop_drafts(
    board: AlphaGieopSeedBoard,
    *,
    dest_dir: Path,
    template_path: Path | None = None,
    skip_existing: bool = True,
) -> AlphaGieopSeedBoard:
    """후보별 기업해부 JSON 초안 · 기존 티커는 skip."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    tasks = _load_tasks(template_path)
    existing = _existing_draft_tickers(dest_dir) if skip_existing else set()
    written: list[str] = []
    skipped: list[str] = []
    now = datetime.now(timezone.utc).isoformat()
    as_of = (board.as_of or "na").replace("-", "")[:8]

    for c in board.candidates:
        if c.ticker in existing:
            skipped.append(c.ticker)
            continue
        logic = c.logic_label_ko or c.source_ko
        question = (
            f"{c.name}({c.ticker})는 알파 스크리너 {c.source_ko}"
            f"({logic}) 투자 후보이다. "
            "배당·자사주·영업현금 법인 경로와 다음 권리 사건·밸류업 공시에서 "
            "확인할 것은 무엇인가? Soft 점수·target은 자동 반영하지 않는다."
        )
        payload = {
            "schema": "ph-cvs.research-project/v1",
            "project_id": f"PROJECT-alpha-{c.source}-{c.ticker}",
            "revision": 1,
            "created_at": now,
            "updated_at": now,
            "meta": {
                "company": c.name,
                "ticker": c.ticker,
                "sector": c.sector,
                "legal_entity": c.name,
                "scope": "연결",
                "period_start": "",
                "period_end": "",
                "as_of": board.as_of or "",
                "currency": "KRW",
                "amount_unit": "억원",
                "scenario": "기본",
                "question": question,
                "mode": 30,
                "depth": "deep" if c.pass_value or c.in_soft else "standard",
            },
            "sources": [],
            "facts": [],
            "calculations": [],
            "tasks": tasks,
            "notes": [
                {
                    "text": (
                        f"{MODEL_VERSION} · {c.source_ko} · "
                        f"Soft={'Y' if c.in_soft else 'N'} · "
                        f"보유={'Y' if c.in_held else 'N'} · "
                        f"논리={'Y' if c.pass_value else 'N'} · "
                        "target 불변"
                    ),
                    "source": "gieop_alpha_seed",
                }
            ],
        }
        fname = (
            f"알파_{c.source_ko}_{c.name}_{c.ticker}_기준일{as_of}_수정1.json"
        )
        safe = "".join(
            ch if ch.isalnum() or ch in "._-()" else "_" for ch in fname
        )
        path = dest_dir / safe
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written.append(str(path))
        existing.add(c.ticker)

    board.written = written
    board.skipped = skipped
    return board


def seed_alpha_to_gieop(
    root: Path,
    *,
    market: str = "KOSPI",
    soft_rows: Sequence[Any] | None = None,
    held_tickers: Sequence[str] | None = None,
    include_value_only: bool = True,
    value_only_max: int = 5,
) -> AlphaGieopSeedBoard:
    """수집 → 내조사 초안 → local JSON 스냅샷."""
    root = Path(root)
    board = collect_alpha_gieop_candidates(
        root,
        market=market,
        soft_rows=soft_rows,
        held_tickers=held_tickers,
        include_value_only=include_value_only,
        value_only_max=value_only_max,
    )
    paths = resolve_gieop_paths(root)
    paths.drafts_dir.mkdir(parents=True, exist_ok=True)
    board = write_alpha_gieop_drafts(
        board,
        dest_dir=paths.drafts_dir,
        template_path=TEMPLATE_DEFAULT if TEMPLATE_DEFAULT.is_file() else None,
    )
    out = root / OUT_REL / f"gieop_alpha_seed_{board.market}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(board.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return board


def alpha_seed_queue_html(board: AlphaGieopSeedBoard) -> str:
    esc = escape
    if not board.candidates:
        return (
            '<div class="pf-gieop-bridge">'
            '<div class="pf-gieop-watch-title">알파 → 기업해부 평가 큐</div>'
            '<p class="pf-gieop-idle">Soft·논리 후보 없음 · 확인① 후 Soft 제안 확인</p>'
            "</div>"
        )
    body = ""
    for c in board.candidates:
        body += (
            "<tr>"
            f"<td>{esc(c.name)}</td><td>{esc(c.ticker)}</td>"
            f"<td>{esc(c.source_ko)}</td>"
            f"<td>{'예' if c.in_soft else '아니오'}</td>"
            f"<td>{'예' if c.pass_value else '아니오'}</td>"
            f"<td>{esc((c.logic_label_ko or '—')[:40])}</td>"
            "</tr>"
        )
    foot = ""
    if board.written or board.skipped:
        foot = (
            f'<p class="pf-gieop-note">초안 신규 {len(board.written)} · '
            f"이미 있음 skip {len(board.skipped)} · Soft·target 불변</p>"
        )
    return (
        '<div class="pf-gieop-bridge">'
        '<div class="pf-gieop-watch-title">알파 → 기업해부 평가 큐</div>'
        f'<div class="pf-gieop-counts">{esc(board.market)} · 후보 {len(board.candidates)}'
        f" · Soft·논리 → 박홍기 능동 평가</div>"
        '<table class="pf-gieop-table"><thead><tr>'
        "<th>종목</th><th>코드</th><th>출처</th><th>Soft</th><th>논리</th><th>라벨</th>"
        "</tr></thead><tbody>"
        f"{body}</tbody></table>"
        f"{foot}"
        '<p class="pf-gieop-note">「알파 후보 → 기업해부」로 내조사 초안 생성 · '
        "해부 후 Soft 편입은 사람만</p>"
        "</div>"
    )
