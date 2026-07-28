from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from src.compass.saa_engine import get_saa_weights, load_saa_profiles
from src.compass.profile_aliases import resolve_profile_name

# blocked_by 우선순위 — primary_blocker 선정용 (v1.0.2 실행 변경 없음)
PRIMARY_BLOCKER_PRIORITY: tuple[str, ...] = (
    "data_gate_red",
    "core_price_gate",
    "health_gate_red",
    "execution_scope_no_trade",
    "systemic_stress",
    "dry_run",
    "policy_cap",
    "stop_buy",
    "data_gate_yellow",
    "health_gate_yellow",
    "execution_scope_etf_only",
    "execution_scope_etf_review",
    "alpha_trade_blocked",
    "alpha_gate_red",
    "portfolio_gate_red",
)

MISSED_BUY_PROXY_TICKER = "069500"  # KODEX 200 — ETF trigger 차단 proxy
GOOD_BLOCK_THRESHOLD_PCT = -1.0
BAD_BLOCK_THRESHOLD_PCT = 2.0


def derive_primary_blocker(blocked_by: list[str]) -> str:
    if not blocked_by:
        return ""
    blocked_set = set(blocked_by)
    for key in PRIMARY_BLOCKER_PRIORITY:
        if key in blocked_set:
            return key
    for key in blocked_by:
        if key.startswith("policy_cap_"):
            return key
    return blocked_by[0]


def _parse_date(s: str) -> datetime | None:
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d")
    except ValueError:
        return None


def add_business_days(start: str, n: int) -> str | None:
    dt = _parse_date(start)
    if dt is None or n < 0:
        return None
    added = 0
    cur = dt
    while added < n:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            added += 1
    return cur.strftime("%Y-%m-%d")


