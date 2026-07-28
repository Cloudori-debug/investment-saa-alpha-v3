from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from src.data_refresh.dart_client import DartCredentialsError
from src.data_refresh.dart_enrich import enrich_fundamentals_from_dart


def _default_as_of(data_dir: Path) -> str:
    mi = data_dir / "market_indicators.csv"
    if mi.exists():
        import pandas as pd

        df = pd.read_csv(mi, dtype=str, keep_default_na=False)
        if not df.empty and "date" in df.columns:
            return str(df.iloc[-1]["date"])
    px = data_dir / "prices.csv"
    if px.exists():
        import pandas as pd

        df = pd.read_csv(px, dtype=str, keep_default_na=False)
        if not df.empty and "date" in df.columns:
            return str(df.iloc[0]["date"])
    return "2026-01-01"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open DART 상세 재무 fundamentals 보강")
    root = Path(__file__).resolve().parents[2]
    parser.add_argument("--data-dir", type=Path, default=root / "data")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument(
        "--scope",
        choices=["prices", "liquid", "holdings", "all"],
        default="prices",
    )
    parser.add_argument("--sleep", type=float, default=0.12)
    parser.add_argument("--tickers", type=str, default="", help="쉼표 구분 ticker")
    args = parser.parse_args(argv)

    from src.settings.user_secrets import apply_secrets_to_env

    apply_secrets_to_env(args.data_dir)

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()] or None
    as_of = args.as_of or _default_as_of(args.data_dir)

    try:
        result = enrich_fundamentals_from_dart(
            args.data_dir,
            as_of=as_of,
            tickers=tickers,
            scope=args.scope,  # type: ignore[arg-type]
            sleep_sec=args.sleep,
        )
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return 0 if result.enriched > 0 else 1
    except DartCredentialsError as exc:
        print(f"CREDENTIALS: {exc}", file=sys.stderr)
        print('PowerShell: $env:DART_API_KEY="your_40_char_key"', file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
