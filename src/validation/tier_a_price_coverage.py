from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from src.data_loader import load_positions, load_target_portfolio
from src.data_refresh.external_market import business_days_between
from src.data_refresh.price_store import normalize_ticker
from src.data_refresh.prices_refresh import _load_alpha_top_tickers

GateStatus = Literal["pass", "warn", "fail"]
AlphaPriceAction = Literal["ALPHA_OK", "ALPHA_REVIEW_ONLY", "ALPHA_DISABLED"]

DEFAULT_TIER_A_GATE = {
    "held_coverage_min": 1.0,
    "target_coverage_min": 1.0,
    "trade_actions_coverage_min": 1.0,
    "alpha_top30_coverage_min": 0.80,
    "alpha_top50_coverage_min": 0.70,
    "alpha_top30_fail_below": 0.60,
    "max_stale_business_days_core": 1,
    "max_stale_business_days_alpha": 2,
    "legacy_stale_hard_fail_weight_pct": 3.0,
}

DEFAULT_TIER_B_GATE = {
    "pass_within_business_days": 5,
    "warn_within_business_days": 10,
    "research_stale_business_days": 20,
}


def load_tier_a_price_gate_config(data_dir: Path) -> dict[str, Any]:
    from src.config import load_yaml

    policy_path = data_dir / "portfolio_policy.yaml"
    if not policy_path.exists():
        return dict(DEFAULT_TIER_A_GATE)
    policy = load_yaml(policy_path)
    raw = policy.get("tier_a_price_gate") or {}
    cfg = dict(DEFAULT_TIER_A_GATE)
    cfg.update({k: raw[k] for k in DEFAULT_TIER_A_GATE if k in raw})
    return cfg


def load_tier_b_gate_config(data_dir: Path) -> dict[str, Any]:
    from src.config import load_yaml

    policy_path = data_dir / "portfolio_policy.yaml"
    if not policy_path.exists():
        return dict(DEFAULT_TIER_B_GATE)
    policy = load_yaml(policy_path)
    raw = policy.get("tier_b_refresh") or {}
    cfg = dict(DEFAULT_TIER_B_GATE)
    for key in ("pass_within_business_days", "warn_within_business_days", "research_stale_business_days"):
        if key in raw:
            cfg[key] = int(raw[key])
    if "interval_business_days" in raw and "pass_within_business_days" not in (policy.get("tier_b_refresh") or {}):
        cfg["pass_within_business_days"] = int(raw["interval_business_days"])
    return cfg


def _needs_price(ticker: str) -> bool:
    t = normalize_ticker(ticker)
    return bool(t) and t.upper() not in {"CASH", "PORTFOLIO"}


def _position_tickers(data_dir: Path) -> set[str]:
    path = data_dir / "positions.csv"
    if not path.exists():
        return set()
    return {
        normalize_ticker(p.ticker)
        for p in load_positions(path)
        if _needs_price(p.ticker)
    }


def _position_weights(data_dir: Path) -> dict[str, float]:
    path = data_dir / "positions.csv"
    if not path.exists():
        return {}
    out: dict[str, float] = {}
    for p in load_positions(path):
        tk = normalize_ticker(p.ticker)
        if not _needs_price(tk):
            continue
        try:
            out[tk] = float(getattr(p, "current_weight", 0) or 0)
        except (TypeError, ValueError):
            out[tk] = 0.0
    return out


def _target_tickers(data_dir: Path) -> set[str]:
    user_path = data_dir / "user_target_portfolio.csv"
    path = user_path if user_path.exists() else (data_dir / "target_portfolio.csv")
    if not path.exists():
        return set()
    return {
        normalize_ticker(t.ticker)
        for t in load_target_portfolio(path)
        if _needs_price(t.ticker) and float(t.target_weight or 0) > 0
    }


def _user_target_tickers(data_dir: Path) -> set[str]:
    path = data_dir / "user_target_portfolio.csv"
    if not path.exists():
        return set()
    return {
        normalize_ticker(t.ticker)
        for t in load_target_portfolio(path)
        if _needs_price(t.ticker) and float(t.target_weight or 0) > 0
    }


