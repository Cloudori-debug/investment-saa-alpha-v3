#!/usr/bin/env python3
"""Generate a review-only policy-B six-name dry report."""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alpha_system.loader import load_config
from alpha_system.report.screen_dry import build_screen_dry, write_dry_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="스크린·CECS 점수로 객관 6종 dry 리포트 생성 (target 자동 변경 없음)"
    )
    parser.add_argument(
        "--scores",
        type=Path,
        default=Path("alpha_portfolio/data/output/alpha_scores.csv"),
    )
    parser.add_argument(
        "--cecs",
        type=Path,
        default=Path("data/cecs_manual_scoring_template.csv"),
    )
    parser.add_argument(
        "--positions",
        type=Path,
        default=Path("data/positions.csv"),
        help="보유 여부 표시 전용; 순위·선정에는 사용하지 않음",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("alpha_system/config/alpha_system.yaml"),
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("data/target_portfolio.csv"),
        help="불변 검증 전용; 읽기·해시 비교만 수행",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("outputs/kr_alpha_screen_dry.csv"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("outputs/kr_alpha_screen_dry.md"),
    )
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=date.today(),
    )
    parser.add_argument(
        "--assumed-cutoff",
        type=float,
        default=None,
        help="config cutoff=null일 때 필수인 dry 가정값 (config에는 기록하지 않음)",
    )
    parser.add_argument(
        "--allow-draft",
        action="store_true",
        help="명시적 연구용: draft 행도 포함하되 CECS 완성 행만 계산",
    )
    args = parser.parse_args(argv)

    try:
        target_before = _sha256(args.target)
        result = build_screen_dry(
            cfg=load_config(args.config),
            scores_df=_read_csv(args.scores),
            cecs_df=_read_csv(args.cecs),
            positions_df=_read_csv(args.positions),
            as_of=args.as_of,
            assumed_cutoff=args.assumed_cutoff,
            allow_draft=args.allow_draft,
            data_dir=ROOT / "data",
        )
        write_dry_report(
            result,
            csv_path=args.output_csv,
            md_path=args.output_md,
        )
        target_after = _sha256(args.target)
        if target_before != target_after:
            raise RuntimeError(
                "안전 검증 실패: target_portfolio.csv가 dry 실행 중 변경되었습니다."
            )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        "DRY report: "
        f"policy=B final={result.final_count}/{result.template_count} "
        f"scored={result.scored_count} eligible={result.eligible_count} "
        f"selected={result.selected_count}"
    )
    print(f"CSV: {args.output_csv}")
    print(f"MD:  {args.output_md}")
    print("target_portfolio.csv: unchanged")
    if result.blocked_reason:
        print(f"BLOCKED: {result.blocked_reason}", file=sys.stderr)
        return 2
    return 0


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path, dtype=str)


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
