from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.alpha.investor_flows import load_investor_flows
from src.alpha_flow.flow_classifier import is_flow_record_stale


@dataclass
class InstitutionalFlowRow:
    ticker: str
    name: str
    market: str
    date: str
    pension_net_buy_1d: float | None
    pension_net_buy_5d: float | None
    pension_net_buy_20d: float | None
    pension_net_buy_60d: float | None
    foreign_net_buy_1d: float | None
    foreign_net_buy_5d: float | None
    foreign_net_buy_20d: float | None
    institution_net_buy_1d: float | None
    data_source: str
    data_as_of: str
    stale_flag: bool


def _float_or_none(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _load_krx_flow_file(path: Path) -> dict[str, InstitutionalFlowRow]:
    if not path.exists():
        return {}
    out: dict[str, InstitutionalFlowRow] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for rec in csv.DictReader(handle):
            ticker = str(rec.get("ticker", "")).zfill(6)
            stale = is_flow_record_stale(rec) or str(rec.get("stale_flag", "")).lower() in {"true", "1", "yes"}
            out[ticker] = InstitutionalFlowRow(
                ticker=ticker,
                name=str(rec.get("name", "")),
                market=str(rec.get("market", "KOSPI")),
                date=str(rec.get("date", "")),
                pension_net_buy_1d=_float_or_none(rec.get("pension_net_buy_1d")),
                pension_net_buy_5d=_float_or_none(rec.get("pension_net_buy_5d")),
                pension_net_buy_20d=_float_or_none(rec.get("pension_net_buy_20d")),
                pension_net_buy_60d=_float_or_none(rec.get("pension_net_buy_60d")),
                foreign_net_buy_1d=_float_or_none(rec.get("foreign_net_buy_1d")),
                foreign_net_buy_5d=_float_or_none(rec.get("foreign_net_buy_5d")),
                foreign_net_buy_20d=_float_or_none(rec.get("foreign_net_buy_20d")),
                institution_net_buy_1d=_float_or_none(rec.get("institution_net_buy_1d")),
                data_source=str(rec.get("data_source", "krx")),
                data_as_of=str(rec.get("data_as_of", rec.get("date", ""))),
                stale_flag=stale,
            )
    return out


def load_institutional_flows(data_dir: Path) -> dict[str, InstitutionalFlowRow]:
    """Load institutional_flow_krx.csv or fall back to investor_flows (institution as pension proxy)."""
    krx = _load_krx_flow_file(data_dir / "institutional_flow_krx.csv")
    if krx:
        return krx

    flows = load_investor_flows(data_dir)
    out: dict[str, InstitutionalFlowRow] = {}
    for ticker, rec in flows.items():
        stale = is_flow_record_stale(rec)
        inst_5d = _float_or_none(rec.get("institution_5d_sum"))
        inst_20d = _float_or_none(rec.get("institution_20d_sum"))
        foreign_5d = _float_or_none(rec.get("foreign_5d_sum"))
        foreign_20d = _float_or_none(rec.get("foreign_20d_sum"))
        inst_1d = _float_or_none(rec.get("institution_net_value"))
        foreign_1d = _float_or_none(rec.get("foreign_net_value"))
        out[ticker] = InstitutionalFlowRow(
            ticker=ticker,
            name=str(rec.get("name", "")),
            market="KOSPI",
            date=str(rec.get("date", "")),
            pension_net_buy_1d=inst_1d,
            pension_net_buy_5d=inst_5d,
            pension_net_buy_20d=inst_20d,
            pension_net_buy_60d=inst_20d,
            foreign_net_buy_1d=foreign_1d,
            foreign_net_buy_5d=foreign_5d,
            foreign_net_buy_20d=foreign_20d,
            institution_net_buy_1d=inst_1d,
            data_source=str(rec.get("source", "investor_flows")),
            data_as_of=str(rec.get("date", "")),
            stale_flag=stale,
        )
    return out
