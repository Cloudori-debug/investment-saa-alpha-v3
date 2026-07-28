from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.alpha.target_bridge import (
    TargetChange,
    TargetProposal,
    compute_full_diff,
    kr_alpha_target_sum,
    load_kr_alpha_budget,
    write_proposal_outputs,
)
from src.data_loader import _normalize_ticker, load_target_portfolio
from src.models import TargetRow


def default_target_draft_path() -> Path:
    # Monorepo: investment-saa-alpha/alpha_portfolio/...
    return Path(__file__).resolve().parents[2] / "alpha_portfolio" / "data" / "output" / "target_draft.csv"


def load_target_draft(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"target_draft 없음: {path}")
    df = pd.read_csv(path, dtype={"ticker": str})
    if df.empty:
        raise ValueError("target_draft.csv가 비어 있습니다")
    df["ticker"] = df["ticker"].astype(str).map(_normalize_ticker)
    if "asset_group" in df.columns:
        df = df[df["asset_group"] == "kr_alpha"].copy()
    df = df[df["target_weight"].astype(float) > 0].copy()
    return df


def load_target_changes(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype={"ticker": str})
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).map(_normalize_ticker)
    return df


def load_replace_pairs(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype={"exit_ticker": str, "candidate_ticker": str})


def enrich_target_changes_for_display(
    changes_df: pd.DataFrame,
    *,
    draft_df: pd.DataFrame | None = None,
    pairs_df: pd.DataFrame | None = None,
    data_dir: Path | None = None,
) -> pd.DataFrame:
    """target_changes.csv — ticker 옆 종목명·paired_with 이름 보강."""
    if changes_df.empty:
        return changes_df
    df = changes_df.copy()
    name_map: dict[str, str] = {}

    if draft_df is not None and not draft_df.empty:
        for _, row in draft_df.iterrows():
            code = _normalize_ticker(str(row["ticker"]))
            picked = str(row.get("name") or "").strip()
            if picked:
                name_map[code] = picked

    if pairs_df is not None and not pairs_df.empty:
        for _, row in pairs_df.iterrows():
            for tick_col, name_col in (
                ("exit_ticker", "exit_name"),
                ("candidate_ticker", "candidate_name"),
            ):
                if tick_col not in row:
                    continue
                code = _normalize_ticker(str(row[tick_col]))
                picked = str(row.get(name_col) or "").strip()
                if picked:
                    name_map[code] = picked

    if data_dir is not None:
        from src.data_loader import load_target_portfolio

        try:
            for row in load_target_portfolio(data_dir / "target_portfolio.csv"):
                code = _normalize_ticker(row.ticker)
                if code not in name_map:
                    name_map[code] = _display_name(code, name_map, row.name, data_dir=data_dir)
        except Exception:
            pass

    df["name"] = df["ticker"].astype(str).map(
        lambda t: _display_name(t, name_map, data_dir=data_dir)
    )
    if "paired_with" in df.columns:
        df["paired_with_name"] = df["paired_with"].apply(
            lambda x: (
                _display_name(str(x), name_map, data_dir=data_dir)
                if pd.notna(x) and str(x).strip()
                else ""
            )
        )

    front = ["ticker", "name"]
    rest = [c for c in df.columns if c not in front]
    return df[front + rest]


def _build_name_map(
    current: list[TargetRow],
    draft: pd.DataFrame,
) -> dict[str, str]:
    names: dict[str, str] = {}
    for row in current:
        code = _normalize_ticker(row.ticker)
        picked = str(row.name or "").strip()
        if picked and picked != code and _normalize_ticker(picked) != code:
            names[code] = picked
    for _, row in draft.iterrows():
        code = _normalize_ticker(str(row["ticker"]))
        picked = str(row.get("name") or "").strip()
        if picked and picked != code and _normalize_ticker(picked) != code:
            names[code] = picked
    return names


def _display_name(
    ticker: str,
    name_map: dict[str, str],
    raw_name: str | None = None,
    *,
    data_dir: Path | None = None,
) -> str:
    code = _normalize_ticker(ticker)
    raw = str(raw_name or "").strip()
    if raw and raw != code and _normalize_ticker(raw) != code:
        return raw
    if code in name_map:
        return name_map[code]
    if data_dir is not None:
        from src.position_lookup import lookup_ticker_metadata

        meta = lookup_ticker_metadata(data_dir, code)
        picked = str(meta.get("name") or code).strip()
        if picked and picked != code:
            return picked
    return code


