"""CLI: emit a one-screen status report from current config + optional inputs."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from alpha_system.entry import TriggerSnapshot, evaluate_entry
from alpha_system.loader import load_config
from alpha_system.report import StatusReportInput, write_status_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="alpha_system status report")
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs/ALPHA_SYSTEM_STATUS_REPORT.md"),
    )
    args = parser.parse_args(argv)

    cfg = load_config()
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    entry = evaluate_entry(
        cfg,
        TriggerSnapshot(as_of=as_of, system_started=True),
        journal=False,
    )
    path = write_status_report(
        cfg,
        StatusReportInput(as_of=as_of, entry=entry, scores=[], fills=[]),
        args.out,
    )
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
