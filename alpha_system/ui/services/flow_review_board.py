"""Review-only investor flow cues for proposal / holdings rows.

Uses alpha `data/investor_flows.csv` only (PyKRX). Does not call the sibling
수급 브리핑 app, and never writes scores or target_portfolio.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from src.alpha.investor_flows import get_flow_for_ticker

_SIGNAL_KO = {
    "ACCUMULATION": "매집",
    "MILD_ACCUMULATION": "약한매집",
    "NEUTRAL": "중립",
    "DISTRIBUTION": "분산",
    "STALE": "오래됨",
}

_SIGNAL_TONE = {
    "ACCUMULATION": "ok",
    "MILD_ACCUMULATION": "ok",
    "NEUTRAL": "muted",
    "DISTRIBUTION": "warn",
    "STALE": "muted",
}


def _pct(v: object) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_mcap_pct(v: float | None) -> str:
    if v is None:
        return "—"
    # Narrow minus for tabular readability
    s = f"{v:+.2f}%"
    return s.replace("-", "−")


def flow_info_for_ticker(data_dir: Path | None, ticker: str) -> dict[str, Any]:
    if data_dir is None:
        return {
            "flow_signal": "STALE",
            "flow_score": 0.0,
            "staleness_days": 999,
            "source": "missing",
        }
    return get_flow_for_ticker(Path(data_dir), ticker)


def flow_chip_html(data_dir: Path | None, ticker: str) -> str:
    """Deprecated for row chrome — keep for callers; strip carries the cue."""
    _ = data_dir, ticker
    return ""


def flow_inline_html(data_dir: Path | None, ticker: str) -> str:
    """Single readable strip under the name row (proposal + holdings)."""
    info = flow_info_for_ticker(data_dir, ticker)
    sig = str(info.get("flow_signal") or "STALE")
    source = str(info.get("source") or "")
    ko = _SIGNAL_KO.get(sig, sig)
    tone = _SIGNAL_TONE.get(sig, "muted")

    if sig == "STALE" and source in {"missing", "template", ""}:
        return (
            f'<div class="pf-flow-strip pf-flow-strip-muted" title="Review-only · 점수 불변">'
            f'<span class="pf-flow-kicker">수급</span>'
            f'<span class="pf-flow-state">데이터 없음</span>'
            f"</div>"
        )

    f5_raw = _pct(info.get("foreign_5d_mcap_pct"))
    i5_raw = _pct(info.get("institution_5d_mcap_pct"))
    f5 = _fmt_mcap_pct(f5_raw)
    i5 = _fmt_mcap_pct(i5_raw)

    def _dir(v: float | None) -> str:
        if v is None or abs(v) < 1e-12:
            return "flat"
        return "up" if v > 0 else "down"

    f_cls = _dir(f5_raw)
    i_cls = _dir(i5_raw)
    return (
        f'<div class="pf-flow-strip pf-flow-strip-{escape(tone)}" '
        f'title="Review-only · 점수·target 불변">'
        f'<span class="pf-flow-kicker">수급</span>'
        f'<span class="pf-flow-state">{escape(ko)}</span>'
        f'<span class="pf-flow-metric">'
        f'<span class="pf-flow-mk">외인 5일</span>'
        f'<span class="pf-flow-mv pf-flow-mv-{f_cls}">{escape(f5)}</span>'
        f"</span>"
        f'<span class="pf-flow-metric">'
        f'<span class="pf-flow-mk">기관 5일</span>'
        f'<span class="pf-flow-mv pf-flow-mv-{i_cls}">{escape(i5)}</span>'
        f"</span>"
        f"</div>"
    )
