from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

PRICE_COLUMNS = [
    "date", "ticker", "close", "market_cap", "trading_value_20d", "trading_value_60d",
    "return_1m", "return_3m", "return_6m", "return_12m", "return_12m_ex_1m",
    "high_52w", "distance_from_52w_high", "volatility_60d",
]


def normalize_ticker(ticker: str) -> str:
    t = str(ticker).strip()
    return t.zfill(6) if t.isdigit() else t


def merge_prices_dataframes(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """ticker 기준 최신 date row 유지 — Tier B 누적 merge."""
    if existing.empty:
        out = new.copy()
    elif new.empty:
        out = existing.copy()
    else:
        out = pd.concat([existing, new], ignore_index=True)
    out["ticker"] = out["ticker"].map(normalize_ticker)
    out = out.sort_values(["ticker", "date"], na_position="last")
    out = out.drop_duplicates(subset=["ticker"], keep="last")
    cols = [c for c in PRICE_COLUMNS if c in out.columns]
    return out[cols]


def inspect_csv_bytes(path: Path) -> dict[str, Any]:
    """Byte-level integrity for critical CSV files (NUL / truncated garbage)."""
    path = Path(path)
    if not path.exists():
        return {
            "exists": False,
            "size_bytes": 0,
            "nul_bytes": 0,
            "first_nul_at": -1,
            "text_line_count": 0,
            "ok": False,
            "reason": "missing",
        }
    raw = path.read_bytes()
    nul = raw.count(b"\x00")
    first_nul = raw.find(b"\x00")
    text = raw if first_nul < 0 else raw[:first_nul]
    # Count newline-terminated rows; tolerate final line without trailing \n
    if not text:
        lines = 0
    else:
        lines = text.count(b"\n")
        if not text.endswith(b"\n") and text.strip():
            lines += 1
    ok = nul == 0 and lines > 0
    return {
        "exists": True,
        "size_bytes": len(raw),
        "nul_bytes": int(nul),
        "first_nul_at": int(first_nul),
        "text_line_count": int(lines),
        "ok": ok,
        "reason": "ok" if ok else ("nul_bytes_present" if nul else "empty"),
    }


def atomic_write_csv(
    path: Path,
    df: pd.DataFrame,
    *,
    encoding: str = "utf-8-sig",
    index: bool = False,
    min_rows: int | None = None,
    required_tickers: list[str] | None = None,
) -> dict[str, Any]:
    """Write DataFrame via temp file → verify → os.replace (never truncate in place).

    On verification failure the destination is left untouched and the temp file removed.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    expected_rows = int(len(df))
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    os.close(fd)
    try:
        df.to_csv(tmp_path, index=index, encoding=encoding)
        probe = inspect_csv_bytes(tmp_path)
        if not probe["ok"]:
            raise RuntimeError(f"atomic_write_csv temp integrity failed: {probe}")
        # Parse-verify row count (header + data). text_line_count includes header.
        check = pd.read_csv(tmp_path, dtype={"ticker": str}, keep_default_na=False)
        if len(check) != expected_rows:
            raise RuntimeError(
                f"atomic_write_csv row mismatch: wrote_df={expected_rows} "
                f"reread={len(check)}"
            )
        if min_rows is not None and len(check) < int(min_rows):
            raise RuntimeError(
                f"atomic_write_csv below min_rows={min_rows}: got {len(check)}"
            )
        if required_tickers:
            present = set(check["ticker"].map(normalize_ticker)) if "ticker" in check.columns else set()
            missing = [normalize_ticker(t) for t in required_tickers if normalize_ticker(t) not in present]
            if missing:
                raise RuntimeError(f"atomic_write_csv missing required tickers: {missing}")
        os.replace(tmp_path, path)
        final = inspect_csv_bytes(path)
        return {
            "path": str(path),
            "rows": expected_rows,
            "integrity": final,
            "replaced": True,
        }
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def inspect_text_bytes(path: Path) -> dict[str, Any]:
    """Byte-level integrity for text/YAML files (NUL / empty)."""
    path = Path(path)
    if not path.exists():
        return {
            "exists": False,
            "size_bytes": 0,
            "nul_bytes": 0,
            "first_nul_at": -1,
            "ok": False,
            "reason": "missing",
        }
    raw = path.read_bytes()
    nul = raw.count(b"\x00")
    first_nul = raw.find(b"\x00")
    ok = nul == 0 and len(raw.strip()) > 0
    return {
        "exists": True,
        "size_bytes": len(raw),
        "nul_bytes": int(nul),
        "first_nul_at": int(first_nul),
        "ok": ok,
        "reason": "ok" if ok else ("nul_bytes_present" if nul else "empty"),
    }


def atomic_write_text(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
    min_bytes: int = 1,
    verify: Any | None = None,
) -> dict[str, Any]:
    """Write text via temp file → verify → os.replace (never truncate in place)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    os.close(fd)
    try:
        tmp_path.write_text(content, encoding=encoding)
        probe = inspect_text_bytes(tmp_path)
        if not probe["ok"]:
            raise RuntimeError(f"atomic_write_text temp integrity failed: {probe}")
        if probe["size_bytes"] < int(min_bytes):
            raise RuntimeError(
                f"atomic_write_text below min_bytes={min_bytes}: got {probe['size_bytes']}"
            )
        if verify is not None:
            verify(tmp_path)
        os.replace(tmp_path, path)
        final = inspect_text_bytes(path)
        return {
            "path": str(path),
            "size_bytes": final.get("size_bytes", 0),
            "integrity": final,
            "replaced": True,
        }
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise
