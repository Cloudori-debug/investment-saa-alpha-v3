from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from src.csv_utils import write_dataframe_csv

from src.field_normalize import normalize_sector

PILLAR_KEYS = ("quality", "valuation", "momentum", "shareholder_return")
PILLAR_SCORE_FIELDS = {
    "quality": "quality_score",
    "valuation": "valuation_score",
    "momentum": "momentum_score",
    "shareholder_return": "shareholder_return_score",
}


@dataclass
class ShortlistRow:
    ticker: str
    name: str
    sector: str
    quality_score: float
    valuation_score: float
    momentum_score: float
    shareholder_return_score: float
    total_score: float
    penalty: float
    q_rank: int
    v_rank: int
    m_rank: int
    sr_rank: int
    pillars_pass: int
    pool_rank: int
    in_shortlist: bool
    grade: str = ""
    eligible_action: str = ""
    in_hakedaka: bool = False
    hakedaka_grade: str = ""
    dart_verified: bool = False
    dart_signal: str = ""
    hakedaka_bonus: float = 0.0
    hakedaka_priority: bool = False


def _tie_break_boost(
    row: dict[str, Any],
    pool: list[dict[str, Any]],
    integration_cfg: dict[str, Any] | None,
    *,
    incumbents: set[str],
    incumbent_bonus: float,
) -> float:
    if not integration_cfg or not pool:
        return 0.0
    from src.hakedaka_gate import proposal_sort_score, tie_breaker_sort_boost

    leader = max(
        proposal_sort_score(
            r,
            integration_cfg,
            incumbent_bonus=incumbent_bonus,
            is_incumbent=r["ticker"] in incumbents,
        )
        for r in pool
    )
    return tie_breaker_sort_boost(row, leader, integration_cfg)


@dataclass
class PortfolioProposalRow:
    rank: int
    ticker: str
    name: str
    sector: str
    role: str
    total_score: float
    quality_score: float
    valuation_score: float
    momentum_score: float
    shareholder_return_score: float
    grade: str
    proposed_weight_pct: float
    is_incumbent: bool
    eligible_action: str


