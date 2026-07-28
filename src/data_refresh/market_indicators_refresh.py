from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.data_refresh.external_market import (
    ExternalMarketFetchResult,
    KOREA_10Y_NOMINAL_MAX,
    KOREA_10Y_NOMINAL_MIN,
    fetch_external_market,
    fetch_foreign_flow_pykrx,
    fetch_korea_10y_pykrx,
    is_valid_korea_10y_nominal,
    korea_10y_from_history,
)
from src.data_refresh.pykrx_client import (
    KrxCredentialsError,
    import_pykrx_stock,
    lookback_start,
    resolve_trading_date,
    to_compact_date,
)

KOSPI_INDEX_CODE = "1001"
MARKET_COLUMNS = [
    "date", "kospi", "kospi_recent_high", "kospi_200ma",
    "sp500", "sp500_recent_high", "vix", "usdkrw", "korea_10y",
    "oil_brent", "gold", "foreign_flow_3d", "regime",
    "regime_override_reason", "regime_set_date", "regime_expires_date",
]


@dataclass
class MarketIndicatorsRefreshResult:
    as_of: str
    updated_fields: list[str] = field(default_factory=list)
    preserved_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    path: str = ""


def _load_existing_row(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return df.iloc[-1].to_dict() if not df.empty else {}


def _compute_kospi_metrics(index_df: pd.DataFrame, *, existing: dict[str, str] | None = None) -> tuple[dict[str, float], list[str]]:
    warnings: list[str] = []
    if index_df.empty:
        raise ValueError("KOSPI index OHLCV empty")
    closes = index_df["종가"].astype(float)
    kospi = float(closes.iloc[-1])
    recent_high = float(closes.max())
    ma_window = min(200, len(closes))
    kospi_200ma = float(closes.tail(ma_window).mean())
    if ma_window < 120:
        warnings.append(f"kospi_200ma: 거래일 {ma_window}일만 사용 — 120일 미만")
    if existing:
        try:
            prev_ma = float(existing.get("kospi_200ma") or 0)
        except ValueError:
            prev_ma = 0.0
        if prev_ma > 0 and kospi_200ma > 0:
            prev_ratio = kospi / prev_ma if prev_ma else 0
            new_ratio = kospi / kospi_200ma
            ma_jump = abs(kospi_200ma - prev_ma) / prev_ma
            if ma_jump > 0.12 and (new_ratio > 1.35 or new_ratio < 0.75):
                warnings.append(
                    f"kospi_200ma 급변 보정: {kospi_200ma:.0f} → 이전 {prev_ma:.0f} 유지 "
                    f"(KOSPI/200MA {new_ratio:.0%}, 이전 {prev_ratio:.0%})"
                )
                kospi_200ma = prev_ma
    return {
        "kospi": round(kospi, 2),
        "kospi_recent_high": round(recent_high, 2),
        "kospi_200ma": round(kospi_200ma, 2),
    }, warnings


def _fetch_kospi_pykrx(
    data_dir: Path,
    as_of: str | None,
    lookback_days: int,
    *,
    existing: dict[str, str] | None = None,
) -> tuple[str, dict[str, float] | None, str | None, list[str]]:
    try:
        stock = import_pykrx_stock(data_dir)
    except (KrxCredentialsError, ImportError) as exc:
        return as_of or "", None, str(exc), []

    as_of_date = resolve_trading_date(stock, as_of)
    start = lookback_start(as_of_date, lookback_days)
    try:
        index_df = stock.get_index_ohlcv_by_date(
            to_compact_date(start), to_compact_date(as_of_date), KOSPI_INDEX_CODE
        )
    except Exception as exc:
        return as_of_date, None, f"KOSPI index fetch failed: {exc}", []

    if index_df is None or index_df.empty:
        return as_of_date, None, "KOSPI index 데이터 없음", []

    metrics, ma_warnings = _compute_kospi_metrics(index_df, existing=existing)
    return as_of_date, metrics, None, ma_warnings


def _apply_external(row: dict[str, str], ext: ExternalMarketFetchResult, updated: list[str]) -> None:
    mapping = {
        "sp500": "sp500",
        "sp500_recent_high": "sp500",
        "vix": "vix",
        "oil_brent": "oil_brent",
        "gold": "gold",
    }
    for field, series_key in mapping.items():
        snap = ext.series.get(series_key)
        if not snap:
            continue
        if field == "sp500_recent_high":
            row[field] = str(snap.recent_high)
        elif field == "sp500":
            row[field] = str(round(snap.close, 2))
        elif field == "vix":
            row[field] = str(round(snap.close, 2))
        elif field == "oil_brent":
            row[field] = str(round(snap.close, 2))
        elif field == "gold":
            row[field] = str(round(snap.close, 2))
        if field not in updated:
            updated.append(field)

    if ext.fx_usdkrw:
        row["usdkrw"] = str(round(ext.fx_usdkrw, 2))
        if "usdkrw" not in updated:
            updated.append("usdkrw")


def refresh_all_market_indicators(
    data_dir: Path,
    *,
    as_of: str | None = None,
    lookback_days: int = 400,
    use_pykrx: bool = True,
    use_external: bool = True,
) -> MarketIndicatorsRefreshResult:
    """KOSPI(PyKRX) + 글로벌 지표(Yahoo) + 국채/외국인(PyKRX·Tier2) → market_indicators.csv."""
    path = data_dir / "market_indicators.csv"
    existing = _load_existing_row(path)
    updated: list[str] = []
    preserved: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []

    row = {col: existing.get(col, "") for col in MARKET_COLUMNS}
    as_of_date = as_of or existing.get("date") or ""

    if use_pykrx:
        as_of_date, kospi_metrics, kospi_err, ma_warnings = _fetch_kospi_pykrx(
            data_dir, as_of, lookback_days, existing=existing,
        )
        warnings.extend(ma_warnings)
        if kospi_metrics:
            row["date"] = as_of_date
            updated.append("date")
            for k, v in kospi_metrics.items():
                row[k] = str(v)
                updated.append(k)
        elif kospi_err:
            warnings.append(kospi_err)

    if use_external:
        ext = fetch_external_market(as_of=as_of_date or None)
        if not as_of_date:
            as_of_date = ext.as_of
            row["date"] = as_of_date
            updated.append("date")
        _apply_external(row, ext, updated)
        warnings.extend(ext.warnings)
        errors.extend(ext.errors)
        from src.data_refresh.external_market import build_provenance, write_provenance

        write_provenance(data_dir, build_provenance(ext, row.get("date", as_of_date)))

    if as_of_date:
        row["date"] = as_of_date
        if "date" not in updated:
            updated.append("date")
        if use_pykrx:
            flow = fetch_foreign_flow_pykrx(data_dir, as_of_date)
            if flow:
                row["foreign_flow_3d"] = flow
                updated.append("foreign_flow_3d")

        k10y = fetch_korea_10y_pykrx(data_dir, as_of_date)
        if k10y is None:
            k10y = korea_10y_from_history(data_dir)
            if k10y is not None:
                warnings.append("korea_10y — PyKRX 실패/범위외, history 유효값 사용")
        if k10y is not None:
            row["korea_10y"] = str(k10y)
            updated.append("korea_10y")
        elif str(existing.get("korea_10y", "")).strip():
            try:
                prev = float(existing["korea_10y"])
                if not is_valid_korea_10y_nominal(prev):
                    warnings.append(
                        f"korea_10y={prev} — 명목 10Y 범위({KOREA_10Y_NOMINAL_MIN}~{KOREA_10Y_NOMINAL_MAX}%) 밖, 수동 갱신 필요"
                    )
            except ValueError:
                pass

    if not row.get("regime"):
        row["regime"] = existing.get("regime") or "NEUTRAL"
    if not row.get("foreign_flow_3d"):
        row["foreign_flow_3d"] = existing.get("foreign_flow_3d") or "neutral"

    for col in MARKET_COLUMNS:
        if col in updated:
            continue
        if existing.get(col):
            row[col] = existing[col]
            preserved.append(col)

    for fld in MARKET_COLUMNS:
        if fld in ("date", "regime", "foreign_flow_3d"):
            continue
        val = str(row.get(fld, "")).strip()
        if not val or (fld != "foreign_flow_3d" and _is_zero(val)):
            warnings.append(f"{fld} 미갱신 — 수동 확인")

    out_df = pd.DataFrame([row], columns=MARKET_COLUMNS)
    path.parent.mkdir(parents=True, exist_ok=True)

    from src.data_loader import normalize_market_row

    repaired, ma_meta = normalize_market_row(row, path)
    if ma_meta.get("repair_applied"):
        fixed_ma = repaired.get("kospi_200ma")
        if fixed_ma is not None:
            row["kospi_200ma"] = str(fixed_ma)
            out_df = pd.DataFrame([row], columns=MARKET_COLUMNS)
            warnings.append(
                f"kospi_200ma CSV 기록 보정: {ma_meta.get('repair_reason', 'outlier')} "
                f"→ {fixed_ma}"
            )

    out_df.to_csv(path, index=False)
    append_market_history_row(data_dir, row)

    return MarketIndicatorsRefreshResult(
        as_of=row.get("date", as_of_date),
        updated_fields=sorted(set(updated)),
        preserved_fields=preserved,
        warnings=warnings,
        errors=errors,
        path=str(path),
    )


def _is_zero(val: str) -> bool:
    try:
        return float(val) <= 0
    except ValueError:
        return True


def refresh_kospi_from_pykrx(
    data_dir: Path,
    *,
    as_of: str | None = None,
    lookback_days: int = 400,
) -> MarketIndicatorsRefreshResult:
    """하위 호환 — KOSPI만 갱신."""
    return refresh_all_market_indicators(
        data_dir, as_of=as_of, lookback_days=lookback_days, use_pykrx=True, use_external=False
    )


def append_market_history_row(data_dir: Path, row: dict[str, str]) -> None:
    hist_path = data_dir / "market_indicators_history.csv"
    if hist_path.exists():
        df = pd.read_csv(hist_path, dtype=str, keep_default_na=False)
        if not df.empty and row["date"] in df["date"].astype(str).values:
            return
    else:
        df = pd.DataFrame(columns=MARKET_COLUMNS)
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(hist_path, index=False)
