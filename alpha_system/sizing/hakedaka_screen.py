"""Hakedaka sequential gate — four binary hits on top of QVM.

Does not change total_score, blend CECS, or write target_portfolio.csv.

Fail-open unless at least ``min_hits`` metrics are actually measured.
A single known miss (or the old CSV default ``related_party_risk_flag=False``)
must not eject a QVM name. Circular ownership is a hit only when True —
False in the July CSV is not an FTC verification.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from alpha_system.sizing.qual_overlay import norm_ticker

HAKEDAKA_CSV = "hakedaka_fundamentals.csv"
WATCH_FILENAME = "opendart_proposal_watch.json"
PAYOUT_CACHE = "opendart_payout_sr4.json"
FTC_CACHE = ("cache", "ftc_circular.json")

# 15~20% band plus 근접 (±2.5pp). Values are percent, not fractions.
OWNER_BAND_LOW = 12.5
OWNER_BAND_HIGH = 22.5
NET_CASH_MIN = 0.0
TREASURY_MIN = 0.0


@dataclass(frozen=True)
class HakedakaHits:
    ticker: str
    net_cash: bool | None
    treasury: bool | None
    owner_band: bool | None
    circular: bool | None
    known: int
    hits: int
    passed: bool
    detail: str


@dataclass
class HakedakaInputs:
    net_cash_to_mcap: dict[str, float] = field(default_factory=dict)
    treasury_ratio: dict[str, float] = field(default_factory=dict)
    buyback: dict[str, bool] = field(default_factory=dict)
    owner_pct: dict[str, float] = field(default_factory=dict)
    circular_flag: dict[str, bool] = field(default_factory=dict)


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


def _boolish(raw: object) -> bool | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except (OSError, csv.Error):
        return []


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def load_hakedaka_inputs(
    root: Path,
    *,
    data_dir: Path | None = None,
) -> HakedakaInputs:
    """Merge CSV + OpenDART watch/payout caches. Never calls the network."""
    root = Path(root)
    book = Path(data_dir) if data_dir is not None else root / "data"
    shared = root / "data"
    out = HakedakaInputs()

    # Shared first, then the active book so KOSDAQ rows win on overlap.
    bases: list[Path] = []
    if shared.resolve() != book.resolve():
        bases.append(shared)
    bases.append(book)
    for base in bases:
        for row in _read_csv_rows(base / HAKEDAKA_CSV):
            ticker = norm_ticker(row.get("ticker"))
            if not ticker:
                continue
            ncm = _f(row.get("net_cash_to_market_cap"))
            if ncm is not None:
                out.net_cash_to_mcap[ticker] = ncm
            tre = _f(row.get("treasury_share_ratio"))
            if tre is not None:
                out.treasury_ratio[ticker] = tre
            owner = _f(row.get("largest_shareholder_pct"))
            if owner is not None:
                out.owner_pct[ticker] = owner
            circ = _boolish(row.get("related_party_risk_flag"))
            gov = _boolish(row.get("governance_event_flag"))
            # Only a positive flag is evidence of circular/affiliate risk.
            # CSV False is a default, not a Fair Trade Commission check.
            if circ is True or gov is True:
                out.circular_flag[ticker] = True

    watch = _load_json(book / WATCH_FILENAME)
    if not watch and book.resolve() != shared.resolve():
        watch = _load_json(shared / WATCH_FILENAME)
    for item in watch.get("metrics") or []:
        if not isinstance(item, Mapping):
            continue
        ticker = norm_ticker(item.get("ticker"))
        if not ticker:
            continue
        owner = _f(item.get("largest_shareholder_pct"))
        if owner is not None:
            out.owner_pct[ticker] = owner
        if item.get("buyback"):
            out.buyback[ticker] = True

    payout = _load_json(book / PAYOUT_CACHE)
    if not payout and book.resolve() != shared.resolve():
        payout = _load_json(shared / PAYOUT_CACHE)
    rows = payout.get("rows") if isinstance(payout.get("rows"), dict) else {}
    for raw_tk, raw_row in rows.items():
        ticker = norm_ticker(raw_tk)
        if not ticker or not isinstance(raw_row, Mapping):
            continue
        if raw_row.get("buyback_3y"):
            out.buyback[ticker] = True

    ftc = _load_json(shared.joinpath(*FTC_CACHE))
    if not ftc:
        ftc = _load_json(book.joinpath(*FTC_CACHE))
    for raw_tk in ftc.get("tickers") or []:
        ticker = norm_ticker(raw_tk)
        if ticker:
            out.circular_flag[ticker] = True

    return out


def evaluate_hakedaka(
    ticker: str,
    inputs: HakedakaInputs,
    *,
    min_hits: int = 2,
    owner_low: float = OWNER_BAND_LOW,
    owner_high: float = OWNER_BAND_HIGH,
    net_cash_min: float = NET_CASH_MIN,
    treasury_min: float = TREASURY_MIN,
) -> HakedakaHits:
    tk = norm_ticker(ticker)
    ncm = inputs.net_cash_to_mcap.get(tk)
    net_cash = None if ncm is None else bool(ncm > net_cash_min)

    tre = inputs.treasury_ratio.get(tk)
    buy = inputs.buyback.get(tk)
    treasury: bool | None
    if tre is not None:
        treasury = bool(tre > treasury_min) or bool(buy)
    elif buy is True:
        treasury = True
    else:
        treasury = None

    owner = inputs.owner_pct.get(tk)
    if owner is not None and 0 < owner < 1.5:
        # OpenDART sometimes emits a 0–1 fraction instead of percent.
        owner = owner * 100.0
    owner_band = None if owner is None else bool(owner_low <= owner <= owner_high)

    circular = inputs.circular_flag.get(tk)
    if circular is True:
        circular = True
    else:
        circular = None

    flags = (net_cash, treasury, owner_band, circular)
    known = sum(1 for item in flags if item is not None)
    hits = sum(1 for item in flags if item is True)
    need = max(1, int(min_hits))
    if known < need:
        passed = True
        detail = (
            "하케다카 지표 없음 (미차단)"
            if known == 0
            else f"하케다카 {hits}/{known} (판정 보류 · 필요 {need})"
        )
    else:
        passed = hits >= need
        detail = f"하케다카 {hits}/{known} (필요 {need})"
        if not passed:
            detail += " · 게이트 미달"
    return HakedakaHits(
        ticker=tk,
        net_cash=net_cash,
        treasury=treasury,
        owner_band=owner_band,
        circular=circular,
        known=known,
        hits=hits,
        passed=passed,
        detail=detail,
    )


def hakedaka_fail_tickers(
    tickers: Sequence[str],
    inputs: HakedakaInputs,
    *,
    min_hits: int = 2,
    enabled: bool = True,
) -> set[str]:
    if not enabled:
        return set()
    out: set[str] = set()
    for raw in tickers:
        verdict = evaluate_hakedaka(raw, inputs, min_hits=min_hits)
        if not verdict.passed:
            out.add(verdict.ticker)
    return out


def hits_label(verdict: HakedakaHits) -> str:
    bits = []
    for key, flag in (
        ("순현금", verdict.net_cash),
        ("자사주", verdict.treasury),
        ("최대주주", verdict.owner_band),
        ("순환출자", verdict.circular),
    ):
        if flag is True:
            bits.append(key)
        elif flag is False:
            bits.append(f"{key}×")
    if not bits:
        return verdict.detail
    return f"{verdict.detail} · " + ", ".join(bits)