@dataclass
class SelectionResult:
    shortlist: list[ShortlistRow] = field(default_factory=list)
    proposal: list[PortfolioProposalRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _selection_cfg(config: dict[str, Any]) -> dict[str, Any]:
    return config.get("selection", {})


def _pillar_ranks(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    ranks: dict[str, dict[str, int]] = {p: {} for p in PILLAR_KEYS}
    for pillar in PILLAR_KEYS:
        field_name = PILLAR_SCORE_FIELDS[pillar]
        ordered = sorted(rows, key=lambda r: float(r.get(field_name, 0)), reverse=True)
        for i, row in enumerate(ordered, start=1):
            ranks[pillar][row["ticker"]] = i
    return ranks


def _pillars_pass(row: dict[str, Any], thresholds: dict[str, float]) -> int:
    count = 0
    for pillar in PILLAR_KEYS:
        field_name = PILLAR_SCORE_FIELDS[pillar]
        min_score = float(thresholds.get(pillar, 55))
        if float(row.get(field_name, 0)) >= min_score:
            count += 1
    return count


def _in_shortlist_pool(
    row: dict[str, Any],
    *,
    thresholds: dict[str, float],
    min_pillars: int,
    floor: float,
) -> bool:
    scores = [float(row.get(PILLAR_SCORE_FIELDS[p], 0)) for p in PILLAR_KEYS]
    if min(scores) < floor:
        return False
    return _pillars_pass(row, thresholds) >= min_pillars


def _assign_role(row: dict[str, Any]) -> str:
    qs = float(row.get("quality_score", 0))
    vs = float(row.get("valuation_score", 0))
    ms = float(row.get("momentum_score", 0))
    srs = float(row.get("shareholder_return_score", 0))
    core = (qs + srs) / 2
    if ms >= max(core, vs) + 8:
        return "satellite"
    if vs >= max(core, ms) + 8:
        return "value"
    if core >= max(vs, ms):
        return "core"
    return "balanced"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_satellite_single_name_sleeve_pct() -> float:
    """운영 진실: alpha_portfolio/config/target_matrix.yaml satellite_cap."""
    from src.config import load_yaml

    cfg = load_yaml(_repo_root() / "alpha_portfolio" / "config" / "target_matrix.yaml")
    return float((cfg.get("satellite_cap") or {}).get("single_name_sleeve_pct", 5))


def sleeve_pct_to_portfolio(sleeve_pct: float, kr_alpha_budget: float) -> float:
    """슬리브 % → 전체 포트폴리오 % (target_matrix.sleeve_to_portfolio와 동일)."""
    return round(float(sleeve_pct) * float(kr_alpha_budget) / 100.0, 2)


def resolve_proposed_weight_cap(
    role: str,
    *,
    kr_alpha_budget: float,
    legacy_max_proposed_pct: float,
    satellite_sleeve_pct: float | None = None,
) -> tuple[float, str]:
    """role별 제안 상한(포트 %). satellite만 target_matrix 슬리브 캡을 동적으로 환산."""
    if str(role).strip().lower() == "satellite":
        sleeve = (
            float(satellite_sleeve_pct)
            if satellite_sleeve_pct is not None
            else load_satellite_single_name_sleeve_pct()
        )
        return sleeve_pct_to_portfolio(sleeve, kr_alpha_budget), "target_matrix.satellite_cap"
    return float(legacy_max_proposed_pct), "max_proposed_weight_pct"


def build_shortlist_and_proposal(
    scored: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    incumbent_tickers: set[str] | None = None,
    kr_alpha_budget: float | None = None,
    integration_cfg: dict[str, Any] | None = None,
) -> SelectionResult:
    """축별 순위 → 숏리스트 풀 → 6~8종 포트 제안."""
    sel = _selection_cfg(config)
    out_cfg = config.get("output", {})
    thresholds = sel.get(
        "min_pillar_score",
        {"quality": 60, "valuation": 55, "momentum": 55, "shareholder_return": 55},
    )
    min_pillars = int(sel.get("min_pillars_pass", 3))
    floor = float(sel.get("min_all_pillar_floor", 45))
    max_pool = int(out_cfg.get("max_candidates", 30))
    target_n = int(out_cfg.get("target_holdings", 6))
    max_n = int(out_cfg.get("max_holdings", 8))
    sector_cap = int(sel.get("max_sector_count", 2))
    incumbent_bonus = float(out_cfg.get("incumbent_bonus", 3))
    default_weight = float(sel.get("default_proposed_weight_pct", 2.5))
    incumbents = incumbent_tickers or set()

    if not scored:
        return SelectionResult(warnings=["스코어 가능 종목 없음"])

    from src.hakedaka_gate import eligible_for_proposal_row, proposal_sort_score

    ranks = _pillar_ranks(scored)
    pool: list[dict[str, Any]] = []
    for row in scored:
        if row.get("eligible_action") == "NO_NEW" and float(row.get("penalty", 0)) >= 100:
            continue
        if _in_shortlist_pool(row, thresholds=thresholds, min_pillars=min_pillars, floor=floor):
            pool.append(dict(row))

    pool.sort(
        key=lambda r: (
            proposal_sort_score(
                r,
                integration_cfg,
                incumbent_bonus=incumbent_bonus,
                is_incumbent=r["ticker"] in incumbents,
            )
            + _tie_break_boost(
                r, pool, integration_cfg,
                incumbents=incumbents, incumbent_bonus=incumbent_bonus,
            )
        ),
        reverse=True,
    )
    pool = pool[:max_pool]

    shortlist_rows: list[ShortlistRow] = []
    for i, row in enumerate(pool, start=1):
        t = row["ticker"]
        shortlist_rows.append(
            ShortlistRow(
                ticker=t,
                name=row.get("name", t),
                sector=normalize_sector(row.get("sector", "")),
                quality_score=float(row.get("quality_score", 0)),
                valuation_score=float(row.get("valuation_score", 0)),
                momentum_score=float(row.get("momentum_score", 0)),
                shareholder_return_score=float(row.get("shareholder_return_score", 0)),
                total_score=float(row.get("total_score", 0)),
                penalty=float(row.get("penalty", 0)),
                q_rank=ranks["quality"].get(t, 999),
                v_rank=ranks["valuation"].get(t, 999),
                m_rank=ranks["momentum"].get(t, 999),
                sr_rank=ranks["shareholder_return"].get(t, 999),
                pillars_pass=_pillars_pass(row, thresholds),
                pool_rank=i,
                in_shortlist=True,
                grade=str(row.get("grade", "")),
                eligible_action=str(row.get("eligible_action", "")),
                in_hakedaka=bool(row.get("in_hakedaka", False)),
                hakedaka_grade=str(row.get("hakedaka_grade", "")),
                dart_verified=bool(row.get("dart_verified", False)),
                dart_signal=str(row.get("dart_signal", "")),
                hakedaka_bonus=float(row.get("hakedaka_bonus", 0)),
                hakedaka_priority=bool(row.get("hakedaka_priority", False)),
            )
        )

    warnings: list[str] = []
    if len(pool) < target_n:
        warnings.append(f"숏리스트 {len(pool)}종 — 목표 {target_n}종 미만 (유니버스·필터·축 기준 확인)")

    grade_order = {"A": 0, "B": 1, "C": 2, "Reject": 9}
    sorted_pool = sorted(
        pool,
        key=lambda r: (
            grade_order.get(str(r.get("grade", "Reject")), 9),
            -proposal_sort_score(
                r,
                integration_cfg,
                incumbent_bonus=incumbent_bonus,
                is_incumbent=r["ticker"] in incumbents,
            ),
        ),
    )

    selected: list[dict[str, Any]] = []
    sector_counts: dict[str, int] = {}
    for row in sorted_pool:
        if len(selected) >= max_n:
            break
        if not eligible_for_proposal_row(row, integration_cfg):
            continue
        sector = normalize_sector(row.get("sector", ""))
        if sector_counts.get(sector, 0) >= sector_cap:
            continue
        if str(row.get("grade", "Reject")) == "Reject":
            continue
        selected.append(row)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        if len(selected) >= target_n and all(g.get("grade") == "A" for g in selected[:target_n]):
            break

    max_single_pct = float(sel.get("max_proposed_weight_pct", 8.0))
    min_proposal_n = int(sel.get("min_proposal_count", target_n))
    satellite_sleeve_pct = load_satellite_single_name_sleeve_pct()

    if len(selected) < min_proposal_n:
        picked = {r["ticker"] for r in selected}
        for row in sorted_pool:
            if len(selected) >= min_proposal_n:
                break
            t = row["ticker"]
            if t in picked:
                continue
            if not eligible_for_proposal_row(row, integration_cfg):
                continue
            sector = normalize_sector(row.get("sector", ""))
            if sector_counts.get(sector, 0) >= sector_cap:
                continue
            if str(row.get("grade", "Reject")) == "Reject":
                continue
            selected.append(row)
            picked.add(t)
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
        if len(selected) < min_proposal_n:
            warnings.append(
                f"제안 {len(selected)}종 — 최소 {min_proposal_n}종 미달 "
                "(남은 비중은 kr_alpha cash buffer)"
            )

    if len(selected) < min(target_n, len(pool)):
        warnings.append(f"섹터 cap·등급 기준 적용 후 {len(selected)}종 제안 (목표 {target_n}종)")

    n_sel = len(selected) or 1
    budget = float(kr_alpha_budget) if kr_alpha_budget else default_weight * target_n
    equal = budget / n_sel
    sat_cap_at_budget = sleeve_pct_to_portfolio(satellite_sleeve_pct, budget)
    if abs(max_single_pct - sat_cap_at_budget) > 0.05:
        warnings.append(
            f"max_proposed_weight_pct={max_single_pct:.2f}% (non-satellite) vs "
            f"satellite sleeve {satellite_sleeve_pct:.0f}%→{sat_cap_at_budget:.2f}% portfolio "
            f"@ kr_alpha_budget={budget:.2f}% — satellite uses target_matrix"
        )

    proposal: list[PortfolioProposalRow] = []
    weight_sum = 0.0
    for i, row in enumerate(selected, start=1):
        role = _assign_role(row)
        role_cap, _cap_src = resolve_proposed_weight_cap(
            role,
            kr_alpha_budget=budget,
            legacy_max_proposed_pct=max_single_pct,
            satellite_sleeve_pct=satellite_sleeve_pct,
        )
        weight = round(min(equal, role_cap), 2)
        weight_sum += weight
        proposal.append(
            PortfolioProposalRow(
                rank=i,
                ticker=row["ticker"],
                name=row.get("name", row["ticker"]),
                sector=normalize_sector(row.get("sector", "")),
                role=role,
                total_score=float(row.get("total_score", 0)),
                quality_score=float(row.get("quality_score", 0)),
                valuation_score=float(row.get("valuation_score", 0)),
                momentum_score=float(row.get("momentum_score", 0)),
                shareholder_return_score=float(row.get("shareholder_return_score", 0)),
                grade=str(row.get("grade", "")),
                proposed_weight_pct=weight,
                is_incumbent=row["ticker"] in incumbents,
                eligible_action=str(row.get("eligible_action", "")),
            )
        )

    cash_buffer = round(budget - weight_sum, 2)
    if cash_buffer > 0.5:
        warnings.append(
            f"kr_alpha cash buffer {cash_buffer:.1f}%p "
            f"(satellite 캡 sleeve {satellite_sleeve_pct:.0f}%→{sat_cap_at_budget:.2f}% · "
            f"기타 max {max_single_pct:.0f}% · 분산 {n_sel}종)"
        )

    return SelectionResult(shortlist=shortlist_rows, proposal=proposal, warnings=warnings)


def write_shortlist_csv(path: Path, rows: list[ShortlistRow]) -> None:
    records = []
    for r in rows:
        rec = dict(r.__dict__)
        t = str(rec["ticker"])
        rec["ticker"] = t.zfill(6) if t.isdigit() else t
        records.append(rec)
    columns = list(ShortlistRow.__dataclass_fields__.keys())
    write_dataframe_csv(path, pd.DataFrame(records), columns=columns)


def write_proposal_csv(path: Path, rows: list[PortfolioProposalRow]) -> None:
    records = []
    for r in rows:
        rec = dict(r.__dict__)
        t = str(rec["ticker"])
        rec["ticker"] = t.zfill(6) if t.isdigit() else t
        records.append(rec)
    columns = list(PortfolioProposalRow.__dataclass_fields__.keys())
    write_dataframe_csv(path, pd.DataFrame(records), columns=columns)


@dataclass
class PillarLeaderboardRow:
    pillar: str
    pillar_label: str
    rank: int
    ticker: str
    name: str
    sector: str
    score: float
    pillars_pass: int
    total_score: float
    grade: str
    validity: str
    validity_label: str


PILLAR_LABELS = {
    "quality": "Q Quality",
    "valuation": "V Valuation",
    "momentum": "M Momentum",
    "shareholder_return": "SR Shareholder Return",
}

VALIDITY_ORDER = {
    "proposal": 0,
    "shortlist": 1,
    "pillar_top": 2,
    "weak": 3,
    "reject": 4,
}


def _validity_for_row(
    row: dict[str, Any],
    *,
    thresholds: dict[str, float],
    min_pillars: int,
    floor: float,
    shortlist: set[str],
    proposal: set[str],
) -> tuple[str, str]:
    ticker = row["ticker"]
    if ticker in proposal:
        return "proposal", "🟢 포트 제안"
    if ticker in shortlist:
        return "shortlist", "🟡 숏리스트"
    if str(row.get("grade", "")) == "Reject" or float(row.get("penalty", 0)) >= 100:
        return "reject", "🔴 제외/Reject"
    pp = _pillars_pass(row, thresholds)
    scores = [float(row.get(PILLAR_SCORE_FIELDS[p], 0)) for p in PILLAR_KEYS]
    if pp >= min_pillars and min(scores) >= floor:
        return "shortlist", "🟡 숏리스트"
    if pp >= 2:
        return "weak", "⚪ 축우수·종합미달"
    return "pillar_top", "⚪ 축 Top만"


def build_pillar_leaderboard(
    scored: list[dict[str, Any]],
    config: dict[str, Any],
    selection: SelectionResult,
    *,
    top_n: int = 10,
) -> list[PillarLeaderboardRow]:
    sel = _selection_cfg(config)
    thresholds = sel.get(
        "min_pillar_score",
        {"quality": 60, "valuation": 55, "momentum": 55, "shareholder_return": 55},
    )
    min_pillars = int(sel.get("min_pillars_pass", 3))
    floor = float(sel.get("min_all_pillar_floor", 45))
    shortlist = {s.ticker for s in selection.shortlist}
    proposal = {p.ticker for p in selection.proposal}

    rows: list[PillarLeaderboardRow] = []
    for pillar in PILLAR_KEYS:
        field_name = PILLAR_SCORE_FIELDS[pillar]
        ordered = sorted(scored, key=lambda r: float(r.get(field_name, 0)), reverse=True)
        for rank, row in enumerate(ordered[:top_n], start=1):
            validity, label = _validity_for_row(
                row,
                thresholds=thresholds,
                min_pillars=min_pillars,
                floor=floor,
                shortlist=shortlist,
                proposal=proposal,
            )
            rows.append(
                PillarLeaderboardRow(
                    pillar=pillar,
                    pillar_label=PILLAR_LABELS[pillar],
                    rank=rank,
                    ticker=row["ticker"],
                    name=row.get("name", row["ticker"]),
                    sector=normalize_sector(row.get("sector", "")),
                    score=round(float(row.get(field_name, 0)), 2),
                    pillars_pass=_pillars_pass(row, thresholds),
                    total_score=round(float(row.get("total_score", 0)), 2),
                    grade=str(row.get("grade", "")),
                    validity=validity,
                    validity_label=label,
                )
            )
    return rows


def write_pillar_leaderboard_csv(path: Path, rows: list[PillarLeaderboardRow]) -> None:
    records = []
    for r in rows:
        rec = r.__dict__.copy()
        t = str(rec["ticker"])
        rec["ticker"] = t.zfill(6) if t.isdigit() else t
        records.append(rec)
    pd.DataFrame(records).to_csv(path, index=False, encoding="utf-8-sig")


def load_portfolio_proposal(output_dir: Path) -> list[dict[str, Any]]:
    path = output_dir / "alpha_portfolio_proposal.csv"
    if not path.exists():
        return []
    return pd.read_csv(path, dtype=str, keep_default_na=False).to_dict(orient="records")
