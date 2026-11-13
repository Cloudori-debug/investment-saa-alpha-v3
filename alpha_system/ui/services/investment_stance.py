"""Active Soft investment stance — Review-only playbook (no target/QVM write).

Loads ``data/investment_stance.yaml``. Park Honggi / macro narrative is
operator guidance only — never auto-orders or Soft score add-ons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

STANCE_REL = Path("data") / "investment_stance.yaml"


@dataclass(frozen=True)
class InvestmentStance:
    active: str
    as_of: str
    title_ko: str
    phase: str
    equity_pct_hint: float | None
    cash_pct_hint: float | None
    household_note_ko: str
    do_ko: tuple[str, ...]
    dont_ko: tuple[str, ...]
    next_phase_ko: str
    source_url: str
    source_title: str
    research_card: str
    review_only: bool = True
    writes_target: bool = False

    @property
    def soft_split_ko(self) -> str:
        if self.equity_pct_hint is None or self.cash_pct_hint is None:
            return "Soft 비중 힌트 없음"
        return (
            f"Soft 힌트 개별주 {int(round(self.equity_pct_hint))}% / "
            f"단기채파킹 {int(round(self.cash_pct_hint))}%"
        )


def _as_list(raw: object) -> list[str]:
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    text = str(raw or "").strip()
    return [text] if text else []


def load_investment_stance(root: Path | str | None = None) -> InvestmentStance | None:
    """Return active stance or None if missing/disabled."""
    base = Path(root) if root else Path(".")
    path = base / STANCE_REL
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(raw, Mapping):
        return None
    active = str(raw.get("active") or "").strip()
    if not active or active.lower() in {"none", "off", "disabled"}:
        return None
    st = raw.get("stance") if isinstance(raw.get("stance"), Mapping) else {}
    soft = st.get("soft_book") if isinstance(st.get("soft_book"), Mapping) else {}
    src = raw.get("source") if isinstance(raw.get("source"), Mapping) else {}

    def _f(key: str, default: float | None = None) -> float | None:
        v = soft.get(key)
        if v is None or v == "":
            return default
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    return InvestmentStance(
        active=active,
        as_of=str(raw.get("as_of") or ""),
        title_ko=str(st.get("title_ko") or active),
        phase=str(st.get("phase") or ""),
        equity_pct_hint=_f("equity_pct_hint"),
        cash_pct_hint=_f("cash_pct_hint"),
        household_note_ko=str(st.get("household_note_ko") or "").strip(),
        do_ko=tuple(_as_list(raw.get("do_ko"))),
        dont_ko=tuple(_as_list(raw.get("dont_ko"))),
        next_phase_ko=str(raw.get("next_phase_ko") or "").strip(),
        source_url=str(src.get("url") or "").strip(),
        source_title=str(src.get("title_ko") or "").strip(),
        research_card=str(src.get("research_card") or "").strip(),
        review_only=bool(raw.get("review_only", True)),
        writes_target=bool(raw.get("writes_target", False)),
    )


def stance_todos(stance: InvestmentStance | None, *, limit: int = 4) -> list[str]:
    """Short todo lines for Trade-today / playbook append."""
    if stance is None:
        return []
    out = [f"방향: {stance.title_ko}", stance.soft_split_ko]
    out.extend(list(stance.do_ko[: max(0, int(limit))]))
    return out


def investment_stance_html(stance: InvestmentStance | None) -> str:
    """Portfolio / economy banner — Review-only."""
    if stance is None:
        return ""
    esc = escape
    do_li = "".join(f"<li>{esc(x)}</li>" for x in stance.do_ko)
    dont_li = "".join(f"<li>{esc(x)}</li>" for x in stance.dont_ko)
    src = ""
    if stance.source_url:
        src = (
            f'<a class="pf-stance-link" href="{esc(stance.source_url)}" '
            f'target="_blank" rel="noopener noreferrer">'
            f"{esc(stance.source_title or '출처')}</a>"
        )
    next_p = (
        f'<p class="pf-stance-next">{esc(stance.next_phase_ko)}</p>'
        if stance.next_phase_ko
        else ""
    )
    house = (
        f'<p class="pf-stance-house">{esc(stance.household_note_ko)}</p>'
        if stance.household_note_ko
        else ""
    )
    return (
        '<div class="pf-stance" role="region" aria-label="투자 방향">'
        '<div class="pf-stance-h">'
        f"{esc(stance.title_ko)}"
        '<span class="pf-stance-sub">Review-only · target·QVM 불변</span>'
        "</div>"
        f'<div class="pf-stance-split">{esc(stance.soft_split_ko)}</div>'
        f"{house}"
        '<div class="pf-stance-cols">'
        f'<div class="pf-stance-col"><div class="pf-stance-k">한다</div><ul>{do_li}</ul></div>'
        f'<div class="pf-stance-col pf-stance-dont"><div class="pf-stance-k">하지 않는다</div><ul>{dont_li}</ul></div>'
        "</div>"
        f"{next_p}"
        f'<div class="pf-stance-foot">{src}'
        f' · as_of {esc(stance.as_of)} · {esc(stance.active)}</div>'
        "</div>"
    )


def merge_playbook_cards(
    cards: Sequence[tuple[str, str]],
    stance: InvestmentStance | None,
) -> tuple[tuple[str, str], ...]:
    """Prepend stance tone to economy playbook action lines."""
    base = list(cards or [])
    if stance is None:
        return tuple(base)
    head = [
        ("방향", stance.title_ko),
        ("Soft힌트", stance.soft_split_ko),
    ]
    if stance.do_ko:
        head.append(("한다", stance.do_ko[0]))
    if stance.dont_ko:
        head.append(("금지", stance.dont_ko[0]))
    # keep stage cards after stance
    return tuple(head + base)


__all__ = [
    "InvestmentStance",
    "STANCE_REL",
    "load_investment_stance",
    "stance_todos",
    "investment_stance_html",
    "merge_playbook_cards",
]