def _executable_trade_action_tickers(output_dir: Path | None) -> set[str]:
    path = (output_dir / "trade_actions.csv") if output_dir else None
    if path is None or not path.exists():
        return set()
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if df.empty or "ticker" not in df.columns:
        return set()
    executable_actions = {"Buy-allowed", "Add", "Trim", "Replace", "Park"}
    out: set[str] = set()
    for row in df.to_dict(orient="records"):
        action = str(row.get("action") or "")
        if action not in executable_actions:
            continue
        try:
            size = float(row.get("allowed_size_pct") or 0)
        except (TypeError, ValueError):
            size = 0.0
        if size <= 0:
            continue
        tk = normalize_ticker(str(row.get("ticker") or ""))
        if _needs_price(tk):
            out.add(tk)
    return out


def _latest_price_dates(data_dir: Path, as_of: str) -> dict[str, str]:
    path = data_dir / "prices.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if df.empty or "ticker" not in df.columns or "date" not in df.columns:
        return {}
    df["ticker"] = df["ticker"].map(normalize_ticker)
    df = df.sort_values(["ticker", "date"], na_position="last")

    as_of_date = as_of[:10]
    pit = df[df["date"] <= as_of_date].drop_duplicates(subset=["ticker"], keep="last")
    out = {str(r["ticker"]): str(r["date"]) for r in pit.to_dict(orient="records")}

    # Snapshot refresh may stamp rows after market.as_of — still required for live ops coverage.
    snapshot = df.drop_duplicates(subset=["ticker"], keep="last")
    for row in snapshot.to_dict(orient="records"):
        ticker = str(row["ticker"])
        if ticker not in out:
            out[ticker] = str(row["date"])
    return out


def _coverage_ratio(tickers: set[str], price_dates: dict[str, str]) -> tuple[float, list[str], list[str]]:
    if not tickers:
        return 1.0, [], []
    covered = {t for t in tickers if t in price_dates}
    missing = sorted(tickers - covered)
    return len(covered) / len(tickers), missing, sorted(covered)


def _stale_tickers(
    tickers: set[str],
    price_dates: dict[str, str],
    as_of: str,
    max_days: int,
) -> list[dict[str, Any]]:
    stale: list[dict[str, Any]] = []
    for t in sorted(tickers):
        d = price_dates.get(t)
        if not d:
            continue
        age = business_days_between(d, as_of[:10])
        if age > max_days:
            stale.append({"ticker": t, "last_price_date": d, "price_age_business_days": age})
    return stale


def _attach_weights(rows: list[dict[str, Any]], weights: dict[str, float]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in rows:
        tk = str(item.get("ticker") or "")
        merged = dict(item)
        merged["current_weight_pct"] = round(float(weights.get(tk, 0.0)), 3)
        out.append(merged)
    return out


@dataclass
class CorePriceGateResult:
    status: GateStatus
    held_coverage: float
    target_coverage: float
    trade_actions_coverage: float
    missing_held: list[str] = field(default_factory=list)
    missing_target: list[str] = field(default_factory=list)
    missing_trade_actions: list[str] = field(default_factory=list)
    stale_core: list[dict[str, Any]] = field(default_factory=list)
    stale_core_critical: list[dict[str, Any]] = field(default_factory=list)
    stale_legacy_holding: list[dict[str, Any]] = field(default_factory=list)
    stale_executable_actions: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "positions_coverage": round(self.held_coverage, 4),
            "target_coverage": round(self.target_coverage, 4),
            "trade_actions_coverage": round(self.trade_actions_coverage, 4),
            "missing": {
                "held": self.missing_held,
                "target": self.missing_target,
                "trade_actions": self.missing_trade_actions,
            },
            "stale_core": self.stale_core,
            "stale_core_critical": self.stale_core_critical,
            "stale_legacy_holding": self.stale_legacy_holding,
            "stale_executable_actions": self.stale_executable_actions,
            "reasons": self.reasons,
        }


@dataclass
class AlphaPriceGateResult:
    status: GateStatus
    action: AlphaPriceAction
    alpha_top30_coverage: float
    alpha_top50_coverage: float
    missing_alpha_top30: list[str] = field(default_factory=list)
    missing_alpha_top50: list[str] = field(default_factory=list)
    stale_alpha_top30: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "action": self.action,
            "alpha_top30_coverage": round(self.alpha_top30_coverage, 4),
            "alpha_top50_coverage": round(self.alpha_top50_coverage, 4),
            "missing_alpha_top30": self.missing_alpha_top30,
            "missing_alpha_top50": self.missing_alpha_top50,
            "stale_alpha_top30": self.stale_alpha_top30,
            "reasons": self.reasons,
        }


