from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.alpha.schemas import UniverseRecord
from src.value_list.ticker_registry import hakedaka_meta_by_ticker, load_integration_config

_GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "W": 3, "Reject": 9}
_LIQUIDITY_RULES = frozenset({
    "min_market_cap",
    "min_20d_trading_value",
    "min_60d_trading_value",
    "missing_price",
})


def merge_hakedaka_into_universe(
    universe: list[UniverseRecord],
    data_dir: Path,
) -> list[UniverseRecord]:
    """universe.csv에 없는 하케다카 종목을 스코어·진단 풀에 합류 (제안 강제 아님)."""
    cfg = load_integration_config(data_dir)
    role = cfg.get("hakedaka_role") or {}
    if not cfg.get("enabled", True) or not role.get("candidate_pool_expansion", True):
        return universe

    by_ticker = {u.ticker: u for u in universe}
    meta = hakedaka_meta_by_ticker(data_dir)
    merged = list(universe)
    for ticker, stock in meta.items():
        if ticker in by_ticker:
            continue
        merged.append(
            UniverseRecord(
                ticker=ticker,
                name=str(stock.get("name", ticker)),
                market="KOSPI",
                security_type="common_stock",
                sector="hakedaka_list",
            )
        )
    return merged


def _bonus_cfg(cfg: dict[str, Any]) -> dict[str, float]:
    raw = cfg.get("bonus") or cfg.get("alpha", {}).get("score_bonus") or {}
    return {k: float(v) for k, v in raw.items()}


