"""Refresh data/krx_sector_mapping.csv from KRX official sectors (PyKRX).

Requires KRX_ID/KRX_PW (or data/ user_secrets). Does not overwrite
krx_sector_mapping_manual.csv — manual rows keep SOURCE priority via
load_krx_sector_mapping().

Usage:
  python scripts/refresh_krx_sector_mapping.py
  python scripts/refresh_krx_sector_mapping.py --apply-screening
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.alpha.sector_mapping import SECTOR_MAPPING_COLUMNS  # noqa: E402
from src.settings.user_secrets import apply_secrets_to_env, load_user_secrets  # noqa: E402

DATA = ROOT / "data"
TAXONOMY_PATH = DATA / "krx_sector_taxonomy.yaml"
MAPPING_PATH = DATA / "krx_sector_mapping.csv"
SCREENING_PATH = ROOT / "alpha_portfolio" / "data" / "input" / "screening_universe.csv"
UNIVERSE_PATH = DATA / "universe.csv"


def _ensure_krx_env() -> None:
    apply_secrets_to_env(DATA)
    secrets = load_user_secrets(DATA)
    if secrets.krx_id and not os.environ.get("KRX_ID"):
        os.environ["KRX_ID"] = secrets.krx_id
    if secrets.krx_pw and not os.environ.get("KRX_PW"):
        os.environ["KRX_PW"] = secrets.krx_pw


def _load_taxonomy() -> dict:
    with TAXONOMY_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _resolve_group(krx_sector: str, taxonomy: dict) -> str:
    mapping = taxonomy.get("krx_to_sector_group") or {}
    aliases = taxonomy.get("legacy_krx_aliases") or {}
    label = aliases.get(krx_sector, krx_sector)
    return str(mapping.get(label) or mapping.get(krx_sector) or "other")


def _fetch_market(market: str, asof_yyyymmdd: str | None = None) -> tuple[str, pd.DataFrame]:
    from pykrx import stock

    last_err: Exception | None = None
    for offset in range(0, 14):
        day = asof_yyyymmdd or (datetime.now() - timedelta(days=offset)).strftime("%Y%m%d")
        try:
            df = stock.get_market_sector_classifications(day, market)
            if df is not None and len(df) > 0:
                out = df.reset_index()
                return day, out
        except Exception as exc:  # noqa: BLE001 — probe trading days
            last_err = exc
            if asof_yyyymmdd:
                break
    raise RuntimeError(f"KRX sector fetch failed for {market}: {last_err}")


def build_mapping_rows(
    *,
    markets: tuple[str, ...] = ("KOSPI", "KOSDAQ"),
    asof_yyyymmdd: str | None = None,
) -> tuple[str, list[dict[str, str]]]:
    taxonomy = _load_taxonomy()
    rows: dict[str, dict[str, str]] = {}
    asof_used = ""
    for market in markets:
        day, df = _fetch_market(market, asof_yyyymmdd)
        asof_used = day
        # Expected columns: 종목코드, 종목명, 업종명, ...
        code_col = "종목코드" if "종목코드" in df.columns else df.columns[0]
        name_col = "종목명" if "종목명" in df.columns else df.columns[1]
        sector_col = "업종명" if "업종명" in df.columns else df.columns[2]
        for _, raw in df.iterrows():
            ticker = str(raw[code_col]).strip().zfill(6)
            if not ticker.isdigit():
                continue
            krx_sector = str(raw[sector_col]).strip()
            rows[ticker] = {
                "ticker": ticker,
                "name": str(raw[name_col]).strip(),
                "market": market,
                "krx_sector": krx_sector,
                "internal_sector": krx_sector,
                "sector_group": _resolve_group(krx_sector, taxonomy),
                "source": "krx_official",
                "asof": f"{day[:4]}-{day[4:6]}-{day[6:]}",
                "is_manual": "false",
                "notes": "pykrx_get_market_sector_classifications",
            }
    return asof_used, [rows[k] for k in sorted(rows)]


def write_mapping(rows: list[dict[str, str]], path: Path = MAPPING_PATH) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SECTOR_MAPPING_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in SECTOR_MAPPING_COLUMNS})


def apply_to_screening(mapping_by_ticker: dict[str, dict[str, str]]) -> dict[str, int]:
    if not SCREENING_PATH.exists():
        return {"updated": 0, "missing": 0}
    df = pd.read_csv(SCREENING_PATH, dtype=str, keep_default_na=False)
    updated = missing = 0
    sectors: list[str] = []
    for _, row in df.iterrows():
        tk = str(row.get("ticker", "")).zfill(6)
        hit = mapping_by_ticker.get(tk)
        if hit and hit.get("krx_sector"):
            sectors.append(hit["krx_sector"])
            updated += 1
        else:
            sectors.append(str(row.get("sector") or "unknown") or "unknown")
            if str(row.get("gate_pass", "")).lower() == "true":
                missing += 1
    df["sector"] = sectors
    df.to_csv(SCREENING_PATH, index=False, encoding="utf-8-sig")
    return {"updated": updated, "missing_gate_pass": missing}


def apply_to_universe(mapping_by_ticker: dict[str, dict[str, str]]) -> dict[str, int]:
    if not UNIVERSE_PATH.exists():
        return {"updated": 0}
    df = pd.read_csv(UNIVERSE_PATH, dtype=str, keep_default_na=False)
    if "sector" not in df.columns:
        df["sector"] = ""
    if "industry" not in df.columns:
        df["industry"] = ""
    updated = 0
    for i, row in df.iterrows():
        tk = str(row.get("ticker", "")).zfill(6)
        hit = mapping_by_ticker.get(tk)
        if not hit:
            continue
        df.at[i, "sector"] = hit["krx_sector"]
        df.at[i, "industry"] = hit["sector_group"]
        updated += 1
    df.to_csv(UNIVERSE_PATH, index=False, encoding="utf-8-sig")
    return {"updated": updated}


def coverage_report(mapping_by_ticker: dict[str, dict[str, str]]) -> dict:
    if not SCREENING_PATH.exists():
        return {}
    df = pd.read_csv(SCREENING_PATH, dtype=str, keep_default_na=False)
    gp = df[df["gate_pass"].str.lower() == "true"].copy()
    resolved = []
    markets = []
    for _, row in gp.iterrows():
        tk = str(row["ticker"]).zfill(6)
        hit = mapping_by_ticker.get(tk)
        sector = hit["krx_sector"] if hit else "unknown"
        resolved.append(sector if sector else "unknown")
        markets.append(hit["market"] if hit else "missing")
    gp = gp.assign(_sector=resolved, _market=markets)
    n = len(gp)
    unknown = sum(1 for s in resolved if s == "unknown")
    by_sector = gp["_sector"].value_counts().to_dict()
    fallback = sorted([s for s, c in by_sector.items() if s != "unknown" and c < 5])
    return {
        "gate_pass": n,
        "unknown": unknown,
        "unknown_pct": round(100 * unknown / n, 2) if n else 0.0,
        "by_market": gp["_market"].value_counts().to_dict(),
        "by_sector": by_sector,
        "sectors_sample_lt_5": fallback,
        "target_unknown_pct": 5.0,
        "target_met": (100 * unknown / n) < 5.0 if n else False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply-screening", action="store_true")
    parser.add_argument("--apply-universe", action="store_true")
    parser.add_argument("--asof", default=None, help="YYYYMMDD trading day")
    args = parser.parse_args()

    _ensure_krx_env()
    asof, rows = build_mapping_rows(asof_yyyymmdd=args.asof)
    write_mapping(rows)
    by_tk = {r["ticker"]: r for r in rows}
    print(f"wrote {MAPPING_PATH} rows={len(rows)} asof={asof}")

    if args.apply_screening:
        stats = apply_to_screening(by_tk)
        print("screening_universe:", stats)
    if args.apply_universe:
        stats = apply_to_universe(by_tk)
        print("universe.csv:", stats)

    cov = coverage_report(by_tk)
    print("coverage:", cov)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