@dataclass
class TierAPriceCoverageResult:
    as_of: str
    core: CorePriceGateResult
    alpha: AlphaPriceGateResult
    held_tickers: list[str] = field(default_factory=list)
    target_tickers: list[str] = field(default_factory=list)
    trade_action_tickers: list[str] = field(default_factory=list)
    alpha_top30_tickers: list[str] = field(default_factory=list)
    alpha_top50_tickers: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def gate_status(self) -> GateStatus:
        if self.core.status == "fail":
            return "fail"
        if self.alpha.status == "fail" or self.core.status == "warn" or self.alpha.status == "warn":
            return "warn" if self.core.status != "fail" else "fail"
        return "pass"

    @property
    def held_coverage(self) -> float:
        return self.core.held_coverage

    @property
    def target_coverage(self) -> float:
        return self.core.target_coverage

    @property
    def trade_actions_coverage(self) -> float:
        return self.core.trade_actions_coverage

    @property
    def alpha_top30_coverage(self) -> float:
        return self.alpha.alpha_top30_coverage

    @property
    def alpha_top50_coverage(self) -> float:
        return self.alpha.alpha_top50_coverage

    @property
    def missing_trade_actions(self) -> list[str]:
        return self.core.missing_trade_actions

    @property
    def gate_reasons(self) -> list[str]:
        return self.core.reasons + self.alpha.reasons

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.1",
            "as_of": self.as_of,
            "gate_status": self.gate_status,
            "core_price_gate": self.core.to_dict(),
            "alpha_price_gate": self.alpha.to_dict(),
            "counts": {
                "held": len(self.held_tickers),
                "target": len(self.target_tickers),
                "trade_actions": len(self.trade_action_tickers),
                "alpha_top30": len(self.alpha_top30_tickers),
                "alpha_top50": len(self.alpha_top50_tickers),
            },
            "thresholds": self.config,
            "restricted_modes": _restricted_modes_from_result(self),
        }


def _restricted_modes_from_result(result: TierAPriceCoverageResult) -> list[str]:
    modes: list[str] = []
    if result.core.status == "fail":
        modes.append("CORE_EXECUTION_BLOCKED")
    if result.alpha.action == "ALPHA_DISABLED" or result.alpha.status == "fail":
        modes.append("ALPHA_DISABLED")
    elif result.alpha.action == "ALPHA_REVIEW_ONLY" or result.alpha.status == "warn":
        modes.append("ALPHA_REVIEW_ONLY")
    return modes


