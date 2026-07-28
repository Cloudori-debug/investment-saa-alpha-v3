from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class PriceFetchLogEntry:
    as_of: str
    requested_tickers: list[str]
    success_tickers: list[str] = field(default_factory=list)
    failed_tickers: list[str] = field(default_factory=list)
    skipped_tickers: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    retry_count: int = 0
    source: str = "pykrx"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def append_price_fetch_log(output_dir: Path, entry: PriceFetchLogEntry) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "price_fetch_log.json"
    records: list[dict[str, Any]] = []
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                records = raw
            elif isinstance(raw, dict) and "entries" in raw:
                records = list(raw["entries"])
        except (json.JSONDecodeError, OSError):
            records = []

    payload = entry.to_dict()
    payload["logged_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    records.append(payload)
    records = records[-50:]
    path.write_text(
        json.dumps({"schema_version": "1.0", "entries": records}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def write_price_fetch_failures(output_dir: Path, entry: PriceFetchLogEntry) -> Path | None:
    if not entry.failed_tickers:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "price_fetch_failures.csv"
    rows = [
        {
            "as_of": entry.as_of,
            "ticker": t,
            "reason": entry.reason or "fetch_failed",
            "source": entry.source,
            "elapsed_seconds": entry.elapsed_seconds,
        }
        for t in entry.failed_tickers
    ]
    df = pd.DataFrame(rows)
    if path.exists():
        old = pd.read_csv(path, dtype=str, keep_default_na=False)
        df = pd.concat([old, df.astype(str)], ignore_index=True)
        df = df.drop_duplicates(subset=["as_of", "ticker"], keep="last")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def write_price_fetch_outputs(output_dir: Path | None, entry: PriceFetchLogEntry) -> dict[str, str]:
    if output_dir is None:
        return {}
    paths: dict[str, str] = {}
    paths["price_fetch_log"] = str(append_price_fetch_log(output_dir, entry))
    fail_path = write_price_fetch_failures(output_dir, entry)
    if fail_path:
        paths["price_fetch_failures"] = str(fail_path)
    return paths
