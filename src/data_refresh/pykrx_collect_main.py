from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from src.data_refresh.pykrx_bulk import run_pykrx_bulk_collect
from src.data_refresh.pykrx_client import KrxCredentialsError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PyKRX KOSPI+KOSDAQ 일괄 수집 (universe + prices + fundamentals)"
    )
    root = Path(__file__).resolve().parents[2]
    parser.add_argument("--data-dir", type=Path, default=root / "data")
    parser.add_argument("--as-of", type=str, default=None, help="YYYY-MM-DD (미지정 시 최근 영업일)")
    parser.add_argument(
        "--kosdaq-sync-only",
        action="store_true",
        help="KOSDAQ universe만 동기화 + liquid 가격 bootstrap (KOSPI 유지)",
    )
    parser.add_argument(
        "--scope",
        choices=["all", "liquid", "holdings"],
        default="liquid",
        help="liquid=유동성 필터 통과 common stock, holdings=보유+target만",
    )
    parser.add_argument("--max-tickers", type=int, default=None, help="테스트용 상한")
    parser.add_argument("--sleep", type=float, default=0.15, help="종목 간 API 지연(초)")
    parser.add_argument("--no-merge-universe", action="store_true")
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--no-dart", action="store_true", help="DART 재무 보강 비활성화")
    args = parser.parse_args(argv)

    from src.settings.user_secrets import apply_secrets_to_env

    apply_secrets_to_env(args.data_dir)

    try:
        if args.kosdaq_sync_only:
            from src.data_refresh.pykrx_bulk import run_kosdaq_universe_sync

            result = run_kosdaq_universe_sync(args.data_dir, as_of=args.as_of)
            print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
            return 0
        result = run_pykrx_bulk_collect(
            args.data_dir,
            as_of=args.as_of,
            scope=args.scope,
            max_tickers=args.max_tickers,
            sleep_sec=args.sleep,
            merge_existing_universe=not args.no_merge_universe,
            write_history=not args.no_history,
            enrich_dart=not args.no_dart,
        )
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return 0
    except KrxCredentialsError as exc:
        print(f"CREDENTIALS: {exc}", file=sys.stderr)
        print(
            "PowerShell: $env:KRX_ID='your_id'; $env:KRX_PW='your_password'",
            file=sys.stderr,
        )
        return 3
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
