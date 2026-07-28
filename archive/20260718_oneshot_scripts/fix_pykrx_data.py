"""기존 PyKRX 수집 데이터 governance·PIT 필드 보정 (재수집 없이)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data_refresh.universe_sync import UNIVERSE_COLUMNS
from src.data_refresh.pykrx_bulk import normalize_universe_defaults


def fix_universe(data_dir: Path) -> int:
    path = data_dir / "universe.csv"
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    before = (df["audit_opinion"].astype(str).str.strip() == "").sum()
    fixed = normalize_universe_defaults(df)
    fixed = fixed[UNIVERSE_COLUMNS]
    fixed.to_csv(path, index=False, encoding="utf-8-sig")
    return int(before)


def fix_fundamentals_pit(data_dir: Path) -> int:
    path = data_dir / "fundamentals.csv"
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    n = 0
    for idx, row in df.iterrows():
        usable = str(row.get("usable_from_date", "")).strip()
        report = str(row.get("report_date", "")).strip()
        if not report:
            continue
        if not usable or usable > report:
            df.at[idx, "usable_from_date"] = report
            n += 1
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return n


if __name__ == "__main__":
    data = ROOT / "data"
    u = fix_universe(data)
    f = fix_fundamentals_pit(data)
    print(f"universe audit filled: {u} rows had empty audit")
    print(f"fundamentals usable_from_date fixed: {f}")
