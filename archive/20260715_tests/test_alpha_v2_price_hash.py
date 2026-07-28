"""P1.6e — alpha_v2 price subset hash and fetch policy tests."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.alpha_v2.cache_decision import (
    commit_pipeline_input_snapshot,
    evaluate_alpha_v2_cache_decision,
    write_alpha_v2_cache_decision,
    write_pipeline_input_snapshot,
)
from src.alpha_v2.input_hash import (
    compute_prices_as_of_hash,
    extract_alpha_v2_price_subset,
)
from src.alpha_v2.price_fetch_policy import (
    ALLOWED_STANDARD_PRICE_REFRESH_REASONS,
    evaluate_standard_price_fetch,
    maybe_refresh_tier_prices_before_alpha,
)
from src.alpha_v2.pipeline import run_alpha_v2_shadow
from src.runtime.profiler import RuntimeProfiler
from src.runtime.run_mode import RunMode, resolve_run_config
from src.runtime.run_mode_contract import validate_run_mode_contract

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _write_prices(path: Path, rows: list[dict[str, str]]) -> None:
    df = pd.DataFrame(rows)
    for col in (
        "trading_value_20d", "trading_value_60d", "return_1m", "return_3m",
        "return_6m", "return_12m", "return_12m_ex_1m", "high_52w",
        "distance_from_52w_high", "volatility_60d",
    ):
        if col not in df.columns:
            df[col] = "0"
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _seed(data: Path, out: Path, as_of: str = "2026-07-07") -> None:
    data.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    tickers = ["005930", "000660", "035420"]
    (data / "universe.csv").write_text(
        "ticker,name,market,sector,security_type,is_etf_etn,is_reit,is_spac,is_preferred,is_trading_halt,is_administrative_issue\n"
        "005930,삼성전자,KOSPI,IT,common_stock,false,false,false,false,false,false\n"
        "000660,SK하이닉스,KOSPI,IT,common_stock,false,false,false,false,false,false\n"
        "035420,NAVER,KOSPI,IT,common_stock,false,false,false,false,false,false\n",
        encoding="utf-8",
    )
    for name in (
        "prices_history.csv",
        "investor_flows.csv",
        "fundamentals_pit.csv",
        "fundamentals.csv",
        "market_indicators.csv",
    ):
        src = DATA_DIR / name
        if src.exists():
            shutil.copy(src, data / name)
    rows = [
        {
            "date": as_of,
            "ticker": t,
            "close": "70000",
            "market_cap": "400000000000000",
        }
        for t in tickers
    ]
    _write_prices(data / "prices.csv", rows)
    for name in (
        "alpha_v2_scored.csv",
        "alpha_v2_summary.json",
        "alpha_v2_top30.csv",
        "alpha_v2_final_candidates.csv",
    ):
        if name.endswith(".json"):
            (out / name).write_text(
                json.dumps({"as_of": as_of, "kosdaq_validation_failures": [], "mode": "shadow"}),
                encoding="utf-8",
            )
        else:
            (out / name).write_text("ticker\n005930\n", encoding="utf-8")
    commit_pipeline_input_snapshot(out, data, as_of=as_of, run_id="seed")
    from src.alpha_v2.input_hash import compute_stable_input_hash, compute_flow_hash

    stable = compute_stable_input_hash(data, as_of=as_of)
    write_alpha_v2_cache_decision(
        out,
        {
            "schema_version": "1.0",
            "run_id": "seed",
            "run_mode": "standard",
            "decision": "reuse_cache",
            "input_hash_current": stable,
            "flow_hash_current": compute_flow_hash(data),
            "refresh_reason": "input_hash_unchanged",
            "alpha_v2_reused_from_cache": True,
            "alpha_v2_full_refresh_executed": False,
        },
    )


def test_mtime_change_does_not_change_hash(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    h1 = compute_prices_as_of_hash(data, "2026-07-07")
    time.sleep(0.05)
    path = data / "prices.csv"
    path.touch()
    h2 = compute_prices_as_of_hash(data, "2026-07-07")
    assert h1 == h2


def test_row_order_change_does_not_change_hash(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    h1 = compute_prices_as_of_hash(data, "2026-07-07")
    df = pd.read_csv(data / "prices.csv", dtype=str)
    df = df.iloc[::-1]
    df.to_csv(data / "prices.csv", index=False, encoding="utf-8-sig")
    h2 = compute_prices_as_of_hash(data, "2026-07-07")
    assert h1 == h2


def test_unrelated_ticker_does_not_change_hash(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    h1 = compute_prices_as_of_hash(data, "2026-07-07")
    df = pd.read_csv(data / "prices.csv", dtype=str)
    extra = {
        "date": "2026-07-07",
        "ticker": "999999",
        "close": "12345",
        "market_cap": "1",
        "trading_value_20d": "0",
        "trading_value_60d": "0",
        "return_1m": "0",
        "return_3m": "0",
        "return_6m": "0",
        "return_12m": "0",
        "return_12m_ex_1m": "0",
        "high_52w": "0",
        "distance_from_52w_high": "0",
        "volatility_60d": "0",
    }
    df = pd.concat([df, pd.DataFrame([extra])], ignore_index=True)
    df.to_csv(data / "prices.csv", index=False, encoding="utf-8-sig")
    h2 = compute_prices_as_of_hash(data, "2026-07-07")
    assert h1 == h2
    subset = extract_alpha_v2_price_subset(data, "2026-07-07")
    assert "999999" in subset["extra_tickers_ignored"]


def test_unrelated_date_does_not_change_hash(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    h1 = compute_prices_as_of_hash(data, "2026-07-07")
    df = pd.read_csv(data / "prices.csv", dtype=str)
    extra = dict(df.iloc[0])
    extra["date"] = "2026-07-01"
    df = pd.concat([df, pd.DataFrame([extra])], ignore_index=True)
    df.to_csv(data / "prices.csv", index=False, encoding="utf-8-sig")
    h2 = compute_prices_as_of_hash(data, "2026-07-07")
    assert h1 == h2


def test_universe_price_value_change_changes_hash(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    h1 = compute_prices_as_of_hash(data, "2026-07-07")
    df = pd.read_csv(data / "prices.csv", dtype=str)
    df.loc[0, "close"] = "99999"
    df.to_csv(data / "prices.csv", index=False, encoding="utf-8-sig")
    h2 = compute_prices_as_of_hash(data, "2026-07-07")
    assert h1 != h2


def test_missing_universe_ticker_changes_hash(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    h1 = compute_prices_as_of_hash(data, "2026-07-07")
    df = pd.read_csv(data / "prices.csv", dtype=str)
    df = df.iloc[1:]
    df.to_csv(data / "prices.csv", index=False, encoding="utf-8-sig")
    h2 = compute_prices_as_of_hash(data, "2026-07-07")
    assert h1 != h2


def test_market_date_change_changes_hash(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out, as_of="2026-07-07")
    h1 = compute_prices_as_of_hash(data, "2026-07-07")
    h2 = compute_prices_as_of_hash(data, "2026-07-08")
    assert h1 != h2


def test_standard_skips_price_fetch_when_hash_matches(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    skip, reason = evaluate_standard_price_fetch(
        data, out, as_of="2026-07-07", run_mode=RunMode.STANDARD,
    )
    assert skip is True
    assert reason == "price_hash_unchanged"


def test_deep_allows_price_fetch(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    skip, reason = evaluate_standard_price_fetch(
        data, out, as_of="2026-07-07", run_mode=RunMode.DEEP,
    )
    assert skip is False
    assert reason == "deep_force_refresh"


def test_quick_forbids_price_fetch(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    skip, reason = evaluate_standard_price_fetch(
        data, out, as_of="2026-07-07", run_mode=RunMode.QUICK,
    )
    assert skip is True
    assert reason == "quick_price_refresh_forbidden"


def test_standard_second_run_reuses_alpha_v2(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    write_pipeline_input_snapshot(out, data, as_of="2026-07-07", run_id="run-2")
    doc = evaluate_alpha_v2_cache_decision(
        data, out, as_of="2026-07-07", run_mode="standard", cache_reuse=True, run_id="run-2",
    )
    assert doc["decision"] == "reuse_cache"
    assert doc["price_hash_match"] is True
    assert doc["alpha_v2_reused_from_cache"] is True


def test_pipeline_reuse_skips_scoring_second_run(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    write_pipeline_input_snapshot(out, data, as_of="2026-07-07", run_id="r2")
    with patch("src.alpha_v2.pipeline.score_alpha_v2_universe") as mock_score:
        result = run_alpha_v2_shadow(
            data, out, as_of="2026-07-07", positions=[], targets=[],
            cache_reuse=True, force_refresh=False, run_mode="standard", run_id="r2", profiler=prof,
        )
        mock_score.assert_not_called()
    assert prof.alpha_v2_reused_from_cache is True
    assert result.get("cache_reused") is True


def test_maybe_refresh_skips_tier_fetch_on_standard(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    _seed(data, out)
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    with patch("src.data_refresh.prices_refresh.ensure_tier_a_prices") as mock_tier:
        meta = maybe_refresh_tier_prices_before_alpha(
            data, out, as_of="2026-07-07", run_mode=RunMode.STANDARD, profiler=prof, run_id="r1",
        )
        mock_tier.assert_not_called()
    assert meta["price_fetch_executed"] is False
    assert prof.price_fetch_executed is False


def test_contract_fail_pykrx_mass_calls(tmp_path: Path) -> None:
    cfg = resolve_run_config(RunMode.STANDARD)
    prof = RuntimeProfiler(run_id="r1", run_mode="standard")
    prof.pykrx_call_count = 80
    doc = validate_run_mode_contract(cfg, prof, hooks_meta={})
    assert doc["contract_pass"] is False
    assert any("PyKRX" in v for v in doc["violations"])


def test_allowed_standard_price_reasons() -> None:
    assert "price_coverage_missing" in ALLOWED_STANDARD_PRICE_REFRESH_REASONS
