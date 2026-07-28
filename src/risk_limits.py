from __future__ import annotations

from dataclasses import dataclass, field

from src.models import GapRow, PositionRow
from alpha_system.sizing.sector_map import concentration_bucket


@dataclass
class RiskViolation:
    code: str
    ticker: str | None
    detail: str
    severity: str  # WARN | HARD


@dataclass
class RiskReport:
    violations: list[RiskViolation] = field(default_factory=list)
    hard_stop_count: int = 0

    @property
    def has_hard_stop(self) -> bool:
        return self.hard_stop_count > 0


def check_risk_limits(
    positions: list[PositionRow],
    gap_rows: list[GapRow],
    policy: dict,
) -> RiskReport:
    limits = policy.get("risk_limits", {})
    exec_policy = policy.get("execution_policy", {})
    defensive_as_warn = exec_policy.get("cash_short_bond_hard_stop_action", "park") == "park"
    report = RiskReport()
    total = sum(p.current_value for p in positions)
    weights = {p.ticker: (p.current_value / total) * 100 for p in positions}
    pos_map = {p.ticker: p for p in positions}

    single_normal = float(limits.get("single_stock_normal_max", 8))
    single_hard = float(limits.get("single_stock_hard_max", 15))
    sector_max = float(limits.get("sector_max", 30))
    kr_alpha_max = float(limits.get("kr_alpha_max", 35))
    kr_alpha_min = float(limits.get("kr_alpha_min", 0))
    cash_min = float(limits.get("cash_short_bond_min", 25))

    for ticker, weight in weights.items():
        if ticker.upper() == "CASH":
            continue
        pos = pos_map.get(ticker)
        is_defensive = pos is not None and pos.asset_group == "cash_short_bond"
        if weight > single_hard:
            if is_defensive and defensive_as_warn:
                report.violations.append(
                    RiskViolation(
                        "DEFENSIVE_OVERWEIGHT",
                        ticker,
                        f"{weight:.1f}% > {single_hard}% (방어·현금성)",
                        "WARN",
                    )
                )
            else:
                report.violations.append(
                    RiskViolation("SINGLE_HARD_MAX", ticker, f"{weight:.1f}% > {single_hard}%", "HARD")
                )
                report.hard_stop_count += 1
        elif weight > single_normal:
            report.violations.append(
                RiskViolation("SINGLE_NORMAL_MAX", ticker, f"{weight:.1f}% > {single_normal}%", "WARN")
            )

    sector_totals: dict[str, float] = {}
    sector_groups: dict[str, set[str]] = {}
    for pos in positions:
        bucket = concentration_bucket(pos.sector) or (pos.sector or "")
        sector_totals[bucket] = sector_totals.get(bucket, 0.0) + weights[pos.ticker]
        sector_groups.setdefault(bucket, set()).add(pos.asset_group)
    for sector, weight in sector_totals.items():
        if not sector or weight <= sector_max:
            continue
        groups = sector_groups.get(sector, set())
        if defensive_as_warn and groups == {"cash_short_bond"}:
            report.violations.append(
                RiskViolation(
                    "DEFENSIVE_SECTOR_OVERWEIGHT",
                    None,
                    f"{sector} {weight:.1f}% > {sector_max}% (방어자산)",
                    "WARN",
                )
            )
        else:
            report.violations.append(
                RiskViolation("SECTOR_MAX", None, f"{sector} {weight:.1f}% > {sector_max}%", "HARD")
            )
            report.hard_stop_count += 1

    kr_alpha_w = sum(weights[p.ticker] for p in positions if p.asset_group == "kr_alpha")
    if kr_alpha_w > kr_alpha_max:
        report.violations.append(
            RiskViolation("KR_ALPHA_MAX", None, f"kr_alpha {kr_alpha_w:.1f}% > {kr_alpha_max}%", "HARD")
        )
        report.hard_stop_count += 1

    cash_w = sum(weights[p.ticker] for p in positions if p.asset_group == "cash_short_bond")
    if cash_w < cash_min:
        report.violations.append(
            RiskViolation("CASH_MIN", None, f"cash_short_bond {cash_w:.1f}% < {cash_min}%", "WARN")
        )

    for row in gap_rows:
        if not row.in_target and row.current_weight > 0:
            report.violations.append(
                RiskViolation("NOT_IN_TARGET", row.ticker, f"{row.name} not in target portfolio", "WARN")
            )

    return report
