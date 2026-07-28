#!/usr/bin/env python3
"""Audit target_portfolio.csv ETF tickers against core_etf_ticker_registry.yaml."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def main() -> int:
    from src.data.core_etf_tickers import audit_target_portfolio_tickers, validate_target_portfolio_structure

    paths = [
        DATA / "target_portfolio.csv",
        DATA / "user_target_portfolio.csv",
    ]
    exit_code = 0
    for path in paths:
        if not path.exists():
            print(f"SKIP {path} (missing)")
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        print(f"=== {path.name} ===")
        struct = validate_target_portfolio_structure(rows, data_dir=DATA)
        print(f"rows={struct['row_count']} weight_sum={struct['weight_sum']}")
        if struct["pass"]:
            print("PASS — structure & weight sum OK")
        else:
            exit_code = 1
            for issue in struct["issues"]:
                loc = f"line {issue['line']} " if issue.get("line") else ""
                print(
                    f"FAIL {loc}{issue.get('ticker', '')}: {issue['issue']} — {issue.get('detail', '')}"
                )

        result = audit_target_portfolio_tickers(rows, data_dir=DATA)
        if result["pass"]:
            print("PASS — ETF tickers match registry")
        else:
            exit_code = 1
            for issue in result["issues"]:
                print(
                    f"FAIL {issue['ticker']} {issue['name']}: {issue['issue']} "
                    f"→ expected {issue.get('expected_ticker')} {issue.get('expected_name')} "
                    f"({issue.get('detail', '')})"
                )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
