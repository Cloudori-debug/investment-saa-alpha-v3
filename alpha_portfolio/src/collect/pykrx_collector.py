from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pandas as pd

from src.collect.dates import lookback_start, normalize_ticker, to_compact, to_iso
from src.collect.pykrx_client import import_stock, resolve_trading_date
from src.config_loader import load_yaml
from src.loaders import load_fundamentals, load_positions, load_target_portfolio

Scope = Literal["holdings", "liquid", "all"]
Market = Literal["KOSPI", "KOSDAQ"]


@dataclass
class CollectResult:
    as_of: str
    universe_count: int
    snapshot_count: int
    scope: str
    warnings: list[str] = field(default_factory=list)
    paths: dict[str, str] = field(default_factory=dict)


def _bool_str(val: bool) -> str:
    return "true" if val else "false"


def _is_etf_name(name: str) -> bool:
    n = name or ""
    keys = ("ETF", "ETN", "KODEX", "TIGER", "ARIRANG", "KBSTAR", "HANARO", "KOSEF", "SOL ", "ACE ")
    return any(k in n.upper() for k in keys)


def fetch_universe(stock, as_of: str, markets: list[Market]) -> pd.DataFrame:
    compact = to_compact(as_of)
    rows: list[dict] = []
    for market in markets:
        try:
            tickers = [normalize_ticker(t) for t in stock.get_market_ticker_list(compact, market=market)]
        except Exception:
            continue
        for ticker in tickers:
            try:
                name = str(stock.get_market_ticker_name(ticker))
            except Exception:
                name = ticker
            is_etf = _is_etf_name(name)
            is_spac = "스팩" in name.upper() or "SPAC" in name.upper()
            rows.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "market": market,
                    "sector": "",
                    "listing_date": "",
                    "is_etf": _bool_str(is_etf),
                    "is_spac": _bool_str(is_spac),
                    "is_managed": "false",
                    "is_halted": "false",
                    "as_of": as_of,
                }
            )
    return pd.DataFrame(rows).drop_duplicates(subset=["ticker"])


def _compute_price_metrics(closes: pd.Series) -> dict[str, float]:
    if closes.empty:
        return {}
    closes = closes.sort_index().astype(float)
    last = float(closes.iloc[-1])
    out: dict[str, float] = {}
    if len(closes) > 126:
        base = float(closes.iloc[-127])
        out["return_6m"] = round((last / base) - 1.0, 4) if base else 0.0
    if len(closes) >= 20:
        rets = closes.pct_change().dropna()
        out["volatility_1y"] = round(float(rets.tail(252).std() * (252**0.5) * 100), 2) if len(rets) else 0.0
    tail = closes.tail(252)
    out["high_52w"] = float(tail.max())
    out["low_52w"] = float(tail.min())
    return out


def _col(df: pd.DataFrame, *names: str) -> pd.Series | None:
    for name in names:
        if name in df.columns:
            return df[name]
    return None


