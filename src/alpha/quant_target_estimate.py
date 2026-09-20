"""Quantitative take-profit draft from residual-income / justified P/B.

Literature (not a calibrated alpha):
- Ohlson (1995); Feltham–Ohlson — residual income, book + PV of (ROE − r)
- CFA / Damodaran justified P/B: (ROE − g) / (r − g)
- Sustainable g = ROE × (1 − payout), capped (perpetuity blow-up guard)

Inputs are trailing PyKRX/DART fields only (no broker consensus).
r and g_cap are **policy constants**, not Korea-optimal.

Does not write kr_alpha_exit_targets.yaml or target_portfolio.csv.
Proposal-book auto-apply lives in weekly_domain_gates (human can still override).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

# Policy — not estimated from Korean sample.
COST_OF_EQUITY = 0.09
G_CAP = 0.04
PAYOUT_DEFAULT = 0.40
PBR_FLOOR = 0.30
PBR_CEIL = 4.00
JUSTIFIED_WEIGHT = 0.60
PEER_WEIGHT = 0.40

# Through-cycle ROE for earnings-cycle names. r / g_cap stay policy constants.
CYCLICAL_SECTOR_GROUPS = frozenset(
    {
        "semiconductor",
        "auto",
        "auto_parts",
        "construction",
        "electronic_components",
        "electronics",
        "materials",
        "materials_metal",
        "materials_nonmetal",
        "materials_paper",
        "industrial",
        "industrials",
        "industrials_other",
        "industrial_transport",
        "transport",
        "consumer_discretionary",
    }
)
_CYCLICAL_NEEDLES = (
    "semiconductor",
    "반도체",
    "운수장비",
    "운송장비",
    "건설",
    "철강",
    "화학",
    "조선",
    "정유",
    "디스플레이",
    "2차전지",
    "electronic_components",
    "auto_parts",
    "materials",
    "cyclical",
)


def _pct_to_unit(val: Any) -> float | None:
    """12.5 or 0.125 → 0.125. Reject non-positive / non-finite."""
    if val is None or val == "":
        return None
    try:
        x = float(val)
    except (TypeError, ValueError):
        return None
    if x != x or x <= 0:
        return None
    return x / 100.0 if x > 1.0 else x


@dataclass(frozen=True)
class QuantTargetEstimate:
    ok: bool
    pbr_justified: float | None
    pbr_peer_median: float | None
    pbr_draft: float | None
    price_lo: float | None
    price_mid: float | None
    price_hi: float | None
    price_justified: float | None
    r: float
    g: float | None
    roe: float | None
    payout: float | None
    method: str
    note: str
    roe_source: str = ""

    def as_extra(self) -> dict[str, Any]:
        return {
            "quant_ok": self.ok,
            "quant_pbr_justified": self.pbr_justified,
            "quant_pbr_peer": self.pbr_peer_median,
            "quant_pbr_draft": self.pbr_draft,
            "quant_price_lo": self.price_lo,
            "quant_price_mid": self.price_mid,
            "quant_price_hi": self.price_hi,
            "quant_price_justified": self.price_justified,
            "quant_method": self.method,
            "quant_note": self.note,
            "quant_roe_source": self.roe_source,
        }


def is_cyclical_sector(sector: object) -> bool:
    """True for earnings-cycle groups. consumer staples / banks / insurance are not."""
    raw = str(sector or "").strip().lower()
    if not raw:
        return False
    compact = (
        raw.replace(" ", "")
        .replace("·", "")
        .replace("/", "")
        .replace("-", "_")
    )
    if raw in CYCLICAL_SECTOR_GROUPS or compact in CYCLICAL_SECTOR_GROUPS:
        return True
    return any(needle in compact for needle in _CYCLICAL_NEEDLES)


def _median_positive_roe(values: Sequence[Any] | None) -> float | None:
    units: list[float] = []
    for val in values or ():
        u = _pct_to_unit(val)
        if u is not None:
            units.append(u)
    if len(units) < 3:
        return None
    units.sort()
    mid = len(units) // 2
    if len(units) % 2:
        return units[mid]
    return (units[mid - 1] + units[mid]) / 2.0


def pick_target_roe(
    *,
    trailing: Any = None,
    roe_3y_avg: Any = None,
    sector: str = "",
    history_values: Sequence[Any] | None = None,
) -> tuple[Any, str]:
    """ROE plugged into (ROE−g)/(r−g). Cyclicals use through-cycle, not peak trailing."""
    hist = _median_positive_roe(history_values)
    if is_cyclical_sector(sector):
        if hist is not None:
            return hist, "cycle_hist"
        if _pct_to_unit(roe_3y_avg) is not None:
            return roe_3y_avg, "cycle_3y"
        return trailing, "trailing"
    if _pct_to_unit(trailing) is not None:
        return trailing, "trailing"
    if _pct_to_unit(roe_3y_avg) is not None:
        return roe_3y_avg, "3y"
    return trailing, "trailing"


def roe_history_values(df: pd.DataFrame | None, ticker: str) -> list[Any]:
    """Positive ROE observations for a ticker (oldest→newest)."""
    if df is None or df.empty or "ticker" not in df.columns or "roe" not in df.columns:
        return []
    work = df.copy()
    work["ticker"] = work["ticker"].map(_norm_ticker)
    sub = work[work["ticker"] == _norm_ticker(ticker)].copy()
    if sub.empty:
        return []
    sort_cols = [
        c for c in ("usable_from_date", "report_date", "period_end", "as_of") if c in sub.columns
    ]
    if sort_cols:
        for col in sort_cols:
            sub[col] = pd.to_datetime(sub[col], errors="coerce")
        sub = sub.sort_values(sort_cols)
    out: list[Any] = []
    seen: set[str] = set()
    for _, row in sub.iterrows():
        val = row.get("roe")
        if _pct_to_unit(val) is None:
            continue
        key = ""
        if "period_end" in row.index and pd.notna(row.get("period_end")):
            key = str(row.get("period_end"))[:10]
        elif "report_date" in row.index and pd.notna(row.get("report_date")):
            key = str(row.get("report_date"))[:10]
        else:
            key = str(len(out))
        if key in seen:
            continue
        seen.add(key)
        out.append(val)
    return out


def justified_pbr(
    roe: float,
    r: float,
    g: float,
) -> float | None:
    """(ROE − g) / (r − g). None if the perpetuity is not defined."""
    if r <= g or roe <= g:
        return None
    raw = (roe - g) / (r - g)
    if raw != raw or raw <= 0:
        return None
    return round(min(PBR_CEIL, max(PBR_FLOOR, raw)), 2)


def sustainable_g(roe: float, payout: float, *, g_cap: float = G_CAP) -> float:
    g = roe * (1.0 - payout)
    return float(min(max(g, 0.0), g_cap))


def peer_pbr_median(
    fundamentals: pd.DataFrame,
    *,
    ticker: str,
    sector: str,
) -> float | None:
    if fundamentals.empty or "pbr" not in fundamentals.columns:
        return None
    work = fundamentals.copy()
    if "ticker" in work.columns:
        work["ticker"] = work["ticker"].astype(str).map(
            lambda t: t.zfill(6) if str(t).isdigit() else str(t)
        )
    t = str(ticker).zfill(6) if str(ticker).isdigit() else str(ticker)
    sec = str(sector or "").strip()
    if sec and "sector" in work.columns:
        pool = work[work["sector"].astype(str) == sec]
    else:
        pool = work
    if "ticker" in pool.columns:
        pool = pool[pool["ticker"] != t]
    series = pd.to_numeric(pool["pbr"], errors="coerce").dropna()
    series = series[series > 0]
    if len(series) < 3:
        return None
    return round(float(series.median()), 2)


def estimate_quant_target(
    *,
    roe: Any = None,
    pbr: Any = None,
    price: Any = None,
    payout: Any = None,
    dividend_yield: Any = None,
    peer_pbr_median: Any = None,
    r: float = COST_OF_EQUITY,
    g_cap: float = G_CAP,
    roe_source: str = "",
    roe_trailing: Any = None,
) -> QuantTargetEstimate:
    roe_u = _pct_to_unit(roe)
    pbr_f: float | None
    try:
        pbr_f = float(pbr) if pbr is not None and str(pbr).strip() != "" else None
        if pbr_f is not None and (pbr_f != pbr_f or pbr_f <= 0):
            pbr_f = None
    except (TypeError, ValueError):
        pbr_f = None
    try:
        px = float(price) if price is not None and str(price).strip() != "" else None
        if px is not None and (px != px or px <= 0):
            px = None
    except (TypeError, ValueError):
        px = None

    payout_u = _pct_to_unit(payout)
    if payout_u is None and dividend_yield is not None and roe_u is not None and pbr_f:
        dy = _pct_to_unit(dividend_yield)
        # trailing yield ≈ payout × ROE / P/B  → payout ≈ yield × P/B / ROE
        if dy is not None and roe_u > 0:
            implied = dy * pbr_f / roe_u
            if 0.05 <= implied <= 0.95:
                payout_u = implied
    if payout_u is None:
        payout_u = PAYOUT_DEFAULT

    try:
        peer = float(peer_pbr_median) if peer_pbr_median is not None else None
        if peer is not None and (peer != peer or peer <= 0):
            peer = None
    except (TypeError, ValueError):
        peer = None

    g = sustainable_g(roe_u, payout_u, g_cap=g_cap) if roe_u is not None else None
    pbr_j = justified_pbr(roe_u, r, g) if roe_u is not None and g is not None else None

    if pbr_j is not None and peer is not None:
        draft = JUSTIFIED_WEIGHT * pbr_j + PEER_WEIGHT * peer
        method = "정당P/B 60% + 섹터중앙 40%"
    elif pbr_j is not None:
        draft = pbr_j
        method = "정당P/B (ROE-g)/(r-g)"
    elif peer is not None:
        draft = peer
        method = "섹터 PBR 중앙값 (정당P/B 불가)"
    else:
        return QuantTargetEstimate(
            ok=False,
            pbr_justified=pbr_j,
            pbr_peer_median=peer,
            pbr_draft=None,
            price_lo=None,
            price_mid=None,
            price_hi=None,
            price_justified=None,
            r=r,
            g=g,
            roe=roe_u,
            payout=payout_u,
            method="불가",
            note="ROE·PBR·섹터중앙이 부족하거나 r≤g",
            roe_source=roe_source,
        )

    draft = round(min(PBR_CEIL, max(PBR_FLOOR, float(draft))), 2)
    lo_p = min(x for x in (pbr_j, peer, draft) if x is not None)
    hi_p = max(x for x in (pbr_j, peer, draft) if x is not None)
    lo_p = round(min(PBR_CEIL, max(PBR_FLOOR, lo_p)), 2)
    hi_p = round(min(PBR_CEIL, max(PBR_FLOOR, hi_p)), 2)

    price_lo = price_mid = price_hi = price_justified = None
    if px is not None and pbr_f:
        price_mid = round(px * (draft / pbr_f), 0)
        price_lo = round(px * (lo_p / pbr_f), 0)
        price_hi = round(px * (hi_p / pbr_f), 0)
        if pbr_j is not None:
            price_justified = round(px * (pbr_j / pbr_f), 0)

    note = (
        f"r={r:.0%} g={g:.1%} payout={payout_u:.0%}"
        if g is not None
        else f"r={r:.0%}"
    )
    if str(roe_source).startswith("cycle") and roe_u is not None:
        note += f" · 순환주 중기ROE {roe_u:.0%}"
        trail_u = _pct_to_unit(roe_trailing)
        if trail_u is not None and abs(trail_u - roe_u) > 1e-4:
            note += f" (최근 {trail_u:.0%})"
    if pbr_f and draft <= pbr_f:
        note += " · 현재 PBR이 초안 이상(이미 정당배수 근처)"

    return QuantTargetEstimate(
        ok=True,
        pbr_justified=pbr_j,
        pbr_peer_median=round(peer, 2) if peer is not None else None,
        pbr_draft=draft,
        price_lo=price_lo,
        price_mid=price_mid,
        price_hi=price_hi,
        price_justified=price_justified,
        r=r,
        g=g,
        roe=roe_u,
        payout=payout_u,
        method=method,
        note=note,
        roe_source=roe_source,
    )


def estimate_from_maps(
    ticker: str,
    *,
    fund: Mapping[str, Any],
    price: Any,
    peer: Any = None,
    sector: str = "",
    history_roe: Sequence[Any] | None = None,
) -> QuantTargetEstimate:
    del ticker  # picker is fund-driven; ticker only for callers
    sec = str(sector or fund.get("sector") or "")
    chosen, src = pick_target_roe(
        trailing=fund.get("roe"),
        roe_3y_avg=fund.get("roe_3y_avg"),
        sector=sec,
        history_values=history_roe,
    )
    return estimate_quant_target(
        roe=chosen,
        pbr=fund.get("pbr"),
        price=price,
        payout=fund.get("payout_ratio") or fund.get("payout"),
        dividend_yield=fund.get("dividend_yield"),
        peer_pbr_median=peer if peer is not None else fund.get("sector_pbr_median"),
        roe_source=src,
        roe_trailing=fund.get("roe"),
    )


def literature_target_from_extra(
    extra: Mapping[str, Any] | None,
) -> tuple[float, float | None] | None:
    """Damodaran/Ohlson justified P/B only. None if the identity is not defined."""
    extra = extra or {}
    return _pbr_price_pair(
        extra.get("quant_pbr_justified"),
        extra.get("quant_price_justified"),
    )


def mix_target_from_extra(
    extra: Mapping[str, Any] | None,
) -> tuple[float, float | None] | None:
    """Take-profit line: justified 60% + sector median 40% (quant_pbr_draft).

    Falls back to justified-only when the mix is missing.
    """
    extra = extra or {}
    mixed = _pbr_price_pair(
        extra.get("quant_pbr_draft"),
        extra.get("quant_price_mid"),
    )
    if mixed is not None:
        return mixed
    return literature_target_from_extra(extra)


def _pbr_price_pair(pbr_raw: Any, px_raw: Any) -> tuple[float, float | None] | None:
    if pbr_raw in (None, ""):
        return None
    try:
        pbr = float(pbr_raw)
    except (TypeError, ValueError):
        return None
    if pbr != pbr or pbr <= 0:
        return None
    px: float | None
    try:
        px = float(px_raw) if px_raw not in (None, "") else None
        if px is not None and (px != px or px <= 0):
            px = None
    except (TypeError, ValueError):
        px = None
    return round(pbr, 2), (round(px, 0) if px is not None else None)


def _norm_ticker(val: Any) -> str:
    s = str(val or "").strip()
    return s.zfill(6) if s.isdigit() else s


def last_history_value(
    df: pd.DataFrame,
    ticker: str,
    column: str,
    *,
    as_ratio: bool,
) -> Any:
    """Newest non-empty observation. as_ratio uses percent/unit conversion."""
    if df is None or df.empty or column not in df.columns or "ticker" not in df.columns:
        return None
    work = df.copy()
    work["ticker"] = work["ticker"].map(_norm_ticker)
    sub = work[work["ticker"] == _norm_ticker(ticker)].copy()
    if sub.empty:
        return None
    sort_cols = [c for c in ("usable_from_date", "report_date", "period_end", "as_of") if c in sub.columns]
    if sort_cols:
        for c in sort_cols:
            sub[c] = pd.to_datetime(sub[c], errors="coerce")
        sub = sub.sort_values(sort_cols)
    for _, row in sub.iloc[::-1].iterrows():
        val = row.get(column)
        if val is None or val == "" or (isinstance(val, float) and val != val):
            continue
        if as_ratio:
            if _pct_to_unit(val) is not None:
                return val
            continue
        try:
            f = float(val)
        except (TypeError, ValueError):
            continue
        if f == f and f > 0:
            return val
    return None


def load_alpha_template_fundamentals(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "alpha_portfolio" / "data" / "raw" / "fundamentals.csv"
    if not path.exists():
        return {}
    try:
        df = pd.read_csv(path)
    except Exception:
        return {}
    if df.empty or "ticker" not in df.columns:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        t = _norm_ticker(row.get("ticker"))
        if t:
            out[t] = row.to_dict()
    return out


def enrich_ops_fund(
    ticker: str,
    ops_row: Mapping[str, Any] | None,
    *,
    history: pd.DataFrame | None = None,
    alpha_row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Ops trailing first; fill ROE/sector median from history or alpha template."""
    out: dict[str, Any] = dict(ops_row or {})
    if _pct_to_unit(out.get("roe")) is None:
        hist = last_history_value(history, ticker, "roe", as_ratio=True) if history is not None else None
        if hist is not None:
            out["roe"] = hist
        elif alpha_row is not None and _pct_to_unit(alpha_row.get("roe")) is not None:
            out["roe"] = alpha_row.get("roe")
        elif alpha_row is not None and _pct_to_unit(alpha_row.get("roe_3y_avg")) is not None:
            out["roe"] = alpha_row.get("roe_3y_avg")
    if out.get("pbr") in (None, "") or (
        isinstance(out.get("pbr"), float) and out.get("pbr") != out.get("pbr")
    ):
        hist_p = last_history_value(history, ticker, "pbr", as_ratio=False) if history is not None else None
        if hist_p is not None:
            out["pbr"] = hist_p
        elif alpha_row is not None:
            out["pbr"] = alpha_row.get("pbr")
    if _pct_to_unit(out.get("roe_3y_avg")) is None and alpha_row is not None:
        if _pct_to_unit(alpha_row.get("roe_3y_avg")) is not None:
            out["roe_3y_avg"] = alpha_row.get("roe_3y_avg")
    if not str(out.get("sector") or "").strip() and alpha_row is not None:
        out["sector"] = alpha_row.get("sector")
    if out.get("sector_pbr_median") in (None, "") and alpha_row is not None:
        out["sector_pbr_median"] = alpha_row.get("sector_pbr_median")
    if _pct_to_unit(out.get("payout_ratio") or out.get("payout")) is None and alpha_row is not None:
        if _pct_to_unit(alpha_row.get("payout_ratio") or alpha_row.get("payout")) is not None:
            out["payout_ratio"] = alpha_row.get("payout_ratio") or alpha_row.get("payout")
    if _pct_to_unit(out.get("dividend_yield")) is None and alpha_row is not None:
        if _pct_to_unit(alpha_row.get("dividend_yield") or alpha_row.get("fcf_yield")) is not None:
            if alpha_row.get("dividend_yield") not in (None, ""):
                out["dividend_yield"] = alpha_row.get("dividend_yield")
    return out