def _load_market_history(data_dir: Path) -> pd.DataFrame:
    path = data_dir / "market_indicators_history.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if df.empty or "date" not in df.columns:
        return pd.DataFrame()
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ("kospi", "sp500", "gold"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def _pct_change(current: float, previous: float) -> float | None:
    if previous <= 0 or current <= 0:
        return None
    return round((current / previous - 1) * 100, 4)


def _row_on_or_before(df: pd.DataFrame, as_of: str) -> pd.Series | None:
    if df.empty:
        return None
    target = pd.to_datetime(as_of[:10], errors="coerce")
    if pd.isna(target):
        return None
    sub = df[df["date"] <= target]
    if sub.empty:
        return None
    return sub.iloc[-1]


def compute_saa_proxy_returns(
    data_dir: Path,
    as_of: str,
    *,
    profile: str | None = None,
) -> dict[str, float | None]:
    """정적 SAA 비중 × 지수 수익률 proxy — 벤치마크 관측용 (TAA 미적용)."""
    df = _load_market_history(data_dir)
    if df.empty:
        return {"benchmark_saa_return_1d": None, "benchmark_saa_return_mtd": None}

    profiles = load_saa_profiles(data_dir / "saa_profiles.yaml")
    name = resolve_profile_name(profiles, profile)
    saa = get_saa_weights(profiles, name)

    today = _row_on_or_before(df, as_of)
    if today is None:
        return {"benchmark_saa_return_1d": None, "benchmark_saa_return_mtd": None}

    prev_rows = df[df["date"] < today["date"]]
    prev = prev_rows.iloc[-1] if not prev_rows.empty else None

    ret_1d: float | None = None
    if prev is not None:
        kospi_r = _pct_change(float(today["kospi"]), float(prev["kospi"])) or 0.0
        sp_r = _pct_change(float(today["sp500"]), float(prev["sp500"])) or 0.0
        gold_r = 0.0
        if "gold" in today and pd.notna(today["gold"]) and pd.notna(prev["gold"]):
            gold_r = _pct_change(float(today["gold"]), float(prev["gold"])) or 0.0
        kr_eq = saa.get("domestic_beta", 0) + saa.get("kr_alpha", 0)
        ret_1d = round(
            kr_eq / 100 * kospi_r
            + saa.get("global_beta", 0) / 100 * sp_r
            + saa.get("hedge_alt", 0) / 100 * gold_r,
            4,
        )

    month_start = today["date"].replace(day=1)
    month_rows = df[(df["date"] >= month_start) & (df["date"] <= today["date"])].reset_index(drop=True)
    mtd: float | None = None
    if len(month_rows) >= 2:
        daily_rets: list[float] = []
        for i in range(1, len(month_rows)):
            row = month_rows.iloc[i]
            prev_row = month_rows.iloc[i - 1]
            kospi_r = _pct_change(float(row["kospi"]), float(prev_row["kospi"])) or 0.0
            sp_r = _pct_change(float(row["sp500"]), float(prev_row["sp500"])) or 0.0
            gold_r = 0.0
            if "gold" in row and pd.notna(row["gold"]) and pd.notna(prev_row["gold"]):
                gold_r = _pct_change(float(row["gold"]), float(prev_row["gold"])) or 0.0
            kr_eq = saa.get("domestic_beta", 0) + saa.get("kr_alpha", 0)
            daily_rets.append(
                kr_eq / 100 * kospi_r
                + saa.get("global_beta", 0) / 100 * sp_r
                + saa.get("hedge_alt", 0) / 100 * gold_r
            )
        compound = 1.0
        for r in daily_rets:
            compound *= 1 + r / 100
        mtd = round((compound - 1) * 100, 4)

    return {
        "benchmark_saa_return_1d": ret_1d,
        "benchmark_saa_return_mtd": mtd,
    }


def compute_portfolio_log_returns(
    log_path: Path,
    as_of: str,
    portfolio_value: float,
) -> dict[str, float | None]:
    """ops_shadow_log 이전 행 대비 포트폴리오 MTD proxy (positions 갱신 시에만 변동)."""
    if not log_path.is_file() or portfolio_value <= 0:
        return {"portfolio_return_1d": None, "portfolio_return_mtd": None}

    rows: list[dict[str, str]] = []
    with log_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("date", "")[:10] < as_of[:10]:
                rows.append(row)

    ret_1d: float | None = None
    if rows:
        prev_val = float(rows[-1].get("portfolio_value_krw") or 0)
        if prev_val > 0 and rows[-1].get("date", "")[:7] == as_of[:7]:
            ret_1d = round((portfolio_value / prev_val - 1) * 100, 4)

    month_rows = [r for r in rows if r.get("date", "")[:7] == as_of[:7]]
    mtd: float | None = None
    if month_rows:
        first_val = float(month_rows[0].get("portfolio_value_krw") or 0)
        if first_val > 0:
            mtd = round((portfolio_value / first_val - 1) * 100, 4)

    return {"portfolio_return_1d": ret_1d, "portfolio_return_mtd": mtd}


def _load_price_history(data_dir: Path) -> pd.DataFrame:
    path = data_dir / "prices_history.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype={"ticker": str}, keep_default_na=False)
    if df.empty:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna(subset=["date", "close"])


def _forward_return_pct(
    prices: pd.DataFrame,
    ticker: str,
    from_date: str,
    business_days_forward: int,
) -> float | None:
    sub = prices[prices["ticker"] == ticker].sort_values("date")
    if sub.empty:
        return None
    start_row = _row_on_or_before(sub, from_date)  # type: ignore[arg-type]
    if start_row is None:
        return None
    target_date = add_business_days(from_date, business_days_forward)
    if not target_date:
        return None
    end_row = _row_on_or_before(sub, target_date)
    if end_row is None or end_row["date"] <= start_row["date"]:
        return None
    return _pct_change(float(end_row["close"]), float(start_row["close"]))


def classify_blocked_outcome(return_20d: float | None) -> str:
    if return_20d is None:
        return ""
    if return_20d <= GOOD_BLOCK_THRESHOLD_PCT:
        return "GOOD_BLOCK"
    if return_20d >= BAD_BLOCK_THRESHOLD_PCT:
        return "BAD_BLOCK"
    return "NEUTRAL"


def enrich_ops_shadow_log_retrospective(log_path: Path, data_dir: Path) -> None:
    """과거 mismatch 행에 missed_buy 수익률·blocked_decision_outcome 보강 (실행 변경 없음)."""
    if not log_path.exists():
        return

    prices = _load_price_history(data_dir)
    if prices.empty:
        return

    with log_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    extra_fields = [
        "missed_buy_return_after_5d",
        "missed_buy_return_after_20d",
        "blocked_decision_outcome",
    ]
    for f in extra_fields:
        if f not in fieldnames:
            fieldnames.append(f)

    today_str = datetime.now().strftime("%Y-%m-%d")
    changed = False
    for row in rows:
        mismatch = str(row.get("signal_execution_mismatch", "")).lower() in {"true", "1", "yes"}
        if not mismatch:
            actual = float(row.get("actual_allowed_krw") or 0)
            mismatch = str(row.get("buy_trigger_active", "")).lower() in {"true", "1", "yes"} and actual == 0
        if not mismatch:
            continue
        if row.get("missed_buy_return_after_20d") and row.get("blocked_decision_outcome"):
            continue
        as_of = row.get("date", "")
        if not as_of:
            continue

        target_5 = add_business_days(as_of, 5)
        target_20 = add_business_days(as_of, 20)
        ret_5: float | None = None
        ret_20: float | None = None
        if target_5 and target_5 <= today_str:
            ret_5 = _forward_return_pct(prices, MISSED_BUY_PROXY_TICKER, as_of, 5)
        if target_20 and target_20 <= today_str:
            ret_20 = _forward_return_pct(prices, MISSED_BUY_PROXY_TICKER, as_of, 20)

        if ret_5 is not None and not row.get("missed_buy_return_after_5d"):
            row["missed_buy_return_after_5d"] = str(ret_5)
            changed = True
        if ret_20 is not None:
            if not row.get("missed_buy_return_after_20d"):
                row["missed_buy_return_after_20d"] = str(ret_20)
                changed = True
            if not row.get("blocked_decision_outcome"):
                row["blocked_decision_outcome"] = classify_blocked_outcome(ret_20)
                changed = True

    if not changed:
        return

    with log_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_performance_fields(
    data_dir: Path,
    as_of: str,
    log_path: Path,
    portfolio_value: float,
    blocked_by: list[str],
    *,
    profile: str | None = None,
) -> dict[str, Any]:
    saa = compute_saa_proxy_returns(data_dir, as_of, profile=profile)
    port = compute_portfolio_log_returns(log_path, as_of, portfolio_value)
    primary = derive_primary_blocker(blocked_by)
    saa_mtd = saa.get("benchmark_saa_return_mtd")
    port_mtd = port.get("portfolio_return_mtd")
    vs_saa_mtd: float | None = None
    if saa_mtd is not None and port_mtd is not None:
        vs_saa_mtd = round(port_mtd - saa_mtd, 4)

    return {
        **saa,
        **port,
        "portfolio_value_krw": round(portfolio_value),
        "primary_blocker": primary,
        "vs_saa_mtd": vs_saa_mtd,
        "missed_buy_return_after_5d": "",
        "missed_buy_return_after_20d": "",
        "blocked_decision_outcome": "",
    }
