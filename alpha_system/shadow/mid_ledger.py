"""Shadow mid ledger — JSONL separate from target_portfolio / positions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from alpha_system.screen_book import operational_data_dir


def ledger_path(root: Path, market: object | None = None) -> Path:
    """KOSPI → data/shadow_mid_ledger.jsonl · KOSDAQ → data/books/kosdaq/…"""
    data = operational_data_dir(Path(root), market, "mid")
    return data / "shadow_mid_ledger.jsonl"


def load_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def append_day(path: Path, day: dict[str, Any]) -> None:
    """Append one day. Never writes target_portfolio.csv."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(day)
    payload.setdefault("review_only", True)
    payload.setdefault("writes_target", False)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def replace_ledger(path: Path, days: Iterable[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for day in days:
        payload = dict(day)
        payload.setdefault("review_only", True)
        payload.setdefault("writes_target", False)
        lines.append(json.dumps(payload, ensure_ascii=False))
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def summarize_ledger(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "n_days": 0,
            "nav_net": 1.0,
            "nav_gross": 1.0,
            "total_net_ret": 0.0,
            "total_gross_ret": 0.0,
            "max_drawdown": 0.0,
            "vs_market": 0.0,
            "vs_ew": 0.0,
            "avg_turnover": 0.0,
            "violations": 0,
            "quality": "insufficient",
            "as_of_first": "",
            "as_of_last": "",
        }

    navs = [float(r.get("nav_net") or 1.0) for r in rows]
    peak = navs[0]
    max_dd = 0.0
    for n in navs:
        peak = max(peak, n)
        if peak > 1e-12:
            max_dd = min(max_dd, (n / peak) - 1.0)

    def _cum(key: str) -> float:
        x = 1.0
        for r in rows:
            x *= 1.0 + float(r.get(key) or 0.0)
        return x - 1.0

    net = _cum("net_ret")
    gross = _cum("gross_ret")
    mkt = _cum("market_ret")
    ew = _cum("ew_ret")
    tov = sum(float(r.get("turnover") or 0.0) for r in rows) / len(rows)
    viol = sum(len(r.get("violations") or []) for r in rows)

    n = len(rows)
    if n <= 59:
        quality = "insufficient"
    elif n <= 179:
        quality = "preliminary"
    else:
        quality = "provisional"

    return {
        "n_days": n,
        "nav_net": navs[-1],
        "nav_gross": float(rows[-1].get("nav_gross") or navs[-1]),
        "total_net_ret": round(net, 8),
        "total_gross_ret": round(gross, 8),
        "max_drawdown": round(max_dd, 8),
        "vs_market": round(net - mkt, 8),
        "vs_ew": round(net - ew, 8),
        "avg_turnover": round(tov, 8),
        "violations": viol,
        "quality": quality,
        "as_of_first": str(rows[0].get("as_of") or ""),
        "as_of_last": str(rows[-1].get("as_of") or ""),
    }
