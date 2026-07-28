from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from src.config import load_yaml
from src.data_loader import _normalize_ticker, load_target_portfolio, normalize_target_weights_to_100, write_target_portfolio
from src.models import TargetRow

ChangeType = Literal["add", "trim", "remove", "adjust", "unchanged"]

_BLOCKED_ADD_ACTIONS = frozenset({"WATCH", "BLOCK_NEW_BUY", "NO_NEW"})


@dataclass
class TargetChange:
    ticker: str
    name: str
    change_type: ChangeType
    old_weight: float | None
    new_weight: float
    asset_group: str
    reason: str


@dataclass
class TargetProposal:
    rows: list[TargetRow]
    changes: list[TargetChange] = field(default_factory=list)
    kr_alpha_sum: float = 0.0
    kr_alpha_budget: float | None = None
    warnings: list[str] = field(default_factory=list)


def load_kr_alpha_budget(output_dir: Path) -> float | None:
    path = output_dir / "target_asset_allocation.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    matched = df[df["asset_group"] == "kr_alpha"]
    if matched.empty:
        return None
    return float(matched.iloc[0]["final_target"])


def kr_alpha_target_sum(targets: list[TargetRow]) -> float:
    return round(sum(t.target_weight for t in targets if t.asset_group == "kr_alpha"), 2)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_target_matrix_cfg() -> dict[str, Any]:
    return load_yaml(_repo_root() / "alpha_portfolio" / "config" / "target_matrix.yaml")