def _build_snapshot_row(
    ticker: str,
    as_of: str,
    ohlcv: pd.DataFrame,
    cap_hist: pd.DataFrame | None,
    cap_today: pd.Series | None,
) -> dict:
    close_s = _col(ohlcv, "종가", "close")
    vol_s = _col(ohlcv, "거래량", "volume")
    close = float(close_s.iloc[-1]) if close_s is not None and not close_s.empty else 0.0
    volume = int(vol_s.iloc[-1]) if vol_s is not None and not vol_s.empty else 0
    tv_today = close * volume
    metrics = _compute_price_metrics(close_s) if close_s is not None else {}

    # Market cap: leave NaN (missing) when the API returns nothing.
    # Never fabricate 0.0 — a silent 0 is indistinguishable from a real tiny cap
    # and would make the market-cap gate reject the name as "low_market_cap".
    mcap: float = float("nan")
    if cap_today is not None:
        for key in ("시가총액", "market_cap"):
            if key in cap_today.index:
                val = float(cap_today[key])
                mcap = val if val > 0 else float("nan")
                break
    if (mcap != mcap) and cap_hist is not None and not cap_hist.empty:  # NaN check
        mcap_s = _col(cap_hist, "시가총액", "market_cap")
        if mcap_s is not None and not mcap_s.empty:
            val = float(mcap_s.iloc[-1])
            mcap = val if val > 0 else float("nan")

    avg20 = 0.0
    if cap_hist is not None and not cap_hist.empty:
        tv_col = _col(cap_hist, "거래대금", "trading_value")
        if tv_col is not None:
            avg20 = float(tv_col.astype(float).tail(20).mean())
        elif close_s is not None and vol_s is not None:
            avg20 = float((close_s.astype(float) * vol_s.astype(float)).tail(20).mean())

    return {
        "ticker": ticker,
        "as_of": as_of,
        "close": close,
        "market_cap": mcap,
        "volume": volume,
        "trading_value": tv_today,
        "avg_trading_value_20d": avg20,
        "high_52w": metrics.get("high_52w", close),
        "low_52w": metrics.get("low_52w", close),
        "return_6m": metrics.get("return_6m", 0.0),
        "volatility_1y": metrics.get("volatility_1y", 0.0),
        "beta_kospi200": "",
    }


def fetch_price_snapshots(
    stock,
    tickers: list[str],
    as_of: str,
    *,
    sleep_sec: float = 0.12,
) -> pd.DataFrame:
    compact_end = to_compact(as_of)
    compact_start = to_compact(lookback_start(as_of, 400))
    cap_today_df = None
    try:
        cap_today_df = stock.get_market_cap_by_ticker(compact_end, market="ALL")
        cap_today_df.index = cap_today_df.index.map(normalize_ticker)
    except Exception:
        pass

    rows: list[dict] = []
    for i, ticker in enumerate(tickers):
        try:
            ohlcv = stock.get_market_ohlcv(compact_start, compact_end, ticker)
            if ohlcv is None or ohlcv.empty:
                continue
            cap_hist = None
            try:
                cap_hist = stock.get_market_cap(compact_start, compact_end, ticker)
            except Exception:
                pass
            cap_today = cap_today_df.loc[ticker] if cap_today_df is not None and ticker in cap_today_df.index else None
            rows.append(_build_snapshot_row(ticker, as_of, ohlcv, cap_hist, cap_today))
        except Exception:
            continue
        if sleep_sec and i < len(tickers) - 1:
            time.sleep(sleep_sec)
    return pd.DataFrame(rows)


def _collect_wanted(paths: dict[str, Path]) -> set[str]:
    wanted: set[str] = set()
    for loader, kr_only in (
        (load_positions(paths["raw"] / "positions.csv"), True),
        (load_fundamentals(paths["raw"] / "fundamentals.csv"), False),
        (load_target_portfolio(paths["raw"] / "target_portfolio.csv"), True),
    ):
        df = loader
        if df.empty:
            continue
        if kr_only and "asset_group" in df.columns:
            df = df[df["asset_group"] == "kr_alpha"]
        wanted.update(df["ticker"].astype(str).map(normalize_ticker))
    return wanted


def filter_liquid_by_cap(
    universe: pd.DataFrame,
    cap_df: pd.DataFrame | None,
    gate_cfg: dict,
    *,
    max_tickers: int = 0,
) -> list[str]:
    """Bulk 시총 API로 Gate 1차 필터 (liquid scope)."""
    common = universe[
        (universe["is_etf"].astype(str).str.lower() != "true")
        & (universe["is_spac"].astype(str).str.lower() != "true")
    ].copy()
    if common.empty:
        return []

    cap_min = float(gate_cfg.get("market_cap_min", 0))
    tickers = common["ticker"].astype(str).map(normalize_ticker).tolist()
    if cap_df is None or cap_df.empty:
        return tickers[:max_tickers] if max_tickers > 0 else tickers

    cap_df = cap_df.copy()
    cap_df.index = cap_df.index.map(normalize_ticker)
    mcap_col = next((c for c in ("시가총액", "market_cap") if c in cap_df.columns), None)
    if not mcap_col:
        return tickers[:max_tickers] if max_tickers > 0 else tickers

    passed: list[tuple[str, float]] = []
    for ticker in tickers:
        if ticker not in cap_df.index:
            continue
        mcap = float(cap_df.loc[ticker, mcap_col])
        if mcap >= cap_min:
            passed.append((ticker, mcap))
    passed.sort(key=lambda x: x[1], reverse=True)
    out = [t for t, _ in passed]
    if max_tickers > 0:
        out = out[:max_tickers]
    return out


