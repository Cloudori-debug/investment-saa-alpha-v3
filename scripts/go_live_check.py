"""Personal go-live checks for SAA alpha v3 (Review-only ops).

Exit 0 = OK. Does not write target_portfolio or place orders.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "alpha_dashboard.py",
    "투자나침반.bat",
    "Start-Ops-Assistant.vbs",
    "run_ui_direct.bat",
    "docs/V3_CHARTER.md",
    "docs/V3_DEPLOY.md",
    "data/kr_alpha_exit_targets.yaml",
    "alpha_system/config/scoring.yaml",
    "data/hakedaka_integration.yaml",
]

LEDGER_WARN_IF_MISSING = [
    "data/positions.csv",
    "data/target_portfolio.csv",
    "data/prices.csv",
    "data/fundamentals.csv",
]


def _ok(msg: str) -> None:
    print(f"OK  {msg}")


def _fail(msg: str, errors: list[str]) -> None:
    print(f"FAIL {msg}")
    errors.append(msg)


def _warn(msg: str) -> None:
    print(f"WARN {msg}")


def check_files(errors: list[str]) -> None:
    for rel in REQUIRED_FILES:
        path = ROOT / rel
        if path.exists():
            _ok(f"file {rel}")
        else:
            _fail(f"missing {rel}", errors)
    for rel in LEDGER_WARN_IF_MISSING:
        if (ROOT / rel).exists():
            _ok(f"ledger {rel}")
        else:
            _warn(f"ledger missing (local ok if first run): {rel}")


def check_invariants(errors: list[str]) -> None:
    hak = (ROOT / "data" / "hakedaka_integration.yaml").read_text(encoding="utf-8")
    if re.search(r"proposal_mode\s*:\s*pure_qvm", hak):
        _ok("proposal_mode: pure_qvm")
    else:
        _fail("proposal_mode is not pure_qvm in hakedaka_integration.yaml", errors)

    scoring = (ROOT / "alpha_system" / "config" / "scoring.yaml").read_text(
        encoding="utf-8"
    )
    # Core factor weights block should not list score_m as a rollup factor.
    if re.search(r"(?m)^\s*score_m\s*:", scoring):
        _fail("scoring.yaml still defines score_m at top-level weight (Core)", errors)
    else:
        _ok("Core scoring.yaml has no score_m weight key")

    dash = (ROOT / "alpha_dashboard.py").read_text(encoding="utf-8")
    if "investment-saa-alpha-v3" in dash or "v3" in dash.lower():
        _ok("alpha_dashboard.py references v3")
    else:
        _warn("alpha_dashboard.py may still say v2 — check docstring")

    # Soft: FASTJUSIK must not appear as an enabled scraper import path in src/
    bad = []
    for py in (ROOT / "src").rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        if "fastjusik" in text.lower() and "forbidden" not in text.lower():
            # allow comments that say forbidden
            if re.search(r"(?i)import\s+.*fastjusik|from\s+.*fastjusik", text):
                bad.append(str(py.relative_to(ROOT)))
    if bad:
        _fail(f"FASTJUSIK import suspected: {bad[:5]}", errors)
    else:
        _ok("no FASTJUSIK imports under src/")


def check_pytest(errors: list[str]) -> None:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_ops_exit_signal.py",
        "tests/test_holdings_input.py",
        "tests/test_rotation_compass.py",
        "-q",
        "--tb=line",
    ]
    print("RUN", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode == 0:
        _ok("pytest go-live subset")
    else:
        _fail(f"pytest failed exit={proc.returncode}", errors)


def main() -> int:
    parser = argparse.ArgumentParser(description="SAA v3 personal go-live check")
    parser.add_argument(
        "--pytest",
        action="store_true",
        help="Also run critical pytest subset",
    )
    args = parser.parse_args()
    print(f"ROOT {ROOT}")
    errors: list[str] = []
    check_files(errors)
    check_invariants(errors)
    if args.pytest:
        check_pytest(errors)
    if errors:
        print(f"\nGO-LIVE CHECK FAILED ({len(errors)})")
        for e in errors:
            print(f" - {e}")
        return 1
    print("\nGO-LIVE CHECK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
