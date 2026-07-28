from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class GateResult:
    ticker: str
    pass_gate: bool
    fail_reason: str | None


def _bool(val) -> bool:
    if pd.isna(val):
        return False
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in {"true", "1", "yes", "y"}


def apply_gate(row: pd.Series, gate_cfg: dict) -> GateResult:
    ticker = str(row.get("ticker", ""))
    reasons: list[str] = []

    if _bool(row.get("is_etf")) or _bool(row.get("is_spac")):
        reasons.append("etf_spac")
    if _bool(row.get("is_managed")) or _bool(row.get("is_halted")):
        reasons.append("managed_halted")

    market_cap = row.get("market_cap")
    cap_min = float(gate_cfg.get("market_cap_min", 0))
    if market_cap is None or pd.isna(market_cap) or float(market_cap) < cap_min:
        reasons.append("low_market_cap")

    avg_tv = row.get("avg_trading_value_20d")
    tv_min = float(gate_cfg.get("avg_trading_value_20d_min", 0))
    if avg_tv is None or pd.isna(avg_tv) or float(avg_tv) < tv_min:
        reasons.append("low_liquidity")

    y1 = row.get("net_income_y1")
    y2 = row.get("net_income_y2")
    if y1 is not None and y2 is not None and not pd.isna(y1) and not pd.isna(y2):
        if float(y1) < 0 and float(y2) < 0:
            reasons.append("consecutive_loss")

    debt = row.get("debt_ratio")
    is_fin = _bool(row.get("is_financial"))
    debt_max = float(gate_cfg.get("debt_ratio_max", 200))
    if not is_fin and debt is not None and not pd.isna(debt) and float(debt) > debt_max:
        reasons.append("high_debt")

    audit = str(row.get("audit_opinion", "unqualified")).strip().lower()
    if audit and audit != "unqualified":
        reasons.append("audit_issue")

    verified_raw = str(row.get("verified", "")).strip().lower()
    if verified_raw not in {"true", "1", "yes", "y", "stub"}:
        reasons.append("unverified")

    if reasons:
        return GateResult(ticker=ticker, pass_gate=False, fail_reason=";".join(reasons))
    return GateResult(ticker=ticker, pass_gate=True, fail_reason=None)


def run_gate(df: pd.DataFrame, gate_cfg: dict) -> pd.DataFrame:
    results = [apply_gate(row, gate_cfg) for _, row in df.iterrows()]
    out = df.copy()
    out["gate_pass"] = [r.pass_gate for r in results]
    out["gate_fail_reason"] = [r.fail_reason or "" for r in results]
    return out
