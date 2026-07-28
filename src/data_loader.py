from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.models import MarketIndicators, PositionRow, TargetRow


_FLOAT_KEYS = (
    "kospi", "kospi_recent_high", "kospi_200ma", "sp500", "sp500_recent_high",
    "vix", "usdkrw", "korea_10y", "oil_brent", "gold",
)

_KOSPI_MA_OUTLIER_RATIO = 1.35


@dataclass(frozen=True)
class MarketIndicatorsBundle:
    """CSV 원본(raw) + 파이프라인 정규화(normalized) — compass·export 공통 권위."""

    raw: dict[str, Any]
    market: MarketIndicators
    repair_applied: bool
    repair_reason: str | None
    kospi_vs_200ma_pct_raw: float | None
    kospi_vs_200ma_pct: float | None

    def to_export_dict(self) -> dict[str, Any]:
        raw_nums = {k: _float_or_none(self.raw.get(k)) for k in _FLOAT_KEYS if k in self.raw}
        raw_nums["date"] = str(self.raw.get("date", ""))
        norm = {
            "date": self.market.date,
            "kospi": self.market.kospi,
            "kospi_recent_high": self.market.kospi_recent_high,
            "kospi_200ma": self.market.kospi_200ma,
            "sp500": self.market.sp500,
            "sp500_recent_high": self.market.sp500_recent_high,
            "vix": self.market.vix,
            "usdkrw": self.market.usdkrw,
            "korea_10y": self.market.korea_10y,
            "oil_brent": self.market.oil_brent,
            "gold": self.market.gold,
            "foreign_flow_3d": self.market.foreign_flow_3d,
            "regime": self.market.regime,
            "kospi_vs_200ma_pct": round(self.kospi_vs_200ma_pct, 2)
            if self.kospi_vs_200ma_pct is not None
            else None,
            "repair_applied": self.repair_applied,
            "repair_reason": self.repair_reason,
        }
        return {
            "market_indicators_raw": raw_nums,
            "market_indicators_normalized": norm,
        }


def _float_or_none(val: Any) -> float | None:
    try:
        text = str(val).strip()
        return float(text) if text else None
    except (TypeError, ValueError):
        return None


def kospi_vs_200ma_pct(kospi: float, kospi_200ma: float) -> float | None:
    if kospi <= 0 or kospi_200ma <= 0:
        return None
    return (kospi / kospi_200ma - 1) * 100