def _evaluate_core_gate(
    cfg: dict[str, Any],
    as_of: str,
    held: set[str],
    held_weights: dict[str, float],
    target: set[str],
    user_target: set[str],
    trade_actions: set[str],
    price_dates: dict[str, str],
) -> CorePriceGateResult:
    held_cov, missing_held, _ = _coverage_ratio(held, price_dates)
    target_cov, missing_target, _ = _coverage_ratio(target, price_dates)
    trade_cov, missing_trade, _ = _coverage_ratio(trade_actions, price_dates)
    core_critical = set(target) | set(trade_actions)
    alpha_holding = set(held)
    legacy_holding = alpha_holding - set(target)
    if user_target:
        legacy_holding |= alpha_holding - set(user_target)

    stale_core_critical = _stale_tickers(
        core_critical,
        price_dates,
        as_of,
        int(cfg["max_stale_business_days_core"]),
    )
    stale_executable = _stale_tickers(
        set(trade_actions),
        price_dates,
        as_of,
        int(cfg["max_stale_business_days_core"]),
    )
    stale_legacy = _stale_tickers(
        legacy_holding,
        price_dates,
        as_of,
        int(cfg["max_stale_business_days_core"]),
    )
    stale_legacy = _attach_weights(stale_legacy, held_weights)
    stale_heavy_legacy = [
        r for r in stale_legacy
        if float(r.get("current_weight_pct") or 0) >= float(cfg.get("legacy_stale_hard_fail_weight_pct", 3.0))
    ]
    stale_core = _attach_weights(stale_core_critical + stale_legacy, held_weights)

    reasons: list[str] = []
    status: GateStatus = "pass"

    if trade_actions and trade_cov < float(cfg["trade_actions_coverage_min"]):
        status = "fail"
        reasons.append(f"trade_actions 시세 누락 {len(missing_trade)}/{len(trade_actions)}")
    if held_cov < float(cfg["held_coverage_min"]):
        status = "fail"
        reasons.append(f"보유 시세 커버리지 {held_cov:.0%} < {cfg['held_coverage_min']:.0%}")
    if target_cov < float(cfg["target_coverage_min"]):
        status = "fail"
        reasons.append(f"target 시세 커버리지 {target_cov:.0%} < {cfg['target_coverage_min']:.0%}")
    if stale_core_critical:
        status = "fail"
        reasons.append(f"core_critical stale {len(stale_core_critical)}종 (>{cfg['max_stale_business_days_core']}영업일)")
    if stale_executable:
        status = "fail"
        reasons.append(f"executable_action stale {len(stale_executable)}종")
    if stale_heavy_legacy:
        status = "fail"
        reasons.append(
            f"legacy stale >= {cfg.get('legacy_stale_hard_fail_weight_pct', 3.0)}% "
            f"{len(stale_heavy_legacy)}종"
        )
    if stale_legacy and status == "pass":
        status = "warn"
        reasons.append(f"legacy_holding stale {len(stale_legacy)}종 (review-only)")

    if status == "pass" and not reasons:
        reasons.append("core price PASS")

    return CorePriceGateResult(
        status=status,
        held_coverage=held_cov,
        target_coverage=target_cov,
        trade_actions_coverage=trade_cov,
        missing_held=missing_held,
        missing_target=missing_target,
        missing_trade_actions=missing_trade,
        stale_core=stale_core,
        stale_core_critical=stale_core_critical,
        stale_legacy_holding=stale_legacy,
        stale_executable_actions=stale_executable,
        reasons=reasons,
    )


def _evaluate_alpha_gate(
    cfg: dict[str, Any],
    as_of: str,
    alpha_top30: set[str],
    alpha_top50: set[str],
    price_dates: dict[str, str],
) -> AlphaPriceGateResult:
    top30_cov, missing_top30, _ = _coverage_ratio(alpha_top30, price_dates)
    top50_cov, missing_top50, _ = _coverage_ratio(alpha_top50, price_dates)
    stale_alpha = _stale_tickers(
        alpha_top30,
        price_dates,
        as_of,
        int(cfg["max_stale_business_days_alpha"]),
    )

    reasons: list[str] = []
    status: GateStatus = "pass"
    action: AlphaPriceAction = "ALPHA_OK"

    fail_below = float(cfg["alpha_top30_fail_below"])
    warn_below = float(cfg["alpha_top30_coverage_min"])

    if alpha_top30 and top30_cov < fail_below:
        status = "fail"
        action = "ALPHA_DISABLED"
        reasons.append(f"Alpha top30 커버리지 {top30_cov:.0%} < {fail_below:.0%}")
    elif alpha_top30 and top30_cov < warn_below:
        status = "warn"
        action = "ALPHA_REVIEW_ONLY"
        reasons.append(f"Alpha top30 커버리지 {top30_cov:.0%} < {warn_below:.0%}")

    if alpha_top50 and top50_cov < float(cfg["alpha_top50_coverage_min"]):
        if status == "pass":
            status = "warn"
        if action == "ALPHA_OK":
            action = "ALPHA_REVIEW_ONLY"
        reasons.append(f"Alpha top50 커버리지 {top50_cov:.0%} < {cfg['alpha_top50_coverage_min']:.0%}")

    if stale_alpha:
        if status == "pass":
            status = "warn"
        if action == "ALPHA_OK":
            action = "ALPHA_REVIEW_ONLY"
        reasons.append(f"Alpha top30 stale {len(stale_alpha)}종 (>{cfg['max_stale_business_days_alpha']}영업일)")

    if status == "pass" and not reasons:
        reasons.append("alpha price PASS")

    return AlphaPriceGateResult(
        status=status,
        action=action,
        alpha_top30_coverage=top30_cov,
        alpha_top50_coverage=top50_cov,
        missing_alpha_top30=missing_top30,
        missing_alpha_top50=missing_top50,
        stale_alpha_top30=stale_alpha,
        reasons=reasons,
    )


