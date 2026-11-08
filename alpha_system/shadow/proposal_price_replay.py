"""Weekly mid-proposal × prices_history replay — Review-only.

Separate ledger from live day-append shadow_mid_ledger.jsonl.
Never writes target_portfolio.csv / QVM.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from alpha_system.hold_exit_review.config import load_hold_exit_config
from alpha_system.proposal_chart import norm_ticker
from alpha_system.screen_book import operational_data_dir
from alpha_system.shadow.costs import load_shadow_cost_bps
from alpha_system.shadow.mid_book import ShadowBookState, ShadowNameGate, step_day
from alpha_system.shadow.mid_ledger import replace_ledger
from src.backtest.cost_model import QUALITY_INSUFFICIENT_MAX, QUALITY_PRELIMINARY_MAX

# Align with sample_quality_label / Go-live gate
LOOKBACK_PRELIMINARY = QUALITY_INSUFFICIENT_MAX + 1  # 60
LOOKBACK_PROVISIONAL = QUALITY_PRELIMINARY_MAX + 1  # 180
# 전략 진화용 — 1년(≈252) · 가용 최대 상한(캐시·네트워크)
LOOKBACK_STRATEGY = 252
LOOKBACK_STRATEGY_MAX = 504


def replay_ledger_path(
    root: Path,
    market: object | None = None,
    *,
    horizon: object | None = "mid",
) -> Path:
    mkt = str(market or "KOSPI").upper()
    hz = "short" if str(horizon or "mid").lower() in {"short", "s", "short_book"} else "mid"
    data = operational_data_dir(Path(root), mkt, hz)
    if hz == "short":
        return data / f"shadow_short_replay_{mkt}.jsonl"
    return data / f"shadow_mid_replay_{mkt}.jsonl"


def prices_history_path(root: Path) -> Path:
    return Path(root) / "data" / "prices_history.csv"


def proposal_replay_prices_path(root: Path) -> Path:
    """Side cache for meaningful-window replay (does not rewrite prices_history)."""
    return Path(root) / "data" / "local" / "proposal_replay_prices.csv"


@dataclass(frozen=True)
class ProposalWeekSnap:
    as_of: str
    tickers: tuple[str, ...]


@dataclass(frozen=True)
class ProposalPriceReplayResult:
    ok: bool
    market: str
    n_days: int
    n_weeks: int
    as_of_first: str
    as_of_last: str
    missing_price_names: int
    ledger: str
    reason: str = ""
    lookback_trading_days: int = 0
    min_trading_days: int = 0
    selection_note: str = ""
    backfill_rows_added: int = 0
    review_only: bool = True
    writes_target: bool = False


def _ew_proposal(tickers: Sequence[str], *, single_cap: float = 0.25) -> dict[str, float]:
    raw: dict[str, float] = {}
    uniq = []
    seen: set[str] = set()
    for t in tickers:
        tk = norm_ticker(t)
        if not tk or tk == "000000" or tk in seen:
            continue
        seen.add(tk)
        uniq.append(tk)
    if not uniq:
        return {}
    w = min(1.0 / len(uniq), float(single_cap))
    for tk in uniq:
        raw[tk] = w
    s = sum(raw.values())
    if s > 1.0 + 1e-9:
        raw = {k: v / s for k, v in raw.items()}
    return raw


def load_mid_proposal_weeks(
    root: Path,
    *,
    market: str = "KOSPI",
    history_path: Path | None = None,
) -> list[ProposalWeekSnap]:
    """Unique as_of mid snapshots for market (last row wins duplicates)."""
    root = Path(root)
    mkt = str(market or "KOSPI").upper()
    path = history_path
    if path is None:
        cfg = load_hold_exit_config(root)
        path = root / cfg.history_relpath
    path = Path(path)
    if not path.exists():
        return []
    by_asof: dict[str, tuple[str, ...]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if str(obj.get("horizon") or "mid").lower() != "mid":
            continue
        if str(obj.get("market") or "").upper() != mkt:
            continue
        as_of = str(obj.get("as_of") or "")[:10]
        if not as_of:
            continue
        tickers = tuple(
            norm_ticker(t)
            for t in (obj.get("tickers") or [])
            if norm_ticker(t) and norm_ticker(t) != "000000"
        )
        # de-dupe preserve order
        seen: set[str] = set()
        ordered: list[str] = []
        for tk in tickers:
            if tk not in seen:
                seen.add(tk)
                ordered.append(tk)
        by_asof[as_of] = tuple(ordered)
    return [
        ProposalWeekSnap(as_of=d, tickers=by_asof[d])
        for d in sorted(by_asof.keys())
    ]


def _normalize_price_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["ticker", "date", "close"])
    cols = {str(c).lower(): c for c in df.columns}
    tk = cols.get("ticker") or cols.get("code")
    dt = cols.get("date") or cols.get("as_of")
    px = cols.get("close") or cols.get("adj_close")
    if not tk or not dt or not px:
        return pd.DataFrame(columns=["ticker", "date", "close"])
    out = df[[tk, dt, px]].copy()
    out.columns = ["ticker", "date", "close"]
    out["ticker"] = out["ticker"].map(norm_ticker)
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    return out.dropna(subset=["ticker", "date", "close"])


def _read_one_prices_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["ticker", "date", "close"])
    try:
        df = pd.read_csv(path, usecols=["date", "ticker", "close"])
    except (ValueError, KeyError, OSError):
        try:
            df = pd.read_csv(path)
        except OSError:
            return pd.DataFrame(columns=["ticker", "date", "close"])
    return _normalize_price_frame(df)


def _read_prices_history(
    path: Path,
    tickers: Sequence[str],
    *,
    extra_paths: Sequence[Path] | None = None,
) -> pd.DataFrame:
    """prices_history + optional prices.csv merge (history wins on dup keys)."""
    want = {norm_ticker(t) for t in tickers if norm_ticker(t)}
    frames = [_read_one_prices_csv(path)]
    for ep in extra_paths or ():
        frames.append(_read_one_prices_csv(Path(ep)))
    parts = [f for f in frames if not f.empty]
    if not parts:
        return pd.DataFrame(columns=["ticker", "date", "close"])
    df = pd.concat(parts, ignore_index=True)
    if want:
        df = df[df["ticker"].isin(want)]
    # Prefer first source on (ticker, date) — history listed first
    df = df.drop_duplicates(subset=["ticker", "date"], keep="first")
    return df


def _rets_between(px: pd.DataFrame, d0: str, d1: str) -> dict[str, float]:
    a = px[px["date"] == d0].set_index("ticker")["close"]
    b = px[px["date"] == d1].set_index("ticker")["close"]
    out: dict[str, float] = {}
    for tk in set(a.index) & set(b.index):
        p0 = float(a.loc[tk])
        p1 = float(b.loc[tk])
        if p0 > 1e-12:
            out[str(tk)] = (p1 / p0) - 1.0
    return out


def _soft_metrics_asof(
    px: pd.DataFrame | None,
    ticker: str,
    day: str,
) -> dict[str, float | None]:
    """Approx 1M/6M returns from close history; ADV unknown → None."""
    closes = _closes_to(px, ticker, day, n=140) if px is not None else []
    r1 = r6 = None
    if len(closes) >= 22:
        p0, p1 = closes[-22], closes[-1]
        if p0 > 1e-12:
            r1 = p1 / p0 - 1.0
    if len(closes) >= 126:
        p0, p1 = closes[-126], closes[-1]
        if p0 > 1e-12:
            r6 = p1 / p0 - 1.0
    elif len(closes) >= 2:
        p0, p1 = closes[0], closes[-1]
        if p0 > 1e-12:
            r6 = p1 / p0 - 1.0
    return {"return_1m": r1, "return_6m": r6, "trading_value_20d": None}


def _proposal_for_day(
    snaps: Sequence[ProposalWeekSnap],
    day: str,
    *,
    freeze_first_back: bool = True,
    px: pd.DataFrame | None = None,
    apply_soft_cut: bool = False,
    apply_ma_soft: bool = False,
    ma_mode: str = "above_60",
    filter_today: bool = True,
) -> dict[str, float]:
    """Carry forward last snap with as_of <= day.

    Before first snap: optionally freeze first snap basket (lookback fill).
    filter_today=False: Soft/MA 컷 생략(중기 주간 sticky — 스냅 사이에 난매 금지).
    """
    if not snaps:
        return {}
    active: tuple[str, ...] = ()
    for snap in snaps:
        if snap.as_of <= day:
            active = snap.tickers
        else:
            break
    if not active and freeze_first_back and day < snaps[0].as_of:
        active = snaps[0].tickers
    if filter_today and apply_soft_cut and px is not None and active:
        from alpha_system.entry.mid_soft_cut import evaluate_mid_soft_cut

        kept: list[str] = []
        for tk in active:
            m = _soft_metrics_asof(px, tk, day)
            cut = evaluate_mid_soft_cut(tk, extra=m)
            if not cut.blocks_add:
                kept.append(tk)
        active = tuple(kept)
    if filter_today and apply_ma_soft and px is not None and active:
        from alpha_system.entry.ma_trend_soft import evaluate_ma_trend_soft

        kept_ma: list[str] = []
        for tk in active:
            closes = _closes_to(px, tk, day, n=140)
            ma = evaluate_ma_trend_soft(tk, closes, mode=ma_mode)  # type: ignore[arg-type]
            if not ma.blocks_add:
                kept_ma.append(tk)
        active = tuple(kept_ma)
    return _ew_proposal(active)
def _calendar_lookback_days(trading_days: int) -> int:
    """Rough calendar span covering N trading sessions."""
    n = max(1, int(trading_days))
    return int(n * 1.55) + 30


def ensure_proposal_prices(
    root: Path,
    tickers: Sequence[str],
    *,
    lookback_trading_days: int = LOOKBACK_PROVISIONAL,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Fetch proposal tickers into data/local/proposal_replay_prices.csv (append-only).

    Avoids rewriting the full prices_history.csv (atomic min_rows guard).
    """
    root = Path(root)
    uniq = [norm_ticker(t) for t in tickers if norm_ticker(t) and norm_ticker(t) != "000000"]
    out: dict[str, Any] = {
        "success": False,
        "reason": "",
        "rows_added": 0,
        "tickers_ok": [],
        "tickers_failed": [],
        "path": str(proposal_replay_prices_path(root)),
    }
    if not uniq:
        out["reason"] = "no_tickers"
        return out
    try:
        from src.data_refresh.pykrx_client import (
            import_pykrx_stock,
            lookback_start,
            to_compact_date,
            to_iso_date,
        )
        from src.data_refresh.price_store import normalize_ticker
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"pykrx_import_failed:{type(exc).__name__}"
        return out

    data_dir = root / "data"
    try:
        stock = import_pykrx_stock(data_dir)
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"krx_login_failed:{type(exc).__name__}"
        return out

    end = (as_of or pd.Timestamp.today().strftime("%Y-%m-%d"))[:10]
    start = lookback_start(end, _calendar_lookback_days(lookback_trading_days))
    c0, c1 = to_compact_date(start), to_compact_date(end)

    path = proposal_replay_prices_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_one_prices_csv(path)
    have: set[tuple[str, str]] = set()
    if not existing.empty:
        for _, row in existing.iterrows():
            have.add((str(row["ticker"]), str(row["date"])))

    new_rows: list[dict[str, str | float]] = []
    for tk in uniq:
        try:
            ohlcv = stock.get_market_ohlcv_by_date(c0, c1, tk)
        except Exception:  # noqa: BLE001
            out["tickers_failed"].append(tk)
            continue
        if ohlcv is None or getattr(ohlcv, "empty", True):
            out["tickers_failed"].append(tk)
            continue
        close_col = "종가" if "종가" in ohlcv.columns else (
            "close" if "close" in ohlcv.columns else None
        )
        if close_col is None:
            out["tickers_failed"].append(tk)
            continue
        ntk = normalize_ticker(tk)
        added_any = False
        for idx, row in ohlcv.iterrows():
            if hasattr(idx, "strftime"):
                date = idx.strftime("%Y-%m-%d")
            else:
                s = str(idx)
                date = to_iso_date(s) if len(s.replace("-", "")) == 8 else s[:10]
            try:
                close = float(row[close_col])
            except (TypeError, ValueError):
                continue
            if close <= 0:
                continue
            key = (ntk, date)
            if key in have:
                continue
            have.add(key)
            new_rows.append({"date": date, "ticker": ntk, "close": close})
            added_any = True
        if added_any:
            out["tickers_ok"].append(ntk)
        else:
            out["tickers_ok"].append(ntk)  # already covered counts as ok

    if new_rows:
        add_df = pd.DataFrame(new_rows)
        merged = pd.concat([existing, add_df], ignore_index=True) if not existing.empty else add_df
        merged = merged.drop_duplicates(subset=["ticker", "date"], keep="last")
        merged = merged.sort_values(["date", "ticker"])
        merged.to_csv(path, index=False)
    out["rows_added"] = len(new_rows)
    out["success"] = True
    out["reason"] = "ok" if new_rows or not existing.empty else "no_new_rows"
    out["window"] = {"start": start, "end": end}
    return out


