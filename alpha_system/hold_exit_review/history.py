"""Weekly proposal membership log (local, gitignored)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Iterable

from alpha_system.proposal_chart import norm_ticker


def _week_key(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def append_proposal_snapshot(
    path: Path,
    *,
    as_of: date,
    market: str,
    horizon: str,
    proposal_tickers: Iterable[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tickers = sorted({norm_ticker(t) for t in proposal_tickers if norm_ticker(t)})
    row = {
        "week": _week_key(as_of),
        "as_of": as_of.isoformat(),
        "market": market,
        "horizon": horizon,
        "tickers": tickers,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def weeks_out_of_proposal(
    path: Path,
    *,
    ticker: str,
    market: str,
    horizon: str,
    as_of: date,
) -> int:
    """Consecutive weeks (including current) ticker absent from proposal set."""
    tk = norm_ticker(ticker)
    if not tk or not path.is_file():
        return 0
    by_week: dict[str, set[str]] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(rec.get("market") or "") != market:
                continue
            if str(rec.get("horizon") or "") != horizon:
                continue
            wk = str(rec.get("week") or "")
            if not wk:
                continue
            by_week[wk] = {norm_ticker(t) for t in (rec.get("tickers") or [])}
    weeks = sorted(by_week.keys())
    if not weeks:
        return 0
    current = _week_key(as_of)
    if current not in weeks:
        weeks.append(current)
        weeks.sort()
    streak = 0
    for wk in reversed(weeks):
        if wk > current:
            continue
        if tk in by_week.get(wk, set()):
            break
        streak += 1
    return streak
