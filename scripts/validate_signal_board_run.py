"""Validate Alpha Signal Board v0.2 after full_pipeline run."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs"
DATA = ROOT / "data"

KEY_TICKERS = [
    "036530", "192400", "453340", "005440", "005830",
    "271560", "006040", "021240", "055550", "105560", "003490",
]


def main() -> int:
    fails: list[str] = []
    warns: list[str] = []

    board_path = OUTPUT / "alpha_signal_board.csv"
    if not board_path.exists():
        print("FAIL: alpha_signal_board.csv missing")
        return 1

    df = pd.read_csv(board_path, dtype=str)
    print("=== action_state counts ===")
    print(df["action_state"].value_counts().to_string())
    print()

    print("=== key tickers ===")
    sub = df[df["ticker"].isin(KEY_TICKERS)]
    for _, r in sub.sort_values("ticker").iterrows():
        print(
            f"{r['ticker']} {r['name']}: {r['action_state']} | "
            f"risk={r.get('risk_blocker', '')[:55]} | "
            f"exit_trigger={str(r.get('exit_trigger', ''))[:55]}"
        )
    print()

    exit_rows = df[df["action_state"].isin(["Exit", "Exit-review"])]
    print("=== Exit / Exit-review ===")
    print("none" if exit_rows.empty else exit_rows[["ticker", "name", "action_state", "risk_blocker"]].to_string(index=False))
    print()

    buy_allowed = df[df["action_state"] == "Buy-allowed"]
    if not buy_allowed.empty:
        fails.append(f"Buy-allowed present ({len(buy_allowed)} rows)")

    flow_col = df["flow_signal"].fillna("")
    stale_dist = flow_col.str.contains("STALE|DISTRIBUTION", case=False, regex=True)
    if not df[(df["action_state"] == "Buy-allowed") & stale_dist].empty:
        fails.append("flow STALE/DISTRIBUTION with Buy-allowed")

    if not df[(df["action_state"] == "Buy-allowed") & (df["sector"].str.lower() == "unknown")].empty:
        fails.append("sector unknown with Buy-allowed")

    rep = df[df.get("review_action", pd.Series(dtype=str)).fillna("") == "REPLACE_CANDIDATE"]
    bad_rep = rep[rep["action_state"] == "Exit"]
    if not bad_rep.empty:
        fails.append(f"REPLACE_CANDIDATE mapped to Exit: {list(bad_rep['ticker'])}")

    for tk in ["036530", "192400", "453340"]:
        row = df[df["ticker"] == tk]
        if row.empty:
            warns.append(f"{tk} not in signal board")
            continue
        st = row.iloc[0]["action_state"]
        if st == "Exit":
            fails.append(f"{tk} is Exit (expected Replace-review or Trim)")

    row_h = df[df["ticker"] == "005440"]
    if not row_h.empty and row_h.iloc[0]["action_state"] not in {"Trim", "Hold", "Replace-review"}:
        warns.append(f"005440 action_state={row_h.iloc[0]['action_state']} (expected Trim)")

    stale_n = stale_dist.sum()
    if stale_n == len(df):
        warns.append(f"all {len(df)} rows flow STALE")

    report_path = OUTPUT / "alpha_report.md"
    if report_path.exists():
        text = report_path.read_text(encoding="utf-8")
        print("=== alpha_report Action Summary ===")
        for line in text.splitlines():
            if line.startswith("## 오늘의 Alpha Action Summary") or (
                line.strip().startswith("- **") and any(
                    k in line for k in ("Buy-allowed", "Replace-review", "Exit-review", "Trim", "Watch")
                )
            ):
                print(line[:130])
        if "Replace-review" not in text and "Action Summary" in text:
            warns.append("alpha_report Action Summary missing Replace-review line")
        if "Exit" in text and "thesis" not in text.lower() and "Replace-review" in text:
            pass
    else:
        fails.append("alpha_report.md missing")

    acc_path = OUTPUT / "acceptance_report.json"
    if acc_path.exists():
        acc = json.loads(acc_path.read_text(encoding="utf-8"))
        print()
        print("acceptance overall:", acc.get("overall"))
    else:
        warns.append("acceptance_report.json missing")

    td_path = OUTPUT / "target_diff_review.csv"
    print("target_diff_review exists:", td_path.exists())
    if td_path.exists():
        print("target_diff rows:", len(pd.read_csv(td_path)))

    print()
    print("=== FAIL ===")
    print("NONE" if not fails else fails)
    print("=== WARN ===")
    print("NONE" if not warns else warns)

    if fails:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