def _import_compute_bands():
    """alpha_portfolio target_matrix.compute_bands — monorepo 경로 import."""
    import importlib.util
    import sys

    mod_name = "alpha_portfolio_target_matrix"
    cached = sys.modules.get(mod_name)
    if cached is not None and hasattr(cached, "compute_bands"):
        return cached.compute_bands

    alpha_src = _repo_root() / "alpha_portfolio" / "src"
    mod_path = alpha_src / "target_matrix.py"
    alpha_src_s = str(alpha_src)
    if alpha_src_s not in sys.path:
        sys.path.insert(0, alpha_src_s)
    spec = importlib.util.spec_from_file_location(mod_name, mod_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load target_matrix from {mod_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module.compute_bands


def infer_tier_from_role(role: str | None, tier: str | None = None) -> str:
    raw = str(tier or role or "").strip().lower()
    if raw in {"satellite", "sat"}:
        return "Satellite"
    return "Core"


def compute_add_bands(
    target_weight: float,
    *,
    role: str | None = None,
    tier: str | None = None,
    kr_alpha_budget: float | None = None,
) -> tuple[float, float]:
    """신규 add용 min/max — target_matrix.compute_bands (기본 1.0/4.0 폐기).

    제안 비중이 satellite sleeve 캡보다 클 때도 제안 target이 밴드 안에 들어가도록
    min/max를 target에 맞게 클램프한다 (경고 회피용 임의 확대가 아니라 제안값 정합).
    """
    compute_bands = _import_compute_bands()
    cfg = _load_target_matrix_cfg()
    tw = float(target_weight)
    budget = float(kr_alpha_budget) if kr_alpha_budget is not None else max(tw * 4.0, 20.0)
    min_w, max_w = compute_bands(tw, infer_tier_from_role(role, tier), cfg, budget)
    min_w = min(min_w, tw)
    max_w = max(max_w, tw)
    return round(min_w, 2), round(max_w, 2)


def scale_kr_alpha_row_to_budget(row: TargetRow, factor: float) -> TargetRow:
    """예산 스케일 시 target과 min/max를 동일 factor로 갱신 (compass decompose와 동일 원칙)."""
    row.target_weight = round(row.target_weight * factor, 2)
    row.min_weight = round(row.min_weight * factor, 2)
    row.max_weight = round(row.max_weight * factor, 2)
    if row.min_weight > row.max_weight:
        row.min_weight = row.max_weight
    return row


def _pick_name(ticker: str, raw_name: str | None) -> str | None:
    name = str(raw_name or "").strip()
    code = _normalize_ticker(ticker)
    if name and _normalize_ticker(name) != code and name != ticker:
        return name
    return None


def resolve_add_candidate(
    ticker: str,
    *,
    data_dir: Path | None = None,
    pools: list[dict[str, Any]] | None = None,
    default_new_weight: float = 2.0,
    default_min_weight: float | None = None,
    default_max_weight: float | None = None,
    kr_alpha_budget: float | None = None,
) -> dict[str, Any]:
    """추가 후보 dict — name을 universe·후보 풀에서 보강. min/max는 compute_bands."""
    code = _normalize_ticker(ticker)
    merged: dict[str, Any] = {"ticker": code}

    for row in pools or []:
        if _normalize_ticker(str(row.get("ticker", ""))) != code:
            continue
        for key, val in row.items():
            if key == "ticker":
                continue
            if val is not None and str(val).strip() != "":
                merged[key] = val
        picked = _pick_name(code, merged.get("name"))
        if picked:
            merged["name"] = picked

    merged["ticker"] = code

    if not _pick_name(code, merged.get("name")) and data_dir is not None:
        from src.position_lookup import lookup_ticker_metadata

        meta = lookup_ticker_metadata(data_dir, code)
        merged["name"] = str(meta.get("name") or code)
        if not merged.get("sector"):
            merged["sector"] = str(meta.get("sector") or "")
    elif not merged.get("name"):
        merged["name"] = code

    merged.setdefault("target_weight", default_new_weight)
    merged.setdefault("role", "alpha_screener")

    has_min = merged.get("min_weight") is not None and str(merged.get("min_weight")).strip() != ""
    has_max = merged.get("max_weight") is not None and str(merged.get("max_weight")).strip() != ""
    if has_min and has_max:
        pass
    elif default_min_weight is not None and default_max_weight is not None:
        merged.setdefault("min_weight", default_min_weight)
        merged.setdefault("max_weight", default_max_weight)
    else:
        min_w, max_w = compute_add_bands(
            float(merged["target_weight"]),
            role=str(merged.get("role") or ""),
            tier=str(merged.get("tier") or "") or None,
            kr_alpha_budget=kr_alpha_budget,
        )
        if not has_min:
            merged["min_weight"] = min_w
        if not has_max:
            merged["max_weight"] = max_w
    return merged


def propose_target_changes(
    current: list[TargetRow],
    *,
    add_candidates: list[dict[str, Any]],
    trim_tickers: set[str],
    remove_tickers: set[str],
    kr_alpha_budget: float | None = None,
    default_new_weight: float = 2.0,
    default_min_weight: float | None = None,
    default_max_weight: float | None = None,
    data_dir: Path | None = None,
) -> TargetProposal:
    """Alpha 승인안 기반 target_portfolio 제안 (자동 반영 아님)."""
    from src.alpha.loaders import load_prices

    price_have: set[str] = set()
    if data_dir is not None:
        price_have = {p.ticker for p in load_prices(data_dir / "prices.csv")}

    row_map = {t.ticker: t.model_copy(deep=True) for t in current}
    changes: list[TargetChange] = []
    warnings: list[str] = []

    if data_dir is not None:
        from src.alpha.target_portfolio_guard import get_blocked_reintroductions, _normalize_ticker

        blocked = get_blocked_reintroductions(data_dir)
        for ticker in list(row_map):
            norm = _normalize_ticker(ticker)
            if norm in blocked:
                row = row_map.pop(ticker)
                warnings.append(
                    f"{ticker}: unintended removal block — proposal baseline에서 제외 "
                    f"(override_previous_removal 필요)"
                )
                changes.append(
                    TargetChange(
                        ticker,
                        row.name,
                        "remove",
                        row.target_weight,
                        0.0,
                        row.asset_group,
                        "blocked unintended reintroduction",
                    )
                )

    for ticker in trim_tickers:
        if ticker not in row_map:
            continue
        row = row_map[ticker]
        if row.asset_group != "kr_alpha":
            warnings.append(f"{ticker}: kr_alpha 외 종목 TRIM 스킵")
            continue
        old = row.target_weight
        new = row.min_weight
        row.target_weight = new
        changes.append(
            TargetChange(ticker, row.name, "trim", old, new, row.asset_group, "Alpha TRIM 승인")
        )

    for ticker in remove_tickers:
        if ticker not in row_map:
            continue
        row = row_map[ticker]
        if row.asset_group != "kr_alpha":
            warnings.append(f"{ticker}: kr_alpha 외 종목 REMOVE 스킵")
            continue
        old = row.target_weight
        row.target_weight = 0.0
        changes.append(
            TargetChange(ticker, row.name, "remove", old, 0.0, row.asset_group, "Alpha REPLACE/REMOVE 승인")
        )

    for cand in add_candidates:
        enriched = resolve_add_candidate(
            str(cand.get("ticker", "")),
            data_dir=data_dir,
            pools=[cand],
            default_new_weight=default_new_weight,
            default_min_weight=default_min_weight,
            default_max_weight=default_max_weight,
            kr_alpha_budget=kr_alpha_budget,
        )
        ticker = str(enriched["ticker"])
        if data_dir is not None:
            from src.alpha.target_portfolio_guard import get_blocked_reintroductions

            blocked = get_blocked_reintroductions(data_dir)
            norm = ticker.zfill(6) if ticker.isdigit() and len(ticker) < 6 else ticker
            if norm in blocked:
                warnings.append(
                    f"{ticker}: unintended removal block — approval_bridge 재편입 불가 "
                    f"(override_previous_removal 필요)"
                )
                continue
        if price_have and ticker not in price_have:
            warnings.append(f"{ticker}: 시세 미확보 — target 추가 스킵 (research-only)")
            continue
        if ticker in row_map and row_map[ticker].target_weight > 0:
            warnings.append(f"{ticker}: 이미 target에 존재")
            continue
        weight = float(enriched.get("target_weight", default_new_weight))
        display_name = str(enriched.get("name") or ticker)
        row = TargetRow(
            ticker=ticker,
            name=display_name,
            asset_group="kr_alpha",
            sector=str(enriched.get("sector", "")),
            role=str(enriched.get("role", "alpha_screener")),
            target_weight=weight,
            min_weight=float(enriched["min_weight"]),
            max_weight=float(enriched["max_weight"]),
        )
        row_map[ticker] = row
        changes.append(
            TargetChange(ticker, display_name, "add", None, weight, "kr_alpha", "Alpha BUY 후보 승인")
        )

    rows = [r for r in row_map.values() if not (r.asset_group == "kr_alpha" and r.target_weight <= 0)]
    kr_sum = kr_alpha_target_sum(rows)

    if kr_alpha_budget is not None and kr_sum > kr_alpha_budget + 0.01:
        factor = kr_alpha_budget / kr_sum if kr_sum else 1.0
        for row in rows:
            if row.asset_group != "kr_alpha":
                continue
            old = row.target_weight
            scale_kr_alpha_row_to_budget(row, factor)
            if abs(old - row.target_weight) > 0.01:
                changes.append(
                    TargetChange(
                        row.ticker,
                        row.name,
                        "adjust",
                        old,
                        row.target_weight,
                        row.asset_group,
                        f"kr_alpha 예산 {kr_alpha_budget:.1f}% 맞춤 스케일",
                    )
                )
        kr_sum = kr_alpha_target_sum(rows)
        warnings.append(f"kr_alpha 합계를 Compass 예산에 맞게 {factor:.2%} 스케일 조정")

    return TargetProposal(
        rows=rows,
        changes=changes,
        kr_alpha_sum=kr_sum,
        kr_alpha_budget=kr_alpha_budget,
        warnings=warnings,
    )


def compute_full_diff(before: list[TargetRow], after: list[TargetRow]) -> list[TargetChange]:
    before_map = {t.ticker: t for t in before}
    after_map = {t.ticker: t for t in after}
    all_tickers = sorted(set(before_map) | set(after_map))
    diffs: list[TargetChange] = []

    for ticker in all_tickers:
        b = before_map.get(ticker)
        a = after_map.get(ticker)
        if b and a:
            if abs(b.target_weight - a.target_weight) < 0.01:
                continue
            ctype: ChangeType = "adjust"
            if a.target_weight < b.target_weight and a.target_weight <= a.min_weight:
                ctype = "trim"
            if a.target_weight == 0:
                ctype = "remove"
            diffs.append(
                TargetChange(
                    ticker,
                    a.name,
                    ctype,
                    b.target_weight,
                    a.target_weight,
                    a.asset_group,
                    "weight 변경",
                )
            )
        elif a and not b:
            diffs.append(
                TargetChange(ticker, a.name, "add", None, a.target_weight, a.asset_group, "신규 추가")
            )
        elif b and not a:
            diffs.append(
                TargetChange(ticker, b.name, "remove", b.target_weight, 0.0, b.asset_group, "제거")
            )
    return diffs


def write_proposal_outputs(proposal: TargetProposal, output_dir: Path) -> None:
    from src.alpha.target_write_audit import proposal_output_dir

    out_dir = proposal_output_dir(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_target_portfolio(proposal.rows, out_dir / "target_portfolio_proposed.csv")
    if proposal.changes:
        pd.DataFrame([c.__dict__ for c in proposal.changes]).to_csv(
            out_dir / "target_proposal_diff.csv",
            index=False,
            encoding="utf-8-sig",
        )


def apply_proposed_target(
    proposal: TargetProposal,
    target_path: Path,
    *,
    backup_dir: Path | None = None,
    approved_by: str = "human",
    data_dir: Path | None = None,
    output_dir: Path | None = None,
    approved_by_user: bool = True,
    override_previous_removal: frozenset[str] | None = None,
    write_reason: str | None = None,
    writer_module: str | None = None,
):
    """사람 승인 후 data/target_portfolio.csv 반영. 백업 필수.

    Returns TargetWriteResult (audit includes write_material_change_count).
    """
    from src.alpha.target_write_audit import write_operational_target
    from src.validation.bundle_consistency import resolve_pipeline_run_id

    target_path.parent.mkdir(parents=True, exist_ok=True)
    data_dir = data_dir or target_path.parent
    out_dir = output_dir or (data_dir.parent / "outputs")
    pipeline_run_id = resolve_pipeline_run_id(out_dir)

    rows, normalized = normalize_target_weights_to_100(proposal.rows)
    if normalized:
        proposal.warnings.append(
            "target_weight 합계를 100%로 정규화 (이전 kr_alpha/전체 합 초과 방지)"
        )

    from src.alpha.target_portfolio_guard import (
        TargetPortfolioWriteBlockedError,
        filter_blocked_reintroduction_rows,
    )

    rows, stripped = filter_blocked_reintroduction_rows(data_dir, rows)
    proposal.warnings.extend(stripped)

    reason = write_reason or f"alpha_proposal_approved_by={approved_by}"
    result = write_operational_target(
        data_dir,
        rows,
        source="approval_bridge",
        reason=reason,
        approved_by_user=approved_by_user,
        writer_module=writer_module or "target_bridge.apply_proposed_target",
        output_dir=out_dir,
        run_id=pipeline_run_id,
        proposal_source_id=str(out_dir / "proposals" / "target_portfolio_proposed.csv"),
        backup=bool(backup_dir is not False),
        override_previous_removal=override_previous_removal,
    )
    if result.blocked or not result.path:
        blocked_reason = result.audit.get("target_write_reason", "target write blocked")
        raise TargetPortfolioWriteBlockedError(blocked_reason)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = out_dir / "approval_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": stamp,
        "approved_by": approved_by,
        "target_path": str(result.path),
        "change_count": len(proposal.changes),
        "write_material_change_count": result.audit.get("write_material_change_count", 0),
        "kr_alpha_sum": proposal.kr_alpha_sum,
        "warnings": proposal.warnings,
        "write_reason": reason,
        "writer_module": result.audit.get("writer_module"),
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return result


def default_trim_candidates(holdings_review: list[dict]) -> set[str]:
    return {str(h["ticker"]) for h in holdings_review if h.get("review_action") == "TRIM"}


def default_remove_candidates(holdings_review: list[dict]) -> set[str]:
    return {str(h["ticker"]) for h in holdings_review if h.get("review_action") == "REPLACE_CANDIDATE"}


def default_add_candidates(
    candidates: list[dict],
    limit: int = 8,
    *,
    output_dir: Path | None = None,
    data_dir: Path | None = None,
) -> list[dict]:
    from src.alpha.portfolio_selector import load_portfolio_proposal
    from src.alpha.loaders import load_prices

    price_have: set[str] = set()
    if data_dir is not None:
        price_have = {p.ticker for p in load_prices(data_dir / "prices.csv")}

    if output_dir is not None:
        proposal = load_portfolio_proposal(output_dir)
        if proposal:
            out: list[dict] = []
            for row in proposal[:limit]:
                action = str(row.get("eligible_action") or "").strip().upper()
                if action in _BLOCKED_ADD_ACTIONS:
                    continue
                if str(row.get("grade", "")) == "Reject":
                    continue
                ticker = str(row["ticker"])
                if price_have and ticker not in price_have:
                    continue
                out.append(
                    {
                        "ticker": row["ticker"],
                        "name": row.get("name", row["ticker"]),
                        "sector": row.get("sector", ""),
                        "grade": row.get("grade", "B"),
                        "eligible_action": row.get("eligible_action", "BUY_CANDIDATE"),
                        "target_weight": float(row.get("proposed_weight_pct", 2.5)),
                        "role": row.get("role", ""),
                    }
                )
            if out:
                return out

    out = []
    for row in candidates:
        action = str(row.get("eligible_action") or "").strip().upper()
        if action in _BLOCKED_ADD_ACTIONS:
            continue
        if row.get("eligible_action") != "BUY_CANDIDATE":
            continue
        if row.get("grade") != "A":
            continue
        ticker = str(row.get("ticker", ""))
        if price_have and ticker not in price_have:
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return out


def build_band_resync_proposal(
    current: list[TargetRow],
    *,
    profiles_path: Path | None = None,
    profile_name: str | None = None,
    draft_path: Path | None = None,
) -> TargetProposal:
    """kr_alpha min/max 재동기화.

    1) draft에 있는 종목: draft 밴드 × (live_target / draft_target) — 예산 스케일 드리프트 역보정
    2) draft에 없는 종목(071050 등): compute_bands(+ 제안 target 정합 클램프)
    non-kr_alpha는 유지.
    """
    from src.alpha.target_draft_bridge import default_target_draft_path, load_target_draft

    _ = profiles_path, profile_name
    draft_path = draft_path or default_target_draft_path()
    draft_map: dict[str, Any] = {}
    if draft_path.exists():
        draft_df = load_target_draft(draft_path)
        for _, drow in draft_df.iterrows():
            draft_map[_normalize_ticker(str(drow["ticker"]))] = drow

    kr_sum = kr_alpha_target_sum(current)
    resynced: list[TargetRow] = []
    changes: list[TargetChange] = []

    for row in current:
        if row.asset_group != "kr_alpha":
            resynced.append(row.model_copy(deep=True))
            continue

        prev_min, prev_max = row.min_weight, row.max_weight
        drow = draft_map.get(row.ticker)
        if drow is not None and float(drow.get("target_weight") or 0) > 0:
            factor = row.target_weight / float(drow["target_weight"])
            min_w = round(float(drow.get("min_weight") or 0) * factor, 2)
            max_w = round(float(drow.get("max_weight") or 0) * factor, 2)
        else:
            min_w, max_w = compute_add_bands(
                row.target_weight,
                role=row.role,
                kr_alpha_budget=kr_sum,
            )

        min_w = min(min_w, row.target_weight)
        max_w = max(max_w, row.target_weight)
        updated = row.model_copy(deep=True)
        updated.min_weight = round(min_w, 2)
        updated.max_weight = round(max_w, 2)
        resynced.append(updated)
        if abs(prev_min - updated.min_weight) >= 0.01 or abs(prev_max - updated.max_weight) >= 0.01:
            changes.append(
                TargetChange(
                    updated.ticker,
                    updated.name,
                    "adjust",
                    row.target_weight,
                    updated.target_weight,
                    updated.asset_group,
                    "band_resync",
                )
            )

    return TargetProposal(
        rows=resynced,
        changes=changes,
        kr_alpha_sum=kr_sum,
        kr_alpha_budget=kr_sum,
        warnings=["band_resync via draft-factor scale / compute_bands"],
    )