def select_tickers(
    universe: pd.DataFrame,
    *,
    scope: Scope,
    paths: dict[str, Path],
    gate_cfg: dict,
    max_tickers: int,
    cap_df: pd.DataFrame | None = None,
    liquid_cfg: dict | None = None,
) -> list[str]:
    liquid_cfg = liquid_cfg or {}
    common = universe[
        (universe["is_etf"].astype(str).str.lower() != "true")
        & (universe["is_spac"].astype(str).str.lower() != "true")
    ]
    tickers = common["ticker"].astype(str).map(normalize_ticker).tolist()
    wanted = _collect_wanted(paths)

    if scope == "holdings":
        tickers = [t for t in tickers if t in wanted] or sorted(wanted)
    elif scope == "liquid":
        liquid_max = int(liquid_cfg.get("max_tickers", max_tickers or 0))
        tickers = filter_liquid_by_cap(universe, cap_df, gate_cfg, max_tickers=liquid_max)
        if liquid_cfg.get("include_holdings", True) and wanted:
            tickers = sorted(set(tickers) | wanted)
    elif scope == "all":
        pass

    if max_tickers > 0 and scope != "liquid":
        tickers = tickers[:max_tickers]
    return tickers


def enrich_fundamentals_per_pbr(
    fundamentals_path: Path,
    stock,
    as_of: str,
    tickers: list[str],
) -> tuple[int, dict[str, dict[str, float]]]:
    per_pbr_map: dict[str, dict[str, float]] = {}
    if not fundamentals_path.exists():
        return 0, per_pbr_map
    df = load_fundamentals(fundamentals_path)
    if df.empty:
        return 0, per_pbr_map
    compact = to_compact(as_of)
    updated = 0
    for market in ("KOSPI", "KOSDAQ"):
        try:
            fdf = stock.get_market_fundamental(compact, market=market)
        except Exception:
            continue
        if fdf.empty:
            continue
        fdf.index = fdf.index.map(normalize_ticker)
        for idx, row in df.iterrows():
            t = normalize_ticker(str(row["ticker"]))
            if t not in tickers or t not in fdf.index:
                continue
            src = fdf.loc[t]
            per = float(src.get("PER", 0) or 0)
            pbr = float(src.get("PBR", 0) or 0)
            if per > 0:
                per_pbr_map.setdefault(t, {})["per"] = round(per, 2)
            if pbr > 0:
                per_pbr_map.setdefault(t, {})["pbr"] = round(pbr, 2)
            if (pd.isna(row.get("per")) or row.get("per") == "") and per > 0:
                df.at[idx, "per"] = round(per, 2)
                updated += 1
            if (pd.isna(row.get("pbr")) or row.get("pbr") == "") and pbr > 0:
                df.at[idx, "pbr"] = round(pbr, 2)
                updated += 1
    if updated:
        df.to_csv(fundamentals_path, index=False, encoding="utf-8-sig")
    return updated, per_pbr_map