def compute_hakedaka_alpha_bonus(
    ticker: str,
    *,
    meta: dict[str, dict],
    verification: dict[str, dict],
    cfg: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    bonuses = _bonus_cfg(cfg)
    max_bonus = float(bonuses.get("max_total_bonus", cfg.get("bonus", {}).get("max_total_bonus", 16)))
    tags: dict[str, Any] = {
        "in_hakedaka": False,
        "hakedaka_grade": "",
        "dart_verified": False,
        "dart_signal": "",
        "hakedaka_bonus": 0.0,
        "hakedaka_priority": False,
        "liquidity_pass": True,
    }
    stock = meta.get(ticker)
    if not stock:
        return 0.0, tags

    tags["in_hakedaka"] = True
    tags["hakedaka_grade"] = str(stock.get("grade", ""))
    bonus = float(bonuses.get("in_list", 3))

    ver = verification.get(ticker) or {}
    tags["dart_signal"] = str(ver.get("dart_signal", ""))
    if ver.get("verification_status") == "verified":
        tags["dart_verified"] = True
        bonus += float(bonuses.get("dart_verified", 5))
    if ver.get("dart_signal") == "strong":
        bonus += float(bonuses.get("dart_strong", 8))
    if str(stock.get("grade", "")) == "A":
        bonus += float(bonuses.get("hakedaka_grade_A", bonuses.get("grade_a", 5)))
    if str(stock.get("priority_bucket", "")) == "핵심":
        bonus += float(bonuses.get("hakedaka_grade_core", 3))

    bonus = min(bonus, max_bonus)
    tags["hakedaka_bonus"] = round(bonus, 2)
    return bonus, tags


def proposal_mode(cfg: dict[str, Any]) -> str:
    return str(cfg.get("proposal_mode", "pure_qvm"))


def tie_breaker_applies_to_proposal(cfg: dict[str, Any]) -> bool:
    return (
        proposal_mode(cfg) == "qvm_with_tiebreaker"
        and bool(cfg.get("hakedaka_tiebreaker_enabled", False))
        and bool((cfg.get("tie_breaker") or {}).get("enabled", False))
    )


def proposal_sort_score(
    row: dict[str, Any],
    cfg: dict[str, Any] | None,
    *,
    incumbent_bonus: float = 0.0,
    is_incumbent: bool = False,
) -> float:
    """제안 포트 정렬용 점수 — pure_qvm이면 하케다카 보너스 미반영."""
    mode = proposal_mode(cfg or {})
    if mode in {"qvm_with_bonus", "qvm_with_tiebreaker"}:
        base = float(row.get("total_score", 0))
    else:
        base = float(row.get("qvm_pure_score", row.get("total_score", 0)))
    if is_incumbent:
        base += incumbent_bonus
    return base


def eligible_for_proposal_row(row: dict[str, Any], cfg: dict[str, Any] | None) -> bool:
    """AC-HK-01: 유동성·QVM reject·강제 슬롯·시세 미확보 차단."""
    if row.get("price_coverage_pass") is False:
        return False
    if row.get("liquidity_pass") is False:
        return False
    if str(row.get("grade", "Reject")) == "Reject":
        return False
    if str(row.get("eligible_action", "")) == "NO_NEW":
        return False
    port = (cfg or {}).get("portfolio_inclusion") or {}
    if not port.get("allow_if_liquidity_failed", False) and row.get("liquidity_pass") is False:
        return False
    if not port.get("hard_slot_enabled", False) and row.get("in_hakedaka"):
        pass  # 하케다카여도 QVM·유동성 통과 시 허용 (강제 아님)
    return True


def _grade_meets_min(grade: str, minimum: str) -> bool:
    return _GRADE_ORDER.get(grade, 9) <= _GRADE_ORDER.get(minimum, 1)


def evaluate_hakedaka_priority(
    row: dict[str, Any],
    *,
    liquidity_pass: bool,
    cfg: dict[str, Any],
    in_shortlist: bool = False,
) -> bool:
    elig = cfg.get("eligibility_for_priority") or {}
    req = elig.get("required") or {}
    if not row.get("in_hakedaka"):
        return False
    if req.get("liquidity_pass", True) and not liquidity_pass:
        return False
    if req.get("dart_verified", True) and not row.get("dart_verified"):
        return False
    min_grade = str(req.get("qvm_grade_min", "B"))
    if not _grade_meets_min(str(row.get("grade", "Reject")), min_grade):
        return False
    if req.get("trading_status") == "normal":
        if row.get("eligible_action") == "NO_NEW" and float(row.get("penalty", 0)) >= 100:
            return False
    return True


def apply_hakedaka_alpha_bonus(
    graded: list[dict[str, Any]],
    data_dir: Path,
    *,
    liquidity_pass_by_ticker: dict[str, bool] | None = None,
) -> list[dict[str, Any]]:
    cfg = load_integration_config(data_dir)
    if not cfg.get("enabled", True):
        return graded

    meta = hakedaka_meta_by_ticker(data_dir)
    verification = _load_verification_index(data_dir)
    liq = liquidity_pass_by_ticker or {}
    mode = proposal_mode(cfg)
    apply_bonus_to_total = mode in {"qvm_with_bonus", "qvm_with_tiebreaker"}

    out: list[dict[str, Any]] = []
    for row in graded:
        r = dict(row)
        ticker = r["ticker"]
        lpass = liq.get(ticker, True)
        r["liquidity_pass"] = lpass
        r["qvm_pure_score"] = round(float(r.get("total_score", 0)), 2)
        bonus, tags = compute_hakedaka_alpha_bonus(
            ticker, meta=meta, verification=verification, cfg=cfg,
        )
        tags["liquidity_pass"] = lpass
        if bonus and lpass and apply_bonus_to_total:
            r["total_score"] = round(float(r.get("total_score", 0)) + bonus, 2)
        elif bonus and not lpass:
            tags["hakedaka_bonus"] = 0.0
        r.update(tags)
        r["hakedaka_priority"] = evaluate_hakedaka_priority(r, liquidity_pass=lpass, cfg=cfg)
        r["proposal_mode"] = mode
        out.append(r)
    return out


def tie_breaker_sort_boost(
    row: dict[str, Any],
    pool_leader_score: float,
    cfg: dict[str, Any],
) -> float:
    """동점·근접 점수 구간 tie-break (proposal_mode=qvm_with_tiebreaker 일 때만)."""
    if not tie_breaker_applies_to_proposal(cfg):
        return 0.0
    if not row.get("hakedaka_priority"):
        return 0.0
    score = proposal_sort_score(row, cfg)
    if pool_leader_score <= 0:
        return 0.0
    tb = cfg.get("tie_breaker") or {}
    gap_pct = float(tb.get("only_within_score_gap_pct", 5)) / 100.0
    if (pool_leader_score - score) / pool_leader_score > gap_pct:
        return 0.0
    return float(tb.get("max_rank_boost", 3))


def _load_verification_index(data_dir: Path) -> dict[str, dict]:
    import json

    path = data_dir / "cache" / "hakedaka_dart_verification.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(r["ticker"]).zfill(6): r for r in payload.get("rows", [])}


def hakedaka_alpha_limitations(
    data_dir: Path,
    graded: list[dict[str, Any]],
    *,
    overlap_count: int = 0,
) -> list[str]:
    cfg = load_integration_config(data_dir)
    if not cfg.get("enabled", True):
        return []
    in_list = sum(1 for r in graded if r.get("in_hakedaka"))
    verified = sum(1 for r in graded if r.get("dart_verified"))
    priority = sum(1 for r in graded if r.get("hakedaka_priority"))
    notes = [
        f"하케다카 soft preference — mode={proposal_mode(cfg)} · "
        f"스코어 풀 {in_list}종 · DART verified {verified}종 · "
        f"priority {priority}종 · 숏리스트 overlap {overlap_count}종",
    ]
    if overlap_count == 0:
        notes.append("overlap 0 — hakedaka_overlap_diagnostics.csv에서 탈락 원인 확인")
    role = cfg.get("hakedaka_role") or {}
    if role.get("liquidity_bypass_for_proposal"):
        notes.append("경고: 유동성 우회가 켜져 있음 — soft_preference 정책과 충돌")
    return notes


def build_liquidity_pass_map(
    universe: list[UniverseRecord],
    excluded: list,
    data_dir: Path,
) -> dict[str, bool]:
    """유동성 탈락 종목 표시 — 제안 포트 편입 금지용."""
    hakedaka = set(hakedaka_meta_by_ticker(data_dir))
    liq_fail = {
        e.ticker for e in excluded
        if e.ticker in hakedaka and e.failed_rule in _LIQUIDITY_RULES
    }
    passed = {u.ticker for u in universe}
    out: dict[str, bool] = {}
    for t in hakedaka:
        if t in liq_fail:
            out[t] = False
        elif t in passed:
            out[t] = True
        else:
            out[t] = False
    return out
