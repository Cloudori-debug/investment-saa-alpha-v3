from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECRET_KEYS = ("dart_api_key", "krx_id", "krx_pw", "fred_api_key", "kosis_api_key")


@dataclass
class UserSecrets:
    dart_api_key: str = ""
    krx_id: str = ""
    krx_pw: str = ""
    fred_api_key: str = ""
    kosis_api_key: str = ""
    pykrx_scope: str = "liquid"
    dart_scope: str = "prices"
    default_as_of: str = ""
    updated_at: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserSecrets:
        return cls(
            dart_api_key=str(data.get("dart_api_key", "")).strip(),
            krx_id=str(data.get("krx_id", "")).strip(),
            krx_pw=str(data.get("krx_pw", "")).strip(),
            fred_api_key=str(data.get("fred_api_key", "")).strip(),
            kosis_api_key=str(data.get("kosis_api_key", "")).strip(),
            pykrx_scope=str(data.get("pykrx_scope", "liquid")).strip() or "liquid",
            dart_scope=str(data.get("dart_scope", "prices")).strip() or "prices",
            default_as_of=str(data.get("default_as_of", "")).strip(),
            updated_at=str(data.get("updated_at", "")).strip(),
        )


def secrets_path(data_dir: Path) -> Path:
    return data_dir / "local" / "user_secrets.json"


def load_user_secrets(data_dir: Path) -> UserSecrets:
    path = secrets_path(data_dir)
    if not path.exists():
        return UserSecrets()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return UserSecrets.from_dict(data)
    except (json.JSONDecodeError, OSError):
        pass
    return UserSecrets()


def save_user_secrets(data_dir: Path, secrets: UserSecrets) -> Path:
    path = secrets_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    secrets.updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(json.dumps(asdict(secrets), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def clear_user_secrets(data_dir: Path) -> None:
    path = secrets_path(data_dir)
    if path.exists():
        path.unlink()


def apply_secrets_to_env(data_dir: Path, *, overwrite: bool = False) -> UserSecrets:
    """파일에 저장된 API 키를 현재 프로세스 환경변수에 적용."""
    secrets = load_user_secrets(data_dir)
    mapping = {
        "DART_API_KEY": secrets.dart_api_key,
        "OPENDART_API_KEY": secrets.dart_api_key,
        "KRX_ID": secrets.krx_id,
        "KRX_PW": secrets.krx_pw,
        "FRED_API_KEY": secrets.fred_api_key,
        "KOSIS_API_KEY": secrets.kosis_api_key,
    }
    for env_name, value in mapping.items():
        if not value:
            continue
        if overwrite or not os.environ.get(env_name, "").strip():
            os.environ[env_name] = value
    return secrets


def credential_status(data_dir: Path) -> dict[str, bool]:
    apply_secrets_to_env(data_dir)
    return {
        "dart": bool(
            os.environ.get("DART_API_KEY", "").strip()
            or os.environ.get("OPENDART_API_KEY", "").strip()
        ),
        "krx": bool(os.environ.get("KRX_ID", "").strip() and os.environ.get("KRX_PW", "").strip()),
        "fred": bool(os.environ.get("FRED_API_KEY", "").strip()),
        "kosis": bool(os.environ.get("KOSIS_API_KEY", "").strip()),
    }


def mask_secret(value: str, visible: int = 4) -> str:
    if not value:
        return "—"
    if len(value) <= visible:
        return "*" * len(value)
    return "*" * (len(value) - visible) + value[-visible:]


def test_dart_api_key(api_key: str) -> tuple[bool, str]:
    if not api_key.strip():
        return False, "API 키가 비어 있습니다."
    try:
        from src.data_refresh.dart_client import dart_get

        dart_get(
            "list.json",
            {
                "corp_code": "00126380",
                "bgn_de": "20240101",
                "end_de": "20240110",
                "page_no": 1,
                "page_count": 1,
            },
            api_key=api_key.strip(),
        )
        return True, "Open DART 연결 성공"
    except Exception as exc:
        return False, str(exc)


def test_krx_credentials(krx_id: str, krx_pw: str) -> tuple[bool, str]:
    if not krx_id.strip() or not krx_pw.strip():
        return False, "KRX ID/PW가 비어 있습니다."
    prev_id = os.environ.get("KRX_ID")
    prev_pw = os.environ.get("KRX_PW")
    try:
        os.environ["KRX_ID"] = krx_id.strip()
        os.environ["KRX_PW"] = krx_pw.strip()
        from src.data_refresh.pykrx_client import import_pykrx_stock

        stock = import_pykrx_stock()
        tickers = stock.get_market_ticker_list(market="KOSPI")
        if tickers:
            return True, f"PyKRX 연결 성공 (KOSPI {len(tickers)}종목)"
        return False, "ticker 목록이 비어 있습니다. KRX 자격증명을 확인하세요."
    except Exception as exc:
        return False, str(exc)
    finally:
        if prev_id is None:
            os.environ.pop("KRX_ID", None)
        else:
            os.environ["KRX_ID"] = prev_id
        if prev_pw is None:
            os.environ.pop("KRX_PW", None)
        else:
            os.environ["KRX_PW"] = prev_pw


def test_fred_api_key(api_key: str) -> tuple[bool, str]:
    if not api_key.strip():
        return False, "API 키가 비어 있습니다."
    try:
        from src.data_refresh.fred_client import fetch_fred_field

        val, _, err = fetch_fred_field(
            "https://api.stlouisfed.org/fred/series/observations",
            series_id="T10Y2Y",
            api_key=api_key.strip(),
            transform="last",
        )
        if val is not None and not err:
            return True, f"FRED 연결 성공 (T10Y2Y={val})"
        return False, err or "응답 없음"
    except Exception as exc:
        return False, str(exc)


def test_kosis_api_key(api_key: str) -> tuple[bool, str]:
    if not api_key.strip():
        return False, "API 키가 비어 있습니다."
    try:
        from src.data_refresh.kosis_client import fetch_kosis_series
        from src.data_refresh.kosis_tblid_discovery import INVALID_TBL_IDS

        # Use the live CPI table from tier2_sources (DT_1J22042).
        # DT_1J20001 / DT_1C8013 are known err=21 invalid IDs — never probe them.
        tbl_id = "DT_1J22042"
        assert tbl_id not in INVALID_TBL_IDS
        result = fetch_kosis_series(
            "https://kosis.kr/openapi/Param/statisticsParameterData.do",
            api_key=api_key.strip(),
            org_id="101",
            tbl_id=tbl_id,
            itm_id="T03",
            obj_l1="0",
            prd_se="M",
        )
        if result.points:
            return True, f"KOSIS 연결 성공 (CPI tbl={tbl_id}, 최근 {result.last_period})"
        return False, result.error or "데이터 없음"
    except Exception as exc:
        return False, str(exc)
