"""Paste / upsert kr_alpha rows into data/positions.csv (Review-only bookkeeping).

Preserves non-kr_alpha rows (cash, ETF, …). Does not write target_portfolio
or place orders.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

_ASSET_GROUP = "kr_alpha"
_COLS = [
    "ticker",
    "name",
    "asset_group",
    "sector",
    "style",
    "quantity",
    "current_value",
    "avg_price",
    "current_price",
]


@dataclass(frozen=True)
class HoldingDraft:
    ticker: str
    quantity: float
    avg_price: float | None
    name: str = ""


@dataclass(frozen=True)
class ParseResult:
    drafts: tuple[HoldingDraft, ...]
    errors: tuple[str, ...]
    raw_lines: int


def _norm_ticker(raw: str) -> str:
    s = str(raw).strip().upper().replace(".KS", "").replace(".KQ", "")
    if s.isdigit():
        return s.zfill(6)
    return s


def parse_holdings_paste(text: str) -> ParseResult:
    """Parse lines: ticker qty [avg_price]. Separators: space, tab, comma."""
    drafts: list[HoldingDraft] = []
    errors: list[str] = []
    lines = 0
    for i, line in enumerate((text or "").splitlines(), start=1):
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        lines += 1
        parts = [p for p in re.split(r"[\s,;|/]+", raw) if p]
        if len(parts) < 2:
            errors.append(f"{i}행: 종목코드와 수량이 필요합니다 — {raw}")
            continue
        # Allow "name ticker qty avg" by finding first digit ticker-like token
        ticker_i = 0
        for j, p in enumerate(parts):
            core = p.replace(".KS", "").replace(".KQ", "")
            if core.isdigit() and len(core) <= 6:
                ticker_i = j
                break
        try:
            tk = _norm_ticker(parts[ticker_i])
            qty = float(parts[ticker_i + 1].replace(",", ""))
        except (IndexError, ValueError):
            errors.append(f"{i}행: 파싱 실패 — {raw}")
            continue
        if qty < 0:
            errors.append(f"{i}행: 수량은 0 이상 — {raw}")
            continue
        avg: float | None = None
        if len(parts) > ticker_i + 2:
            try:
                avg = float(parts[ticker_i + 2].replace(",", ""))
            except ValueError:
                errors.append(f"{i}행: 평단 숫자 아님 — {raw}")
                continue
        name_bits = parts[:ticker_i]
        name = " ".join(name_bits) if name_bits else ""
        drafts.append(HoldingDraft(ticker=tk, quantity=qty, avg_price=avg, name=name))

    # Dedupe by ticker (last wins)
    by_tk: dict[str, HoldingDraft] = {}
    for d in drafts:
        by_tk[d.ticker] = d
    return ParseResult(
        drafts=tuple(by_tk.values()),
        errors=tuple(errors),
        raw_lines=lines,
    )


def _name_lookup(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in (
        "data/universe.csv",
        "data/prices.csv",
        "data/target_portfolio.csv",
        "alpha_portfolio/data/output/alpha_scores.csv",
    ):
        path = root / rel
        if not path.exists():
            continue
        try:
            df = pd.read_csv(path, dtype=str)
        except Exception:
            continue
        if "ticker" not in df.columns:
            continue
        name_col = "name" if "name" in df.columns else None
        if name_col is None:
            continue
        for _, row in df.iterrows():
            tk = _norm_ticker(str(row.get("ticker") or ""))
            nm = str(row.get(name_col) or "").strip()
            if tk and nm and tk not in out:
                out[tk] = nm
    return out


def _price_lookup(root: Path) -> dict[str, float]:
    path = root / "data" / "prices.csv"
    out: dict[str, float] = {}
    if not path.exists():
        return out
    try:
        df = pd.read_csv(path, dtype={"ticker": str})
    except Exception:
        return out
    if df.empty or "ticker" not in df.columns:
        return out
    df["ticker"] = df["ticker"].astype(str).str.zfill(6)
    if "date" in df.columns:
        df = df.sort_values("date").drop_duplicates("ticker", keep="last")
    close_col = "close" if "close" in df.columns else None
    if close_col is None:
        return out
    for _, row in df.iterrows():
        try:
            out[str(row["ticker"]).zfill(6)] = float(row[close_col])
        except (TypeError, ValueError):
            continue
    return out


def drafts_from_tickers(
    tickers: Sequence[str],
    *,
    root: Path,
    quantity: float = 0.0,
    avg_price: float | None = None,
) -> list[HoldingDraft]:
    """Build drafts for a ticker list (candidate pick / proposal fill)."""
    names = _name_lookup(root)
    out: list[HoldingDraft] = []
    seen: set[str] = set()
    for t in tickers:
        tk = _norm_ticker(str(t))
        if not tk.strip("0") and tk.isdigit():
            continue
        if tk in seen:
            continue
        seen.add(tk)
        out.append(
            HoldingDraft(
                ticker=tk,
                quantity=float(quantity),
                avg_price=avg_price,
                name=names.get(tk, ""),
            )
        )
    return out


def drafts_from_proposal_tickers(
    tickers: Sequence[str],
    *,
    root: Path,
) -> list[HoldingDraft]:
    """Empty qty rows for operator to fill — never invent quantities."""
    return drafts_from_tickers(tickers, root=root)


def upsert_kr_alpha_positions(
    positions_path: Path,
    drafts: Sequence[HoldingDraft],
    *,
    root: Path | None = None,
    replace_alpha: bool = True,
    keep_zero_qty: bool = False,
    keep_existing_meta: bool = False,
) -> dict[str, Any]:
    """Write kr_alpha block. Other asset_group rows kept intact.

    keep_existing_meta
        When True and a draft has qty<=0 / no avg, reuse existing kr_alpha
        quantity/avg for that ticker (candidate re-pick without wiping fills).
    """
    root = root or positions_path.parent.parent
    if positions_path.parent.name == "data":
        root = positions_path.parent.parent
    names = _name_lookup(root)
    prices = _price_lookup(root)

    if positions_path.exists():
        try:
            base = pd.read_csv(positions_path, dtype=str)
        except Exception:
            base = pd.DataFrame(columns=_COLS)
    else:
        base = pd.DataFrame(columns=_COLS)

    for col in _COLS:
        if col not in base.columns:
            base[col] = ""

    if "asset_group" in base.columns:
        keep = base[base["asset_group"].astype(str) != _ASSET_GROUP].copy()
        existing_alpha = base[base["asset_group"].astype(str) == _ASSET_GROUP].copy()
    else:
        keep = base.copy()
        existing_alpha = pd.DataFrame(columns=_COLS)

    existing_by_tk: dict[str, Any] = {}
    for _, row in existing_alpha.iterrows():
        existing_by_tk[_norm_ticker(str(row.get("ticker") or ""))] = row

    if not replace_alpha and "asset_group" in base.columns:
        # merge: update matching tickers, append new
        merged: dict[str, HoldingDraft] = {}
        for tk, row in existing_by_tk.items():
            try:
                q = float(row.get("quantity") or 0)
            except (TypeError, ValueError):
                q = 0.0
            try:
                ap = (
                    float(row.get("avg_price"))
                    if row.get("avg_price") not in (None, "")
                    else None
                )
            except (TypeError, ValueError):
                ap = None
            merged[tk] = HoldingDraft(
                ticker=tk,
                quantity=q,
                avg_price=ap,
                name=str(row.get("name") or ""),
            )
        for d in drafts:
            merged[d.ticker] = d
        drafts = list(merged.values())

    if keep_existing_meta:
        patched: list[HoldingDraft] = []
        for d in drafts:
            row = existing_by_tk.get(d.ticker)
            q = d.quantity
            ap = d.avg_price
            if row is not None:
                if q <= 0:
                    try:
                        q = float(row.get("quantity") or 0)
                    except (TypeError, ValueError):
                        q = 0.0
                if ap is None:
                    try:
                        raw = row.get("avg_price")
                        ap = float(raw) if raw not in (None, "") else None
                    except (TypeError, ValueError):
                        ap = None
            patched.append(
                HoldingDraft(
                    ticker=d.ticker,
                    quantity=q,
                    avg_price=ap,
                    name=d.name or (str(row.get("name") or "") if row is not None else ""),
                )
            )
        drafts = patched

    alpha_rows: list[dict[str, Any]] = []
    for d in drafts:
        if d.quantity <= 0 and not keep_zero_qty:
            # omit zero lines on normal paste save (delete by leaving out)
            continue
        cur_px = prices.get(d.ticker)
        avg = d.avg_price
        if cur_px is None and avg is not None:
            cur_px = avg
        value = 0.0
        if cur_px is not None and d.quantity:
            value = round(float(d.quantity) * float(cur_px), 0)
        elif avg is not None and d.quantity:
            value = round(float(d.quantity) * float(avg), 0)
        nm = d.name or names.get(d.ticker) or d.ticker
        alpha_rows.append(
            {
                "ticker": d.ticker,
                "name": nm,
                "asset_group": _ASSET_GROUP,
                "sector": "",
                "style": "",
                "quantity": d.quantity,
                "current_value": value,
                "avg_price": avg if avg is not None else "",
                "current_price": cur_px if cur_px is not None else "",
            }
        )

    alpha_df = (
        pd.DataFrame(alpha_rows, columns=_COLS)
        if alpha_rows
        else pd.DataFrame(columns=_COLS)
    )
    # Keep column order: non-alpha first, then alpha
    out = pd.concat([keep[_COLS], alpha_df], ignore_index=True)
    positions_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(positions_path, index=False)

    return {
        "ok": True,
        "alpha_count": len(alpha_rows),
        "kept_other": len(keep),
        "path": str(positions_path),
    }


def format_drafts_as_paste(drafts: Sequence[HoldingDraft]) -> str:
    lines: list[str] = []
    for d in drafts:
        if d.quantity and d.quantity > 0:
            avg = f" {d.avg_price:g}" if d.avg_price is not None else ""
            lines.append(f"{d.ticker} {d.quantity:g}{avg}")
        else:
            lines.append(d.ticker)
    return "\n".join(lines)
