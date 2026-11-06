"""기업해부 판정 파일 → 알파 Review 관문.

점수·target에 더하지 않는다. HOLD는 판단 보류이며 보유 권고가 아니다.
PASS가 가격일 또는 다음 확인일보다 오래되면 HOLD로 되돌린다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from alpha_system.proposal_chart import norm_ticker

SCHEMA = "alpha-gieop-verdict/v1"
GATE_FAIL = "FAIL"
GATE_HOLD = "HOLD"
GATE_PASS = "PASS"
_GATES = frozenset({GATE_FAIL, GATE_HOLD, GATE_PASS})
_DATE = re.compile(r"(20\d{2}-\d{2}-\d{2})")


@dataclass(frozen=True)
class GieopVerdict:
    ticker: str
    company: str
    as_of: str
    price_date: str
    gate: str
    effective_gate: str
    blockers: tuple[str, ...]
    next_check: str
    report: str
    stale: bool = False
    stale_reason: str = ""

    @property
    def chip_ko(self) -> str:
        if self.effective_gate == GATE_PASS:
            return "해부 PASS"
        base = f"해부 {self.effective_gate}"
        if self.stale:
            base += " · 오래됨"
        if self.blockers:
            return f"{base} · {self.blockers[0]}"
        if self.stale and self.stale_reason:
            return f"{base} · {self.stale_reason}"
        return base


def parse_iso_date(text: object) -> date | None:
    match = _DATE.search(str(text or ""))
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def _effective(
    gate: str,
    *,
    price_date: str,
    next_check: str,
    today: date,
    book_price: date | None,
) -> tuple[str, bool, str]:
    if gate != GATE_PASS:
        return gate, False, ""
    reasons: list[str] = []
    priced = parse_iso_date(price_date)
    if priced is None:
        reasons.append("가격일 없음")
    elif book_price is not None and book_price > priced:
        reasons.append("장부 가격일이 판정보다 새로움")
    nxt = parse_iso_date(next_check)
    if nxt is not None and today > nxt:
        reasons.append("다음 확인일이 지남")
    if reasons:
        return GATE_HOLD, True, " · ".join(reasons)
    return GATE_PASS, False, ""


def parse_verdict(
    raw: object,
    *,
    today: date | None = None,
    book_price_date: str | None = None,
) -> GieopVerdict | None:
    if not isinstance(raw, dict):
        return None
    if str(raw.get("schema") or "") != SCHEMA:
        return None
    ticker = norm_ticker(raw.get("ticker"))
    gate = str(raw.get("gate") or "").strip().upper()
    if not ticker or gate not in _GATES:
        return None
    today = today or date.today()
    price_date = str(raw.get("price_date") or "")
    next_check = str(raw.get("next_check") or "")
    blockers_raw = raw.get("blockers") if isinstance(raw.get("blockers"), list) else []
    blockers = tuple(str(b).strip() for b in blockers_raw if str(b).strip())
    effective, stale, why = _effective(
        gate,
        price_date=price_date,
        next_check=next_check,
        today=today,
        book_price=parse_iso_date(book_price_date or ""),
    )
    return GieopVerdict(
        ticker=ticker,
        company=str(raw.get("company") or ""),
        as_of=str(raw.get("as_of") or ""),
        price_date=price_date,
        gate=gate,
        effective_gate=effective,
        blockers=blockers,
        next_check=next_check,
        report=str(raw.get("report") or ""),
        stale=stale,
        stale_reason=why,
    )


def load_verdicts(
    drafts_dir: Path,
    *,
    today: date | None = None,
    book_price_date: str | None = None,
) -> dict[str, GieopVerdict]:
    """내조사/verdicts/*.json. 시드 과제 상태는 읽지 않는다."""
    folder = Path(drafts_dir) / "verdicts"
    if not folder.is_dir():
        return {}
    today = today or date.today()
    out: dict[str, GieopVerdict] = {}
    files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for path in files:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        verdict = parse_verdict(raw, today=today, book_price_date=book_price_date)
        if verdict is None:
            continue
        prev = out.get(verdict.ticker)
        if prev is None or (verdict.as_of or "") >= (prev.as_of or ""):
            out[verdict.ticker] = verdict
    return out


def review_lock(
    *,
    action: str,
    action_ko: str,
    hint: str,
    verdict: GieopVerdict | None,
    buy_action: str,
) -> tuple[str, str, str, bool] | None:
    """사 Review 잠금. None이면 매수 Review 후보에서 뺀다. target은 쓰지 않는다."""
    if verdict is None:
        return action, action_ko, hint, False
    gate = verdict.effective_gate
    chip = verdict.chip_ko
    if gate == GATE_FAIL and action == buy_action:
        return None
    if gate == GATE_HOLD and action == buy_action:
        return (
            action,
            "사 Review 잠금",
            f"{chip} · 실행 전 · target 사람만",
            True,
        )
    if gate == GATE_FAIL:
        return action, action_ko, f"{chip} · target 사람만", True
    if gate == GATE_PASS and action == buy_action:
        return action, action_ko, "해부 PASS · 하루≤33% · target 사람만", False
    if gate == GATE_PASS:
        return action, action_ko, f"{chip} · target 사람만", False
    return action, action_ko, hint, False
