#!/usr/bin/env python3
"""alpha_portfolio target_draft → target_portfolio (고급/관리자 CLI).

Streamlit 승인 UI는 **알파 → Target 승인** 탭이 유일한 진입점입니다.
이 스크립트는 headless/자동화용이며, --apply 시에도 apply_proposed_target() →
write_operational_target() 경로만 사용합니다 (target_portfolio.csv 직접 write 금지).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.alpha.target_bridge import apply_proposed_target
from src.alpha.target_draft_bridge import build_proposal_from_draft, preview_target_draft


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="alpha_portfolio target_draft → target_portfolio 승인")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--draft", type=Path, default=None, help="target_draft.csv 경로")
    parser.add_argument("--apply", action="store_true", help="승인 반영 (백업 후 target_portfolio.csv 갱신)")
    parser.add_argument("--approved-by", default="cli")
    args = parser.parse_args(argv)

    try:
        if args.apply:
            proposal = build_proposal_from_draft(args.data_dir, args.output_dir, draft_path=args.draft)
            result = apply_proposed_target(
                proposal,
                args.data_dir / "target_portfolio.csv",
                backup_dir=args.data_dir / "backups",
                approved_by=args.approved_by,
                writer_module="scripts.apply_target_draft",
            )
            n = int((result.audit or {}).get("write_material_change_count") or 0)
            print(
                f"Applied: kr_alpha sum={proposal.kr_alpha_sum:.2f}% "
                f"changes={len(proposal.changes)} material={n} "
                f"writer={result.audit.get('writer_module')}"
            )        else:
            proposal = preview_target_draft(args.data_dir, args.output_dir, draft_path=args.draft)
            print(f"Preview: kr_alpha sum={proposal.kr_alpha_sum:.2f}% changes={len(proposal.changes)}")
            for w in proposal.warnings:
                print(f"  WARN: {w}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
