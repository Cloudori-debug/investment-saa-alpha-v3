"""One trade-and-hold row per name. Scores stay on the check page.

Review-only. Does not write target_portfolio.csv and does not send orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alpha_system.ui.services.trail_exit_signal import trail_path_state

ACTION_SELL = "팔기"
ACTION_TRIM = "줄이기"
ACTION_HOLD = "유지"
ACTION_BUY = "사기"
ACTION_CLEAR = "정리"

_ACTION_ORDER = {
    ACTION_SELL: 0,
    ACTION_TRIM: 1,
    ACTION_CLEAR: 2,
    ACTION_HOLD: 3,
    ACTION_BUY: 4,
}


@dataclass(frozen=True)
class TradeDeskRow:
    action: str
    ticker: str
    name: str
    held: str
    proposal: str
    price: float | None
    signal: str


def load_snapshot_closes(
    root: Path, tickers: set[str]
) -> tuple[dict[str, str], dict[str, float]]:
    """Per-ticker as-of date and latest close from data/prices.csv."""
    path = root / "data" / "prices.csv"
    if not path.exists() or not tickers:
        return {}, {}
    wanted = {t.zfill(6) if t.isdigit() else t for t in tickers}
    out: dict[str, float] = {}
    as_of: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return {}, {}
    lines = text.splitlines()
    if not lines:
        return {}, {}
    header = [c.strip().lstrip("\ufeff") for c in lines[0].split(",")]
    try:
        i_tk = header.index("ticker")
    except ValueError:
        return {}, {}
    i_dt = header.index("date") if "date" in header else None
    i_px = None
    for name in ("close", "current_price", "price"):
        if name in header:
            i_px = header.index(name)
            break
    if i_px is None:
        return {}, {}
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) <= max(i_tk, i_px):
            continue
        raw = parts[i_tk].strip()
        tk = raw.zfill(6) if raw.isdigit() else raw
        if tk not in wanted:
            continue
        try:
            px = float(parts[i_px])
        except ValueError:
            continue
        if px > 0:
            out[tk] = px
            if i_dt is not None and i_dt < len(parts):
                as_of[tk] = parts[i_dt].strip()
    return as_of, out


def load_snapshot_prices(root: Path, tickers: set[str]) -> dict[str, float]:
    """Latest close from data/prices.csv for the given tickers."""
    _as_of, prices = load_snapshot_closes(root, tickers)
    return prices


def load_dated_closes(
    root: Path, tickers: set[str]
) -> dict[str, list[tuple[str, float]]]:
    """Daily (date, close) from the local replay file. Missing file yields {}."""
    path = root / "data" / "local" / "proposal_replay_prices.csv"
    if not path.exists() or not tickers:
        return {}
    wanted = {t.zfill(6) if t.isdigit() else t for t in tickers}
    buckets: dict[str, list[tuple[str, float]]] = {t: [] for t in wanted}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    lines = text.splitlines()
    if not lines:
        return {}
    header = [c.strip() for c in lines[0].split(",")]
    try:
        i_tk = header.index("ticker")
        i_dt = header.index("date")
        i_px = header.index("close")
    except ValueError:
        return {}
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) <= max(i_tk, i_dt, i_px):
            continue
        raw = parts[i_tk].strip()
        tk = raw.zfill(6) if raw.isdigit() else raw
        if tk not in wanted:
            continue
        try:
            px = float(parts[i_px])
        except ValueError:
            continue
        if px <= 0:
            continue
        buckets[tk].append((parts[i_dt].strip(), px))
    out: dict[str, list[tuple[str, float]]] = {}
    for tk, rows in buckets.items():
        rows.sort(key=lambda item: item[0])
        if rows:
            out[tk] = rows
    return out


def load_close_series(root: Path, tickers: set[str]) -> dict[str, list[float]]:
    """Daily closes from the local replay file. Missing file yields {}."""
    dated = load_dated_closes(root, tickers)
    return {tk: [px for _, px in rows] for tk, rows in dated.items()}


def _norm(ticker: str) -> str:
    try:
        from alpha_system.proposal_chart import norm_ticker

        tk = norm_ticker(ticker)
        if tk:
            return tk
    except Exception:  # noqa: BLE001
        pass
    raw = str(ticker or "").strip()
    return raw.zfill(6) if raw.isdigit() else raw


def _held_label(qty: float | None) -> str:
    if qty is None:
        return "—"
    if qty > 0:
        return "보유"
    return "수량 0"


def _signal(
    *,
    band: int,
    drawdown: float,
    jump: str | None,
    in_proposal: bool,
    qty: float | None,
    action: str,
) -> str:
    parts: list[str] = []
    exit_like = action in (ACTION_SELL, ACTION_TRIM)
    if jump and (exit_like or action == ACTION_CLEAR):
        parts.append("하루 점프")
    if exit_like:
        if band >= 3:
            parts.append("전량")
        elif band == 2:
            parts.append("절반")
        elif band == 1:
            parts.append("25%")
        if drawdown > 0:
            parts.append(f"고점 −{drawdown * 100:.1f}%")
    elif action == ACTION_BUY and drawdown >= 0.12:
        # 미보유 Soft 신규: 낙폭은 참고만 · 팔기/줄이기로 바꾸지 않음
        parts.append(f"고점대비 −{drawdown * 100:.1f}% 참고")
    if in_proposal and exit_like:
        parts.append("제안에는 있음")
    if action == ACTION_CLEAR:
        parts.append("수량 0")
    if action == ACTION_HOLD and not parts:
        parts.append("보유 유지")
    elif action == ACTION_BUY:
        parts.append("신규")
    elif (
        qty is not None
        and qty > 0
        and not parts
        and not in_proposal
        and action not in (ACTION_SELL, ACTION_TRIM, ACTION_CLEAR)
    ):
        parts.append("제안 밖")
    return " · ".join(parts)


def build_trade_desk(
    *,
    proposal: list[tuple[str, str, float | None]],
    holdings: list[tuple[str, str, float]],
    closes_by_ticker: dict[str, list[float]] | None = None,
    live_price: dict[str, float] | None = None,
) -> list[TradeDeskRow]:
    """One row for each proposed or held name. Watch-only names stay off this table."""
    closes_by_ticker = closes_by_ticker or {}
    live_price = live_price or {}
    names: dict[str, str] = {}
    in_prop: set[str] = set()
    qty_by: dict[str, float] = {}
    price_by: dict[str, float] = {}

    for ticker, name, price in proposal:
        tk = _norm(ticker)
        if not tk:
            continue
        in_prop.add(tk)
        if name:
            names[tk] = name
        if price is not None and price > 0:
            price_by[tk] = float(price)
    for ticker, name, qty in holdings:
        tk = _norm(ticker)
        if not tk:
            continue
        qty_by[tk] = float(qty)
        if name and tk not in names:
            names[tk] = name

    rows: list[TradeDeskRow] = []
    for tk in sorted(in_prop | set(qty_by)):
        qty = qty_by.get(tk)
        proposed = tk in in_prop
        if not proposed and qty is None:
            continue
        series = list(closes_by_ticker.get(tk) or [])
        live = live_price.get(tk) or price_by.get(tk)
        if live is not None and live > 0 and (
            not series or abs(series[-1] - live) / live > 0.001
        ):
            series.append(float(live))
        band, drawdown, jump = trail_path_state(series) if len(series) >= 2 else (0, 0.0, None)
        held_shares = qty is not None and qty > 0
        # 트레일 팔기/줄이기 = 실보유(또는 수량0 장부행)만.
        # 미보유 Soft 제안에 고점낙폭을 적용해 「팔기」로 뒤집지 않음.
        on_book = qty is not None
        if held_shares and (band >= 3 or not proposed):
            action = ACTION_SELL
        elif held_shares and band >= 1:
            action = ACTION_TRIM
        elif proposed and on_book and band >= 3:
            action = ACTION_SELL
        elif proposed and on_book and band >= 1:
            action = ACTION_TRIM
        elif proposed and held_shares:
            action = ACTION_HOLD
        elif proposed:
            action = ACTION_BUY
        elif qty is not None:
            action = ACTION_CLEAR
        else:
            continue
        shown = live if live is not None and live > 0 else (series[-1] if series else None)
        rows.append(
            TradeDeskRow(
                action=action,
                ticker=tk,
                name=names.get(tk) or tk,
                held=_held_label(qty),
                proposal="예" if proposed else "—",
                price=shown,
                signal=_signal(
                    band=band,
                    drawdown=drawdown,
                    jump=jump,
                    in_proposal=proposed,
                    qty=qty,
                    action=action,
                ),
            )
        )
    rows.sort(key=lambda row: (_ACTION_ORDER.get(row.action, 9), row.name))
    return rows
