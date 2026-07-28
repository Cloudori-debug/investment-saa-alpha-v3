from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Any

from src.data_refresh.dart_client import DartApiError, RateLimiter, dart_get_bytes, get_dart_api_key


def _decode_bytes(raw: bytes) -> str:
    for enc in ("utf-8", "euc-kr", "cp949", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def normalize_document_text(raw: str) -> str:
    """Strip HTML/XML tags and collapse whitespace."""
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_text_from_zip(zip_bytes: bytes) -> str:
    parts: list[str] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in sorted(zf.infolist(), key=lambda x: x.filename):
            if info.is_dir():
                continue
            raw = zf.read(info.filename)
            decoded = _decode_bytes(raw)
            parts.append(normalize_document_text(decoded))
    return "\n".join(p for p in parts if p)


def fetch_dart_document_text(
    rcept_no: str,
    *,
    data_dir: Path | None = None,
    limiter: RateLimiter | None = None,
) -> tuple[str | None, str]:
    """Fetch disclosure body text. Returns (text, missing_reason)."""
    rcept = re.sub(r"\D", "", str(rcept_no))
    if len(rcept) < 8:
        return None, "invalid_receipt_no"

    try:
        get_dart_api_key(data_dir)
    except Exception as exc:
        return None, f"no_credentials:{exc}"

    if limiter:
        limiter.wait()

    try:
        raw = dart_get_bytes(
            "document.xml",
            {"rcept_no": rcept},
            api_key=get_dart_api_key(data_dir),
        )
    except DartApiError as exc:
        return None, f"fetch_error:{exc}"
    except Exception as exc:
        return None, f"fetch_error:{exc}"

    if not raw:
        return None, "empty_response"

    # API may return XML error payload instead of zip
    if raw[:2] != b"PK":
        snippet = _decode_bytes(raw[:500])
        if "<status>" in snippet:
            m = re.search(r"<message>(.*?)</message>", snippet, re.I | re.S)
            msg = m.group(1).strip() if m else snippet[:120]
            return None, f"dart_status:{msg}"
        return None, "not_zip_response"

    try:
        text = _extract_text_from_zip(raw)
    except zipfile.BadZipFile:
        return None, "bad_zip"
    except Exception as exc:
        return None, f"zip_extract_error:{exc}"

    if not text.strip():
        return None, "empty_document_text"
    return text, ""


def save_document_text(
    output_dir: Path,
    *,
    ticker: str,
    rcept_no: str,
    text: str,
) -> Path:
    doc_dir = output_dir / "dart_documents" / "hakedaka"
    doc_dir.mkdir(parents=True, exist_ok=True)
    rcept = re.sub(r"\D", "", str(rcept_no))
    path = doc_dir / f"{ticker.zfill(6)}_{rcept}.txt"
    path.write_text(text, encoding="utf-8")
    return path


def load_cached_document_text(
    output_dir: Path,
    *,
    ticker: str,
    rcept_no: str,
) -> str | None:
    rcept = re.sub(r"\D", "", str(rcept_no))
    path = output_dir / "dart_documents" / "hakedaka" / f"{ticker.zfill(6)}_{rcept}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def fetch_or_load_document(
    output_dir: Path,
    *,
    ticker: str,
    rcept_no: str,
    data_dir: Path | None = None,
    limiter: RateLimiter | None = None,
    use_cache: bool = True,
) -> tuple[str | None, str, Path | None]:
    """Returns (text, missing_reason, saved_path)."""
    cached = load_cached_document_text(output_dir, ticker=ticker, rcept_no=rcept_no) if use_cache else None
    if cached:
        rcept = re.sub(r"\D", "", str(rcept_no))
        path = output_dir / "dart_documents" / "hakedaka" / f"{ticker.zfill(6)}_{rcept}.txt"
        return cached, "", path

    text, reason = fetch_dart_document_text(rcept_no, data_dir=data_dir, limiter=limiter)
    if text is None:
        return None, reason, None
    path = save_document_text(output_dir, ticker=ticker, rcept_no=rcept_no, text=text)
    return text, "", path
