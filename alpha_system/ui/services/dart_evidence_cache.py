"""Disk cache for OpenDART evidence — reuse before network.

Stores per-ticker list/major fragments and per-rcept amounts/doc snippets.
Never writes target_portfolio. Fail-open when cache missing.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

CACHE_DIRNAME = "dart_evidence_cache"
TICKER_DIR = "tickers"
AMOUNT_FILE = "amounts_by_rcept.json"
DOC_DIR = "documents"
DEFAULT_TTL_HOURS = 24 * 7


def cache_root(data_dir: Path) -> Path:
    return Path(data_dir) / "local" / CACHE_DIRNAME


def ticker_cache_path(data_dir: Path, ticker: str) -> Path:
    tk = str(ticker).zfill(6) if str(ticker).isdigit() else str(ticker)
    return cache_root(data_dir) / TICKER_DIR / f"{tk}.json"


def amounts_path(data_dir: Path) -> Path:
    return cache_root(data_dir) / AMOUNT_FILE


def doc_cache_path(data_dir: Path, rcept_no: str) -> Path:
    digits = re.sub(r"\D", "", str(rcept_no or ""))
    return cache_root(data_dir) / DOC_DIR / f"{digits}.json"


def _parse_iso(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_fresh(fetched_at: str, *, hours: int = DEFAULT_TTL_HOURS) -> bool:
    fetched = _parse_iso(fetched_at)
    if fetched is None:
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - fetched <= timedelta(hours=hours)


def load_ticker_cache(data_dir: Path, ticker: str) -> dict[str, Any] | None:
    path = ticker_cache_path(data_dir, ticker)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def save_ticker_cache(data_dir: Path, ticker: str, payload: Mapping[str, Any]) -> Path:
    path = ticker_cache_path(data_dir, ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = dict(payload)
    body.setdefault(
        "fetched_at", datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_amounts(data_dir: Path) -> dict[str, dict[str, Any]]:
    path = amounts_path(data_dir)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for k, v in raw.items():
        if isinstance(v, dict) and v.get("amount_krw") is not None:
            out[str(k)] = v
    return out


def merge_amounts(
    data_dir: Path, updates: Mapping[str, tuple[int, str]]
) -> dict[str, dict[str, Any]]:
    table = load_amounts(data_dir)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for rcept, (amt, note) in updates.items():
        digits = re.sub(r"\D", "", str(rcept))
        if not digits or amt is None:
            continue
        table[digits] = {
            "amount_krw": int(amt),
            "amount_note": str(note),
            "fetched_at": now,
        }
    path = amounts_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return table


def amounts_as_tuples(
    table: Mapping[str, Mapping[str, Any]],
) -> dict[str, tuple[int, str]]:
    out: dict[str, tuple[int, str]] = {}
    for rcept, row in table.items():
        try:
            amt = int(row["amount_krw"])
        except (KeyError, TypeError, ValueError):
            continue
        out[str(rcept)] = (amt, str(row.get("amount_note") or "cache"))
    return out


def load_doc_cache(data_dir: Path, rcept_no: str) -> dict[str, Any] | None:
    path = doc_cache_path(data_dir, rcept_no)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def save_doc_cache(
    data_dir: Path,
    rcept_no: str,
    *,
    snippet: str,
    amount_krw: int | None,
    amount_note: str,
) -> Path:
    path = doc_cache_path(data_dir, rcept_no)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "rcept_no": re.sub(r"\D", "", str(rcept_no)),
        "snippet": (snippet or "")[:4000],
        "amount_krw": amount_krw,
        "amount_note": amount_note,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _parse_int_krw(raw: str) -> int | None:
    try:
        n = int(str(raw).replace(",", "").replace(" ", ""))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def extract_div_amount_from_document_text(text: str) -> tuple[int | None, str]:
    """Parse 현금ㆍ현물배당결정 body — prefer 총액, else 1주당(보통주).

    OpenDART has no tsstk-style JSON for dividend decisions; document.xml is SoT.
    """
    blob = text or ""
    # 배당금총액(원) 12,345,678,901  /  배당금 총액 123억원
    for pat, note in (
        (
            r"배당금\s*총\s*액\s*[\(（]?\s*원?\s*[\)）]?\s*[:：]?\s*([\d,]+)\s*원?",
            "document.xml(배당금총액)",
        ),
        (
            r"현금\s*배당금\s*총\s*액[^\d]{0,16}([\d,]+)\s*원?",
            "document.xml(배당금총액)",
        ),
        (
            r"배당금\s*총\s*액[^\d]{0,16}([\d,]+)\s*억\s*원",
            "document.xml(배당금총액·억)",
        ),
    ):
        m = re.search(pat, blob, re.I)
        if not m:
            continue
        n = _parse_int_krw(m.group(1))
        if n is None:
            continue
        if "억" in note:
            return n * 100_000_000, note
        # Guard: tiny integers are likely DPS mis-captured as total
        if n < 10_000:
            continue
        return n, note

    # 1주당 배당금(원) 보통주 361
    for pat in (
        r"1\s*주당\s*(?:현금\s*)?배당금[^\d]{0,40}?보통주[^\d]{0,12}([\d,]+)",
        r"1\s*주당\s*(?:현금\s*)?배당금\s*[\(（]?\s*원?\s*[\)）]?\s*[:：]?\s*([\d,]+)",
    ):
        m = re.search(pat, blob, re.I)
        if not m:
            continue
        n = _parse_int_krw(m.group(1))
        if n is None or n > 10_000_000:
            continue
        return n, "document.xml(1주당배당금)"
    return None, ""


def extract_amount_from_document_text(text: str) -> tuple[int | None, str]:
    """Conservative KRW parse from disclosure body — never invent."""
    blob = text or ""
    div_amt, div_note = extract_div_amount_from_document_text(blob)
    if div_amt is not None:
        return div_amt, div_note
    m = re.search(r"([\d,]+)\s*억\s*원", blob)
    if m:
        try:
            return int(m.group(1).replace(",", "")) * 100_000_000, "document.xml(억)"
        except ValueError:
            pass
    m = re.search(r"양도\s*가\s*액[^\d]{0,12}([\d,]+)\s*원", blob)
    if m:
        try:
            return int(m.group(1).replace(",", "")), "document.xml(양도가액)"
        except ValueError:
            pass
    m = re.search(r"취득\s*예\s*정\s*금\s*액[^\d]{0,12}([\d,]+)\s*원", blob)
    if m:
        try:
            return int(m.group(1).replace(",", "")), "document.xml(취득예정)"
        except ValueError:
            pass
    return None, ""
