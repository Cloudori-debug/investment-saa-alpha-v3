from __future__ import annotations

import argparse
import sys
from datetime import date

from src.pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alpha Portfolio screener + exit review (P0)")
    parser.add_argument("--kr-alpha-weight", type=float, default=None, help="전체 포트 kr_alpha %% (상위 주입)")
    parser.add_argument("--as-of", type=str, default=None, help="기준일 YYYY-MM-DD")
    parser.add_argument("--collect", action="store_true", help="실행 전 PyKRX price_snapshot 수집")
    parser.add_argument(
        "--collect-scope",
        choices=["holdings", "liquid", "all"],
        default=None,
        help="PyKRX 수집 범위 (기본: config/collect.yaml)",
    )
    args = parser.parse_args(argv)

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()

    try:
        result = run_pipeline(
            kr_alpha_weight=args.kr_alpha_weight,
            as_of=as_of,
            collect_first=args.collect,
            collect_scope=args.collect_scope,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise

    print(f"Scored      : {len(result.scores)}")
    print(f"Candidates  : {len(result.candidates)}")
    print(f"Exit review : {len(result.exit_review)}")
    print(f"Gate pass   : {int(result.scores['gate_pass'].sum()) if not result.scores.empty else 0}")

    for _, row in result.candidates.head(8).iterrows():
        print(f"  [{row['grade']}] {row['ticker']} {row.get('name','')} score={row['composite_score']} tier={row['tier']}")

    for _, row in result.exit_review.iterrows():
        if row.get("exit_type") != "None":
            print(f"  EXIT [{row['action_suggested']}] {row['ticker']} - {row['exit_rule_id']} {row['exit_reason']}")

    if result.target_draft is not None and not result.target_draft.empty:
        total = result.target_draft["target_weight"].sum()
        print(f"Target draft: {len(result.target_draft)} rows, sum={total:.2f}%")
        for _, row in result.target_draft.head(6).iterrows():
            tier = str(row.get("tier", "")).replace("\u2014", "-")
            print(f"  [{row['matrix_action']}] {row['ticker']} {row['target_weight']:.2f}% tier={tier}")

    if result.replace_pairs is not None and not result.replace_pairs.empty:
        for _, row in result.replace_pairs.iterrows():
            print(f"  REPLACE {row['exit_ticker']} -> {row['candidate_ticker']} ({row['candidate_name']})")

    for w in result.matrix_warnings or []:
        print(f"  WARN matrix: {w}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