def evaluate_tier_a_price_coverage(
    data_dir: Path,
    output_dir: Path | None,
    as_of: str,
    *,
    config: dict[str, Any] | None = None,
) -> TierAPriceCoverageResult:
    cfg = config or load_tier_a_price_gate_config(data_dir)
    price_dates = _latest_price_dates(data_dir, as_of)

    held = _position_tickers(data_dir)
    held_weights = _position_weights(data_dir)
    target = _target_tickers(data_dir)
    user_target = _user_target_tickers(data_dir)
    trade_actions = _executable_trade_action_tickers(output_dir)
    alpha_top30 = set(_load_alpha_top_tickers(output_dir, top_n=30))
    alpha_top50 = set(_load_alpha_top_tickers(output_dir, top_n=50))

    core = _evaluate_core_gate(cfg, as_of, held, held_weights, target, user_target, trade_actions, price_dates)
    alpha = _evaluate_alpha_gate(cfg, as_of, alpha_top30, alpha_top50, price_dates)

    return TierAPriceCoverageResult(
        as_of=as_of,
        core=core,
        alpha=alpha,
        held_tickers=sorted(held),
        target_tickers=sorted(target),
        trade_action_tickers=sorted(trade_actions),
        alpha_top30_tickers=sorted(alpha_top30),
        alpha_top50_tickers=sorted(alpha_top50),
        config=cfg,
    )


def evaluate_tier_b_refresh_health(data_dir: Path, as_of: str) -> tuple[GateStatus, str, dict[str, Any]]:
    from src.data_refresh.tier_b_refresh import load_tier_b_state

    cfg = load_tier_b_gate_config(data_dir)
    state = load_tier_b_state(data_dir)
    last = str(state.get("last_run_date", "")).strip()
    if not last:
        return "warn", "Tier B bulk 미실행 — liquid pool 수동/주간 갱신 권장", {"last_run_date": None, "age_business_days": None}

    age = business_days_between(last, as_of[:10])
    detail = {
        "last_run_date": last,
        "age_business_days": age,
        "prices_count": state.get("prices_count"),
        "scope": state.get("scope", "liquid"),
    }
    pass_days = int(cfg["pass_within_business_days"])
    warn_days = int(cfg["warn_within_business_days"])
    research_days = int(cfg["research_stale_business_days"])

    if age <= pass_days:
        return "pass", f"Tier B 최근 실행 {last} ({age}영업일 전)", detail
    if age <= warn_days:
        return "warn", f"Tier B {age}영업일 경과 (>{pass_days}) — 주간 bulk 권장", detail
    if age <= research_days:
        return "warn", f"Tier B {age}영업일 미실행 — Alpha research pool 품질 하락 가능", detail
    return "warn", f"Tier B {age}영업일 초과 — screener 신뢰도 하락 경고", detail


def _load_fetch_log_map(output_dir: Path | None) -> dict[str, dict[str, Any]]:
    if output_dir is None:
        return {}
    path = output_dir / "price_fetch_log.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = raw.get("entries", raw if isinstance(raw, list) else [])
    except (json.JSONDecodeError, OSError):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for entry in reversed(entries):
        if not isinstance(entry, dict):
            continue
        for t in entry.get("success_tickers") or []:
            out.setdefault(str(t), {"fetch_attempted": True, "fetch_success": True, "fail_reason": ""})
        for t in entry.get("failed_tickers") or []:
            out.setdefault(
                str(t),
                {"fetch_attempted": True, "fetch_success": False, "fail_reason": entry.get("reason") or "fetch_failed"},
            )
    return out