def _closes_to(
    px: pd.DataFrame,
    ticker: str,
    day: str,
    *,
    n: int = 25,
) -> list[float]:
    tk = norm_ticker(ticker)
    sub = px[(px["ticker"] == tk) & (px["date"] <= day)].sort_values("date")
    if sub.empty:
        return []
    return [float(x) for x in sub["close"].tail(int(n)).tolist()]


def _soft_defense_hot(
    px: pd.DataFrame,
    proposal: Mapping[str, float],
    day: str,
    *,
    greed_ret: float = 0.10,
    look: int = 20,
) -> bool:
    """Soft proxy: basket ~20d EW return high → chase risk (C2 spirit · block adds)."""
    rets: list[float] = []
    for tk in proposal:
        closes = _closes_to(px, tk, day, n=look + 1)
        if len(closes) < 2:
            continue
        p0, p1 = closes[0], closes[-1]
        if p0 > 1e-12:
            rets.append(p1 / p0 - 1.0)
    if len(rets) < 2:
        return False
    return (sum(rets) / len(rets)) >= float(greed_ret)


def _basket_nd_ret(
    px: pd.DataFrame,
    tickers: Sequence[str],
    day: str,
    *,
    n: int = 5,
) -> float | None:
    rets: list[float] = []
    for tk in tickers:
        closes = _closes_to(px, tk, day, n=n + 1)
        if len(closes) < 2:
            continue
        p0, p1 = closes[0], closes[-1]
        if p0 > 1e-12:
            rets.append(p1 / p0 - 1.0)
    if not rets:
        return None
    return sum(rets) / len(rets)


