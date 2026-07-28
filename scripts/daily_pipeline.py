#!/usr/bin/env python3
"""일일 데이터 갱신 + 전체 파이프라인 + 실투자 요약.

Windows 작업 스케줄러 또는 수동 실행:
  python scripts/daily_pipeline.py
  python scripts/daily_pipeline.py --as-of 2026-06-22
  python scripts/daily_pipeline.py --run-mode standard
  python scripts/daily_pipeline.py --run-mode deep

알파 정량 스냅샷(alpha_scores + provenance)은 STANDARD 모드의
refresh_network=False와 분리된 경로입니다:
  python scripts/run_alpha_quant_snapshot.py --collect
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    from src.runtime.cli import add_run_mode_argument, execute_pipeline_with_run_mode
    from src.runtime.run_mode import RunMode, resolve_run_config

    root = ROOT
    parser = argparse.ArgumentParser(description="일일 갱신 + 전체 파이프라인 (dry-run 로그)")
    parser.add_argument("--data-dir", type=Path, default=root / "data")
    parser.add_argument("--output-dir", type=Path, default=root / "outputs")
    parser.add_argument("--as-of", type=str, default=None, help="YYYY-MM-DD (기본: 오늘)")
    parser.add_argument("--skip-refresh", action="store_true", help="시장지표·가격 갱신 생략")
    parser.add_argument("--no-backtest", action="store_true")
    add_run_mode_argument(parser)
    args = parser.parse_args(argv)

    as_of = args.as_of or date.today().isoformat()
    cfg = resolve_run_config(args.run_mode)
    report: dict = {"as_of": as_of, "run_mode": cfg.run_mode.value, "steps": []}

    try:
        from src.settings.user_secrets import apply_secrets_to_env

        apply_secrets_to_env(args.data_dir)

        skip_refresh = (
            args.skip_refresh
            or cfg.run_mode in {RunMode.QUICK, RunMode.BUNDLE_ONLY}
            or not cfg.refresh_network
        )
        if not skip_refresh and cfg.run_mode in {RunMode.STANDARD, RunMode.DEEP}:
            from src.data_refresh.refresh_main import run_refresh

            refresh_report = run_refresh(
                args.data_dir,
                as_of=as_of,
                refresh_kospi_market=True,
                refresh_tier2=True,
                sync_regime_auto=True,
                output_dir=args.output_dir,
                refresh_prices=True,
                append_history=True,
                validate_fund=True,
            )
            from src.data_refresh.tier_h import refresh_tier_h_snapshot

            tier_h = refresh_tier_h_snapshot(args.data_dir, as_of=as_of)
            refresh_report.setdefault("steps", []).append({
                "tier_h_prices": {
                    "coverage_pct": tier_h.coverage_pct,
                    "required": tier_h.required_count,
                    "added": tier_h.added,
                    "failed": tier_h.failed[:12],
                },
            })
            report["steps"].append({"refresh": refresh_report})

        from src.operational_checklist import write_executable_brief
        from src.validation.system_health import run_system_health, write_health_report

        pipe = execute_pipeline_with_run_mode(
            args.data_dir,
            args.output_dir,
            run_mode=args.run_mode,
            entrypoint="cli",
            run_backtest=not args.no_backtest if cfg.run_mode not in {RunMode.QUICK, RunMode.BUNDLE_ONLY} else False,
            refresh_market=False,
        )
        health = run_system_health(args.data_dir, args.output_dir)
        write_health_report(health, args.output_dir / "system_health.json")
        brief_path = write_executable_brief(args.data_dir, args.output_dir)

        ac_path = args.output_dir / "acceptance_report.json"
        ac = json.loads(ac_path.read_text(encoding="utf-8")) if ac_path.exists() else {}

        report["steps"].append({
            "pipeline": {
                "run_mode": pipe.run_mode,
                "data_gate": pipe.data_gate,
                "actual_buy_allowed": pipe.actual_buy_allowed,
                "health": health.overall,
                "execution_scope": ac.get("execution_scope"),
                "dry_run_days": ac.get("dry_run_days"),
                "executable_brief": str(brief_path.name),
                "macro_scenario": (args.output_dir / "macro_scenario.json").exists(),
                "research_checklist": (args.output_dir / "research_checklist.json").exists(),
            },
        })

        log_path = args.output_dir / "daily_run_log.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(report, ensure_ascii=False) + "\n")

        print(f"OK as_of={as_of} mode={pipe.run_mode} gate={pipe.data_gate} scope={ac.get('execution_scope')}")
        print(f"Actual Buy Allowed: {pipe.actual_buy_allowed}")
        print(f"dry-run {ac.get('dry_run_days', 0)}/10 | brief: {brief_path.name}")
        verdict = ac.get("operational_verdict", "")
        if verdict:
            try:
                print(verdict)
            except UnicodeEncodeError:
                print(verdict.encode("ascii", errors="replace").decode("ascii"))
        gate = pipe.data_gate or ac.get("data_gate") or "GREEN"
        return 0 if gate != "RED" else 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