def build_price_coverage_rows(
    result: TierAPriceCoverageResult,
    data_dir: Path,
    output_dir: Path | None = None,
) -> list[dict[str, Any]]:
    price_dates = _latest_price_dates(data_dir, result.as_of)
    cfg = result.config
    core_max = int(cfg.get("max_stale_business_days_core", 1))
    alpha_max = int(cfg.get("max_stale_business_days_alpha", 2))
    fetch_map = _load_fetch_log_map(output_dir)

    tier_a = (
        set(result.held_tickers)
        | set(result.target_tickers)
        | set(result.trade_action_tickers)
        | set(result.alpha_top50_tickers)
    )
    all_missing = (
        set(result.core.missing_held)
        | set(result.core.missing_target)
        | set(result.core.missing_trade_actions)
        | set(result.alpha.missing_alpha_top50)
    )
    tickers = sorted(tier_a | all_missing)

    name_map: dict[str, str] = {}
    uni_path = data_dir / "universe.csv"
    if uni_path.exists():
        uni = pd.read_csv(uni_path, dtype=str, keep_default_na=False)
        for r in uni.to_dict(orient="records"):
            name_map[normalize_ticker(str(r.get("ticker", "")))] = str(r.get("name", ""))

    rows: list[dict[str, Any]] = []
    for t in tickers:
        in_held = t in result.held_tickers
        in_target = t in result.target_tickers
        in_trade = t in result.trade_action_tickers
        in_top50 = t in result.alpha_top50_tickers
        in_top30 = t in result.alpha_top30_tickers

        if in_trade or in_held or in_target:
            tier = "A-core"
            gate_role = "core"
            stale_max = core_max
        elif in_top30:
            tier = "A-alpha30"
            gate_role = "alpha"
            stale_max = alpha_max
        elif in_top50:
            tier = "A-alpha50"
            gate_role = "alpha"
            stale_max = alpha_max
        else:
            tier = "A-missing"
            gate_role = "research"
            stale_max = alpha_max

        last_date = price_dates.get(t, "")
        age = business_days_between(last_date, result.as_of[:10]) if last_date else 99
        is_stale = bool(last_date) and age > stale_max
        if not last_date:
            is_stale = True

        fetch_meta = fetch_map.get(t, {})
        fail_reason = ""
        if not last_date:
            fail_reason = "missing_price"
        elif is_stale and gate_role == "core":
            fail_reason = "stale_price"
        elif is_stale and gate_role == "alpha":
            fail_reason = "stale_alpha_price"

        rows.append({
            "ticker": t,
            "name": name_map.get(t, t),
            "tier": tier,
            "gate_role": gate_role,
            "in_positions": in_held,
            "in_target": in_target,
            "in_trade_actions": in_trade,
            "in_alpha_top50": in_top50,
            "in_alpha_top30": in_top30,
            "last_price_date": last_date,
            "price_age_business_days": age if last_date else "",
            "is_stale": is_stale,
            "price_available": bool(last_date),
            "fetch_attempted": fetch_meta.get("fetch_attempted", ""),
            "fetch_success": fetch_meta.get("fetch_success", ""),
            "fail_reason": fail_reason or fetch_meta.get("fail_reason", ""),
        })
    return rows


def write_price_coverage_reports(
    result: TierAPriceCoverageResult,
    data_dir: Path,
    output_dir: Path,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    report_path = output_dir / "price_coverage_report.json"
    report_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["price_coverage_report"] = str(report_path)

    rows = build_price_coverage_rows(result, data_dir, output_dir)
    by_tier_path = output_dir / "price_coverage_by_tier.csv"
    pd.DataFrame(rows).to_csv(by_tier_path, index=False, encoding="utf-8-sig")
    paths["price_coverage_by_tier"] = str(by_tier_path)

    missing = [r for r in rows if not r["price_available"] or r.get("is_stale")]
    missing_path = output_dir / "missing_price_tickers.csv"
    pd.DataFrame(missing).to_csv(missing_path, index=False, encoding="utf-8-sig")
    paths["missing_price_tickers"] = str(missing_path)

    return paths


def apply_alpha_price_gate_to_data_gate(alpha_data_gate: str | None, alpha_gate: AlphaPriceGateResult) -> str:
    """Alpha price gate → alpha_data_gate (전체 health RED로 번지지 않음)."""
    base = alpha_data_gate or "GREEN"
    if alpha_gate.status == "fail" or alpha_gate.action == "ALPHA_DISABLED":
        return "YELLOW" if base == "GREEN" else base if base == "RED" else "YELLOW"
    if alpha_gate.status == "warn" or alpha_gate.action == "ALPHA_REVIEW_ONLY":
        if base == "GREEN":
            return "YELLOW"
    return base


def alpha_gate_from_health_detail(detail: dict[str, Any]) -> AlphaPriceGateResult:
    return AlphaPriceGateResult(
        status=detail.get("status", "pass"),  # type: ignore[arg-type]
        action=detail.get("action", "ALPHA_OK"),  # type: ignore[arg-type]
        alpha_top30_coverage=float(detail.get("alpha_top30_coverage", 0)),
        alpha_top50_coverage=float(detail.get("alpha_top50_coverage", 0)),
    )
