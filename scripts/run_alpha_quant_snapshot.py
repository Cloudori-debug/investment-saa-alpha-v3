#!/usr/bin/env python3
"""Alpha quant snapshot orchestrator — PyKRX/DART path → alpha_scores + provenance.

Does NOT write target_portfolio.csv. Review-only scoring refresh.

Examples:
  python scripts/run_alpha_quant_snapshot.py
  python scripts/run_alpha_quant_snapshot.py --collect --collect-scope liquid
  python scripts/run_alpha_quant_snapshot.py --skip-collect
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _input_hash(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for path in sorted(paths, key=lambda p: str(p).lower()):
        digest = _sha256_file(path) or "missing"
        h.update(f"{path.as_posix()}={digest}\n".encode("utf-8"))
    return h.hexdigest()


def run_quant_snapshot(
    *,
    root: Path,
    as_of: date,
    collect: bool,
    collect_scope: str | None,
    refresh_t3_pbr: bool,
) -> dict:
    from alpha_system.ui.services.proposal_freeze import assert_quant_refresh_allowed

    assert_quant_refresh_allowed(root)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    alpha_root = root / "alpha_portfolio"
    scores_path = alpha_root / "data" / "output" / "alpha_scores.csv"
    provenance_path = root / "data" / "alpha_quant_snapshot_provenance.json"

    inputs = [
        root / "data" / "fundamentals.csv",
        root / "data" / "prices.csv",
        root / "data" / "positions.csv",
        alpha_root / "data" / "raw" / "fundamentals.csv",
        alpha_root / "data" / "raw" / "price_snapshot.csv",
        root / "data" / "cecs_manual_scoring_template.csv",
    ]
    before_hash = _input_hash(inputs)

    # Ensure alpha_portfolio can import its local src package.
    if str(alpha_root) not in sys.path:
        sys.path.insert(0, str(alpha_root))

    from src.pipeline import run_pipeline  # type: ignore

    result = run_pipeline(
        root=alpha_root,
        as_of=as_of,
        collect_first=collect,
        collect_scope=collect_scope,
    )

    t3_detail = None
    if refresh_t3_pbr:
        try:
            from alpha_system.ui.services.t3_history_refresh import try_generate_t3_history

            t3_result = try_generate_t3_history(root=root)
            t3_detail = {
                "ok": bool(getattr(t3_result, "ok", False)),
                "detail": str(getattr(t3_result, "message", t3_result)),
            }
        except Exception as exc:  # network optional
            t3_detail = {"ok": False, "error": str(exc)}

    after_hash = _input_hash(inputs + [scores_path])
    provenance = {
        "run_id": run_id,
        "as_of": as_of.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collect": collect,
        "collect_scope": collect_scope,
        "input_hash_before": before_hash,
        "input_hash_after": after_hash,
        "scores_path": str(scores_path.relative_to(root)).replace("\\", "/"),
        "scores_sha256": _sha256_file(scores_path),
        "scored_rows": int(len(result.scores)),
        "gate_pass": int(result.scores["gate_pass"].sum()) if not result.scores.empty else 0,
        "candidates": int(len(result.candidates)),
        "target_portfolio_written": False,
        "t3_pbr_refresh": t3_detail,
        "sources": {
            "pykrx": "allowed",
            "dart": "allowed",
            "fastjusik": "forbidden",
        },
    }
    provenance_path.parent.mkdir(parents=True, exist_ok=True)
    provenance_path.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    try:
        from alpha_system.journal import append_record

        append_record(
            action_kind="QUANT_SNAPSHOT_OK",
            as_of=as_of,
            subject=run_id,
            rationale=f"alpha quant snapshot scored={provenance['scored_rows']}",
            payload=provenance,
        )
    except Exception:
        pass

    return provenance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alpha quant snapshot orchestrator")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--collect", action="store_true", help="PyKRX collect before score")
    parser.add_argument("--skip-collect", action="store_true")
    parser.add_argument(
        "--collect-scope",
        choices=["holdings", "liquid", "all"],
        default="liquid",
    )
    parser.add_argument("--refresh-t3-pbr", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    collect = bool(args.collect) and not bool(args.skip_collect)
    try:
        provenance = run_quant_snapshot(
            root=args.root.resolve(),
            as_of=as_of,
            collect=collect,
            collect_scope=args.collect_scope if collect else None,
            refresh_t3_pbr=bool(args.refresh_t3_pbr),
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"run_id     : {provenance['run_id']}")
    print(f"as_of      : {provenance['as_of']}")
    print(f"scored     : {provenance['scored_rows']}")
    print(f"gate_pass  : {provenance['gate_pass']}")
    print(f"scores     : {provenance['scores_path']}")
    print(f"provenance : data/alpha_quant_snapshot_provenance.json")
    print("target_portfolio.csv: NOT written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
