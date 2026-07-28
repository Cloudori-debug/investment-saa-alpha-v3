"""P5-D1 — narrow-scope historical price backfill (KOSPI200 proxy + Core SAA).



Does NOT touch gate/policy_cap/target_write. Read-only price collection.

Idempotent: existing (ticker, date) rows are never overwritten.



Safety:

- Preflight integrity check (reject NUL / empty history)

- Collect all new rows in memory, then ONE atomic write

- Postflight: NUL==0, row count, required tickers present

"""

from __future__ import annotations



import argparse

import json

import shutil

import sys

import time

from datetime import datetime, timezone

from pathlib import Path

from typing import Any



import pandas as pd



ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:

    sys.path.insert(0, str(ROOT))



from src.data_loader import load_target_portfolio  # noqa: E402

from src.data_refresh.price_store import (  # noqa: E402

    PRICE_COLUMNS,

    atomic_write_csv,

    inspect_csv_bytes,

    normalize_ticker,

)

from src.data_refresh.pykrx_client import (  # noqa: E402

    KrxCredentialsError,

    import_pykrx_stock,

    lookback_start,

    to_compact_date,

    to_iso_date,

)



BENCHMARK_TICKERS = ("069500",)

OUTPUT_REPORT = "price_backfill_report.json"





def resolve_backfill_tickers(data_dir: Path) -> list[str]:

    """069500 + target_portfolio.csv tickers with asset_group != kr_alpha. CASH excluded."""

    out: list[str] = []

    seen: set[str] = set()

    for t in BENCHMARK_TICKERS:

        nt = normalize_ticker(t)

        if nt not in seen:

            seen.add(nt)

            out.append(nt)

    path = data_dir / "target_portfolio.csv"

    if path.exists():

        for row in load_target_portfolio(path):

            if str(row.asset_group or "") == "kr_alpha":

                continue

            t = normalize_ticker(row.ticker)

            if not t or t.upper() == "CASH":

                continue

            if t not in seen:

                seen.add(t)

                out.append(t)

    return out





def _existing_keys_from_df(df: pd.DataFrame) -> set[tuple[str, str]]:

    if df.empty or "date" not in df.columns or "ticker" not in df.columns:

        return set()

    keys: set[tuple[str, str]] = set()

    for _, row in df.iterrows():

        keys.add((normalize_ticker(row["ticker"]), str(row["date"])[:10]))

    return keys