def _gates_for_replay(
    proposal: Mapping[str, float],
    held: Mapping[str, float],
    *,
    px: pd.DataFrame | None = None,
    as_of: str = "",
    apply_l3: bool = False,
    apply_soft: bool = False,
    soft_hold_r1: float | None = -0.08,
    mkt_5d_cash: float | None = -0.025,
    risk_on_20d: float | None = 0.0,
    apply_ma_soft: bool = False,
    ma_mode: str = "above_60",
) -> dict[str, ShadowNameGate]:
    """Enter proposal · exit leavers · L3 · Soft chase/hold/market-cash · MA Soft."""
    gates: dict[str, ShadowNameGate] = {}
    prop = {norm_ticker(k) for k in proposal}
    names = list(proposal.keys()) or list(held.keys())
    soft_hot = bool(
        apply_soft and px is not None and as_of and _soft_defense_hot(px, proposal, as_of)
    )
    mkt_cash = False
    if mkt_5d_cash is not None and px is not None and as_of and names:
        mkt_r = _basket_nd_ret(px, names, as_of, n=5)
        mkt_cash = mkt_r is not None and mkt_r < float(mkt_5d_cash)
    risk_off = False
    if risk_on_20d is not None and px is not None and as_of and names:
        r20 = _basket_nd_ret(px, names, as_of, n=20)
        risk_off = r20 is not None and r20 < float(risk_on_20d)

    l3_fn = None
    if apply_l3 and px is not None and as_of:
        from alpha_system.ui.services.crash_defense_signal import classify_crash_defense

        l3_fn = classify_crash_defense

    def _ma_reduce(tk: str) -> bool:
        if not apply_ma_soft or px is None or not as_of:
            return False
        from alpha_system.entry.ma_trend_soft import evaluate_ma_trend_soft

        closes = _closes_to(px, tk, as_of, n=140)
        ma = evaluate_ma_trend_soft(tk, closes, mode=ma_mode)  # type: ignore[arg-type]
        return bool(ma.soft_hold_reduce)

    def _ops_for(tk: str) -> str:
        ops = "hold"
        if l3_fn is not None:
            closes = _closes_to(px, tk, as_of, n=8)
            if len(closes) >= 2:
                kind = str(getattr(l3_fn(closes), "kind", "hold") or "hold")
                if kind in {"trim", "cash_half"}:
                    ops = kind
        if soft_hold_r1 is not None and px is not None and as_of:
            m = _soft_metrics_asof(px, tk, as_of)
            r1 = m.get("return_1m")
            if r1 is not None and float(r1) < float(soft_hold_r1):
                if ops in {"hold", "trim"}:
                    ops = "cash_half"
        if _ma_reduce(tk) and ops in {"hold", "trim"}:
            ops = "cash_half"
        if (mkt_cash or risk_off) and ops == "hold":
            ops = "cash_half"
        return ops

    block_adds = soft_hot or mkt_cash or risk_off
    for tk in prop:
        gates[tk] = ShadowNameGate(
            ops_signal=_ops_for(tk),
            in_buy_zone=not block_adds,
            mom_weak=block_adds,
            has_target=True,
        )
    for tk in held:
        ntk = norm_ticker(tk)
        if ntk not in prop:
            gates[ntk] = ShadowNameGate(
                ops_signal="exit_full",
                in_buy_zone=False,
                has_target=True,
            )
            continue
        g = gates[ntk]
        ops = _ops_for(ntk)
        strength = {"hold": 0, "trim": 1, "cash_half": 2, "exit_full": 3}
        if strength.get(ops, 0) >= strength.get(g.ops_signal, 0):
            gates[ntk] = ShadowNameGate(
                ops_signal=ops,
                in_buy_zone=g.in_buy_zone,
                mom_weak=g.mom_weak,
                has_target=True,
            )
    return gates


