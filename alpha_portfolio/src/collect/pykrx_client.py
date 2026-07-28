from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.collect.dates import to_compact, to_iso


class PyKrxImportError(ImportError):
    pass


def _secrets_paths() -> list[Path]:
    here = Path(__file__).resolve()
    roots = [
        # alpha_portfolio/data/local (optional)
        here.parents[2] / "data" / "local" / "user_secrets.json",
        # monorepo parent: investment-saa-alpha/data/local
        here.parents[3] / "data" / "local" / "user_secrets.json",
    ]
    return [p for p in roots if p.exists()]


def apply_krx_credentials() -> bool:
    """KRX_ID/KRX_PW 환경변수 또는 user_secrets.json 에서 로드."""
    if os.environ.get("KRX_ID", "").strip() and os.environ.get("KRX_PW", "").strip():
        return True
    for path in _secrets_paths():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            krx_id = str(data.get("krx_id", "")).strip()
            krx_pw = str(data.get("krx_pw", "")).strip()
            if krx_id and krx_pw:
                os.environ["KRX_ID"] = krx_id
                os.environ["KRX_PW"] = krx_pw
                return True
        except (OSError, json.JSONDecodeError):
            continue
    return False


def import_stock(*, require_login: bool = True) -> Any:
    if require_login and not apply_krx_credentials():
        raise RuntimeError(
            "KRX 로그인 필요: KRX_ID/KRX_PW 환경변수 또는 "
            "data/local/user_secrets.json (investment-saa-alpha 또는 alpha_portfolio)"
        )
    try:
        from pykrx import stock  # type: ignore[import-untyped]
    except ImportError as exc:
        raise PyKrxImportError("pip install -e '.[data]' 로 pykrx를 설치하세요.") from exc
    return stock


def resolve_trading_date(stock: Any, as_of: str | None = None) -> str:
    if as_of:
        compact = to_compact(as_of)
        try:
            tickers = stock.get_market_ticker_list(compact, market="KOSPI")
            if tickers:
                return to_iso(compact)
        except Exception:
            pass
    nearest = stock.get_nearest_business_day_in_a_week()
    return to_iso(str(nearest))
