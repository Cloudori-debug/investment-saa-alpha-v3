"""PH-CVS-style deep verify for *screener* observation/proposal names.

Review-only · no score mix · no target writes · no network.
Automates what hakedaka CSV + OpenDART watch already carry.
Never invents missing values as 0.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from alpha_system.sizing.hakedaka_screen import (
    HAKEDAKA_CSV,
    evaluate_hakedaka,
    load_hakedaka_inputs,
)
from alpha_system.sizing.qual_overlay import norm_ticker
from alpha_system.ui.services.dart_evidence import (
    TickerEvidence,
    withdrawn_buyback_gate_candidates,
)

MODEL_VERSION = "screen-deep-verify-v3"
VERIFY_FILENAME = "screen_deep_verify.json"

_HOLDING_NAME = re.compile(r"(홀딩스|지주|홀딩)", re.I)

# Hard risk → 제외검토 (점수 불변 · target 자동 없음)
_EXCLUDE_FAIL_KEYS = frozenset({"buyback_withdrawn", "control_flag"})
# Soft risk → 보류
_HOLD_FAIL_KEYS = frozenset(
    {
        "hakedaka",
        "opendart_evidence",
        "capital_waterfall",
        "cash_attribution",
        "restricted_cash",
        "nav_double_count",
    }
)

VERDICT_LABEL = {
    "pass_review": "통과",
    "hold": "보류",
    "exclude_review": "제외검토",
    "watch": "관찰",
    "parked": "대기",
}


@dataclass(frozen=True)
class CheckItem:
    key: str
    label: str
    status: str  # PASS | FAIL | U | NA
    note: str = ""


@dataclass
class ScreenVerifyRow:
    ticker: str
    name: str
    book: str  # 제안 | 대기 | 관찰
    overall: str  # ok | warn | incomplete
    headline: str
    warn_tags: list[str] = field(default_factory=list)
    checks: list[CheckItem] = field(default_factory=list)
    # Review action — never writes scores/target
    verdict: str = "watch"  # pass_review | hold | exclude_review | watch | parked
    verdict_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "book": self.book,
            "overall": self.overall,
            "headline": self.headline,
            "warn_tags": list(self.warn_tags),
            "checks": [asdict(c) for c in self.checks],
            "verdict": self.verdict,
            "verdict_note": self.verdict_note,
        }


@dataclass
class ScreenVerifyBoard:
    available: bool
    as_of: str
    evaluated_at: str
    model_version: str
    source_note: str
    rows: list[ScreenVerifyRow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "evaluated_at": self.evaluated_at,
            "model_version": self.model_version,
            "source_note": self.source_note,
            "charter": {
                "proposal_mode": "pure_qvm",
                "target_portfolio_written": False,
                "note": (
                    "스크린 심층·Review 판정 · 점수·target 불변 · "
                    "결측은 U(0 추정 금지) · 사람만 주문"
                ),
            },
            "names": [r.to_dict() for r in self.rows],
        }


def verify_path(data_dir: Path) -> Path:
    return Path(data_dir) / VERIFY_FILENAME


def _f(raw: object) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.lower() in {"nan", "none", ""}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except (OSError, csv.Error):
        return []


def load_hakedaka_fund_rows(
    root: Path,
    *,
    data_dir: Path | None = None,
) -> dict[str, dict[str, str]]:
    """Full hakedaka CSV rows by ticker (shared then book override)."""
    root = Path(root)
    book = Path(data_dir) if data_dir is not None else root / "data"
    shared = root / "data"
    out: dict[str, dict[str, str]] = {}
    bases: list[Path] = []
    if shared.resolve() != book.resolve():
        bases.append(shared)
    bases.append(book)
    for base in bases:
        for row in _read_csv_rows(base / HAKEDAKA_CSV):
            tk = norm_ticker(row.get("ticker"))
            if tk:
                out[tk] = row
    return out


def load_screen_verify(data_dir: Path) -> ScreenVerifyBoard:
    path = verify_path(data_dir)
    empty = ScreenVerifyBoard(
        available=False,
        as_of="",
        evaluated_at="",
        model_version=MODEL_VERSION,
        source_note="",
        rows=[],
    )
    if not path.exists():
        return empty
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return empty
    if not isinstance(raw, dict):
        return empty
    rows: list[ScreenVerifyRow] = []
    for item in raw.get("names") or []:
        if not isinstance(item, dict):
            continue
        tk = norm_ticker(item.get("ticker"))
        if not tk:
            continue
        checks = [
            CheckItem(
                key=str(c.get("key") or ""),
                label=str(c.get("label") or ""),
                status=str(c.get("status") or "U"),
                note=str(c.get("note") or ""),
            )
            for c in (item.get("checks") or [])
            if isinstance(c, dict)
        ]
        rows.append(
            ScreenVerifyRow(
                ticker=tk,
                name=str(item.get("name") or tk),
                book=str(item.get("book") or "관찰"),
                overall=str(item.get("overall") or "incomplete"),
                headline=str(item.get("headline") or ""),
                warn_tags=[str(t) for t in (item.get("warn_tags") or [])],
                checks=checks,
                verdict=str(item.get("verdict") or "watch"),
                verdict_note=str(item.get("verdict_note") or ""),
            )
        )
    return ScreenVerifyBoard(
        available=bool(rows),
        as_of=str(raw.get("as_of") or ""),
        evaluated_at=str(raw.get("evaluated_at") or ""),
        model_version=str(raw.get("model_version") or MODEL_VERSION),
        source_note=str(raw.get("source_note") or ""),
        rows=rows,
    )


def save_screen_verify(data_dir: Path, board: ScreenVerifyBoard) -> Path:
    path = verify_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(board.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _book_of(
    tk: str,
    proposal: set[str],
    blocked: set[str],
) -> str:
    if tk in proposal:
        return "제안"
    if tk in blocked:
        return "대기"
    return "관찰"


def _ev_by_ticker(evidence_raw: Sequence[Mapping[str, Any]] | None) -> dict[str, TickerEvidence]:
    from alpha_system.ui.services.opendart_evidence_board import parse_evidence_board

    board = parse_evidence_board(evidence_raw or [])
    return {b.ticker: b for b in board if b.ticker}


def _is_holding_name(name: str) -> bool:
    return bool(_HOLDING_NAME.search(name or ""))


def _eok(n: float) -> str:
    """Format KRW as 억 for notes."""
    eok = n / 100_000_000.0
    if abs(eok) >= 100:
        return f"{eok:,.0f}억"
    return f"{eok:,.1f}억"


def _check_hakedaka(
    tk: str,
    inputs: Any,
    *,
    min_hits: int,
) -> CheckItem:
    v = evaluate_hakedaka(tk, inputs, min_hits=min_hits)
    if v.known < max(1, min_hits):
        return CheckItem(
            "hakedaka",
            "하케다카 hit",
            "U",
            v.detail or "측정 부족",
        )
    if v.passed:
        return CheckItem("hakedaka", "하케다카 hit", "PASS", v.detail)
    return CheckItem("hakedaka", "하케다카 hit", "FAIL", v.detail)


def _check_evidence(tk: str, ev_map: Mapping[str, TickerEvidence]) -> CheckItem:
    item = ev_map.get(tk)
    if item is None:
        return CheckItem(
            "opendart_evidence",
            "공시 증거",
            "U",
            "watch에 없음 · 증분 갱신",
        )
    st = item.data_status or ""
    if st == "ok" and item.events:
        kinds = sorted({e.kind for e in item.events})
        return CheckItem(
            "opendart_evidence",
            "공시 증거",
            "PASS",
            item.headline or ",".join(kinds),
        )
    if st in {"fetch_error", "missing_key", "no_corp"}:
        return CheckItem(
            "opendart_evidence",
            "공시 증거",
            "FAIL",
            item.data_note or st,
        )
    if st == "no_events":
        # Explored empty ≠ unknown
        return CheckItem(
            "opendart_evidence",
            "공시 증거",
            "PASS",
            "관련 공시 없음(탐색완료)",
        )
    return CheckItem("opendart_evidence", "공시 증거", "U", st or "미확인")


def _check_withdrawn(
    tk: str,
    withdrawn: set[str],
    ev_map: Mapping[str, TickerEvidence],
) -> CheckItem:
    if tk in withdrawn:
        return CheckItem(
            "buyback_withdrawn",
            "자사주 철회",
            "FAIL",
            "체인 최종 철회",
        )
    item = ev_map.get(tk)
    if item and any(e.kind == "buyback" for e in item.events):
        return CheckItem("buyback_withdrawn", "자사주 철회", "PASS", "철회 아님")
    if item and item.data_status == "no_events":
        return CheckItem("buyback_withdrawn", "자사주 철회", "NA", "자사주 사건 없음")
    if item and item.data_status == "ok":
        return CheckItem("buyback_withdrawn", "자사주 철회", "NA", "자사주 사건 없음")
    return CheckItem("buyback_withdrawn", "자사주 철회", "U", "증거 미수집")


def _check_control(
    tk: str,
    flag_kinds: Mapping[str, list[str]],
    metrics: Mapping[str, Mapping[str, Any]],
) -> CheckItem:
    kinds = flag_kinds.get(tk) or []
    hot = [k for k in kinds if k in {"control_purpose", "control", "activist"}]
    if hot:
        return CheckItem(
            "control_flag",
            "경영참여·지배",
            "FAIL",
            ",".join(hot),
        )
    m = metrics.get(tk) or {}
    if "control_purpose" in m:
        if m.get("control_purpose") is True:
            return CheckItem(
                "control_flag",
                "경영참여·지배",
                "FAIL",
                "control_purpose=true",
            )
        if m.get("control_purpose") is False:
            soft = [k for k in kinds if k]
            note = "경영참여 목적 아님"
            if soft:
                note += " · " + ",".join(soft)
            return CheckItem("control_flag", "경영참여·지배", "PASS", note)
    soft = [k for k in kinds if k]
    if soft:
        return CheckItem(
            "control_flag",
            "경영참여·지배",
            "PASS",
            "플래그:" + ",".join(soft),
        )
    if m:
        return CheckItem(
            "control_flag",
            "경영참여·지배",
            "PASS",
            "metrics 있음·지배목적 미표기",
        )
    return CheckItem("control_flag", "경영참여·지배", "U", "metrics/플래그 없음")


def _check_capital_waterfall(
    tk: str,
    fund: Mapping[str, str] | None,
    ev_map: Mapping[str, TickerEvidence],
) -> CheckItem:
    """FCF / (OCF−CAPEX) proxy — not full PH-CVS equity/loan waterfall."""
    row = fund or {}
    fcf = _f(row.get("fcf_annual"))
    if fcf is None:
        fcf = _f(row.get("free_cash_flow"))
    ocf = _f(row.get("ocf_annual"))
    if ocf is None:
        ocf = _f(row.get("operating_cash_flow"))
    capex = _f(row.get("capital_expenditure"))
    residual: float | None = None
    source = ""
    if fcf is not None:
        residual = fcf
        source = "fcf_annual"
    elif ocf is not None and capex is not None:
        residual = ocf - abs(capex)
        source = "ocf−|capex|"
    if residual is None:
        return CheckItem(
            "capital_waterfall",
            "자본사용후잔여",
            "U",
            "FCF/OCF·CAPEX 없음 · 하케다카 보강",
        )
    ev = ev_map.get(tk)
    payout_note = ""
    if ev and ev.events:
        kinds = sorted({e.kind for e in ev.events if e.kind in {"div", "buyback"}})
        if kinds:
            payout_note = " · 공시:" + ",".join(kinds)
    note = f"{source} {_eok(residual)}{payout_note} · 지분·대여 미차감"
    if residual >= 0:
        return CheckItem("capital_waterfall", "자본사용후잔여", "PASS", note)
    return CheckItem("capital_waterfall", "자본사용후잔여", "FAIL", note)


def _check_cash_attribution(
    tk: str,
    name: str,
    fund: Mapping[str, str] | None,
) -> CheckItem:
    """Holding-company cash-uplift risk — not full parent/sub split."""
    row = fund or {}
    hold_proxy = _f(row.get("holding_company_discount_proxy"))
    cash = _f(row.get("cash_and_equivalents"))
    if cash is None:
        cash = _f(row.get("cash_annual"))
    is_hold = _is_holding_name(name) or (
        hold_proxy is not None and hold_proxy > 0
    )
    if is_hold:
        note = "지주·홀딩스 · 자회사현금≠모주주"
        if hold_proxy is not None:
            note += f" · 할인프록시 {hold_proxy:.2f}"
        if cash is not None:
            note += f" · 연결현금 {_eok(cash)}"
        return CheckItem("cash_attribution", "현금 귀속", "FAIL", note)
    if cash is not None:
        return CheckItem(
            "cash_attribution",
            "현금 귀속",
            "PASS",
            f"비지주 추정 · 현금 {_eok(cash)} · 별도분리 미검증",
        )
    return CheckItem(
        "cash_attribution",
        "현금 귀속",
        "U",
        "현금·지주 단서 없음",
    )


def _check_restricted_cash(fund: Mapping[str, str] | None) -> CheckItem:
    """Short-term financial assets vs cash — collateral notes still human."""
    row = fund or {}
    cash = _f(row.get("cash_and_equivalents"))
    if cash is None:
        cash = _f(row.get("cash_annual"))
    stfa = _f(row.get("short_term_financial_assets"))
    if cash is None:
        return CheckItem(
            "restricted_cash",
            "담보·제한예금",
            "U",
            "현금 계정 없음",
        )
    if stfa is None:
        return CheckItem(
            "restricted_cash",
            "담보·제한예금",
            "U",
            "단기금융자산 미기재 · 주석 확인",
        )
    if stfa <= 0:
        return CheckItem(
            "restricted_cash",
            "담보·제한예금",
            "PASS",
            "단기금융자산 0 관측 · 담보주석은 추가확인",
        )
    ratio = stfa / cash if cash > 0 else None
    note = f"단기금융자산 {_eok(stfa)}"
    if ratio is not None:
        note += f" · 현금대비 {ratio:.0%}"
    note += " · 담보·중도해지 주석 확인"
    # High STFA share → operator must not treat as free cash
    if ratio is not None and ratio >= 0.3:
        return CheckItem("restricted_cash", "담보·제한예금", "FAIL", note)
    return CheckItem("restricted_cash", "담보·제한예금", "PASS", note)


def _check_nav_double_count(
    name: str,
    fund: Mapping[str, str] | None,
) -> CheckItem:
    """Holding / NAV-discount proxy — locks double-count attention, not full NAV."""
    row = fund or {}
    nav_pct = _f(row.get("nav_discount_proxy_pct"))
    hold_proxy = _f(row.get("holding_company_discount_proxy"))
    is_hold = _is_holding_name(name) or (
        hold_proxy is not None and hold_proxy > 0
    )
    if is_hold:
        note = "지주·투자주식 장부 이중가산 주의"
        if nav_pct is not None:
            note += f" · NAV할인프록시 {nav_pct:.0f}%"
        return CheckItem("nav_double_count", "NAV 이중계산", "FAIL", note)
    if nav_pct is not None:
        return CheckItem(
            "nav_double_count",
            "NAV 이중계산",
            "PASS",
            f"NAV할인프록시 {nav_pct:.0f}% · 단순경로",
        )
    return CheckItem(
        "nav_double_count",
        "NAV 이중계산",
        "PASS",
        "비지주 추정 · 장부NAV 단순경로",
    )


def _overall(checks: Sequence[CheckItem]) -> tuple[str, list[str], str]:
    warns: list[str] = []
    fails = [c for c in checks if c.status == "FAIL"]
    auto_u = [c for c in checks if c.status == "U"]
    for c in fails:
        warns.append(c.label.replace(" ", "") + "FAIL")
    for c in auto_u:
        warns.append(c.label.replace(" ", "") + "U")
    if fails:
        return "warn", warns, "자동 검증 FAIL · 점수 불변 · Review"
    if auto_u:
        return "incomplete", warns, "캐시 미비 · 증분 갱신·하케다카 보강"
    return "ok", warns, "자동 검증 통과 · 주석 심층은 사람 Review"


def assign_review_verdict(row: ScreenVerifyRow) -> ScreenVerifyRow:
    """Map book + checks → operator action. Never touches scores/target."""
    fails = {c.key: c for c in row.checks if c.status == "FAIL"}
    us = [c for c in row.checks if c.status == "U"]

    if row.book == "대기":
        row.verdict = "parked"
        row.verdict_note = "게이트·적격 대기 · 비중 없음"
        return row
    if row.book == "관찰":
        row.verdict = "watch"
        row.verdict_note = "관찰 풀 · 제안 아님"
        return row

    # book == 제안
    hard = [fails[k] for k in _EXCLUDE_FAIL_KEYS if k in fails]
    if hard:
        row.verdict = "exclude_review"
        row.verdict_note = " · ".join(c.label for c in hard) + " · 편입 전 제외 검토"
        return row
    soft = [fails[k] for k in _HOLD_FAIL_KEYS if k in fails]
    if soft or us or row.overall in {"warn", "incomplete"}:
        row.verdict = "hold"
        bits = [c.label for c in soft] or []
        if us:
            bits.append(f"U {len(us)}항")
        row.verdict_note = (
            (" · ".join(bits) if bits else row.headline)
            + " · 보류 후 사람 Review"
        )
        return row
    row.verdict = "pass_review"
    row.verdict_note = "자동 심층 통과 · 사람만 target·주문"
    return row


def build_screen_verify(
    root: Path,
    *,
    data_dir: Path,
    tickers: Sequence[str],
    names: Mapping[str, str] | None = None,
    proposal_tickers: Sequence[str] | None = None,
    blocked_tickers: Sequence[str] | None = None,
    opendart_watch: Mapping[str, Any] | None = None,
    min_hits: int = 2,
    as_of: str = "",
) -> ScreenVerifyBoard:
    """Build deep-verify board from disk caches only (0 DART calls)."""
    root = Path(root)
    data_dir = Path(data_dir)
    name_map = dict(names or {})
    prop = {norm_ticker(t) for t in (proposal_tickers or []) if norm_ticker(t)}
    blocked = {norm_ticker(t) for t in (blocked_tickers or []) if norm_ticker(t)}
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        tk = norm_ticker(raw)
        if tk and tk not in seen:
            seen.add(tk)
            ordered.append(tk)

    watch = dict(opendart_watch or {})
    if not watch:
        from alpha_system.ui.services.cecs_opendart_pack import load_opendart_watch

        snap = load_opendart_watch(root, data_dir=data_dir)
        if snap is not None:
            watch = {
                "evidence": list(getattr(snap, "evidence", None) or []),
                "flags": [
                    {
                        "ticker": f.ticker,
                        "kind": f.kind,
                        "note": f.note,
                    }
                    for f in snap.flag_models()
                ],
                "metrics": list(getattr(snap, "metrics", None) or []),
            }

    ev_map = _ev_by_ticker(watch.get("evidence") if isinstance(watch, dict) else None)
    withdrawn = {tk for tk, _ in withdrawn_buyback_gate_candidates(list(ev_map.values()))}
    flag_kinds: dict[str, list[str]] = {}
    for item in (watch.get("flags") or []) if isinstance(watch, dict) else []:
        if not isinstance(item, Mapping):
            continue
        tk = norm_ticker(item.get("ticker"))
        if not tk:
            continue
        flag_kinds.setdefault(tk, []).append(str(item.get("kind") or ""))

    metrics_by: dict[str, dict[str, Any]] = {}
    for item in (watch.get("metrics") or []) if isinstance(watch, dict) else []:
        if not isinstance(item, Mapping):
            continue
        tk = norm_ticker(item.get("ticker"))
        if tk:
            metrics_by[tk] = dict(item)

    hk = load_hakedaka_inputs(root, data_dir=data_dir)
    fund_rows = load_hakedaka_fund_rows(root, data_dir=data_dir)
    rows: list[ScreenVerifyRow] = []
    for tk in ordered:
        name = name_map.get(tk, tk)
        fund = fund_rows.get(tk)
        checks = [
            _check_hakedaka(tk, hk, min_hits=min_hits),
            _check_evidence(tk, ev_map),
            _check_withdrawn(tk, withdrawn, ev_map),
            _check_control(tk, flag_kinds, metrics_by),
            _check_capital_waterfall(tk, fund, ev_map),
            _check_cash_attribution(tk, name, fund),
            _check_restricted_cash(fund),
            _check_nav_double_count(name, fund),
        ]
        overall, warns, headline = _overall(checks)
        row = ScreenVerifyRow(
            ticker=tk,
            name=name,
            book=_book_of(tk, prop, blocked),
            overall=overall,
            headline=headline,
            warn_tags=warns,
            checks=checks,
        )
        rows.append(assign_review_verdict(row))

    pri = {"제안": 0, "대기": 1, "관찰": 2}
    v_pri = {
        "exclude_review": 0,
        "hold": 1,
        "pass_review": 2,
        "parked": 3,
        "watch": 4,
    }
    rows.sort(
        key=lambda r: (
            pri.get(r.book, 9),
            v_pri.get(r.verdict, 9),
            r.ticker,
        )
    )

    return ScreenVerifyBoard(
        available=bool(rows),
        as_of=as_of or datetime.now(timezone.utc).date().isoformat(),
        evaluated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        model_version=MODEL_VERSION,
        source_note=(
            "하케다카 CSV + OpenDART watch · DART 0회 · "
            "판정=통과/보류/제외검토(점수·target 불변)"
        ),
        rows=rows,
    )


def screen_verify_attention_html(board: ScreenVerifyBoard) -> str:
    """Compact verdict chips only — name list lives in the join table."""
    if not board.available:
        return (
            '<div class="pf-od-empty">'
            "스크린 심층 검증 없음 · 「심층 다시 그리기」로 관찰·제안 풀을 평가하세요."
            "</div>"
        )

    n_pass = sum(1 for r in board.rows if r.verdict == "pass_review")
    n_hold = sum(1 for r in board.rows if r.verdict == "hold")
    n_ex = sum(1 for r in board.rows if r.verdict == "exclude_review")
    return (
        f'<div class="pf-od-verdict-sum">'
        f'<span class="pf-od-chip pf-od-chip-ok">통과 {n_pass}</span> '
        f'<span class="pf-od-chip pf-od-chip-warn">보류 {n_hold}</span> '
        f'<span class="pf-od-chip pf-od-chip-hot">제외검토 {n_ex}</span> '
        f'<span class="pf-od-verdict-hint">'
        "아래 한눈 표에서 제외검토·보류부터 · 사람만 target·주문"
        f"</span></div>"
        f'<div class="pf-od-routine">'
        "정량 → (정성) → 증분 → 심층 → 한눈 Review → 통과분만 집행"
        f"</div>"
    )


def warn_tags_for_join(row: ScreenVerifyRow) -> list[str]:
    return list(row.warn_tags)
