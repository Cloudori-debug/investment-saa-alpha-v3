from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from pathlib import Path


DART_BASE = "https://opendart.fss.or.kr/api"


class DartCredentialsError(RuntimeError):
    pass


class DartApiError(RuntimeError):
    pass


def get_dart_api_key(data_dir: Path | None = None) -> str:
    if data_dir is not None:
        from src.settings.user_secrets import apply_secrets_to_env

        apply_secrets_to_env(data_dir)
    key = os.environ.get("DART_API_KEY", "").strip() or os.environ.get("OPENDART_API_KEY", "").strip()
    if not key and data_dir is not None:
        from src.settings.user_secrets import load_user_secrets

        key = load_user_secrets(data_dir).dart_api_key
    if not key:
        raise DartCredentialsError(
            "Open DART API 키가 필요합니다. Streamlit **설정** 페이지 또는 환경변수 DART_API_KEY를 설정하세요."
        )
    return key


def dart_get(path: str, params: dict[str, Any], *, api_key: str | None = None, timeout: int = 30) -> dict[str, Any]:
    key = api_key or get_dart_api_key()
    query = urllib.parse.urlencode({**params, "crtfc_key": key})
    url = f"{DART_BASE}/{path.lstrip('/')}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "multi-asset-trigger-portfolio/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise DartApiError(f"DART HTTP {exc.code}: {path}") from exc
    except urllib.error.URLError as exc:
        raise DartApiError(f"DART network error: {exc}") from exc

    if path.endswith(".xml") or path.endswith("corpCode.xml"):
        return {"_raw": raw}

    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise DartApiError(f"DART JSON parse failed: {path}") from exc

    status = str(data.get("status", ""))
    if status and status != "000":
        msg = str(data.get("message", "unknown"))
        if status == "013":
            return {"status": status, "message": msg, "list": []}
        raise DartApiError(f"DART status {status}: {msg}")
    return data


def dart_get_bytes(path: str, params: dict[str, Any], *, api_key: str | None = None) -> bytes:
    data = dart_get(path, params, api_key=api_key)
    if "_raw" in data:
        return data["_raw"]
    raise DartApiError(f"expected binary response: {path}")


class RateLimiter:
    def __init__(self, min_interval_sec: float = 0.12) -> None:
        self.min_interval = min_interval_sec
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()
