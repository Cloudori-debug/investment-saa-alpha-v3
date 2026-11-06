"""기업해부 ↔ 알파 편의 융합 (Review-only).

1) 내조사 JSON 해부 과제 진행(사람) — 시드만 하면 전부 미착수·0/50 가능
2) 알파 정량 커버 — Soft/논리/재무/증빙 등으로 변별 (자동·갱신 가능)
Soft/target 불변 · 주관 미니체크 없음.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Mapping, Sequence

from alpha_system.proposal_chart import norm_ticker
from alpha_system.screen_book import normalize_market
from alpha_system.ui.services.gieop_alpha_seed import AlphaGieopCandidate
from alpha_system.ui.services.gieop_observe_board import resolve_gieop_paths
from alpha_system.ui.services.gieop_verdict import GieopVerdict, load_verdicts

MODEL_VERSION = "gieop-fusion-desk-v3"

STATUS_NONE = "none"
STATUS_IDLE = "idle"
STATUS_ACTIVE = "active"
STATUS_DONE = "done"

STATUS_KO = {
    STATUS_NONE: "초안없음",
    STATUS_IDLE: "미착수",
    STATUS_ACTIVE: "진행중",
    STATUS_DONE: "완료",
}

DONE_STATUSES = frozenset(
    {
        "DONE",
        "COMPLETE",
        "COMPLETED",
        "PASS",
        "PASSED",
        "OK",
        "FINISHED",
        "DONE_OK",
    }
)
ACTIVE_STATUSES = frozenset(
    {
        "IN_PROGRESS",
        "PROGRESS",
        "STARTED",
        "WORKING",
        "REVIEW",
        "PARTIAL",
    }
)

# 정량 커버 체크 (사람 해부 50문항과 별개)
QUANT_CHECKS: tuple[tuple[str, str], ...] = (
    ("soft", "Soft편입"),
    ("value", "논리가치"),
    ("fund", "PER·PBR·ROE"),
    ("cheap", "절대저P|섹터할인"),
    ("qual", "퀄통과"),
    ("no_crash", "낙폭함정아님"),
    ("evidence", "독점증빙"),
)


@dataclass(frozen=True)
class DraftProgress:
    ticker: str
    status: str
    status_ko: str
    n_tasks: int
    n_done: int
    n_active: int
    path: str
    company: str = ""


@dataclass(frozen=True)
class QuantCover:
    """알파 정량으로 채우는 커버리지 · Soft 점수 가산 없음."""

    n_ok: int
    n_total: int
    checks: tuple[tuple[str, bool, str], ...]  # id, ok, label_ko
    detail_ko: str = ""

    @property
    def label(self) -> str:
        return f"{self.n_ok}/{self.n_total}"

    @property
    def pct(self) -> float:
        return 100.0 * self.n_ok / max(self.n_total, 1)


@dataclass
class FusionRow:
    ticker: str
    name: str
    source_ko: str
    in_soft: bool
    pass_value: bool
    draft: DraftProgress | None
    quant: QuantCover | None = None
    verdict: GieopVerdict | None = None


@dataclass
class FusionDeskBoard:
    market: str
    rows: list[FusionRow] = field(default_factory=list)
    n_draft_idle: int = 0
    n_draft_active: int = 0
    n_draft_done: int = 0
    n_draft_none: int = 0
    quant_as_of: str = ""
    n_quant_hi: int = 0  # 정량 ≥6/8
    n_quant_mid: int = 0
    n_quant_lo: int = 0


def _task_bucket(status: object) -> str:
    s = str(status or "").strip().upper().replace(" ", "_")
    if not s or s in {"NOT_STARTED", "NONE", "TODO", "PENDING", "NEW"}:
        return "idle"
    if s in DONE_STATUSES or s.endswith("_DONE") or s.startswith("DONE"):
        return "done"
    if s in ACTIVE_STATUSES or "PROGRESS" in s or "REVIEW" in s:
        return "active"
    return "active"


def scan_draft_progress(drafts_dir: Path) -> dict[str, DraftProgress]:
    """티커 → 최신 수정 초안 진행도 (사람 과제)."""
    out: dict[str, DraftProgress] = {}
    if not drafts_dir.is_dir():
        return out
    files = sorted(
        drafts_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in files:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(raw, dict):
            continue
        meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
        tk = norm_ticker(meta.get("ticker"))
        if not tk:
            for part in path.stem.replace("-", "_").split("_"):
                if part.isdigit() and len(part) == 6:
                    tk = part
                    break
        if not tk or tk in out:
            continue
        tasks = raw.get("tasks") if isinstance(raw.get("tasks"), list) else []
        n_done = n_active = n_idle = 0
        for t in tasks:
            if not isinstance(t, dict):
                continue
            bucket = _task_bucket(t.get("status"))
            if bucket == "done":
                n_done += 1
            elif bucket == "active":
                n_active += 1
            else:
                if str(t.get("reason") or "").strip() or str(
                    t.get("next_action") or ""
                ).strip():
                    n_active += 1
                else:
                    n_idle += 1
        n_tasks = n_done + n_active + n_idle
        if n_tasks == 0:
            status = STATUS_IDLE
        elif n_done >= n_tasks and n_tasks > 0:
            status = STATUS_DONE
        elif n_done / max(n_tasks, 1) >= 0.8 and n_active == 0:
            status = STATUS_DONE
        elif n_done > 0 or n_active > 0:
            status = STATUS_ACTIVE
        else:
            status = STATUS_IDLE
        out[tk] = DraftProgress(
            ticker=tk,
            status=status,
            status_ko=STATUS_KO[status],
            n_tasks=n_tasks,
            n_done=n_done,
            n_active=n_active,
            path=str(path),
            company=str(meta.get("company") or ""),
        )
    return out


def _f(v: object) -> float | None:
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x:
        return None
    return x


def build_quant_cover(
    *,
    in_soft: bool,
    pass_value: bool,
    value_row: Any | None = None,
    size_floor_krw: float = 0.0,
) -> QuantCover:
    """알파 정량으로 변별 커버 산출 · Soft/QVM 가산 없음 · 시총 하한 없음."""
    del size_floor_krw  # kept for call-site compat; size gate removed
    vr = value_row
    per = _f(getattr(vr, "per", None)) if vr is not None else None
    pbr = _f(getattr(vr, "pbr", None)) if vr is not None else None
    roe = _f(getattr(vr, "roe", None)) if vr is not None else None
    fund_ok = per is not None and pbr is not None and roe is not None
    abs_ok = bool(getattr(vr, "pass_absolute", False)) if vr is not None else False
    sec_ok = bool(getattr(vr, "pass_sector_rel", False)) if vr is not None else False
    qual_ok = bool(getattr(vr, "pass_quality", False)) if vr is not None else False
    crash = bool(getattr(vr, "crash_flag", False)) if vr is not None else False
    # 낙폭함정 = crash이면서 섹터할인 없음(논리 스크린과 동일 취지)
    no_crash_trap = (not crash) or sec_ok
    evid = bool(getattr(vr, "evidence_ok", False)) if vr is not None else False

    flags = {
        "soft": bool(in_soft),
        "value": bool(pass_value),
        "fund": fund_ok,
        "cheap": abs_ok or sec_ok,
        "qual": qual_ok,
        "no_crash": no_crash_trap,
        "evidence": evid,
    }
    checks: list[tuple[str, bool, str]] = []
    for cid, label in QUANT_CHECKS:
        checks.append((cid, bool(flags.get(cid)), label))
    n_ok = sum(1 for _, ok, _ in checks if ok)
    bits = [lab for _, ok, lab in checks if ok]
    miss = [lab for _, ok, lab in checks if not ok]
    detail = ""
    if bits:
        detail += "OK " + ",".join(bits)
    if miss:
        detail += (" · " if detail else "") + "미 " + ",".join(miss)
    return QuantCover(
        n_ok=n_ok,
        n_total=len(checks),
        checks=tuple(checks),
        detail_ko=detail,
    )


def _load_value_by(root: Path, market: str) -> tuple[dict[str, Any], str]:
    try:
        from alpha_system.review.monopoly_value_screen import build_value_screen

        board = build_value_screen(root, market=market)
        return (
            {norm_ticker(r.ticker): r for r in board.rows},
            str(board.price_as_of or ""),
        )
    except Exception:  # noqa: BLE001
        return {}, ""


def build_fusion_desk(
    root: Path,
    *,
    market: str,
    candidates: Sequence[AlphaGieopCandidate],
) -> FusionDeskBoard:
    paths = resolve_gieop_paths(root)
    drafts = scan_draft_progress(paths.drafts_dir)
    mkt = str(normalize_market(market) or "KOSPI").upper()
    value_by, as_of = _load_value_by(Path(root), mkt)
    verdicts = load_verdicts(paths.drafts_dir, book_price_date=as_of or None)

    rows: list[FusionRow] = []
    n_idle = n_active = n_done = n_none = 0
    n_hi = n_mid = n_lo = 0
    for c in candidates:
        d = drafts.get(c.ticker)
        if d is None:
            n_none += 1
        elif d.status == STATUS_IDLE:
            n_idle += 1
        elif d.status == STATUS_ACTIVE:
            n_active += 1
        elif d.status == STATUS_DONE:
            n_done += 1
        vr = value_by.get(c.ticker)
        quant = build_quant_cover(
            in_soft=c.in_soft,
            pass_value=c.pass_value
            or bool(getattr(vr, "pass_value", False) if vr else False),
            value_row=vr,
        )
        if quant.n_ok >= 6:
            n_hi += 1
        elif quant.n_ok >= 4:
            n_mid += 1
        else:
            n_lo += 1
        rows.append(
            FusionRow(
                ticker=c.ticker,
                name=c.name,
                source_ko=c.source_ko,
                in_soft=c.in_soft,
                pass_value=c.pass_value,
                draft=d,
                quant=quant,
                verdict=verdicts.get(c.ticker),
            )
        )
    rows.sort(
        key=lambda r: (
            -(r.quant.n_ok if r.quant else 0),
            0 if r.in_soft else 1,
            0 if r.pass_value else 1,
            r.ticker,
        )
    )
    return FusionDeskBoard(
        market=mkt,
        rows=rows,
        n_draft_idle=n_idle,
        n_draft_active=n_active,
        n_draft_done=n_done,
        n_draft_none=n_none,
        quant_as_of=as_of,
        n_quant_hi=n_hi,
        n_quant_mid=n_mid,
        n_quant_lo=n_lo,
    )


def refresh_quant_on_drafts(
    root: Path,
    *,
    market: str,
    candidates: Sequence[AlphaGieopCandidate],
) -> dict[str, Any]:
    """내조사 JSON에 alpha_quant 블록만 갱신 · tasks 상태·Soft·target 불변."""
    root = Path(root)
    paths = resolve_gieop_paths(root)
    board = build_fusion_desk(root, market=market, candidates=candidates)
    drafts = scan_draft_progress(paths.drafts_dir)
    now = datetime.now(timezone.utc).isoformat()
    updated: list[str] = []
    missing: list[str] = []
    for r in board.rows:
        d = drafts.get(r.ticker) or r.draft
        if d is None or not d.path:
            missing.append(r.ticker)
            continue
        path = Path(d.path)
        if not path.is_file():
            missing.append(r.ticker)
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            missing.append(r.ticker)
            continue
        if not isinstance(raw, dict):
            missing.append(r.ticker)
            continue
        q = r.quant
        payload = {
            "model": MODEL_VERSION,
            "updated_at": now,
            "as_of": board.quant_as_of,
            "n_ok": q.n_ok if q else 0,
            "n_total": q.n_total if q else 0,
            "label": q.label if q else "0/0",
            "detail_ko": q.detail_ko if q else "",
            "checks": [
                {"id": cid, "ok": ok, "label_ko": lab}
                for cid, ok, lab in (q.checks if q else ())
            ],
            "soft_score_unchanged": True,
            "target_portfolio_written": False,
            "human_tasks_untouched": True,
        }
        raw["alpha_quant"] = payload
        raw["updated_at"] = now
        notes = raw.get("notes") if isinstance(raw.get("notes"), list) else []
        note_txt = (
            f"{MODEL_VERSION} 정량커버 {payload['label']} · {payload['detail_ko']}"
        )
        notes = [
            n
            for n in notes
            if not (
                isinstance(n, dict)
                and str(n.get("source") or "") == "gieop_alpha_quant"
            )
        ]
        notes.append({"text": note_txt, "source": "gieop_alpha_quant"})
        raw["notes"] = notes
        path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        updated.append(r.ticker)

    snap = root / "data" / "local" / f"gieop_quant_cover_{board.market}.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_text(
        json.dumps(
            {
                "market": board.market,
                "as_of": board.quant_as_of,
                "updated_at": now,
                "updated": updated,
                "missing_draft": missing,
                "hi": board.n_quant_hi,
                "mid": board.n_quant_mid,
                "lo": board.n_quant_lo,
                "rows": [
                    {
                        "ticker": r.ticker,
                        "name": r.name,
                        "quant": r.quant.label if r.quant else None,
                        "detail": r.quant.detail_ko if r.quant else "",
                        "draft": r.draft.status_ko if r.draft else STATUS_KO[STATUS_NONE],
                        "gate": r.verdict.effective_gate if r.verdict else "",
                    }
                    for r in board.rows
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "updated": updated,
        "missing_draft": missing,
        "n_hi": board.n_quant_hi,
        "n_mid": board.n_quant_mid,
        "n_lo": board.n_quant_lo,
        "as_of": board.quant_as_of,
        "snap": str(snap),
    }


def fusion_status_html(board: FusionDeskBoard) -> str:
    esc = escape
    if not board.rows:
        return (
            '<div class="pf-gieop-bridge">'
            '<div class="pf-gieop-watch-title">해부 초안 상태</div>'
            '<p class="pf-gieop-idle">알파 후보 없음</p></div>'
        )
    body = ""
    for r in board.rows:
        st = r.draft.status_ko if r.draft else STATUS_KO[STATUS_NONE]
        human = "—"
        if r.draft and r.draft.n_tasks:
            human = f"{r.draft.n_done}/{r.draft.n_tasks}"
        soft_ko = "예" if r.in_soft else "아니오"
        val_ko = "예" if r.pass_value else "아니오"
        q = r.quant
        q_lab = q.label if q else "—"
        q_title = esc(q.detail_ko) if q else ""
        q_cls = "pf-quant-hi"
        if q:
            if q.n_ok >= 6:
                q_cls = "pf-quant-hi"
            elif q.n_ok >= 4:
                q_cls = "pf-quant-mid"
            else:
                q_cls = "pf-quant-lo"
        gate = r.verdict.chip_ko if r.verdict else "—"
        body += (
            "<tr>"
            f"<td>{esc(r.name)}</td><td>{esc(r.ticker)}</td>"
            f"<td>{esc(r.source_ko)}</td>"
            f"<td>{soft_ko}</td><td>{val_ko}</td>"
            f'<td class="{q_cls}" title="{q_title}"><strong>{esc(q_lab)}</strong></td>'
            f'<td class="pf-human-draft">{esc(st)}</td>'
            f'<td class="pf-human-tasks" title="사람 해부 과제(시드 직후엔 0/50)">'
            f"{esc(human)}</td>"
            f'<td class="pf-gieop-gate">{esc(gate)}</td>'
            "</tr>"
        )
    asof = f" · 가격 {esc(board.quant_as_of)}" if board.quant_as_of else ""
    return (
        '<div class="pf-gieop-bridge">'
        '<div class="pf-gieop-watch-title">해부 · 정량 커버 (객관)</div>'
        f'<div class="pf-gieop-counts">'
        f"정량 높음 {board.n_quant_hi} · 중간 {board.n_quant_mid} · "
        f"낮음 {board.n_quant_lo}{asof}"
        f"<br/>해부초안 없음 {board.n_draft_none} · "
        f"미착수 {board.n_draft_idle} · 진행 {board.n_draft_active} · "
        f"완료 {board.n_draft_done}"
        "</div>"
        '<table class="pf-gieop-table"><thead><tr>'
        "<th>종목</th><th>코드</th><th>출처</th><th>Soft</th><th>논리</th>"
        "<th>정량</th><th>해부</th><th>해부과제</th><th>관문</th>"
        "</tr></thead><tbody>"
        f"{body}</tbody></table>"
        '<p class="pf-gieop-note">'
        "정량=Soft·논리·재무·퀄·낙폭·증빙 자동(7항) · "
        "해부과제=사람 50항(시드만이면 0/50) · "
        "관문=판정 파일(FAIL/HOLD/PASS) · 점수 가산 없음 · "
        "HOLD는 판단 보류 · Soft·target 불변"
        "</p>"
        "</div>"
    )


__all__ = [
    "DraftProgress",
    "FusionDeskBoard",
    "FusionRow",
    "MODEL_VERSION",
    "QUANT_CHECKS",
    "QuantCover",
    "build_fusion_desk",
    "build_quant_cover",
    "fusion_status_html",
    "refresh_quant_on_drafts",
    "scan_draft_progress",
]
