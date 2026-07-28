#!/usr/bin/env python3
"""시나리오 B 전체 target 반영 (kr_alpha + income_alt) — manual_admin_override CLI.

기존 approval_bridge / Target 승인 UI는 kr_alpha-only (`merge_target_draft`).
그룹 간 비중 이동(income_alt)은 이 관리자 스크립트로만 반영한다.

기본: preview(diff만, write 없음).
실제 write: 원장이 명시적으로
  python scripts/apply_kr_alpha_hybrid_scenario_b.py --apply --approved-by <이름>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data_loader import load_target_portfolio
from src.models import TargetRow

# Scenario B — docs/KR_ALPHA_HYBRID_TRANSITION_RESULT.md §4
KR_ALPHA_KEEP: dict[str, tuple[float, str, str, str]] = {
    # ticker: (target_weight, name, sector, role)
    "005830": (3.50, "DB손해보험", "insurance", "shareholder_return"),
    "005440": (2.50, "현대지에프홀딩스", "holding", "value_rerating"),
}
INCOME_ALT_SET: dict[str, float] = {
    "161510": 11.79,
    "279530": 7.08,
}
INCOME_ALT_NEW: dict[str, tuple[str, str, str]] = {
    "279530": ("KODEX 고배당주", "income_equity", "dividend_kr_kodex"),
}
REASON = "KR_ALPHA_HYBRID_TRANSITION scenario B"


def _z(ticker: str) -> str:
    t = str(ticker).strip()
    return t.zfill(6) if t.isdigit() else t


def _scale_bands(old_tw: float, old_min: float, old_max: float, new_tw: float) -> tuple[float, float]:
    if old_tw <= 0:
        return round(new_tw * 0.7, 2), round(new_tw * 1.35, 2)
    mn = round(new_tw * (old_min / old_tw), 2)
    mx = round(new_tw * (old_max / old_tw), 2)
    if mn > new_tw:
        mn = round(min(new_tw, new_tw * 0.85), 2)
    if mx < new_tw:
        mx = round(max(new_tw, new_tw * 1.15), 2)
    return mn, mx


def build_scenario_b_rows(current: list[TargetRow]) -> list[TargetRow]:
    """현행 target에서 시나리오 B를 적용한 전체 TargetRow 리스트."""
    by_ticker = {_z(r.ticker): r for r in current}
    income_template = next((r for r in current if _z(r.ticker) == "161510"), None)
    if income_template is None:
        income_template = next((r for r in current if r.asset_group == "income_alt"), None)

    out: list[TargetRow] = []

    for row in current:
        t = _z(row.ticker)
        if row.asset_group == "kr_alpha":
            continue  # rebuild keepers below
        if t in INCOME_ALT_SET:
            new_tw = INCOME_ALT_SET[t]
            mn, mx = _scale_bands(row.target_weight, row.min_weight, row.max_weight, new_tw)
            out.append(
                row.model_copy(
                    update={
                        "ticker": t,
                        "target_weight": new_tw,
                        "min_weight": mn,
                        "max_weight": mx,
                    }
                )
            )
            continue
        out.append(row.model_copy(deep=True))

    # New income_alt ticker (279530) if missing from current
    for t, new_tw in INCOME_ALT_SET.items():
        if any(_z(r.ticker) == t for r in out):
            continue
        name, sector, role = INCOME_ALT_NEW[t]
        if income_template is not None:
            mn, mx = _scale_bands(
                income_template.target_weight,
                income_template.min_weight,
                income_template.max_weight,
                new_tw,
            )
        else:
            mn, mx = _scale_bands(3.59, 2.55, 4.73, new_tw)
        out.append(
            TargetRow(
                ticker=t,
                name=name,
                asset_group="income_alt",
                sector=sector,
                role=role,
                target_weight=new_tw,
                min_weight=mn,
                max_weight=mx,
            )
        )

    for t, (tw, name, sector, role) in KR_ALPHA_KEEP.items():
        old = by_ticker.get(t)
        if old is not None:
            mn, mx = _scale_bands(old.target_weight, old.min_weight, old.max_weight, tw)
            out.append(
                old.model_copy(
                    update={
                        "ticker": t,
                        "name": old.name or name,
                        "sector": old.sector or sector,
                        "role": old.role or role,
                        "target_weight": tw,
                        "min_weight": mn,
                        "max_weight": mx,
                    }
                )
            )
        else:
            mn, mx = _scale_bands(tw, tw * 0.5, tw * 1.25, tw)
            out.append(
                TargetRow(
                    ticker=t,
                    name=name,
                    asset_group="kr_alpha",
                    sector=sector,
                    role=role,
                    target_weight=tw,
                    min_weight=mn,
                    max_weight=mx,
                )
            )

    # Stable-ish order: non-kr groups as before, then kr_alpha keepers
    group_order = [
        "cash_short_bond",
        "global_beta",
        "fx_dollar",
        "hedge_alt",
        "income_alt",
        "domestic_beta",
        "kr_alpha",
    ]
    rank = {g: i for i, g in enumerate(group_order)}
    out.sort(key=lambda r: (rank.get(r.asset_group, 99), _z(r.ticker)))
    return out


def _group_sums(rows: list[TargetRow]) -> dict[str, float]:
    sums: dict[str, float] = {}
    for r in rows:
        sums[r.asset_group] = sums.get(r.asset_group, 0.0) + float(r.target_weight)
    return sums


def _diff_lines(before: list[TargetRow], after: list[TargetRow]) -> list[str]:
    bmap = {_z(r.ticker): r for r in before}
    amap = {_z(r.ticker): r for r in after}
    lines: list[str] = []
    all_t = sorted(set(bmap) | set(amap))
    for t in all_t:
        b = bmap.get(t)
        a = amap.get(t)
        bw = float(b.target_weight) if b else None
        aw = float(a.target_weight) if a else None
        if bw is None and aw is not None:
            lines.append(f"  + {t} {a.name} [{a.asset_group}] → {aw:.2f}%")
        elif aw is None and bw is not None:
            lines.append(f"  - {t} {b.name} [{b.asset_group}] {bw:.2f}% → (removed)")
        elif bw is not None and aw is not None and abs(bw - aw) >= 0.005:
            lines.append(
                f"  ~ {t} {a.name} [{a.asset_group}] {bw:.2f}% → {aw:.2f}% (Δ{aw - bw:+.2f})"
            )
    return lines


def validate_scenario_b(rows: list[TargetRow]) -> list[str]:
    errs: list[str] = []
    sums = _group_sums(rows)
    total = sum(sums.values())
    if abs(total - 100.0) > 0.05:
        errs.append(f"total={total:.4f} (want 100)")
    if abs(sums.get("kr_alpha", 0.0) - 6.0) > 0.05:
        errs.append(f"kr_alpha={sums.get('kr_alpha', 0):.4f} (want 6.00)")
    if abs(sums.get("income_alt", 0.0) - 29.64) > 0.05:
        errs.append(f"income_alt={sums.get('income_alt', 0):.4f} (want 29.64)")
    if sums.get("domestic_beta", 0.0) > 0.05:
        errs.append(f"domestic_beta={sums.get('domestic_beta', 0):.4f} (want 0)")
    by_t = {_z(r.ticker): r for r in rows}
    for t, tw in [("161510", 11.79), ("279530", 7.08), ("005830", 3.50), ("005440", 2.50)]:
        r = by_t.get(t)
        if r is None:
            errs.append(f"missing {t}")
        elif abs(float(r.target_weight) - tw) > 0.005:
            errs.append(f"{t}={r.target_weight} (want {tw})")
    kr_tickers = {_z(r.ticker) for r in rows if r.asset_group == "kr_alpha"}
    if kr_tickers != {"005830", "005440"}:
        errs.append(f"kr_alpha tickers={sorted(kr_tickers)} (want 005830,005440 only)")
    return errs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="시나리오 B 전체 target (kr_alpha+income_alt) — manual_admin_override"
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument(
        "--apply",
        action="store_true",
        help="실제 write (원장 명시 실행 시에만). --approved-by 필수.",
    )
    parser.add_argument(
        "--approved-by",
        default="",
        help="승인자 식별자. --apply 시 필수(빈 값/cli 단독 하드코딩 게이트 우회 금지).",
    )
    args = parser.parse_args(argv)

    current = load_target_portfolio(args.data_dir / "target_portfolio.csv")
    proposed = build_scenario_b_rows(current)
    errs = validate_scenario_b(proposed)
    sums_b = _group_sums(current)
    sums_a = _group_sums(proposed)

    print("=== Scenario B preview ===")
    print("Group sums (before → after):")
    for g in sorted(set(sums_b) | set(sums_a)):
        print(f"  {g}: {sums_b.get(g, 0):.2f} → {sums_a.get(g, 0):.2f}")
    print(f"  TOTAL: {sum(sums_b.values()):.2f} → {sum(sums_a.values()):.2f}")
    print("Ticker diffs:")
    for line in _diff_lines(current, proposed):
        print(line)
    if errs:
        print("VALIDATION ERRORS:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print("Validation: OK (kr_alpha=6.00, income_alt=29.64, domestic_beta=0, total=100)")

    if not args.apply:
        print("Mode: preview only (no write). To apply:")
        print(
            "  python scripts/apply_kr_alpha_hybrid_scenario_b.py "
            "--apply --approved-by <원장이름>"
        )
        return 0

    approved = (args.approved_by or "").strip()
    if not approved or approved.lower() in {"cli", "true", "1", "yes"}:
        print(
            "ERROR: --apply requires a real --approved-by <name> "
            "(not empty / not cli). Refusing to set approved_by_user=True.",
            file=sys.stderr,
        )
        return 2

    from src.alpha.target_write_audit import write_operational_target

    result = write_operational_target(
        args.data_dir,
        proposed,
        source="manual_admin_override",
        reason=f"{REASON}; approved_by={approved}",
        approved_by_user=True,
        writer_module="scripts.apply_kr_alpha_hybrid_scenario_b",
        output_dir=args.output_dir,
        backup=True,
    )
    if result.blocked or not result.success:
        print(f"BLOCKED: {result.audit.get('target_write_reason')}", file=sys.stderr)
        return 3
    n = int((result.audit or {}).get("write_material_change_count") or 0)
    print(
        f"Applied via manual_admin_override: material={n} "
        f"writer={result.audit.get('writer_module')} "
        f"approved_by={approved}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