def normalize_market_row(row: dict, path: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """KOSPI 200MA 이상치 보정 + 메타데이터."""
    raw = dict(row)
    meta: dict[str, Any] = {
        "repair_applied": False,
        "repair_reason": None,
        "kospi_vs_200ma_pct_raw": None,
        "kospi_vs_200ma_pct": None,
    }
    try:
        kospi = float(raw.get("kospi") or 0)
        ma_raw = float(raw.get("kospi_200ma") or 0)
    except (TypeError, ValueError):
        return raw, meta

    if kospi > 0 and ma_raw > 0:
        meta["kospi_vs_200ma_pct_raw"] = kospi_vs_200ma_pct(kospi, ma_raw)

    repaired = dict(raw)
    if kospi > 0 and ma_raw > 0 and kospi / ma_raw > _KOSPI_MA_OUTLIER_RATIO:
        hist_path = path.parent / "market_indicators_history.csv" if path else None
        if hist_path and hist_path.exists():
            hist = pd.read_csv(hist_path, dtype=str, keep_default_na=False)
            for rec in reversed(hist.to_dict(orient="records")):
                try:
                    hk = float(rec.get("kospi") or 0)
                    hm = float(rec.get("kospi_200ma") or 0)
                except (TypeError, ValueError):
                    continue
                if hk > 0 and hm > 0 and hk / hm <= 1.25:
                    repaired["kospi_200ma"] = hm
                    meta["repair_applied"] = True
                    meta["repair_reason"] = "csv_200ma_ratio_outlier"
                    break

    try:
        kospi_n = float(repaired.get("kospi") or 0)
        ma_n = float(repaired.get("kospi_200ma") or 0)
        if kospi_n > 0 and ma_n > 0:
            meta["kospi_vs_200ma_pct"] = kospi_vs_200ma_pct(kospi_n, ma_n)
    except (TypeError, ValueError):
        pass

    from src.data_refresh.external_market import is_valid_korea_10y_nominal, korea_10y_from_history

    data_dir = path.parent if path else None
    try:
        k10_raw = str(repaired.get("korea_10y", "")).strip()
        if k10_raw:
            k10_v = float(k10_raw)
            if not is_valid_korea_10y_nominal(k10_v) and data_dir is not None:
                hist = korea_10y_from_history(data_dir)
                if hist is not None:
                    repaired["korea_10y"] = str(hist)
                    meta["repair_applied"] = True
                    meta["repair_reason"] = f"korea_10y_out_of_range({k10_v})"
                else:
                    meta["korea_10y_invalid"] = k10_v
    except (TypeError, ValueError):
        pass

    return repaired, meta


def _repair_kospi_200ma(row: dict, path: Path | None = None) -> dict:
    repaired, _ = normalize_market_row(row, path)
    return repaired


def _parse_market_row(row: dict, *, path: Path | None = None) -> MarketIndicators:
    row = _repair_kospi_200ma(dict(row), path)
    for key in _FLOAT_KEYS:
        if key in row and str(row.get(key, "")).strip():
            row[key] = float(row[key])
    return MarketIndicators.model_validate(row)


def _normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip()
    return t.zfill(6) if t.isdigit() else t


def _is_cash_ticker(ticker: str) -> bool:
    return str(ticker).strip().upper() == "CASH"


def _parse_optional_float(raw: object) -> float | None:
    val = str(raw or "").strip()
    return float(val) if val else None


def compute_position_value(
    ticker: str,
    quantity: float | None,
    current_price: float | None,
    *,
    fallback_value: float = 0.0,
) -> float:
    """보유수량 × 현재가 → 평가금액. CASH는 현재가=예수금(원), quantity 기본 1."""
    if _is_cash_ticker(ticker):
        if current_price and current_price > 0:
            qty = quantity if quantity and quantity > 0 else 1.0
            return qty * current_price
        return fallback_value
    if quantity and quantity > 0 and current_price and current_price > 0:
        return quantity * current_price
    return fallback_value


def infer_quantity(row: PositionRow) -> float | None:
    if row.quantity is not None and row.quantity > 0:
        return row.quantity
    if _is_cash_ticker(row.ticker):
        return 1.0
    if row.current_price and row.current_price > 0 and row.current_value > 0:
        return row.current_value / row.current_price
    return None


def load_latest_close_map(prices_path: Path) -> tuple[dict[str, float], str]:
    """prices.csv 최신 종가 맵 (ticker → close)."""
    if not prices_path.exists():
        return {}, ""
    prices = pd.read_csv(prices_path, dtype=str, keep_default_na=False)
    if prices.empty or "ticker" not in prices.columns or "close" not in prices.columns:
        return {}, ""
    latest = prices.copy()
    latest["ticker"] = latest["ticker"].map(_normalize_ticker)
    as_of = ""
    if "date" in latest.columns:
        latest = latest.sort_values("date").groupby("ticker", as_index=False).tail(1)
        as_of = str(latest["date"].max()) if not latest.empty else ""
    close_map: dict[str, float] = {}
    for ticker, close in latest.set_index("ticker")["close"].items():
        val = pd.to_numeric(close, errors="coerce")
        if pd.notna(val) and float(val) > 0:
            close_map[_normalize_ticker(str(ticker))] = float(val)
    return close_map, as_of


def apply_prices_from_csv(
    df: pd.DataFrame,
    prices_path: Path,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """positions 표에 prices.csv 종가를 자동 반영 (CASH 제외)."""
    stats: dict[str, object] = {
        "applied": 0,
        "missing_tickers": [],
        "as_of": "",
        "source": str(prices_path.name),
    }
    if df.empty:
        return df, stats
    close_map, as_of = load_latest_close_map(prices_path)
    stats["as_of"] = as_of
    if not close_map:
        stats["missing_tickers"] = [
            str(t)
            for t in df["ticker"].tolist()
            if str(t).strip().upper() != "CASH"
        ]
        return df, stats

    out = df.copy()
    missing: list[str] = []
    applied = 0
    for idx, row in out.iterrows():
        ticker = _normalize_ticker(str(row.get("ticker", "")))
        if _is_cash_ticker(ticker):
            continue
        px = close_map.get(ticker)
        if px is None:
            missing.append(ticker)
            continue
        out.at[idx, "current_price"] = px
        applied += 1
    stats["applied"] = applied
    stats["missing_tickers"] = missing
    return enrich_positions_dataframe(out), stats


def enrich_positions_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """수량·현재가로 평가금액·비중(%) 자동 계산."""
    if df.empty:
        return df
    out = df.copy()
    qty_series = (
        pd.to_numeric(out["quantity"], errors="coerce")
        if "quantity" in out.columns
        else pd.Series([pd.NA] * len(out), index=out.index)
    )
    price_series = (
        pd.to_numeric(out["current_price"], errors="coerce")
        if "current_price" in out.columns
        else pd.Series([pd.NA] * len(out), index=out.index)
    )
    fallback = pd.to_numeric(out.get("current_value"), errors="coerce").fillna(0)
    values = []
    for idx in range(len(out)):
        ticker = str(out.iloc[idx].get("ticker", ""))
        q = float(qty_series.iloc[idx]) if pd.notna(qty_series.iloc[idx]) else None
        p = float(price_series.iloc[idx]) if pd.notna(price_series.iloc[idx]) else None
        fb = float(fallback.iloc[idx])
        values.append(compute_position_value(ticker, q, p, fallback_value=fb))
    out["current_value"] = pd.Series(values, index=out.index).round(0)
    total = float(out["current_value"].sum())
    out["weight_pct"] = (
        (out["current_value"] / total * 100).round(2) if total > 0 else 0.0
    )
    return out


def load_positions(path: Path) -> list[PositionRow]:
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df = df.apply(lambda col: col.str.strip() if col.dtype == object else col)
    rows: list[PositionRow] = []
    for record in df.to_dict(orient="records"):
        record["ticker"] = _normalize_ticker(record["ticker"])
        record["quantity"] = _parse_optional_float(record.get("quantity"))
        record["current_value"] = float(record["current_value"])
        for key in ("avg_price", "current_price"):
            record[key] = _parse_optional_float(record.get(key))
        row = PositionRow.model_validate(record)
        value = compute_position_value(
            row.ticker,
            infer_quantity(row),
            row.current_price,
            fallback_value=row.current_value,
        )
        if value > 0 and abs(value - row.current_value) > 0.5:
            row = row.model_copy(update={"current_value": value})
        rows.append(row)
    return rows


def normalize_target_weights_to_100(
    rows: list[TargetRow],
    *,
    tolerance: float = 0.01,
) -> tuple[list[TargetRow], bool]:
    """target_weight 합계를 100%로 비례 스케일. (rows, changed)."""
    if not rows:
        return rows, False
    total = round(sum(r.target_weight for r in rows), 4)
    if abs(total - 100.0) <= tolerance:
        return rows, False
    if total <= 0:
        return rows, False
    factor = 100.0 / total
    scaled: list[TargetRow] = []
    for row in rows:
        scaled.append(
            row.model_copy(update={"target_weight": round(row.target_weight * factor, 2)})
        )
    drift = round(100.0 - sum(r.target_weight for r in scaled), 2)
    if drift != 0:
        idx = max(range(len(scaled)), key=lambda i: scaled[i].target_weight)
        top = scaled[idx]
        scaled[idx] = top.model_copy(
            update={"target_weight": round(top.target_weight + drift, 2)}
        )
    return scaled, True


def load_target_portfolio(path: Path) -> list[TargetRow]:
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    rows: list[TargetRow] = []
    for record in df.to_dict(orient="records"):
        record["ticker"] = _normalize_ticker(record["ticker"])
        for key in ("target_weight", "min_weight", "max_weight"):
            record[key] = float(record[key])
        rows.append(TargetRow.model_validate(record))
    return rows


def load_market_indicators_bundle(path: Path) -> MarketIndicatorsBundle:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if df.empty:
        raise ValueError("market_indicators.csv is empty")
    raw = df.iloc[-1].to_dict()
    repaired, meta = normalize_market_row(raw, path)
    for key in _FLOAT_KEYS:
        if key in repaired and str(repaired.get(key, "")).strip():
            repaired[key] = float(repaired[key])
    market = MarketIndicators.model_validate(repaired)
    return MarketIndicatorsBundle(
        raw=raw,
        market=market,
        repair_applied=bool(meta.get("repair_applied")),
        repair_reason=meta.get("repair_reason"),
        kospi_vs_200ma_pct_raw=meta.get("kospi_vs_200ma_pct_raw"),
        kospi_vs_200ma_pct=meta.get("kospi_vs_200ma_pct"),
    )


def write_market_indicators_normalized(bundle: MarketIndicatorsBundle, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    import json as _json

    path.write_text(
        _json.dumps(bundle.to_export_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_market_indicators(path: Path) -> MarketIndicators:
    return load_market_indicators_bundle(path).market


def load_market_indicators_history(path: Path) -> list[MarketIndicators]:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return [_parse_market_row(row, path=path) for row in df.to_dict(orient="records")]


def load_market_row(path: Path, date: str) -> MarketIndicators | None:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    matched = df[df["date"] == date]
    if matched.empty:
        return None
    return _parse_market_row(matched.iloc[-1].to_dict(), path=path)


def write_target_portfolio(rows: list[TargetRow], path: Path) -> None:
    from src.alpha.target_write_audit import assert_operational_write_allowed

    assert_operational_write_allowed(path)
    df = pd.DataFrame([r.model_dump() for r in rows])
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def positions_to_dataframe(
    positions: list[PositionRow],
    *,
    prices_path: Path | None = None,
) -> pd.DataFrame:
    total = sum(p.current_value for p in positions)
    rows = []
    for p in positions:
        weight = (p.current_value / total * 100) if total else 0.0
        qty = infer_quantity(p)
        rows.append(
            {
                "ticker": p.ticker,
                "name": p.name,
                "asset_group": p.asset_group,
                "sector": p.sector,
                "style": p.style,
                "quantity": round(qty, 4) if qty is not None else "",
                "current_price": round(p.current_price, 2) if p.current_price is not None else "",
                "current_value": round(p.current_value, 0),
                "weight_pct": round(weight, 2),
                "avg_price": p.avg_price if p.avg_price is not None else "",
            }
        )
    df = enrich_positions_dataframe(pd.DataFrame(rows))
    if prices_path is not None:
        df, _ = apply_prices_from_csv(df, prices_path)
    return df


def dataframe_to_positions(df: pd.DataFrame) -> list[PositionRow]:
    enriched = enrich_positions_dataframe(df)
    rows: list[PositionRow] = []
    for record in enriched.to_dict(orient="records"):
        ticker = _normalize_ticker(str(record.get("ticker", "")).strip())
        if not ticker:
            continue
        qty = _parse_optional_float(record.get("quantity"))
        price = _parse_optional_float(record.get("current_price"))
        value = compute_position_value(
            ticker,
            qty,
            price,
            fallback_value=float(record.get("current_value", 0) or 0),
        )
        if value <= 0:
            raise ValueError(f"{ticker}: 보유수량과 현재가(또는 CASH 금액)를 입력하세요.")
        avg_raw = str(record.get("avg_price", "")).strip()
        rows.append(
            PositionRow.model_validate(
                {
                    "ticker": ticker,
                    "name": str(record.get("name", ticker)).strip() or ticker,
                    "asset_group": str(record.get("asset_group", "")).strip(),
                    "sector": str(record.get("sector", "")).strip(),
                    "style": str(record.get("style", "")).strip(),
                    "quantity": qty,
                    "current_value": value,
                    "avg_price": float(avg_raw) if avg_raw else None,
                    "current_price": price,
                }
            )
        )
    return rows


def write_positions(rows: list[PositionRow], path: Path, *, backup: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup and path.exists():
        from datetime import datetime, timezone
        import shutil

        backup_dir = path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(path, backup_dir / f"positions.{stamp}.bak.csv")
    out = pd.DataFrame(
        [
            {
                "ticker": r.ticker,
                "name": r.name,
                "asset_group": r.asset_group,
                "sector": r.sector,
                "style": r.style,
                "quantity": int(round(r.quantity)) if r.quantity is not None else "",
                "current_value": int(round(r.current_value)),
                "avg_price": r.avg_price if r.avg_price is not None else "",
                "current_price": r.current_price if r.current_price is not None else "",
            }
            for r in rows
        ]
    )
    out.to_csv(path, index=False, encoding="utf-8-sig")
