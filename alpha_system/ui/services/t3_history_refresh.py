"""Best-effort KOSPI monthly PBR history generation for T3."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class T3HistoryRefreshResult:
    ok: bool
    message: str
    rows: int = 0
    path: Path | None = None


def try_generate_t3_history(
    root: Path,
    *,
    today: date | None = None,
    fetcher: Callable[[str, str, str], pd.DataFrame] | None = None,
) -> T3HistoryRefreshResult:
    """Fetch 10y KOSPI index PBR monthly data; never fabricate unavailable rows."""
    today = today or date.today()
    start = date(today.year - 10, today.month, 1)
    if fetcher is None:
        try:
            from pykrx import stock
        except ImportError:
            return T3HistoryRefreshResult(
                ok=False,
                message="PyKRX가 설치되지 않아 자동 산출할 수 없습니다. CSV를 수동 적재하세요.",
            )
        try:
            from src.settings.user_secrets import apply_secrets_to_env, credential_status
        except ImportError:
            apply_secrets_to_env = None  # type: ignore[assignment]
            credential_status = None  # type: ignore[assignment]
        if apply_secrets_to_env is not None:
            apply_secrets_to_env(root / "data")
        if credential_status is not None and not credential_status(root / "data").get("krx"):
            return T3HistoryRefreshResult(
                ok=False,
                message=(
                    "KRX 로그인 정보가 없습니다. 설정에서 KRX_ID/KRX_PW를 저장하거나 "
                    "data/local/user_secrets.json을 준비한 뒤 다시 시도하세요."
                ),
            )

        def _pykrx_day(start_s: str, end_s: str, ticker: str) -> pd.DataFrame:
            # Current pykrx has no freq=; it returns daily rows.
            return stock.get_index_fundamental_by_date(  # type: ignore[no-any-return]
                start_s,
                end_s,
                ticker,
            )

        def fetcher(start_s: str, end_s: str, ticker: str) -> pd.DataFrame:
            return _fetch_year_chunks(_pykrx_day, start_s, end_s, ticker)

    try:
        raw = fetcher(start.strftime("%Y%m%d"), today.strftime("%Y%m%d"), "1001")
    except Exception as exc:
        return T3HistoryRefreshResult(
            ok=False,
            message=f"KRX/PyKRX 자동 산출 실패: {exc}",
        )
    if raw is None or raw.empty:
        return T3HistoryRefreshResult(
            ok=False,
            message="KRX/PyKRX가 KOSPI PBR 이력을 반환하지 않았습니다.",
        )

    frame = raw.reset_index()
    date_col = frame.columns[0]
    pbr_col = next(
        (col for col in frame.columns if str(col).strip().upper() == "PBR"),
        None,
    )
    if pbr_col is None:
        return T3HistoryRefreshResult(
            ok=False,
            message=f"자동 산출 결과에 PBR 열이 없습니다: {list(frame.columns)}",
        )

    out = pd.DataFrame(
        {
            "month_end": pd.to_datetime(frame[date_col], errors="coerce"),
            "market_pbr": pd.to_numeric(frame[pbr_col], errors="coerce"),
        }
    ).dropna()
    out = out[out["market_pbr"] > 0].sort_values("month_end")
    # Collapse daily KRX rows to one month-end observation (last trading day).
    out = (
        out.set_index("month_end")
        .resample("ME")
        .last()
        .dropna()
        .reset_index()
    )
    # T3 is a month-end rule. Never label a partial current month as completed.
    current_month_start = pd.Timestamp(today.replace(day=1))
    out = out[out["month_end"] < current_month_start]
    out = out.drop_duplicates(subset=["month_end"], keep="last")
    if len(out) < 24:
        return T3HistoryRefreshResult(
            ok=False,
            message=f"자동 산출 표본이 부족합니다 ({len(out)}개월, 최소 24개월).",
        )
    out["month_end"] = out["month_end"].dt.date.astype(str)

    path = root / "data" / "kospi_market_pbr_history.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw_temp = tempfile.mkstemp(
        prefix=".kospi_market_pbr_",
        suffix=".csv",
        dir=path.parent,
    )
    os.close(handle)
    temp = Path(raw_temp)
    try:
        out.to_csv(temp, index=False, encoding="utf-8-sig")
        checked = pd.read_csv(temp)
        if len(checked) != len(out):
            raise ValueError("임시 CSV 검증 실패")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return T3HistoryRefreshResult(
        ok=True,
        message=f"KOSPI 월간 PBR 이력 {len(out)}개월을 저장했습니다.",
        rows=len(out),
        path=path,
    )


def _fetch_year_chunks(
    day_fetcher: Callable[[str, str, str], pd.DataFrame],
    start_s: str,
    end_s: str,
    ticker: str,
) -> pd.DataFrame:
    """Fetch year-by-year to avoid long-range KRX failures, then concat."""
    start = date(int(start_s[:4]), int(start_s[4:6]), int(start_s[6:8]))
    end = date(int(end_s[:4]), int(end_s[4:6]), int(end_s[6:8]))
    chunks: list[pd.DataFrame] = []
    cursor = start
    while cursor <= end:
        year_end = date(cursor.year, 12, 31)
        chunk_end = min(year_end, end)
        piece = day_fetcher(
            cursor.strftime("%Y%m%d"),
            chunk_end.strftime("%Y%m%d"),
            ticker,
        )
        if piece is not None and not piece.empty:
            chunks.append(piece)
        cursor = date(cursor.year + 1, 1, 1)
    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks).sort_index()
