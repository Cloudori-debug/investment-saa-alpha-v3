"""Investor flow (foreign/institution) — auxiliary Buy-allowed confirmation signal."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

FLOW_COLUMNS = [
    "date",
    "ticker",
    "name",
    "foreign_net_value",
    "institution_net_value",
    "retail_net_value",
    "program_net_value",
    "foreign_5d_sum",
    "institution_5d_sum",
    "foreign_20d_sum",
    "institution_20d_sum",
    "foreign_5d_mcap_pct",
    "institution_5d_mcap_pct",
    "foreign_20d_mcap_pct",
    "institution_20d_mcap_pct",
    "flow_score",
    "flow_signal",
    "source",
    "staleness_days",
]

FLOW_SIGNALS = frozenset({
    "ACCUMULATION",
    "MILD_ACCUMULATION",
    "NEUTRAL",
    "DISTRIBUTION",
    "STALE",
})


def classify_flow_signal(
    *,
    foreign_5d_mcap_pct: float | None,
    foreign_20d_mcap_pct: float | None,
    institution_5d_mcap_pct: float | None,
    institution_20d_mcap_pct: float | None = None,
    staleness_days: int,
) -> str:
    if staleness_days >= 3:
        return "STALE"
    f5 = foreign_5d_mcap_pct if foreign_5d_mcap_pct is not None else 0.0
    f20 = foreign_20d_mcap_pct if foreign_20d_mcap_pct is not None else 0.0
    i5 = institution_5d_mcap_pct if institution_5d_mcap_pct is not None else 0.0
    i20 = institution_20d_mcap_pct if institution_20d_mcap_pct is not None else 0.0

    if (f5 < -0.10 and i5 < -0.05) or f20 < -0.25 or f5 < -0.10:
        return "DISTRIBUTION"
    if f20 < -0.10 and i20 < -0.10:
        return "DISTRIBUTION"

    foreign_acc = f20 > 0.10 and f5 >= -0.05
    inst_acc = i20 > 0.10 and i5 >= -0.05
    if foreign_acc or inst_acc:
        return "ACCUMULATION"

    if abs(f5) < 0.05 and i5 > 0.05:
        return "MILD_ACCUMULATION"
    if abs(i5) < 0.05 and f5 > 0.05:
        return "MILD_ACCUMULATION"
    if i20 > 0.05 and f20 <= 0.05:
        return "MILD_ACCUMULATION"
    if f20 > 0.05 and i20 <= 0.05:
        return "MILD_ACCUMULATION"
    return "NEUTRAL"


def flow_score_from_signal(signal: str) -> float:
    return {
        "ACCUMULATION": 80.0,
        "MILD_ACCUMULATION": 65.0,
        "NEUTRAL": 50.0,
        "DISTRIBUTION": 20.0,
        "STALE": 0.0,
    }.get(signal, 0.0)


def load_investor_flows(data_dir: Path) -> dict[str, dict[str, Any]]:
    path = data_dir / "investor_flows.csv"
    if not path.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            tk = str(row.get("ticker", "")).zfill(6)
            if not tk:
                continue
            out[tk] = {k: row.get(k) for k in FLOW_COLUMNS if k in row}
            for key in (
                "foreign_5d_mcap_pct",
                "institution_5d_mcap_pct",
                "foreign_20d_mcap_pct",
                "institution_20d_mcap_pct",
                "flow_score",
                "staleness_days",
            ):
                if key in row and row[key] not in (None, ""):
                    try:
                        out[tk][key] = float(row[key])
                    except ValueError:
                        pass
            if "staleness_days" not in out[tk]:
                out[tk]["staleness_days"] = 999
            sig = str(out[tk].get("flow_signal") or "")
            if sig not in FLOW_SIGNALS:
                out[tk]["flow_signal"] = classify_flow_signal(
                    foreign_5d_mcap_pct=out[tk].get("foreign_5d_mcap_pct"),
                    foreign_20d_mcap_pct=out[tk].get("foreign_20d_mcap_pct"),
                    institution_5d_mcap_pct=out[tk].get("institution_5d_mcap_pct"),
                    institution_20d_mcap_pct=out[tk].get("institution_20d_mcap_pct"),
                    staleness_days=int(out[tk].get("staleness_days") or 999),
                )
    return out


def get_flow_for_ticker(data_dir: Path, ticker: str) -> dict[str, Any]:
    flows = load_investor_flows(data_dir)
    tk = str(ticker).zfill(6)
    if tk in flows:
        return flows[tk]
    return {
        "ticker": tk,
        "flow_signal": "STALE",
        "flow_score": 0.0,
        "staleness_days": 999,
        "source": "missing",
    }


def refresh_investor_flows_pykrx(
    data_dir: Path,
    tickers: list[dict[str, str]],
    *,
    as_of: str,
    lookback_days: int = 25,
) -> int:
    """Best-effort PyKRX refresh — returns rows refreshed. Requires KRX credentials."""
    from src.alpha.flow_refresh import refresh_investor_flows

    result = refresh_investor_flows(
        data_dir,
        tickers,
        as_of=as_of,
        lookback_days=lookback_days,
        sleep_sec=0.25,
    )
    return result.refreshed_count


def write_investor_flows_template(data_dir: Path, tickers: list[dict[str, str]], *, as_of: str) -> Path:
    """Create STALE placeholder rows when no flow feed yet."""
    path = data_dir / "investor_flows.csv"
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FLOW_COLUMNS)
        writer.writeheader()
        for item in tickers:
            tk = str(item.get("ticker", "")).zfill(6)
            writer.writerow({
                "date": as_of[:10],
                "ticker": tk,
                "name": item.get("name", ""),
                "flow_signal": "STALE",
                "flow_score": 0,
                "source": "template",
                "staleness_days": 999,
            })
    return path