def scrub_blocked_from_draft_files(
    data_dir: Path,
    draft_path: Path,
    changes_path: Path,
) -> list[str]:
    """Remove blocked tickers from alpha target_draft / target_changes on disk."""
    from src.alpha.target_portfolio_guard import (
        blocked_reintroduction_exclusion_warning,
        get_blocked_reintroductions,
    )

    blocked = get_blocked_reintroductions(data_dir)
    if not blocked:
        return []
    blocked_set = set(blocked.keys())
    warnings: list[str] = []

    if draft_path.exists():
        df = pd.read_csv(draft_path, dtype={"ticker": str})
        if "ticker" in df.columns and not df.empty:
            df["ticker"] = df["ticker"].astype(str).map(_normalize_ticker)
            mask = df["ticker"].isin(blocked_set)
            if mask.any():
                for ticker in sorted(df.loc[mask, "ticker"].unique()):
                    reason = str(blocked.get(ticker, {}).get("reason") or "unintended removal")
                    warnings.append(blocked_reintroduction_exclusion_warning(ticker, reason=reason))
                df = df[~mask].copy()
                df.to_csv(draft_path, index=False, encoding="utf-8-sig")

    if changes_path.exists():
        cdf = pd.read_csv(changes_path, dtype={"ticker": str})
        if "ticker" in cdf.columns and not cdf.empty:
            cdf["ticker"] = cdf["ticker"].astype(str).map(_normalize_ticker)
            mask = cdf["ticker"].isin(blocked_set)
            if mask.any():
                cdf = cdf[~mask].copy()
                cdf.to_csv(changes_path, index=False, encoding="utf-8-sig")

    return warnings


def draft_row_to_target(row: pd.Series) -> TargetRow:
    return TargetRow(
        ticker=_normalize_ticker(str(row["ticker"])),
        name=str(row.get("name") or row["ticker"]),
        asset_group="kr_alpha",
        sector=str(row.get("sector") or ""),
        role=str(row.get("role") or "alpha_screener"),
        target_weight=float(row["target_weight"]),
        min_weight=float(row.get("min_weight") or 0),
        max_weight=float(row.get("max_weight") or max(float(row["target_weight"]) * 1.5, 4.0)),
    )


def merge_target_draft(
    current: list[TargetRow],
    draft: pd.DataFrame,
    *,
    kr_alpha_budget: float | None = None,
    changes_df: pd.DataFrame | None = None,
    data_dir: Path | None = None,
) -> TargetProposal:
    """alpha_portfolio target_draft → kr_alpha 행만 교체한 TargetProposal."""
    from src.alpha.target_portfolio_guard import (
        blocked_reintroduction_exclusion_warning,
        get_blocked_reintroductions,
    )

    non_kr = [r.model_copy(deep=True) for r in current if r.asset_group != "kr_alpha"]
    draft_kr = draft.copy()
    warnings: list[str] = []
    if data_dir is not None:
        blocked = get_blocked_reintroductions(data_dir)
        if blocked and not draft_kr.empty:
            draft_kr["ticker"] = draft_kr["ticker"].astype(str).map(_normalize_ticker)
            mask = draft_kr["ticker"].isin(blocked.keys())
            if mask.any():
                for ticker in sorted(draft_kr.loc[mask, "ticker"].unique()):
                    reason = str(blocked[ticker].get("reason") or "unintended removal")
                    warnings.append(blocked_reintroduction_exclusion_warning(ticker, reason=reason))
                draft_kr = draft_kr[~mask].copy()
        if blocked and changes_df is not None and not changes_df.empty:
            cdf = changes_df.copy()
            cdf["ticker"] = cdf["ticker"].astype(str).map(_normalize_ticker)
            changes_df = cdf[~cdf["ticker"].isin(blocked.keys())].copy()

    new_kr = [draft_row_to_target(row) for _, row in draft_kr.iterrows()]
    rows = non_kr + new_kr
    kr_sum = kr_alpha_target_sum(rows)

    if kr_alpha_budget is not None and kr_sum > kr_alpha_budget + 0.01:
        factor = kr_alpha_budget / kr_sum if kr_sum else 1.0
        from src.alpha.target_bridge import scale_kr_alpha_row_to_budget

        for row in rows:
            if row.asset_group != "kr_alpha":
                continue
            scale_kr_alpha_row_to_budget(row, factor)
        kr_sum = kr_alpha_target_sum(rows)
        warnings.append(f"kr_alpha 합계를 Compass 예산 {kr_alpha_budget:.1f}%에 맞게 {factor:.2%} 스케일")

    if changes_df is not None and not changes_df.empty:
        name_map = _build_name_map(current, draft)
        changes = [
            TargetChange(
                _normalize_ticker(str(r["ticker"])),
                _display_name(
                    str(r["ticker"]),
                    name_map,
                    r.get("name"),
                    data_dir=data_dir,
                ),
                str(r.get("action", "adjust")),  # type: ignore[arg-type]
                float(r["old_weight"]) if pd.notna(r.get("old_weight")) else None,
                float(r.get("new_weight", 0) or 0),
                "kr_alpha",
                str(r.get("reason") or "target_draft"),
            )
            for _, r in changes_df.iterrows()
        ]
    else:
        changes = compute_full_diff(current, rows)

    return TargetProposal(
        rows=rows,
        changes=changes,
        kr_alpha_sum=kr_sum,
        kr_alpha_budget=kr_alpha_budget,
        warnings=warnings,
    )