def quant_portfolio_extra(
    ticker: str,
    *,
    fund_row: Mapping[str, Any] | None,
    price: Any,
    sector: str = "",
    fundamentals_df: pd.DataFrame | None = None,
    alpha_row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    enriched = enrich_ops_fund(
        ticker,
        fund_row,
        history=fundamentals_df,
        alpha_row=alpha_row,
    )
    if sector and not str(enriched.get("sector") or "").strip():
        enriched["sector"] = sector
    sec = str(enriched.get("sector") or sector or "")
    peer = enriched.get("sector_pbr_median")
    if (peer in (None, "") or (isinstance(peer, float) and peer != peer)) and fundamentals_df is not None:
        peer = peer_pbr_median(fundamentals_df, ticker=ticker, sector=sec)
    est = estimate_from_maps(
        ticker,
        fund=enriched,
        price=price,
        peer=peer,
        sector=sec,
        history_roe=roe_history_values(fundamentals_df, ticker),
    )
    return est.as_extra()


def markdown_target_fields(extra: Mapping[str, Any] | None) -> list[str]:
    """Parser-safe E fields. Blanks when the draft is not ok."""
    extra = extra or {}
    if not extra.get("quant_ok"):
        return [
            "- pbr_max: _____",
            "- target_price: _____",
            "- 펀더멘털 사유: _____",
            "- 근거: _____",
            "- 출처:",
            "  - ",
        ]
    pbr = extra.get("quant_pbr_draft")
    mid = extra.get("quant_price_mid")
    pbr_s = f"{float(pbr):.2f}" if pbr not in (None, "") else "_____"
    if mid not in (None, ""):
        try:
            px_s = str(int(round(float(mid))))
        except (TypeError, ValueError):
            px_s = "_____"
    else:
        px_s = "_____"
    method = str(extra.get("quant_method") or "정당P/B")
    note = str(extra.get("quant_note") or "")
    return [
        f"- pbr_max: {pbr_s}",
        f"- target_price: {px_s}",
        f"- 펀더멘털 사유: 정량초안({method}). {note}".rstrip(),
        "- 근거: 잔여이익 정당 P/B=(ROE-g)/(r-g) (Ohlson 1995 · CFA · Damodaran). "
        "순환주는 중기 ROE. r=9%·g상한=4%는 정책상수이며 한국 최적값이 아님. E 승인 전 yaml 미기입.",
        "- 출처:",
        "  - https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/pbvdata.html",
    ]
