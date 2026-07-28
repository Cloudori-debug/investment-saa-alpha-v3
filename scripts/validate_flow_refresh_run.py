"""Validate investor flow auto-refresh after full_pipeline run."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"

FLOW_BUY_BLOCKERS = frozenset({"STALE", "DISTRIBUTION"})
FLOW_OUTPUT_FILES = (
    "flow_daily_timeseries.csv",
    "flow_streaks.csv",
    "flow_leaderboard_pension.csv",
    "flow_leaderboard_foreign.csv",
    "flow_leaderboard_cobuy.csv",
)
FLOW_DASHBOARD_SUMMARY = "flow_dashboard_summary.json"


@dataclass
class ValidationResult:
    target_fails: list[str] = field(default_factory=list)
    target_warns: list[str] = field(default_factory=list)
    flow_fails: list[str] = field(default_factory=list)
    flow_warns: list[str] = field(default_factory=list)
    info: dict[str, Any] = field(default_factory=dict)

    @property
    def fails(self) -> list[str]:
        return self.target_fails + self.flow_fails

    @property
    def warns(self) -> list[str]:
        return self.target_warns + self.flow_warns

    @property
    def ok(self) -> bool:
        return not self.fails


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def read_target_write_occurred(output_dir: Path) -> bool:
    for name in ("alpha_v2_summary.json", "daily_brief.json", "ai_export_bundle.json"):
        doc = _read_json(output_dir / name)
        if not doc:
            continue
        if "target_write_occurred" in doc:
            return bool(doc["target_write_occurred"])
        bundle = doc.get("bundle") or {}
        if "target_write_occurred" in bundle:
            return bool(bundle["target_write_occurred"])
    return False


def validate_target_integrity(
    data_dir: Path,
    output_dir: Path,
    *,
    expected_target_hash: str | None = None,
) -> ValidationResult:
    from src.alpha.target_portfolio_guard import evaluate_target_guard

    result = ValidationResult()
    guard = evaluate_target_guard(data_dir, output_dir)
    target_hash = str(guard.get("current_hash") or "")
    user_hash = str(guard.get("user_target_hash") or "")
    severity = str(guard.get("severity") or guard.get("target_portfolio_guard_severity") or "")
    changed_rows = int(guard.get("changed_rows") or 0)
    proposal_leak = int(guard.get("system_proposal_leak_count") or 0)
    target_write = read_target_write_occurred(output_dir)

    result.info.update({
        "target_hash": target_hash,
        "user_target_hash": user_hash,
        "target_guard_severity": severity,
        "changed_rows": changed_rows,
        "proposal_leak": proposal_leak,
        "target_write_occurred": target_write,
    })

    if severity != "PASS":
        result.target_fails.append(f"[target] target_guard != PASS (severity={severity})")

    if target_hash != user_hash:
        result.target_fails.append(
            "[target] target_hash != user_target_hash "
            f"({target_hash[:12]}... != {user_hash[:12]}...)"
        )

    if changed_rows != 0:
        result.target_fails.append(f"[target] changed_rows={changed_rows} (expected 0)")

    if proposal_leak != 0:
        result.target_fails.append(f"[target] proposal_leak={proposal_leak} (expected 0)")

    if target_write:
        result.target_fails.append("[target] target_write_occurred=true")

    if expected_target_hash and target_hash != expected_target_hash:
        result.target_fails.append(
            "[target] target hash mismatch vs --expected-target-hash "
            f"(current={target_hash[:12]}..., expected={expected_target_hash[:12]}...)"
        )

    return result


def validate_flow_refresh(
    data_dir: Path,
    output_dir: Path,
) -> ValidationResult:
    result = ValidationResult()

    board_path = output_dir / "alpha_signal_board.csv"
    if not board_path.exists():
        result.flow_fails.append("[flow] alpha_signal_board.csv missing")
        return result

    for fname in FLOW_OUTPUT_FILES:
        path = output_dir / fname
        if not path.exists():
            result.flow_fails.append(f"[flow] missing {fname}")
        elif path.stat().st_size == 0:
            result.flow_fails.append(f"[flow] empty {fname}")

    dash = _read_json(output_dir / FLOW_DASHBOARD_SUMMARY)
    if dash:
        result.info["fresh_count"] = dash.get("fresh_count", dash.get("fresh_flow_count"))
        result.info["stale_count"] = dash.get("stale_count", dash.get("stale_flow_count"))
        result.info["fresh_ratio"] = dash.get("fresh_ratio")
        result.info["pykrx_failed_tickers"] = dash.get("pykrx_failed_tickers") or []
        result.info["last_successful_flow_refresh"] = dash.get("last_successful_flow_refresh")
    else:
        result.flow_warns.append("[flow] flow_dashboard_summary.json missing")

    board = pd.read_csv(board_path, dtype=str)
    board["ticker"] = board["ticker"].str.zfill(6)
    board_tks = set(board["ticker"])
    result.info["board_ticker_count"] = len(board_tks)

    flows_path = data_dir / "investor_flows.csv"
    if not flows_path.exists():
        result.flow_fails.append("[flow] investor_flows.csv missing")
        return result

    flows = pd.read_csv(flows_path, dtype=str)
    flows["ticker"] = flows["ticker"].str.zfill(6)
    board_flows = flows[flows["ticker"].isin(board_tks)].copy()

    sig_dist = Counter(board_flows["flow_signal"].fillna("STALE"))
    result.info["board_flow_signal"] = dict(sig_dist)
    result.info["board_source"] = dict(Counter(board_flows["source"].fillna("")))

    gpt = _read_json(output_dir / "gpt_context.json")
    fr = (gpt.get("kr_alpha_meta") or {}).get("flow_refresh") or {}
    result.info["flow_refresh_meta"] = fr

    coverage = float(fr.get("flow_coverage_pct") or 0)
    failed = list(fr.get("failed_tickers") or [])
    stale_n = int(fr.get("stale_signal_count") or sig_dist.get("STALE", 0))
    result.info["flow_coverage_pct"] = coverage
    result.info["pykrx_failed_ticker_count"] = len(failed)

    if coverage < 80:
        result.flow_warns.append(f"[flow] flow_coverage_pct {coverage}% < 80%")
    if stale_n == len(board_tks) and board_tks:
        result.flow_warns.append(
            f"[flow] all {len(board_tks)} board tickers STALE — PyKRX fetch likely failed"
        )
    if not failed and stale_n > 0:
        result.flow_warns.append("[flow] failed_tickers empty but stale signals present")

    manual_rows = board_flows[board_flows["source"] == "manual_verified"]
    if not manual_rows.empty:
        overwritten = manual_rows[manual_rows["source"] != "manual_verified"]
        if not overwritten.empty:
            result.flow_fails.append("[flow] manual_verified rows overwritten")

    buy_allowed = board[board["action_state"] == "Buy-allowed"]
    for _, row in buy_allowed.iterrows():
        fs = str(row.get("flow_signal") or "STALE")
        if fs in FLOW_BUY_BLOCKERS:
            result.flow_fails.append(
                f"[flow] Buy-allowed with flow_signal={fs}: {row['ticker']}"
            )

    report_path = output_dir / "alpha_report.md"
    if report_path.exists():
        text = report_path.read_text(encoding="utf-8")
        if "## Investor Flow Refresh" not in text:
            result.flow_fails.append("[flow] alpha_report missing Flow Refresh section")
        else:
            for key in ("flow_coverage_pct", "stale_signal_count"):
                if key not in text:
                    result.flow_warns.append(f"[flow] alpha_report missing {key}")
    else:
        result.flow_fails.append("[flow] alpha_report.md missing")

    return result


def run_validation(
    data_dir: Path,
    output_dir: Path,
    *,
    expected_target_hash: str | None = None,
) -> ValidationResult:
    target = validate_target_integrity(
        data_dir, output_dir, expected_target_hash=expected_target_hash
    )
    flow = validate_flow_refresh(data_dir, output_dir)
    return ValidationResult(
        target_fails=target.target_fails,
        target_warns=target.target_warns,
        flow_fails=flow.flow_fails,
        flow_warns=flow.flow_warns,
        info={**target.info, **flow.info},
    )


def _print_section(title: str, payload: Any) -> None:
    print(f"\n=== {title} ===")
    if isinstance(payload, dict):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate flow refresh + target integrity")
    parser.add_argument("--data-dir", type=Path, default=DATA)
    parser.add_argument("--output-dir", type=Path, default=OUT)
    parser.add_argument(
        "--expected-target-hash",
        default=None,
        help="Optional: fail if current target hash differs from this value",
    )
    args = parser.parse_args(argv)

    result = run_validation(
        args.data_dir,
        args.output_dir,
        expected_target_hash=args.expected_target_hash,
    )

    _print_section("target integrity", {
        k: result.info.get(k)
        for k in (
            "target_hash",
            "user_target_hash",
            "target_guard_severity",
            "changed_rows",
            "proposal_leak",
            "target_write_occurred",
        )
    })
    if result.info.get("board_flow_signal") is not None:
        _print_section("board flow_signal", result.info.get("board_flow_signal"))
        _print_section("board source", result.info.get("board_source"))
    if result.info.get("flow_refresh_meta"):
        _print_section("flow_refresh meta", result.info.get("flow_refresh_meta"))
    if result.info.get("fresh_count") is not None:
        _print_section("flow dashboard coverage", {
            "fresh_count": result.info.get("fresh_count"),
            "stale_count": result.info.get("stale_count"),
            "fresh_ratio": result.info.get("fresh_ratio"),
            "pykrx_failed_ticker_count": result.info.get("pykrx_failed_ticker_count"),
            "last_successful_flow_refresh": result.info.get("last_successful_flow_refresh"),
        })

    print("\n=== TARGET FAIL ===")
    print("NONE" if not result.target_fails else result.target_fails)
    print("=== FLOW FAIL ===")
    print("NONE" if not result.flow_fails else result.flow_fails)
    print("=== WARN ===")
    print("NONE" if not result.warns else result.warns)

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
