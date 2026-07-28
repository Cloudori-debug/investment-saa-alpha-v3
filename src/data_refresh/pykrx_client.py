from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class KrxCredentialsError(RuntimeError):
    pass


class KrxFetchError(RuntimeError):
    pass


def check_krx_credentials(data_dir: Path | None = None) -> tuple[str, str]:
    if data_dir is not None:
        from src.settings.user_secrets import apply_secrets_to_env

        apply_secrets_to_env(data_dir)
    krx_id = os.environ.get("KRX_ID", "").strip()
    krx_pw = os.environ.get("KRX_PW", "").strip()
    if (not krx_id or not krx_pw) and data_dir is not None:
        from src.settings.user_secrets import load_user_secrets

        sec = load_user_secrets(data_dir)
        krx_id = krx_id or sec.krx_id
        krx_pw = krx_pw or sec.krx_pw
    if not krx_id or not krx_pw:
        raise KrxCredentialsError(
            "PyKRX 일괄 수집에는 KRX 로그인이 필요합니다. Streamlit **설정** 페이지 또는 KRX_ID/KRX_PW 환경변수를 설정하세요."
        )
    return krx_id, krx_pw


def import_pykrx_stock(data_dir: Path | None = None):
    check_krx_credentials(data_dir)
    try:
        from pykrx import stock  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError("pip install -e '.[data]' 로 pykrx를 설치하세요.") from exc
    return stock


def to_compact_date(iso_date: str) -> str:
    return iso_date.replace("-", "")


def to_iso_date(compact: str) -> str:
    c = compact.replace("-", "")
    return f"{c[:4]}-{c[4:6]}-{c[6:8]}"


def resolve_trading_date(stock: Any, as_of: str | None = None) -> str:
    """ISO date of nearest available KOSPI business day."""
    if as_of:
        compact = to_compact_date(as_of)
        tickers = stock.get_market_ticker_list(compact, market="KOSPI")
        if tickers:
            return to_iso_date(compact)
    nearest = stock.get_nearest_business_day_in_a_week()
    return to_iso_date(str(nearest))


def lookback_start(iso_date: str, calendar_days: int) -> str:
    dt = datetime.strptime(iso_date[:10], "%Y-%m-%d") - timedelta(days=calendar_days)
    return dt.strftime("%Y-%m-%d")
