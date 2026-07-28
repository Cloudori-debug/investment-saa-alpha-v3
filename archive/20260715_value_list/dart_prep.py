from __future__ import annotations

from pathlib import Path

from src.settings.user_secrets import credential_status
from src.value_list.dart_verification import run_hakedaka_dart_verification
from src.value_list.ticker_registry import hakedaka_ticker_set, load_integration_config, resolve_hakedaka_registry


def _tickers_missing_fundamentals(data_dir: Path, tickers: list[str]) -> list[str]:
    import pandas as pd

    path = data_dir / "fundamentals.csv"
    have: set[str] = set()
    if path.exists():
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        have = {str(t).zfill(6) for t in df["ticker"].tolist()}
    return [t for t in tickers if t not in have]


def prepare_hakedaka_dart_pipeline(data_dir: Path, output_dir: Path) -> dict:
    """알파·하케다카 전 DART 공시 스캔 + 재무 보강 + 검증 리포트."""
    cfg = load_integration_config(data_dir)
    if not cfg.get("enabled", True):
        return {"skipped": True}

    registry = resolve_hakedaka_registry(data_dir)
    tickers = [str(r["ticker"]).zfill(6) for r in registry if r.get("ticker")]
    result: dict = {"tickers": len(tickers)}

    if not credential_status(data_dir).get("dart"):
        result["dart"] = "no_credentials"
        from src.value_list.dart_verification import build_verification_rows, write_hakedaka_dart_verification

        rows = build_verification_rows(data_dir)
        write_hakedaka_dart_verification(data_dir, output_dir, rows)
        return result

    dart_cfg = cfg.get("dart") or {}
    if dart_cfg.get("auto_enrich_fundamentals", True):
        missing = _tickers_missing_fundamentals(data_dir, tickers)
        if missing:
            from datetime import date

            from src.data_refresh.dart_enrich import enrich_fundamentals_from_dart

            try:
                enr = enrich_fundamentals_from_dart(
                    data_dir,
                    as_of=date.today().isoformat(),
                    tickers=missing,
                    scope="all",
                )
                result["fundamentals_enriched"] = enr.enriched
                result["fundamentals_missing_before"] = len(missing)
            except Exception as exc:
                result["fundamentals_enrich_error"] = str(exc)

    ver = run_hakedaka_dart_verification(data_dir, output_dir, tickers)
    result["verification"] = ver.get("summary", {})
    return result