def build_proposal_from_draft(
    data_dir: Path,
    output_dir: Path,
    *,
    draft_path: Path | None = None,
    changes_path: Path | None = None,
) -> TargetProposal:
    draft_path = draft_path or default_target_draft_path()
    changes_path = changes_path or draft_path.parent / "target_changes.csv"
    scrub_warnings = scrub_blocked_from_draft_files(data_dir, draft_path, changes_path)
    current = load_target_portfolio(data_dir / "target_portfolio.csv")
    draft = load_target_draft(draft_path)
    changes_df = load_target_changes(changes_path)
    budget = load_kr_alpha_budget(output_dir)
    proposal = merge_target_draft(
        current,
        draft,
        kr_alpha_budget=budget,
        changes_df=changes_df if not changes_df.empty else None,
        data_dir=data_dir,
    )
    if scrub_warnings:
        proposal.warnings = scrub_warnings + proposal.warnings
    return proposal


def preview_target_draft(
    data_dir: Path,
    output_dir: Path,
    *,
    draft_path: Path | None = None,
) -> TargetProposal:
    proposal = build_proposal_from_draft(data_dir, output_dir, draft_path=draft_path)
    write_proposal_outputs(proposal, output_dir)
    return proposal


def is_target_draft_pending(data_dir: Path, draft_path: Path | None = None) -> bool:
    """draft 파일이 있고 target_portfolio kr_alpha와 아직 불일치하면 True."""
    draft_path = draft_path or default_target_draft_path()
    if not draft_path.exists():
        return False
    try:
        current = load_target_portfolio(data_dir / "target_portfolio.csv")
        draft = load_target_draft(draft_path)
    except (FileNotFoundError, ValueError):
        return False

    current_kr = {_normalize_ticker(t.ticker) for t in current if t.asset_group == "kr_alpha"}
    draft_kr = set(draft["ticker"].astype(str))
    if current_kr != draft_kr:
        return True

    cur_weights = {
        _normalize_ticker(t.ticker): t.target_weight
        for t in current
        if t.asset_group == "kr_alpha"
    }
    for _, row in draft.iterrows():
        ticker = _normalize_ticker(str(row["ticker"]))
        if abs(cur_weights.get(ticker, 0.0) - float(row["target_weight"])) > 0.2:
            return True
    return False


def load_current_kr_alpha_df(data_dir: Path) -> pd.DataFrame:
    """data/target_portfolio.csv 의 kr_alpha 목표만."""
    targets = load_target_portfolio(data_dir / "target_portfolio.csv")
    records = [
        {
            "ticker": t.ticker,
            "name": t.name,
            "target_weight": t.target_weight,
            "min_weight": t.min_weight,
            "max_weight": t.max_weight,
        }
        for t in targets
        if t.asset_group == "kr_alpha"
    ]
    if not records:
        return pd.DataFrame(columns=["ticker", "name", "target_weight", "min_weight", "max_weight"])
    df = pd.DataFrame(records)
    df["ticker"] = df["ticker"].astype(str).map(_normalize_ticker)
    return df.sort_values("target_weight", ascending=False).reset_index(drop=True)


def _kr_alpha_user_action(
    *,
    in_current: bool,
    in_draft: bool,
    change_action: str,
    matrix_action: str,
    delta_pct: float | None,
    paired_with: str | None,
    change_reason: str,
) -> str:
    action = (change_action or matrix_action or "").strip().lower()
    if action == "remove" and not in_draft:
        if in_current:
            return "목표에서 제외 — 승인 시 target_portfolio에서 삭제"
        return "alpha 제외 제안 — 현재 target 미포함 (보유·실매매는 executable 별도)"
    if in_current and not in_draft:
        return "목표에서 제외 — 승인 시 target_portfolio에서 삭제"
    if not in_current and in_draft:
        base = "신규 편입 — 승인 시 target에 추가"
        if paired_with:
            return f"{base} ({paired_with} 대체)"
        if change_reason:
            return f"{base} — {change_reason}"
        return base
    if action == "trim":
        return "목표 비중 축소 — 승인 시 target 반영 (실매매는 executable 별도)"
    if action == "remove":
        return "목표에서 제외 — 승인 시 target_portfolio에서 삭제"
    if action == "add":
        if paired_with:
            return f"신규 편입 — 승인 시 target 추가 ({paired_with} 대체)"
        return "신규 편입 — 승인 시 target에 추가"
    if action == "keep":
        if delta_pct is not None and abs(delta_pct) >= 0.2:
            return "유지 종목 — 비중만 재조정"
        return "유지 — 구성 변경 없음"
    if delta_pct is not None and abs(delta_pct) < 0.01:
        return "변경 없음"
    if delta_pct is not None:
        return "비중 조정 — 승인 시 target 반영"
    return "검토"


