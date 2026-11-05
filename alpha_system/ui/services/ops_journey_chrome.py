"""운영 여정 스트립 — 가계 본체 + 알파 위성 · 일상 최신화 경로 명시."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any

from alpha_system.ui.services import nav as _nav
from alpha_system.ui.services.refresh import quant_refresh_when
from alpha_system.ui.services.ui_copy import copy_get

PAGE_APPROVAL = _nav.PAGE_APPROVAL
PAGE_PORTFOLIO = _nav.PAGE_PORTFOLIO
PAGE_ECONOMY = _nav.PAGE_ECONOMY
# 전략·백테스트 페이지는 신 IA에만 있음 · 구 nav 호환
_NAV_STRATEGY = frozenset(getattr(_nav, "NAV_STRATEGY_PAGES", ()) or ())
_PAGE_BACKTEST = str(getattr(_nav, "PAGE_BACKTEST", "") or "")
_BODY_PAGES = frozenset(
    p for p in (*_NAV_STRATEGY, _PAGE_BACKTEST) if p
)

_KST = timezone(timedelta(hours=9))

# 일상 순서 (백테스트는 전략 심화로 묶음)
_STEPS: tuple[tuple[str, str, frozenset[str]], ...] = (
    (
        "1 데이터",
        "확인① 정량·정성",
        frozenset({PAGE_APPROVAL}),
    ),
    (
        "2 본체",
        "전략 탭 운용 · 전체 비교",
        _BODY_PAGES or frozenset({PAGE_PORTFOLIO}),
    ),
    (
        "3 알파",
        "포트 Soft 매매 UI",
        frozenset({PAGE_PORTFOLIO}),
    ),
    (
        "4 태도",
        "나침반 Review",
        frozenset({PAGE_ECONOMY}),
    ),
)


def _hh_lab_when(root: Path) -> str | None:
    try:
        from alpha_system.shadow.household_alloc_lab import load_report

        raw = load_report(root)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(raw, dict):
        return None
    generated = str(raw.get("as_of") or "").strip()
    if not generated:
        return None
    try:
        dt = datetime.fromisoformat(generated.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_KST).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return generated[:16]


def household_lab_is_stale(root: Path, *, max_age_hours: float = 24.0) -> bool:
    """True if missing or older than max_age_hours."""
    try:
        from alpha_system.shadow.household_alloc_lab import load_report

        raw = load_report(root)
    except Exception:  # noqa: BLE001
        return True
    if not isinstance(raw, dict) or not raw.get("ok"):
        return True
    generated = str(raw.get("as_of") or "").strip()
    if not generated:
        return True
    try:
        dt = datetime.fromisoformat(generated.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    age = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
    return age > timedelta(hours=float(max_age_hours))


def maybe_refresh_household_lab_after_quant(
    root: Path,
    *,
    force: bool = False,
    max_age_hours: float = 24.0,
) -> dict[str, Any]:
    """확인① 성공 후 가계 ETF Lab — 하루 1회·실패 비치명 · Soft/target 불변."""
    out: dict[str, Any] = {"skipped": False, "ok": False}
    if not force and not household_lab_is_stale(root, max_age_hours=max_age_hours):
        out["skipped"] = True
        out["ok"] = True
        out["reason"] = "fresh"
        return out
    try:
        from alpha_system.shadow.household_alloc_lab import (
            run_household_alloc_lab,
            save_report,
        )

        report = run_household_alloc_lab(Path(root), ensure_fetch=True)
        path = save_report(Path(root), report)
        out["ok"] = bool(report.ok)
        out["path"] = str(path)
        out["n_ok"] = sum(1 for s in report.strategies if s.ok)
        out["writes_target"] = False
    except Exception as exc:  # noqa: BLE001
        out["ok"] = False
        out["error"] = str(exc)[:240]
    return out


def render_ops_journey(root: Path, *, page: str) -> None:
    """모든 주메뉴 상단 — 여정 + 신선도 + 한 줄 운영."""
    import streamlit as st

    active = str(page or "")
    bits: list[str] = []
    for title, hint, pages in _STEPS:
        on = active in pages
        cls = "ops-j-step ops-j-on" if on else "ops-j-step"
        bits.append(
            f'<div class="{cls}" title="{escape(hint)}">'
            f'<div class="ops-j-t">{escape(title)}</div>'
            f'<div class="ops-j-h">{escape(hint)}</div>'
            f"</div>"
        )
    quant_when = quant_refresh_when(root) or "미실행"
    hh_when = _hh_lab_when(root) or "미실행"
    fresh = copy_get(
        "ops_journey",
        "fresh_line",
        default="정량 {q} · 가계ETF Lab {h} · 일상 최신화=확인① 한 번",
        q=quant_when,
        h=hh_when,
    )
    rule = copy_get(
        "ops_journey",
        "rule_line",
        default=(
            "본체 70~90%(전략 비교) · 알파 Soft 10~30%(포트) · "
            "합산 집행·target 자동 없음 · Review-only"
        ),
    )
    st.markdown(
        '<div class="ops-j" role="navigation" aria-label="운영 여정">'
        f'<div class="ops-j-row">{"".join(bits)}</div>'
        f'<div class="ops-j-fresh">{escape(fresh)}</div>'
        f'<div class="ops-j-rule">{escape(rule)}</div>'
        "</div>",
        unsafe_allow_html=True,
    )
    try:
        from alpha_system.ui.services.data_fetch_alerts import render_data_fetch_alerts

        render_data_fetch_alerts(Path(root))
    except Exception:  # noqa: BLE001 — never block chrome
        pass
    try:
        from alpha_system.ui.services.system_health import render_system_health_strip

        render_system_health_strip(Path(root))
    except Exception:  # noqa: BLE001 — never block chrome
        pass


__all__ = [
    "household_lab_is_stale",
    "maybe_refresh_household_lab_after_quant",
    "render_ops_journey",
]
