"""OpenDART payout / corporate-action evidence — rules only, no score blend.

Pipeline: list.json titles → classify status → keep rcpNo link → Review UI.
Never writes target_portfolio.csv or changes total_score / QVM ranks.
Fail-open: extraction miss ≠ confirmed absence (data_status distinguishes).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

# Reuse payout title stems from the pack module when available; keep local
# mirrors so this file stays import-light for unit tests.
_BUYBACK = ("자기주식취득", "자기주식 취득", "자사주 매입", "자사주매입")
_CANCEL = ("자기주식소각", "자기주식 소각", "이익소각", "자사주소각")
_DIV = ("현금배당", "배당결정", "중간배당", "분기배당", "결산배당")
_ASSET = (
    "유형자산양도",
    "자산양도결정",
    "영업양도",
    "부동산매각",
    "타법인주식및출자증권처분",
    "타법인주식 및 출자증권 처분",
)

_STATUS_WITHDRAWN = ("철회", "취소", "중단")
_STATUS_COMPLETED = ("결과", "종료", "완료", "취득종료", "신탁계약해지")
_STATUS_PROGRESS = ("현황", "진행", "중간보고")
_STATUS_REVIEW = ("검토", "계획수립")
_STATUS_RESOLVED = ("결정", "결의")
_CORRECTION = ("정정", "기재정정", "[기재정정]")

KIND_LABEL = {
    "buyback": "자사주 취득",
    "cancel": "자사주 소각",
    "div": "배당",
    "asset_sale": "자산 양도",
    "unknown": "기타",
}
STATUS_LABEL = {
    "review": "검토",
    "resolved": "결의",
    "in_progress": "진행",
    "completed": "완료",
    "withdrawn": "철회",
    "unknown": "미분류",
}
DATA_STATUS_LABEL = {
    "missing_key": "API 키 없음",
    "no_corp": "corp_code 없음",
    "fetch_error": "수집 실패",
    "no_events": "관련 공시 없음(또는 미탐지)",
    "ok": "수집됨",
    "stale": "갱신 필요",
}


@dataclass(frozen=True)
class EvidenceEvent:
    kind: str
    status: str
    date: str
    title: str
    rcept_no: str
    source_url: str
    amount_krw: int | None = None
    amount_note: str = ""
    is_correction: bool = False
    chain_id: str = ""
    chain_role: str = ""  # initial | correction | progress | result | withdrawn | alone

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TickerEvidence:
    ticker: str
    data_status: str
    data_note: str = ""
    events: list[EvidenceEvent] = field(default_factory=list)
    headline: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "data_status": self.data_status,
            "data_note": self.data_note,
            "headline": self.headline,
            "events": [e.to_dict() for e in self.events],
        }


def evidence_source_url(rcept_no: str) -> str:
    digits = re.sub(r"\D", "", str(rcept_no or ""))
    if digits:
        return f"https://opendart.fss.or.kr/#rcpNo={digits}"
    return "https://opendart.fss.or.kr/"


def classify_kind(title: str) -> str | None:
    name = title or ""
    if any(k in name for k in _CANCEL):
        return "cancel"
    if any(k in name for k in _BUYBACK):
        return "buyback"
    if any(k in name for k in _DIV):
        return "div"
    if any(k in name for k in _ASSET):
        return "asset_sale"
    return None


def classify_status(title: str) -> str:
    name = title or ""
    if any(k in name for k in _STATUS_WITHDRAWN):
        return "withdrawn"
    if any(k in name for k in _STATUS_COMPLETED):
        return "completed"
    if any(k in name for k in _STATUS_PROGRESS):
        return "in_progress"
    if any(k in name for k in _STATUS_REVIEW):
        return "review"
    if any(k in name for k in _STATUS_RESOLVED):
        return "resolved"
    # Bare "자기주식취득결정" already caught; bare kind titles → 결의 취급
    if classify_kind(name):
        return "resolved"
    return "unknown"


def is_correction_title(title: str) -> bool:
    name = title or ""
    return any(k in name for k in _CORRECTION)


def parse_amount_krw(title: str) -> tuple[int | None, str]:
    """Best-effort amount from title text only — never invent.

    Returns (amount_or_None, note). Titles rarely carry KRW; leave 미확인.
    """
    name = title or ""
    # e.g. 100억원, 1,200백만원 — keep conservative
    m = re.search(r"([\d,]+)\s*억\s*원", name)
    if m:
        try:
            return int(m.group(1).replace(",", "")) * 100_000_000, "제목 추출(억)"
        except ValueError:
            pass
    m = re.search(r"([\d,]+)\s*백만\s*원", name)
    if m:
        try:
            return int(m.group(1).replace(",", "")) * 1_000_000, "제목 추출(백만)"
        except ValueError:
            pass
    return None, "미확인"


def _coerce_amount(raw: object) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    text = str(raw).strip().replace(",", "").replace("원", "")
    if not text or text in {"-", ".", "null", "None"}:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_tsstk_amount_row(row: Mapping[str, Any]) -> tuple[int | None, str]:
    """Sum planned buyback KRW from tsstkAqDecsn.json fields."""
    ostk = _coerce_amount(row.get("aqpln_prc_ostk"))
    estk = _coerce_amount(row.get("aqpln_prc_estk"))
    total = 0
    n = 0
    for part in (ostk, estk):
        if part is not None and part > 0:
            total += part
            n += 1
    if n == 0:
        return None, "미확인"
    return total, "tsstkAqDecsn"


def parse_tgast_amount_row(row: Mapping[str, Any]) -> tuple[int | None, str]:
    """Transfer price from tgastTrfDecsn.json — not assumed to reach shareholders."""
    amt = _coerce_amount(row.get("trfdtl_trfprc"))
    if amt is None or amt <= 0:
        return None, "미확인"
    return amt, "tgastTrfDecsn(양도·환원가정금지)"


def event_from_list_row(row: Mapping[str, Any]) -> EvidenceEvent | None:
    title = re.sub(r"\s+", " ", str(row.get("title") or row.get("report_nm") or "")).strip()
    kind = str(row.get("kind") or "") or (classify_kind(title) or "")
    if not kind:
        return None
    status = classify_status(title)
    rcept = re.sub(r"\D", "", str(row.get("rcept_no") or ""))
    amount = _coerce_amount(row.get("amount_krw"))
    amount_note = str(row.get("amount_note") or "").strip()
    if amount is None:
        amount, amount_note = parse_amount_krw(title)
    elif not amount_note:
        amount_note = "구조화 API"
    return EvidenceEvent(
        kind=kind,
        status=status,
        date=str(row.get("date") or ""),
        title=title[:120],
        rcept_no=rcept,
        source_url=evidence_source_url(rcept),
        amount_krw=amount,
        amount_note=amount_note,
        is_correction=is_correction_title(title),
    )


def _dedupe_key(ev: EvidenceEvent) -> tuple[str, str, str]:
    return (ev.kind, ev.date, ev.rcept_no or ev.title)


def _normalize_chain_key(kind: str, title: str) -> str:
    """Strip status/correction noise so 결정·정정·결과 share one chain key."""
    name = title or ""
    # Longer correction markers first (avoid leaving '기재' after stripping '정정')
    for token in ("[기재정정]", "기재정정", "[정정]", "정정"):
        name = name.replace(token, "")
    name = name.replace("[", "").replace("]", "")
    for token in (
        "결과보고서",
        "결과",
        "현황",
        "중간보고",
        "철회",
        "취소",
        "중단",
        "종료",
        "완료",
        "결정",
        "결의",
        "검토",
        "계획수립",
    ):
        name = name.replace(token, "")
    name = re.sub(r"\s+", "", name)
    name = re.sub(r"\(.*?\)", "", name)
    return f"{kind}:{name[:48] or kind}"


def _role_for_event(ev: EvidenceEvent) -> str:
    if ev.status == "withdrawn":
        return "withdrawn"
    if ev.is_correction or ev.status == "unknown" and is_correction_title(ev.title):
        return "correction"
    if ev.status == "completed":
        return "result"
    if ev.status == "in_progress":
        return "progress"
    if ev.status in {"resolved", "review"}:
        return "initial"
    return "alone"


def link_event_chains(events: Sequence[EvidenceEvent]) -> list[EvidenceEvent]:
    """Group 최초→정정→진행→결과/철회 by kind+normalized title. No double-count."""
    buckets: dict[str, list[EvidenceEvent]] = {}
    for ev in events:
        key = _normalize_chain_key(ev.kind, ev.title)
        buckets.setdefault(key, []).append(ev)
    out: list[EvidenceEvent] = []
    for key, group in buckets.items():
        group_sorted = sorted(group, key=lambda e: (e.date or "", e.rcept_no))
        if len(group_sorted) == 1:
            ev = group_sorted[0]
            out.append(
                EvidenceEvent(
                    kind=ev.kind,
                    status=ev.status,
                    date=ev.date,
                    title=ev.title,
                    rcept_no=ev.rcept_no,
                    source_url=ev.source_url,
                    amount_krw=ev.amount_krw,
                    amount_note=ev.amount_note,
                    is_correction=ev.is_correction,
                    chain_id=key,
                    chain_role=_role_for_event(ev)
                    if _role_for_event(ev) != "alone"
                    else "alone",
                )
            )
            continue
        chain_id = key
        for ev in group_sorted:
            out.append(
                EvidenceEvent(
                    kind=ev.kind,
                    status=ev.status,
                    date=ev.date,
                    title=ev.title,
                    rcept_no=ev.rcept_no,
                    source_url=ev.source_url,
                    amount_krw=ev.amount_krw,
                    amount_note=ev.amount_note,
                    is_correction=ev.is_correction,
                    chain_id=chain_id,
                    chain_role=_role_for_event(ev),
                )
            )
    out.sort(key=lambda e: (e.date or "", e.rcept_no), reverse=True)
    return out


def enrich_events_with_amounts(
    events: Sequence[EvidenceEvent],
    amount_by_rcept: Mapping[str, tuple[int, str]] | None,
) -> list[EvidenceEvent]:
    """Prefer structured API amounts; keep title parse as fallback."""
    table = amount_by_rcept or {}
    out: list[EvidenceEvent] = []
    for ev in events:
        amt = ev.amount_krw
        note = ev.amount_note
        hit = table.get(ev.rcept_no)
        if hit is not None:
            amt, note = hit
        out.append(
            EvidenceEvent(
                kind=ev.kind,
                status=ev.status,
                date=ev.date,
                title=ev.title,
                rcept_no=ev.rcept_no,
                source_url=ev.source_url,
                amount_krw=amt,
                amount_note=note,
                is_correction=ev.is_correction,
                chain_id=ev.chain_id,
                chain_role=ev.chain_role,
            )
        )
    return out


def merge_events(raw_events: Sequence[Mapping[str, Any]]) -> list[EvidenceEvent]:
    """Classify, drop exact duplicates, keep corrections as linked rows (not double hits)."""
    out: list[EvidenceEvent] = []
    seen: set[tuple[str, str, str]] = set()
    for row in raw_events:
        ev = event_from_list_row(row)
        if ev is None:
            continue
        key = _dedupe_key(ev)
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
    out.sort(key=lambda e: (e.date or "", e.rcept_no), reverse=True)
    return out


def _chain_latest_status(events: Sequence[EvidenceEvent]) -> str | None:
    if not events:
        return None
    ordered = sorted(events, key=lambda e: (e.date or "", e.rcept_no))
    return ordered[-1].status


def _headline(events: Sequence[EvidenceEvent]) -> str:
    if not events:
        return "관련 공시 없음"
    by_chain: dict[str, list[EvidenceEvent]] = {}
    for ev in events:
        by_chain.setdefault(ev.chain_id or ev.rcept_no or ev.title, []).append(ev)
    parts: list[str] = []
    for kind in ("buyback", "cancel", "div", "asset_sale"):
        kind_chains = [
            (cid, grp)
            for cid, grp in by_chain.items()
            if grp and grp[0].kind == kind
        ]
        if not kind_chains:
            continue
        # Prefer most recent chain's latest status
        kind_chains.sort(
            key=lambda item: max((e.date or "" for e in item[1]), default=""),
            reverse=True,
        )
        latest_status = _chain_latest_status(kind_chains[0][1])
        path = []
        for role in ("initial", "correction", "progress", "result", "withdrawn"):
            if any(e.chain_role == role for e in kind_chains[0][1]):
                path.append(
                    STATUS_LABEL.get(
                        next(e.status for e in kind_chains[0][1] if e.chain_role == role),
                        role,
                    )
                )
        label = KIND_LABEL.get(kind, kind)
        if path:
            parts.append(f"{label} {'→'.join(path)}")
        else:
            parts.append(
                f"{label} {STATUS_LABEL.get(latest_status or '', latest_status or '')}"
            )
    return " · ".join(parts) if parts else "관련 공시 있음"


def ticker_evidence_from_events(
    ticker: str,
    events: Sequence[EvidenceEvent],
    *,
    data_status: str = "ok",
    data_note: str = "",
) -> TickerEvidence:
    """Rebuild headline after in-place amount enrich (no network)."""
    tk = str(ticker).zfill(6) if str(ticker).isdigit() else str(ticker)
    evs = list(events)
    if not evs:
        return TickerEvidence(
            ticker=tk,
            data_status="no_events",
            data_note=data_note or "관련 공시 없음(또는 미탐지)",
            headline="관련 공시 없음(또는 미탐지)",
        )
    return TickerEvidence(
        ticker=tk,
        data_status=data_status,
        data_note=data_note,
        events=evs,
        headline=_headline(evs),
    )


def build_ticker_evidence(
    ticker: str,
    raw_events: Sequence[Mapping[str, Any]] | None,
    *,
    missing_key: bool = False,
    fetch_error: str | None = None,
    no_corp: bool = False,
    amount_by_rcept: Mapping[str, tuple[int, str]] | None = None,
) -> TickerEvidence:
    tk = str(ticker).zfill(6) if str(ticker).isdigit() else str(ticker)
    if missing_key:
        return TickerEvidence(
            ticker=tk,
            data_status="missing_key",
            data_note="Open DART API 키 없음",
            headline="미수집",
        )
    if no_corp:
        return TickerEvidence(
            ticker=tk,
            data_status="no_corp",
            data_note="corp_code 없음",
            headline="미수집",
        )
    if fetch_error:
        return TickerEvidence(
            ticker=tk,
            data_status="fetch_error",
            data_note=str(fetch_error)[:160],
            headline="수집 실패(없음과 구분)",
        )
    events = merge_events(raw_events or ())
    events = enrich_events_with_amounts(events, amount_by_rcept)
    events = link_event_chains(events)
    if not events:
        return TickerEvidence(
            ticker=tk,
            data_status="no_events",
            data_note=(
                "조회 구간에 배당·자사주·자산양도 제목 없음. "
                "실제 부재와 제목 미탐지를 단정하지 않음."
            ),
            headline="관련 공시 없음(또는 미탐지)",
        )
    return TickerEvidence(
        ticker=tk,
        data_status="ok",
        data_note="",
        events=events,
        headline=_headline(events),
    )


def build_evidence_board(
    tickers: Sequence[str],
    events_by_ticker: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    missing_key: bool = False,
    errors_by_ticker: Mapping[str, str] | None = None,
    no_corp_tickers: Sequence[str] | None = None,
    amounts_by_ticker: Mapping[str, Mapping[str, tuple[int, str]]] | None = None,
) -> list[TickerEvidence]:
    err = errors_by_ticker or {}
    amounts = amounts_by_ticker or {}
    no_corp = {
        (t.zfill(6) if t.isdigit() else t)
        for t in (str(x) for x in (no_corp_tickers or ()))
    }
    board: list[TickerEvidence] = []
    for raw in tickers:
        tk = str(raw).zfill(6) if str(raw).isdigit() else str(raw)
        board.append(
            build_ticker_evidence(
                tk,
                events_by_ticker.get(tk) or events_by_ticker.get(raw) or (),
                missing_key=missing_key,
                fetch_error=err.get(tk) or err.get(raw),
                no_corp=tk in no_corp,
                amount_by_rcept=amounts.get(tk) or amounts.get(raw),
            )
        )
    return board


def latest_buyback_chain_withdrawn(item: TickerEvidence) -> EvidenceEvent | None:
    """Return latest buyback event if that chain ends in withdrawn. Fail-open otherwise."""
    if item.data_status != "ok":
        return None
    buybacks = [e for e in item.events if e.kind == "buyback"]
    if not buybacks:
        return None
    by_chain: dict[str, list[EvidenceEvent]] = {}
    for ev in buybacks:
        by_chain.setdefault(ev.chain_id or ev.rcept_no, []).append(ev)
    # Most recent chain by max date
    chains = sorted(
        by_chain.values(),
        key=lambda grp: max((e.date or "" for e in grp), default=""),
        reverse=True,
    )
    if not chains:
        return None
    latest = sorted(chains[0], key=lambda e: (e.date or "", e.rcept_no))[-1]
    if latest.status == "withdrawn":
        return latest
    return None


def withdrawn_buyback_gate_candidates(
    board: Sequence[TickerEvidence],
) -> list[tuple[str, EvidenceEvent]]:
    """Tickers whose latest buyback chain ended in 철회 — gate candidates only."""
    out: list[tuple[str, EvidenceEvent]] = []
    for item in board:
        hit = latest_buyback_chain_withdrawn(item)
        if hit is not None:
            out.append((item.ticker, hit))
    return out


DEFAULT_EVIDENCE_GATE_POLICY: dict[str, Any] = {
    "enabled": False,
    "exclude_withdrawn_buyback": True,
    "notes": (
        "A/B: enabled=false 기본(표시만). true면 자사주 체인 최종 철회만 제안 제외. "
        "점수·target 불변 · 수집실패/없음은 fail-open."
    ),
}


def load_evidence_gate_policy(path: Path | None) -> dict[str, Any]:
    out = dict(DEFAULT_EVIDENCE_GATE_POLICY)
    if path is None:
        return out
    p = Path(path)
    if not p.exists():
        return out
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return out
    if not isinstance(raw, dict):
        return out
    if "enabled" in raw:
        out["enabled"] = bool(raw["enabled"])
    if "exclude_withdrawn_buyback" in raw:
        out["exclude_withdrawn_buyback"] = bool(raw["exclude_withdrawn_buyback"])
    return out


def evidence_gate_policy_path(data_dir: Path) -> Path:
    return Path(data_dir) / "evidence_gate_policy.json"


def evidence_rows_for_display(
    board: Sequence[TickerEvidence],
    *,
    only_with_events: bool = True,
    limit_per_ticker: int = 4,
) -> list[dict[str, str]]:
    """Flat rows for Streamlit — Review only."""
    rows: list[dict[str, str]] = []
    for item in board:
        if only_with_events and item.data_status != "ok":
            if item.data_status in {"fetch_error", "missing_key", "no_corp"}:
                rows.append(
                    {
                        "ticker": item.ticker,
                        "data_status": DATA_STATUS_LABEL.get(
                            item.data_status, item.data_status
                        ),
                        "headline": item.headline,
                        "kind": "",
                        "status": "",
                        "date": "",
                        "title": item.data_note,
                        "source_url": "",
                        "amount_note": "",
                    }
                )
            continue
        if item.data_status == "ok" and not item.events:
            continue
        if item.data_status == "no_events" and only_with_events:
            continue
        for ev in item.events[:limit_per_ticker]:
            amt = (
                f"{ev.amount_krw:,.0f}원"
                if ev.amount_krw is not None
                else ev.amount_note
            )
            rows.append(
                {
                    "ticker": item.ticker,
                    "data_status": DATA_STATUS_LABEL.get(
                        item.data_status, item.data_status
                    ),
                    "headline": item.headline,
                    "kind": KIND_LABEL.get(ev.kind, ev.kind),
                    "status": STATUS_LABEL.get(ev.status, ev.status),
                    "date": ev.date,
                    "title": ev.title
                    + (" · 정정" if ev.is_correction else "")
                    + (f" · 체인:{ev.chain_role}" if ev.chain_role else ""),
                    "source_url": ev.source_url,
                    "amount_note": amt,
                }
            )
    return rows