def build_kr_alpha_target_comparison(
    data_dir: Path,
    draft: pd.DataFrame,
    *,
    draft_path: Path | None = None,
    changes_path: Path | None = None,
) -> pd.DataFrame:
    """현재 목표 vs target_draft 비교 + 종목별 해야 할 일."""
    draft_path = draft_path or default_target_draft_path()
    changes_path = changes_path or draft_path.parent / "target_changes.csv"
    current = load_current_kr_alpha_df(data_dir)
    changes_df = load_target_changes(changes_path)
    current_targets = load_target_portfolio(data_dir / "target_portfolio.csv")
    name_map = _build_name_map(current_targets, draft)

    cur_map = {str(r["ticker"]): r for _, r in current.iterrows()}
    drf_map = {str(r["ticker"]): r for _, r in draft.iterrows()}

    chg_action: dict[str, str] = {}
    chg_reason: dict[str, str] = {}
    pair_map: dict[str, str] = {}
    if not changes_df.empty:
        for _, row in changes_df.iterrows():
            code = _normalize_ticker(str(row["ticker"]))
            chg_action[code] = str(row.get("action", "")).strip()
            chg_reason[code] = str(row.get("reason", "")).strip()
            if pd.notna(row.get("paired_with")) and str(row.get("paired_with")).strip():
                pair_map[code] = _normalize_ticker(str(row["paired_with"]))

    tickers = sorted(set(cur_map) | set(drf_map) | set(chg_action))
    rows: list[dict[str, object]] = []
    for ticker in tickers:
        cur = cur_map.get(ticker)
        drf = drf_map.get(ticker)
        in_current = cur is not None
        in_draft = drf is not None
        current_pct = float(cur["target_weight"]) if in_current else None
        draft_pct = float(drf["target_weight"]) if in_draft else None
        if current_pct is not None and draft_pct is not None:
            delta_pct = round(draft_pct - current_pct, 2)
        elif current_pct is not None:
            delta_pct = round(-current_pct, 2)
        elif draft_pct is not None:
            delta_pct = round(draft_pct, 2)
        else:
            delta_pct = None

        matrix_action = str(drf.get("matrix_action", "")).strip() if in_draft else ""
        change_action = chg_action.get(ticker, "")
        if not change_action and not in_draft and in_current:
            change_action = "remove"
        reason = ""
        if in_draft:
            reason = str(drf.get("change_reason") or drf.get("reason") or "").strip()
        if not reason:
            reason = chg_reason.get(ticker, "")

        rows.append(
            {
                "ticker": ticker,
                "name": _display_name(
                    ticker,
                    name_map,
                    str((drf.get("name") if in_draft and drf is not None else None)
                        or (cur.get("name") if in_current and cur is not None else "")
                        or ""),
                    data_dir=data_dir,
                ),
                "current_pct": current_pct,
                "draft_pct": draft_pct,
                "delta_pct": delta_pct,
                "matrix_action": matrix_action or change_action,
                "change_reason": reason,
                "user_action": _kr_alpha_user_action(
                    in_current=in_current,
                    in_draft=in_draft,
                    change_action=change_action,
                    matrix_action=matrix_action,
                    delta_pct=delta_pct,
                    paired_with=pair_map.get(ticker),
                    change_reason=reason,
                ),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "ticker", "name", "current_pct", "draft_pct", "delta_pct",
                "matrix_action", "change_reason", "user_action",
            ]
        )
    out = pd.DataFrame(rows)
    out["_sort"] = out["draft_pct"].fillna(0)
    return out.sort_values("_sort", ascending=False).drop(columns="_sort").reset_index(drop=True)


def summarize_kr_alpha_draft_actions(comparison: pd.DataFrame) -> dict[str, int]:
    """matrix_action 기준 요약."""
    if comparison.empty:
        return {}
    counts: dict[str, int] = {}
    for _, row in comparison.iterrows():
        if row.get("current_pct") is not None and pd.isna(row.get("draft_pct")):
            key = "remove"
        else:
            key = str(row.get("matrix_action") or "other").strip().lower() or "other"
        counts[key] = counts.get(key, 0) + 1
    return counts