def name_stats_from_ledger(
    rows: Sequence[Mapping[str, Any]],
    *,
    px: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    """Per-ticker diagnosis: days held, rough price change over hold span."""
    first_day: dict[str, str] = {}
    last_day: dict[str, str] = {}
    days_held: dict[str, int] = {}
    for r in rows:
        as_of = str(r.get("as_of") or "")
        weights = r.get("weights") if isinstance(r.get("weights"), dict) else {}
        for tk, w in weights.items():
            try:
                wf = float(w or 0)
            except (TypeError, ValueError):
                continue
            if wf <= 1e-8:
                continue
            ntk = norm_ticker(tk)
            days_held[ntk] = days_held.get(ntk, 0) + 1
            first_day.setdefault(ntk, as_of)
            last_day[ntk] = as_of
    out: list[dict[str, Any]] = []
    for tk in sorted(days_held.keys()):
        px_ret = None
        if px is not None and not px.empty:
            d0, d1 = first_day[tk], last_day[tk]
            a = px[(px["ticker"] == tk) & (px["date"] == d0)]
            b = px[(px["ticker"] == tk) & (px["date"] == d1)]
            if not a.empty and not b.empty:
                p0 = float(a.iloc[0]["close"])
                p1 = float(b.iloc[0]["close"])
                if p0 > 1e-12:
                    px_ret = p1 / p0 - 1.0
        out.append(
            {
                "ticker": tk,
                "days_held": days_held[tk],
                "from": first_day[tk],
                "to": last_day[tk],
                "price_ret": None if px_ret is None else round(px_ret, 6),
            }
        )
    out.sort(key=lambda x: (x["price_ret"] is None, x["price_ret"] or 0.0))
    return out


def run_proposal_price_replay(
    root: Path,
    *,
    market: str = "KOSPI",
    persist: bool = True,
    weeks: Sequence[ProposalWeekSnap] | None = None,
    prices_csv: Path | None = None,
    lookback_trading_days: int = LOOKBACK_PROVISIONAL,
    min_trading_days: int | None = None,
    ensure_prices: bool = False,
    allow_short: bool = False,
    point_in_time: bool = False,
    apply_l3: bool = False,
    apply_soft: bool = False,
    apply_soft_cut: bool = True,
    soft_hold_r1: float | None = -0.08,
    mkt_5d_cash: float | None = -0.025,
    risk_on_20d: float | None = 0.0,
    apply_ma_soft: bool = True,
    ma_mode: str = "above_60",
    mid_cadence: bool = True,
    add_frac: float = 0.25,
    horizon: str = "mid",
) -> ProposalPriceReplayResult:
    """Rebuild replay ledger over a meaningful lookback window.

    point_in_time=True: start at first mid snap (no freeze-back).
    apply_l3 / apply_soft: crash trim/half + Soft add-block proxy.
    apply_soft_cut: mid momentum/liquidity Soft entry cut.
    soft_hold_r1 / mkt_5d_cash: Soft hold·시장 현금 방어 (exit_full 아님).
    apply_ma_soft: 60/120일선 Soft 추세 (신규 차단 · 120아래 보유 축소).
    mid_cadence: 중기=주간 스냅에만 Soft/MA·비중 리밸 · 일별 난매 금지 (L3만 일별).
    horizon=short → 단기 수익기 원장 (중기 mid replay와 파일 분리).
    """
    root = Path(root)
    mkt = str(market or "KOSPI").upper()
    out_path = replay_ledger_path(root, mkt, horizon=horizon)
    lookback = max(2, int(lookback_trading_days or LOOKBACK_PROVISIONAL))
    min_days = int(min_trading_days) if min_trading_days is not None else lookback
    snaps = list(weeks) if weeks is not None else load_mid_proposal_weeks(root, market=mkt)
    if not snaps:
        return ProposalPriceReplayResult(
            ok=False,
            market=mkt,
            n_days=0,
            n_weeks=0,
            as_of_first="",
            as_of_last="",
            missing_price_names=0,
            ledger=str(out_path),
            reason="no_mid_proposal_weeks",
            lookback_trading_days=lookback,
            min_trading_days=min_days,
        )

    all_tickers: list[str] = []
    seen: set[str] = set()
    for s in snaps:
        for t in s.tickers:
            if t not in seen:
                seen.add(t)
                all_tickers.append(t)

    if point_in_time:
        selection_note = (
            f"PIT 스냅 이후만 · 목표 {lookback}거래일 · "
            f"제안 {snaps[0].as_of}→{snaps[-1].as_of} · 사후고정 없음"
        )
        extras = []
        if apply_l3:
            extras.append("L3")
        if apply_soft:
            extras.append("Soft")
        if apply_soft_cut:
            extras.append("편입컷")
        if soft_hold_r1 is not None:
            extras.append("보유방어")
        if mkt_5d_cash is not None:
            extras.append("시장현금")
        if risk_on_20d is not None:
            extras.append("risk20")
        if apply_ma_soft:
            extras.append(f"이평{ma_mode.replace('above_', '')}")
        if mid_cadence:
            extras.append("주간리밸")
        if extras:
            selection_note += " · " + "+".join(extras)
    else:
        selection_note = (
            f"가격창 최근 {lookback}거래일 · "
            f"제안 스냅 {snaps[0].as_of}→{snaps[-1].as_of} · "
            "스냅 이전은 첫 mid 바구니 고정(선정 사후편향 가능)"
        )
    backfill_added = 0
    if ensure_prices and prices_csv is None:
        bf = ensure_proposal_prices(
            root,
            all_tickers,
            lookback_trading_days=lookback,
        )
        backfill_added = int(bf.get("rows_added") or 0)
        if not bf.get("success") and bf.get("reason") not in {"dry_run", ""}:
            # Continue — may still have enough local history; note failure
            selection_note += f" · 가격보강:{bf.get('reason') or 'fail'}"

    px_path = Path(prices_csv) if prices_csv else prices_history_path(root)
    extra: list[Path] = []
    if prices_csv is None:
        from alpha_system.screen_book import source_data_dir

        # Prefer dedicated replay cache (meaningful window), then history/snapshot
        extra.append(proposal_replay_prices_path(root))
        extra.append(root / "data" / "prices.csv")
        extra.append(source_data_dir(root, mkt) / "prices.csv")
    # Replay cache first so lookback dates are dense for the universe
    if prices_csv is None and proposal_replay_prices_path(root).exists():
        px = _read_prices_history(
            proposal_replay_prices_path(root),
            all_tickers,
            extra_paths=[px_path, *extra[1:]],
        )
    else:
        px = _read_prices_history(px_path, all_tickers, extra_paths=extra)
    if px.empty:
        return ProposalPriceReplayResult(
            ok=False,
            market=mkt,
            n_days=0,
            n_weeks=len(snaps),
            as_of_first=snaps[0].as_of,
            as_of_last=snaps[-1].as_of,
            missing_price_names=len(all_tickers),
            ledger=str(out_path),
            reason="prices_history_empty · 가격 보강 후 재시도",
            lookback_trading_days=lookback,
            min_trading_days=min_days,
            selection_note=selection_note,
            backfill_rows_added=backfill_added,
        )

    # lookback = return/NAV steps → need lookback+1 close sessions
    all_dates = sorted(str(d) for d in px["date"].unique())
    if len(all_dates) < 2:
        return ProposalPriceReplayResult(
            ok=False,
            market=mkt,
            n_days=0,
            n_weeks=len(snaps),
            as_of_first=snaps[0].as_of,
            as_of_last=snaps[-1].as_of,
            missing_price_names=0,
            ledger=str(out_path),
            reason="prices_need_two_sessions · 제안 유니버스 가격 보강 필요",
            lookback_trading_days=lookback,
            min_trading_days=min_days,
            selection_note=selection_note,
            backfill_rows_added=backfill_added,
        )
    need_sessions = lookback + 1
    freeze_back = not point_in_time
    if point_in_time:
        snap0 = snaps[0].as_of
        # Need one session ≤ snap for first mark, then days ≥ snap
        pit = [d for d in all_dates if d >= snap0]
        before = [d for d in all_dates if d < snap0]
        if not pit:
            return ProposalPriceReplayResult(
                ok=False,
                market=mkt,
                n_days=0,
                n_weeks=len(snaps),
                as_of_first=snaps[0].as_of,
                as_of_last=snaps[-1].as_of,
                missing_price_names=0,
                ledger=str(out_path),
                reason="pit_no_prices_on_or_after_first_snap",
                lookback_trading_days=lookback,
                min_trading_days=min_days,
                selection_note=selection_note,
                backfill_rows_added=backfill_added,
            )
        anchor = before[-1] if before else None
        dates = ([anchor] + pit) if anchor else list(pit)
        if len(dates) > need_sessions:
            # Prefer earliest PIT window from snap (not last-N of all history)
            dates = dates[:need_sessions] if anchor else dates[:need_sessions]
            if anchor and dates[0] != anchor:
                dates = [anchor] + [d for d in dates if d >= snap0][:lookback]
    else:
        dates = (
            all_dates[-need_sessions:]
            if len(all_dates) >= need_sessions
            else list(all_dates)
        )

    if len(dates) < 2:
        return ProposalPriceReplayResult(
            ok=False,
            market=mkt,
            n_days=0,
            n_weeks=len(snaps),
            as_of_first=snaps[0].as_of,
            as_of_last=snaps[-1].as_of,
            missing_price_names=0,
            ledger=str(out_path),
            reason="prices_need_two_sessions · PIT/가격 보강 필요",
            lookback_trading_days=lookback,
            min_trading_days=min_days,
            selection_note=selection_note,
            backfill_rows_added=backfill_added,
        )

    have = set(px["ticker"].unique())
    missing_n = sum(1 for t in all_tickers if t not in have)

    # PIT: available steps may be << 180 — keep requested min unless allow_short
    pit_steps = max(0, len(dates) - 1)
    if point_in_time and pit_steps < min_days and not allow_short:
        selection_note += f" · 가용 PIT {pit_steps}일 < 목표 {min_days}일"

    cost_bps, assumptions = load_shadow_cost_bps(root)
    snap_days = {s.as_of for s in snaps}
    first_prop = _proposal_for_day(
        snaps,
        dates[0],
        freeze_first_back=freeze_back,
        px=px,
        apply_soft_cut=apply_soft_cut,
        apply_ma_soft=apply_ma_soft,
        ma_mode=ma_mode,
        filter_today=True,
    )
    if not first_prop:
        # PIT: first date may be anchor < snap → use first snap basket at seed
        first_prop = _proposal_for_day(
            snaps,
            snaps[0].as_of,
            freeze_first_back=True,
            px=px,
            apply_soft_cut=apply_soft_cut,
            apply_ma_soft=apply_ma_soft,
            ma_mode=ma_mode,
            filter_today=True,
        ) or _ew_proposal(snaps[0].tickers)
    state = ShadowBookState(weights=dict(first_prop), nav=1.0)
    last_proposal: dict[str, float] = dict(first_prop)
    days_out: list[dict[str, Any]] = []

    for i in range(1, len(dates)):
        d0, d1 = str(dates[i - 1]), str(dates[i])
        if point_in_time and d1 < snaps[0].as_of:
            continue
        rets = _rets_between(px, d0, d1)
        # 중기: Soft/MA·바구니 교체는 주간 스냅일만 (일별 난매 금지)
        rebal_today = (not mid_cadence) or (d1 in snap_days)
        if rebal_today:
            proposal = _proposal_for_day(
                snaps,
                d1,
                freeze_first_back=freeze_back,
                px=px,
                apply_soft_cut=apply_soft_cut,
                apply_ma_soft=apply_ma_soft,
                ma_mode=ma_mode,
                filter_today=True,
            )
            if not proposal and point_in_time:
                proposal = _proposal_for_day(
                    snaps,
                    snaps[0].as_of,
                    freeze_first_back=True,
                    px=px,
                    apply_soft_cut=apply_soft_cut,
                    apply_ma_soft=apply_ma_soft,
                    ma_mode=ma_mode,
                    filter_today=True,
                ) or _ew_proposal(snaps[0].tickers)
            if proposal:
                last_proposal = dict(proposal)
        else:
            proposal = dict(last_proposal)
        gates = _gates_for_replay(
            proposal,
            state.weights,
            px=px,
            as_of=d1,
            apply_l3=apply_l3,
            # Soft chase / hold / mkt cash / MA reduce: 리밸일에만 (중기)
            apply_soft=apply_soft and rebal_today,
            soft_hold_r1=soft_hold_r1 if rebal_today else None,
            mkt_5d_cash=mkt_5d_cash if rebal_today else None,
            risk_on_20d=risk_on_20d if rebal_today else None,
            apply_ma_soft=apply_ma_soft and rebal_today,
            ma_mode=ma_mode,
        )
        mkt_ret = 0.0
        if rets:
            keys = [t for t in proposal if t in rets] or list(rets.keys())
            mkt_ret = sum(rets[t] for t in keys) / len(keys)
        state, day = step_day(
            state,
            name_returns=rets,
            proposal=proposal,
            gates=gates,
            cost_bps_per_one_way=cost_bps,
            market_return=mkt_ret,
            ew_returns=rets,
            as_of=d1,
            add_frac=float(add_frac) if rebal_today else 0.0,
        )
        day["market"] = mkt
        day["source"] = "proposal_price_replay"
        day["cost_assumptions_source"] = assumptions.get("source")
        day["n_proposal"] = len(proposal)
        day["lookback_trading_days"] = lookback
        day["point_in_time"] = bool(point_in_time)
        day["apply_l3"] = bool(apply_l3)
        day["apply_soft"] = bool(apply_soft)
        day["apply_soft_cut"] = bool(apply_soft_cut)
        day["apply_ma_soft"] = bool(apply_ma_soft)
        day["ma_mode"] = str(ma_mode)
        day["mid_cadence"] = bool(mid_cadence)
        day["rebal_today"] = bool(rebal_today)
        days_out.append(day)

    n_days = len(days_out)
    if point_in_time and n_days < min_days:
        # Honest short PIT: still persist for Soft·L3 diagnosis (snap history thin)
        selection_note += (
            f" · 경고:가용 {n_days}일 < 목표 {min_days}일 (주간 스냅 이력 더 필요)"
        )
    if n_days < min_days and not allow_short and not point_in_time:
        return ProposalPriceReplayResult(
            ok=False,
            market=mkt,
            n_days=n_days,
            n_weeks=len(snaps),
            as_of_first=str(days_out[0]["as_of"]) if days_out else "",
            as_of_last=str(days_out[-1]["as_of"]) if days_out else "",
            missing_price_names=missing_n,
            ledger=str(out_path),
            reason=(
                f"sample_too_short · {n_days}일 < 목표 {min_days}일 · "
                "가격 보강(ensure) 또는 기간을 예비(60일)로 낮춰 재시도"
            ),
            lookback_trading_days=lookback,
            min_trading_days=min_days,
            selection_note=selection_note,
            backfill_rows_added=backfill_added,
        )

    if persist and days_out:
        replace_ledger(out_path, days_out)

    return ProposalPriceReplayResult(
        ok=True,
        market=mkt,
        n_days=n_days,
        n_weeks=len(snaps),
        as_of_first=str(days_out[0]["as_of"]) if days_out else "",
        as_of_last=str(days_out[-1]["as_of"]) if days_out else "",
        missing_price_names=missing_n,
        ledger=str(out_path),
        lookback_trading_days=lookback,
        min_trading_days=min_days,
        selection_note=selection_note,
        backfill_rows_added=backfill_added,
    )


__all__ = [
    "LOOKBACK_PRELIMINARY",
    "LOOKBACK_PROVISIONAL",
    "LOOKBACK_STRATEGY",
    "LOOKBACK_STRATEGY_MAX",
    "ProposalPriceReplayResult",
    "ProposalWeekSnap",
    "ensure_proposal_prices",
    "load_mid_proposal_weeks",
    "prices_history_path",
    "name_stats_from_ledger",
    "proposal_replay_prices_path",
    "replay_ledger_path",
    "run_proposal_price_replay",
]