def run_collect(
    root: Path | None = None,
    *,
    as_of: str | None = None,
    scope: Scope | None = None,
) -> CollectResult:
    from src.paths import get_paths

    paths = get_paths(root)
    paths["raw"].mkdir(parents=True, exist_ok=True)

    cfg = load_yaml(paths["config"] / "collect.yaml").get("collect", {})
    gate_cfg = load_yaml(paths["config"] / "universe_gate.yaml").get("gate", {})
    scope = scope or cfg.get("scope", "holdings")  # type: ignore[assignment]
    markets = cfg.get("markets", ["KOSPI", "KOSDAQ"])
    sleep_sec = float(cfg.get("sleep_sec", 0.12))
    max_tickers = int(cfg.get("max_tickers", 0))
    enrich = bool(cfg.get("enrich_per_pbr", True))
    liquid_cfg = cfg.get("liquid", {})

    warnings: list[str] = []
    snapshot_path = paths["raw"] / "price_snapshot.csv"
    universe_path = paths["raw"] / "kospi_universe.csv"
    fundamentals_path = paths["raw"] / "fundamentals.csv"

    try:
        stock = import_stock(require_login=True)
        as_of_date = resolve_trading_date(stock, as_of)

        universe = fetch_universe(stock, as_of_date, markets)
        universe.to_csv(universe_path, index=False, encoding="utf-8-sig")

        cap_today_df = None
        try:
            cap_today_df = stock.get_market_cap_by_ticker(to_compact(as_of_date), market="ALL")
            cap_today_df.index = cap_today_df.index.map(normalize_ticker)
        except Exception:
            pass

        tickers = select_tickers(
            universe,
            scope=scope,  # type: ignore[arg-type]
            paths=paths,
            gate_cfg=gate_cfg,
            max_tickers=max_tickers,
            cap_df=cap_today_df,
            liquid_cfg=liquid_cfg,
        )
        if not tickers:
            warnings.append("수집 대상 ticker 없음 — positions/fundamentals 확인")

        snapshot = fetch_price_snapshots(stock, tickers, as_of_date, sleep_sec=sleep_sec)
        if snapshot.empty:
            raise RuntimeError("price_snapshot 수집 0건")
        snapshot.to_csv(snapshot_path, index=False, encoding="utf-8-sig")

        if "market_cap" in snapshot.columns:
            missing_cap = int(
                pd.to_numeric(snapshot["market_cap"], errors="coerce").isna().sum()
            )
            if missing_cap:
                warnings.append(
                    f"시가총액 미수집 {missing_cap}/{len(snapshot)}종 — PyKRX 시총 조회 실패. "
                    "게이트가 low_market_cap으로 자동 탈락시키므로 유효 거래일로 재수집 필요."
                )

        per_pbr_map: dict[str, dict[str, float]] = {}
        if enrich:
            n, per_pbr_map = enrich_fundamentals_per_pbr(fundamentals_path, stock, as_of_date, tickers)
            if n:
                warnings.append(f"fundamentals PER/PBR {n}건 보강")

        if scope == "liquid" and liquid_cfg.get("sync_stub_fundamentals", True):
            from src.collect.liquid_fundamentals import sync_liquid_fundamentals_stubs

            stub_n, template_path = sync_liquid_fundamentals_stubs(
                fundamentals_path,
                snapshot,
                universe,
                as_of=as_of_date,
                gate_cfg=gate_cfg,
                max_stubs=int(liquid_cfg.get("max_stub_rows", 150)),
                per_pbr_map=per_pbr_map,
            )
            if stub_n:
                warnings.append(f"liquid stub fundamentals {stub_n}건 추가 (verified=stub)")
            if template_path:
                warnings.append(f"수동 입력 템플릿: {template_path.name}")

        return CollectResult(
            as_of=as_of_date,
            universe_count=len(universe),
            snapshot_count=len(snapshot),
            scope=str(scope),
            warnings=warnings,
            paths={"universe": str(universe_path), "price_snapshot": str(snapshot_path)},
        )
    except Exception as exc:
        if snapshot_path.exists():
            existing = pd.read_csv(snapshot_path)
            warnings.append(f"PyKRX 수집 실패 — 기존 price_snapshot 유지 ({exc})")
            return CollectResult(
                as_of=as_of or "",
                universe_count=0,
                snapshot_count=len(existing),
                scope=str(scope),
                warnings=warnings,
                paths={"price_snapshot": str(snapshot_path)},
            )
        raise