def _load_history_safe(history_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:

    """Load history only if byte integrity passes."""

    integrity = inspect_csv_bytes(history_path)

    if not history_path.exists():

        return pd.DataFrame(columns=PRICE_COLUMNS), integrity

    if integrity.get("nul_bytes", 0) > 0:

        raise RuntimeError(

            f"prices_history integrity failed (NUL bytes): {integrity}"

        )

    if not integrity.get("ok"):

        raise RuntimeError(f"prices_history integrity failed: {integrity}")

    df = pd.read_csv(history_path, dtype={"ticker": str}, keep_default_na=False)

    # Drop fully-empty garbage rows pandas can silently keep

    if not df.empty:

        nonempty = df.astype(str).apply(lambda s: s.str.strip().ne("").any(), axis=1)

        df = df.loc[nonempty].copy()

    return df, integrity





def _ohlcv_to_rows(ticker: str, ohlcv: pd.DataFrame) -> list[dict[str, Any]]:

    """Expand pykrx OHLCV into prices_history schema rows (daily close)."""

    if ohlcv is None or getattr(ohlcv, "empty", True):

        return []

    rows: list[dict[str, Any]] = []

    close_col = "종가" if "종가" in ohlcv.columns else ("close" if "close" in ohlcv.columns else None)

    if close_col is None:

        return []

    for idx, row in ohlcv.iterrows():

        if hasattr(idx, "strftime"):

            date = idx.strftime("%Y-%m-%d")

        else:

            s = str(idx)

            date = to_iso_date(s) if len(s.replace("-", "")) == 8 else s[:10]

        try:

            close = float(row[close_col])

        except (TypeError, ValueError):

            continue

        if close <= 0:

            continue

        rows.append({

            "date": date,

            "ticker": normalize_ticker(ticker),

            "close": int(round(close)),

            "market_cap": 0,

            "trading_value_20d": 0,

            "trading_value_60d": 0,

            "return_1m": 0.0,

            "return_3m": 0.0,

            "return_6m": 0.0,

            "return_12m": 0.0,

            "return_12m_ex_1m": 0.0,

            "high_52w": int(round(close)),

            "distance_from_52w_high": 0.0,

            "volatility_60d": 0.0,

        })

    return rows





def _merge_new_rows(

    old: pd.DataFrame,

    new_rows: list[dict[str, Any]],

    existing_keys: set[tuple[str, str]],

) -> tuple[pd.DataFrame, int, int]:

    """Return merged frame + (added, skipped). Never overwrites existing keys."""

    added = 0

    skipped = 0

    to_write: list[dict[str, Any]] = []

    for row in new_rows:

        key = (normalize_ticker(row["ticker"]), str(row["date"])[:10])

        if key in existing_keys:

            skipped += 1

            continue

        existing_keys.add(key)

        to_write.append(row)

        added += 1

    if not to_write:

        return old, 0, skipped

    new_df = pd.DataFrame(to_write)

    if old is None or old.empty:

        out = new_df

    else:

        out = pd.concat([old, new_df], ignore_index=True)

    out["ticker"] = out["ticker"].map(normalize_ticker)

    out = out.sort_values(["ticker", "date"], na_position="last")

    out = out.drop_duplicates(subset=["ticker", "date"], keep="first")

    cols = [c for c in PRICE_COLUMNS if c in out.columns]

    return out[cols], added, skipped





# Retained for unit tests (single-batch helper)

def _append_only_merge(

    history_path: Path,

    new_rows: list[dict[str, Any]],

    existing_keys: set[tuple[str, str]],

) -> tuple[int, int]:

    old, _ = _load_history_safe(history_path) if history_path.exists() else (

        pd.DataFrame(columns=PRICE_COLUMNS), {"ok": True},

    )

    baseline = len(old)

    out, added, skipped = _merge_new_rows(old, new_rows, existing_keys)

    if added == 0:

        return 0, skipped

    atomic_write_csv(

        history_path,

        out,

        encoding="utf-8-sig",

        min_rows=baseline + added,

    )

    return added, skipped





def _backup_history(history_path: Path, backup_dir: Path) -> Path | None:

    if not history_path.exists():

        return None

    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    dest = backup_dir / f"prices_history_pre_backfill_{stamp}.csv"

    shutil.copy2(history_path, dest)

    return dest





def backfill_price_history(

    data_dir: Path,

    tickers: list[str] | None = None,

    as_of: str | None = None,

    lookback_days: int = 400,

    *,

    output_dir: Path | None = None,

    dry_run: bool = False,

    sleep_sec: float = 0.15,

    stock: Any | None = None,

) -> dict[str, Any]:

    """Reuse pykrx OHLCV; append-only merge into prices_history.csv (single atomic write)."""

    data_dir = Path(data_dir)

    output_dir = Path(output_dir) if output_dir else data_dir.parent / "outputs"

    as_of = (as_of or datetime.now().strftime("%Y-%m-%d"))[:10]

    tickers = tickers or resolve_backfill_tickers(data_dir)

    history_path = data_dir / "prices_history.csv"

    backup_dir = data_dir / "quarantine"



    report: dict[str, Any] = {

        "schema_version": "1.1",

        "as_of": as_of,

        "requested_tickers": list(tickers),

        "lookback_days": lookback_days,

        "rows_added": 0,

        "rows_skipped_existing": 0,

        "rows_before": 0,

        "rows_after": 0,

        "tickers_ok": [],

        "tickers_failed": [],

        "krx_login_status": "unknown",

        "dry_run": dry_run,

        "success": False,

        "reason": "",

        "preflight_integrity": {},

        "postflight_integrity": {},

        "backup_path": "",

        "note": "read-only price backfill — gate/policy/target_write 미변경; atomic write",

        "generated_at": datetime.now(timezone.utc).isoformat(),

    }



    def _write_report() -> None:

        output_dir.mkdir(parents=True, exist_ok=True)

        (output_dir / OUTPUT_REPORT).write_text(

            json.dumps(report, ensure_ascii=False, indent=2) + "\n",

            encoding="utf-8",

        )



    if stock is None:

        try:

            stock = import_pykrx_stock(data_dir)

            report["krx_login_status"] = "ok"

        except KrxCredentialsError:

            report["krx_login_status"] = "missing"

            report["reason"] = "krx_credentials_missing"

            report["success"] = False

            _write_report()

            return report

        except Exception as exc:

            report["krx_login_status"] = "error"

            report["reason"] = f"pykrx_import_failed:{type(exc).__name__}"

            report["success"] = False

            _write_report()

            return report

    else:

        report["krx_login_status"] = "injected"



    if dry_run:

        start = lookback_start(as_of, lookback_days)

        report["dry_run_window"] = {"start": start, "end": as_of}

        if history_path.exists():

            try:

                report["preflight_integrity"] = inspect_csv_bytes(history_path)

            except Exception as exc:

                report["preflight_integrity"] = {"error": type(exc).__name__}

        report["success"] = True

        report["reason"] = "dry_run"

        _write_report()

        return report



    # Preflight — refuse to write on top of NUL-corrupted file

    try:

        old, pre = _load_history_safe(history_path) if history_path.exists() else (

            pd.DataFrame(columns=PRICE_COLUMNS),

            {"exists": False, "ok": True, "nul_bytes": 0},

        )

    except RuntimeError as exc:

        report["preflight_integrity"] = inspect_csv_bytes(history_path)

        report["reason"] = f"preflight_integrity_failed:{exc}"

        report["success"] = False

        _write_report()

        return report



    report["preflight_integrity"] = pre

    report["rows_before"] = int(len(old))

    existing = _existing_keys_from_df(old)



    bak = _backup_history(history_path, backup_dir)

    if bak is not None:

        report["backup_path"] = str(bak)



    compact_end = to_compact_date(as_of)

    compact_start = to_compact_date(lookback_start(as_of, lookback_days))

    all_new_rows: list[dict[str, Any]] = []

    total_skipped = 0



    for i, ticker in enumerate(tickers):

        try:

            ohlcv = stock.get_market_ohlcv(compact_start, compact_end, ticker)

            rows = _ohlcv_to_rows(ticker, ohlcv)

            # Count skip against current key set without mutating history yet

            added_here = 0

            skipped_here = 0

            for row in rows:

                key = (normalize_ticker(row["ticker"]), str(row["date"])[:10])

                if key in existing:

                    skipped_here += 1

                else:

                    existing.add(key)

                    all_new_rows.append(row)

                    added_here += 1

            total_skipped += skipped_here

            if added_here or skipped_here:

                report["tickers_ok"].append({

                    "ticker": ticker,

                    "rows_fetched": len(rows),

                    "rows_added": added_here,

                    "rows_skipped_existing": skipped_here,

                })

            else:

                report["tickers_failed"].append({"ticker": ticker, "reason": "empty_ohlcv"})

        except Exception as exc:

            report["tickers_failed"].append({

                "ticker": ticker,

                "reason": f"{type(exc).__name__}",

            })

        if sleep_sec and i < len(tickers) - 1:

            time.sleep(sleep_sec)



    merged, added, _ = _merge_new_rows(

        old,

        all_new_rows,

        _existing_keys_from_df(old),  # rematerialize from old for keep-first semantics

    )

    # Prefer explicit added from all_new_rows length (already de-duped against keys)

    added = len(all_new_rows)

    report["rows_added"] = added

    report["rows_skipped_existing"] = total_skipped

    report["rows_after"] = int(len(merged))



    if added == 0 and not report["tickers_failed"]:

        report["success"] = True

        report["reason"] = "ok_noop_no_new_rows"

        report["postflight_integrity"] = inspect_csv_bytes(history_path) if history_path.exists() else {}

        _write_report()

        return report



    try:

        write_info = atomic_write_csv(

            history_path,

            merged,

            encoding="utf-8-sig",

            min_rows=int(len(old)) + added,

            required_tickers=tickers,

        )

        post = inspect_csv_bytes(history_path)

        report["postflight_integrity"] = post

        report["write_info"] = write_info

        if post.get("nul_bytes", 0) > 0 or not post.get("ok"):

            report["success"] = False

            report["reason"] = "postflight_integrity_failed"

        else:

            # Spot-check each requested ticker has ≥1 row

            check = pd.read_csv(history_path, dtype={"ticker": str}, keep_default_na=False)

            missing = [

                t for t in tickers

                if normalize_ticker(t) not in set(check["ticker"].map(normalize_ticker))

            ]

            if missing:

                report["success"] = False

                report["reason"] = f"missing_tickers_after_write:{missing}"

            elif len(check) < int(len(old)) + added:

                report["success"] = False

                report["reason"] = (

                    f"row_shrink_after_write: before={len(old)} added={added} after={len(check)}"

                )

            else:

                report["success"] = len(report["tickers_failed"]) == 0 or added > 0

                report["reason"] = "ok" if not report["tickers_failed"] else "partial_ok"

    except Exception as exc:

        report["success"] = False

        report["reason"] = f"atomic_write_failed:{type(exc).__name__}:{exc}"

        report["postflight_integrity"] = inspect_csv_bytes(history_path) if history_path.exists() else {}



    _write_report()

    return report





def main(argv: list[str] | None = None) -> int:

    parser = argparse.ArgumentParser(description="P5-D1 narrow price history backfill")

    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")

    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")

    parser.add_argument("--as-of", type=str, default=None)

    parser.add_argument("--lookback-days", type=int, default=400)

    parser.add_argument("--dry-run", action="store_true")

    parser.add_argument("--sleep-sec", type=float, default=0.15)

    args = parser.parse_args(argv)



    tickers = resolve_backfill_tickers(args.data_dir)

    print(f"tickers ({len(tickers)}): {', '.join(tickers)}")

    report = backfill_price_history(

        args.data_dir,

        tickers=tickers,

        as_of=args.as_of,

        lookback_days=args.lookback_days,

        output_dir=args.output_dir,

        dry_run=args.dry_run,

        sleep_sec=args.sleep_sec,

    )

    print(json.dumps({

        "success": report.get("success"),

        "reason": report.get("reason"),

        "krx_login_status": report.get("krx_login_status"),

        "rows_before": report.get("rows_before"),

        "rows_added": report.get("rows_added"),

        "rows_after": report.get("rows_after"),

        "rows_skipped_existing": report.get("rows_skipped_existing"),

        "failed": report.get("tickers_failed"),

        "preflight_nul": (report.get("preflight_integrity") or {}).get("nul_bytes"),

        "postflight_nul": (report.get("postflight_integrity") or {}).get("nul_bytes"),

        "backup_path": report.get("backup_path"),

    }, ensure_ascii=False, indent=2))

    print(f"report: {args.output_dir / OUTPUT_REPORT}")

    if report.get("reason") == "krx_credentials_missing":

        return 2

    return 0 if report.get("success") else 1





if __name__ == "__main__":

    raise SystemExit(main())


