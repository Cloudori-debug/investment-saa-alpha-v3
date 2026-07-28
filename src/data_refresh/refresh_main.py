from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from src.data_refresh.fundamentals_validate import ensure_fundamentals_for_universe, validate_fundamentals
from src.data_refresh.prices_refresh import append_prices_history, refresh_prices_snapshot
from src.data_refresh.pykrx_client import KrxCredentialsError
from src.data_refresh.dart_client import DartCredentialsError
from src.data_refresh.universe_sync import sync_universe_from_holdings


def run_refresh(
    data_dir: Path,
    *,
    as_of: str | None = None,
    sync_universe: bool = True,
    refresh_prices: bool = True,
    append_history: bool = True,
    validate_fund: bool = True,
    pykrx_bulk: bool = False,
    pykrx_scope: str = "liquid",
    pykrx_max_tickers: int | None = None,
    enrich_dart: bool = False,
    dart_scope: str = "prices",
    refresh_kospi_market: bool = False,
    refresh_tier2: bool = False,
    tier_b_if_due: bool = False,
    tier_b_force: bool = False,
    sync_regime_auto: bool = False,
    output_dir: Path | None = None,
) -> dict:
    from src.settings.user_secrets import apply_secrets_to_env

    apply_secrets_to_env(data_dir)
    report: dict = {"as_of": as_of or date.today().isoformat(), "steps": []}

    if refresh_tier2:
        from src.data_refresh.tier2_refresh import refresh_macro_tier2

        t2 = refresh_macro_tier2(data_dir, as_of=as_of)
        step: dict = {
            "tier2_refresh": {
                "as_of": t2.as_of,
                "updated": t2.updated_fields,
                "preserved": t2.preserved_fields,
                "api_fields_fetched": t2.api_fields_fetched,
                "warnings": t2.warnings,
                "errors": t2.errors,
                "path": t2.path,
                "provenance_path": t2.provenance_path,
                "stale_before": t2.stale_before,
                "stale_after": t2.stale_after,
            },
        }
        if output_dir is not None:
            try:
                from src.validation.tier2_refresh_diagnostics import write_tier2_refresh_diagnostics

                diag = write_tier2_refresh_diagnostics(
                    refresh_result=t2,
                    data_dir=data_dir,
                    output_dir=output_dir,
                    stale_before=t2.stale_before,
                )
                step["tier2_refresh_diagnostics"] = {
                    "path": str(output_dir / "tier2_refresh_diagnostics.json"),
                    "stale_before": diag.get("stale_before"),
                    "stale_after": diag.get("stale_after"),
                    "alpha_gate_expected_impact": diag.get("alpha_gate_expected_impact"),
                }
            except Exception as exc:
                step["tier2_refresh_diagnostics_error"] = str(exc)
        report["steps"].append(step)

    if refresh_kospi_market or pykrx_bulk:
        from src.data_refresh.market_indicators_refresh import refresh_all_market_indicators

        mi = refresh_all_market_indicators(
            data_dir,
            as_of=as_of,
            use_pykrx=True,
            use_external=pykrx_bulk or refresh_kospi_market,
        )
        report["steps"].append({
            "market_indicators": {
                "as_of": mi.as_of,
                "updated": mi.updated_fields,
                "preserved": mi.preserved_fields,
                "warnings": mi.warnings,
                "errors": mi.errors,
                "path": mi.path,
            },
        })

    if pykrx_bulk:
        from src.data_refresh.pykrx_bulk import run_pykrx_bulk_collect

        bulk = run_pykrx_bulk_collect(
            data_dir,
            as_of=as_of,
            scope=pykrx_scope,  # type: ignore[arg-type]
            max_tickers=pykrx_max_tickers,
            write_history=append_history,
            enrich_dart=enrich_dart,
        )
        report["steps"].append({"pykrx_bulk": {
            "as_of": bulk.as_of,
            "universe_count": bulk.universe_count,
            "prices_count": bulk.prices_count,
            "fundamentals_count": bulk.fundamentals_count,
            "dart_enriched": bulk.dart_enriched,
            "scope": bulk.scope,
            "warnings": bulk.warnings,
            "paths": bulk.paths,
        }})
        if validate_fund:
            fv = validate_fundamentals(data_dir)
            missing = ensure_fundamentals_for_universe(data_dir)
            report["steps"].append({
                "fundamentals_validate": {
                    "row_count": fv.row_count,
                    "errors": fv.errors,
                    "warnings": fv.warnings,
                },
                "missing_fundamentals_tickers": missing[:50],
            })
        return report

    if enrich_dart and not pykrx_bulk:
        from src.data_refresh.dart_enrich import enrich_fundamentals_from_dart

        as_of_date = as_of or date.today().isoformat()
        dart = enrich_fundamentals_from_dart(
            data_dir,
            as_of=as_of_date,
            scope=dart_scope,  # type: ignore[arg-type]
        )
        report["steps"].append({"dart_enrich": {
            "as_of": dart.as_of,
            "requested": dart.requested,
            "enriched": dart.enriched,
            "skipped": dart.skipped,
            "path": dart.path,
            "errors_sample": dart.errors[:10],
        }})
        if validate_fund:
            fv = validate_fundamentals(data_dir)
            missing = ensure_fundamentals_for_universe(data_dir)
            report["steps"].append({
                "fundamentals_validate": {
                    "row_count": fv.row_count,
                    "errors": fv.errors,
                    "warnings": fv.warnings,
                },
                "missing_fundamentals_tickers": missing[:50],
            })
        return report

    if tier_b_if_due or tier_b_force:
        from src.data_refresh.tier_b_refresh import run_tier_b_if_due

        as_of_date = as_of or date.today().isoformat()
        tb = run_tier_b_if_due(data_dir, as_of=as_of_date, force=tier_b_force)
        report["steps"].append({
            "tier_b_refresh": {
                "as_of": tb.as_of,
                "ran": tb.ran,
                "reason": tb.reason,
                "prices_count": tb.prices_count,
                "warnings": tb.warnings,
            },
        })

    if sync_universe:
        uni = sync_universe_from_holdings(data_dir)
        report["steps"].append(
            {"universe_sync": {"added": uni.added, "total": uni.total, "path": str(uni.path)}}
        )

    if refresh_prices:
        px = refresh_prices_snapshot(data_dir, as_of=as_of)
        report["steps"].append(
            {
                "prices_refresh": {
                    "as_of": px.as_of,
                    "row_count": px.row_count,
                    "source": px.source,
                    "warnings": px.warnings,
                    "path": str(px.path) if px.path else None,
                }
            }
        )

    if append_history:
        hist = append_prices_history(data_dir)
        report["steps"].append({"prices_history": str(hist) if hist else None})

    if validate_fund:
        fv = validate_fundamentals(data_dir)
        missing = ensure_fundamentals_for_universe(data_dir)
        report["steps"].append({
            "fundamentals_validate": {
                "row_count": fv.row_count,
                "errors": fv.errors,
                "warnings": fv.warnings,
            },
            "missing_fundamentals_tickers": missing,
        })

    if sync_regime_auto and output_dir is not None:
        from src.compass.regime_auto import sync_regime_from_compass

        regime = sync_regime_from_compass(data_dir, output_dir, as_of=as_of)
        report["steps"].append({
            "regime_auto_sync": {
                "as_of": regime.as_of,
                "synced": regime.synced,
                "computed_regime": regime.computed_regime,
                "previous_regime": regime.previous_regime,
                "applied_regime": regime.applied_regime,
                "reason": regime.reason,
                "warnings": regime.warnings,
                "suggestion_path": regime.suggestion_path,
            },
        })

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alpha 데이터 갱신 (universe/prices/fundamentals)")
    root = Path(__file__).resolve().parents[2]
    parser.add_argument("--data-dir", type=Path, default=root / "data")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--no-universe", action="store_true")
    parser.add_argument("--no-prices", action="store_true")
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--no-fundamentals", action="store_true")
    parser.add_argument("--bulk", action="store_true", help="PyKRX KOSPI 일괄 수집 (KRX_ID/KRX_PW 필요)")
    parser.add_argument("--scope", choices=["all", "liquid", "holdings"], default="liquid")
    parser.add_argument("--max-tickers", type=int, default=None)
    parser.add_argument("--dart", action="store_true", help="Open DART 상세 재무 보강 (DART_API_KEY 필요)")
    parser.add_argument("--dart-scope", choices=["prices", "liquid", "holdings", "all"], default="prices")
    parser.add_argument("--no-dart", action="store_true", help="PyKRX bulk 시 DART 보강 비활성화")
    parser.add_argument("--kospi-market", action="store_true", help="KOSPI 지수 → market_indicators.csv 갱신")
    parser.add_argument("--tier-b", action="store_true", help="Tier B liquid bulk (주간 due 시 merge)")
    parser.add_argument("--tier-b-force", action="store_true", help="Tier B liquid bulk 강제 실행")
    parser.add_argument("--regime-auto", action="store_true", help="산출 레짐 자동 동기화 (AUTO/만료 시)")
    parser.add_argument("--output-dir", type=Path, default=None, help="regime_auto_suggestion.json 출력 경로")
    parser.add_argument("--report", type=Path, default=None, help="JSON 리포트 저장 경로")
    args = parser.parse_args(argv)

    try:
        report = run_refresh(
            args.data_dir,
            as_of=args.as_of,
            sync_universe=not args.no_universe,
            refresh_prices=not args.no_prices,
            append_history=not args.no_history,
            validate_fund=not args.no_fundamentals,
            pykrx_bulk=args.bulk,
            pykrx_scope=args.scope,
            pykrx_max_tickers=args.max_tickers,
            enrich_dart=(args.dart or args.bulk) and not args.no_dart,
            dart_scope=args.dart_scope,
            refresh_kospi_market=args.kospi_market,
            refresh_tier2=args.tier2,
            tier_b_if_due=args.tier_b or args.tier_b_force,
            tier_b_force=args.tier_b_force,
            sync_regime_auto=args.regime_auto,
            output_dir=args.output_dir or root / "outputs",
        )
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for step in report["steps"]:
            print(json.dumps(step, ensure_ascii=False))
        return 0
    except KrxCredentialsError as exc:
        print(f"CREDENTIALS: {exc}", file=sys.stderr)
        return 3
    except DartCredentialsError as exc:
        print(f"DART CREDENTIALS: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
