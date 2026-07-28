"""Policy-B dry portfolio: screened scores -> review-only six-name proposal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from alpha_system.schema import AlphaSystemConfig, TrancheId
from alpha_system.scoring.cecs import CatalystInputs
from alpha_system.scoring.engine import NameScore, score_name
from alpha_system.entry.scale_in import build_scale_in_plan, render_plan_markdown
from alpha_system.sizing.allocate import allocate_tranche
from alpha_system.sizing.sector_map import load_sector_groups

SELECTION_POLICY = "B"
REQUIRED_CECS_INPUTS = (
    "execution_continuity",
    "pension_flow_score",
    "investment_purpose_flag",
)


@dataclass(frozen=True)
class DryRunResult:
    as_of: date
    cutoff: float
    cutoff_source: str
    final_count: int
    template_count: int
    scored_count: int
    eligible_count: int
    selected_count: int
    blocked_reason: Optional[str]
    rows: pd.DataFrame
    warnings: tuple[str, ...] = ()


def build_screen_dry(
    *,
    cfg: AlphaSystemConfig,
    scores_df: pd.DataFrame,
    cecs_df: pd.DataFrame,
    positions_df: pd.DataFrame,
    as_of: date,
    assumed_cutoff: float | None = None,
    allow_draft: bool = False,
    data_dir: Path | None = None,
) -> DryRunResult:
    """Build a dry six-name proposal without writing any operational files."""
    cutoff, cutoff_source = _resolve_cutoff(cfg, assumed_cutoff)
    dry_cfg = cfg.model_copy(
        update={
            "scoring": cfg.scoring.model_copy(update={"score_cutoff": cutoff})
        }
    )

    prepared_scores = _prepare_scores(scores_df)
    prepared_cecs = _prepare_cecs(cecs_df)
    held = _held_tickers(positions_df)
    template_count = len(prepared_cecs)
    final_count = int((prepared_cecs["status"] == "final").sum()) if template_count else 0
    sector_map = load_sector_groups(str((data_dir or Path("data")).resolve()))

    candidates = prepared_cecs
    if not allow_draft and not candidates.empty:
        candidates = candidates[candidates["status"] == "final"].copy()

    report_rows: list[dict] = []
    model_scores: list[NameScore] = []

    for _, cecs_row in candidates.iterrows():
        ticker = cecs_row["ticker"]
        score_hit = prepared_scores[prepared_scores["ticker"] == ticker]
        if score_hit.empty:
            report_rows.append(
                _excluded_row(
                    ticker=ticker,
                    name=cecs_row["name"],
                    status=cecs_row["status"],
                    is_held=ticker in held,
                    reason="팩터 스코어 없음",
                )
            )
            continue

        factor_row = score_hit.iloc[0]
        if not _as_bool(factor_row.get("gate_pass")):
            reason = str(factor_row.get("gate_fail_reason") or "gate 미통과")
            report_rows.append(
                _excluded_row(
                    ticker=ticker,
                    name=cecs_row["name"] or str(factor_row.get("name") or ""),
                    status=cecs_row["status"],
                    is_held=ticker in held,
                    reason=f"gate 미통과: {reason}",
                    gate_pass=False,
                )
            )
            continue

        cecs_value, cecs_inputs = _cecs_value_or_inputs(cecs_row)
        if cecs_value is None and cecs_inputs is None:
            report_rows.append(
                _excluded_row(
                    ticker=ticker,
                    name=cecs_row["name"],
                    status=cecs_row["status"],
                    is_held=ticker in held,
                    reason="CECS 미완 (computed 또는 3개 하위점수 필요)",
                    gate_pass=True,
                )
            )
            continue

        try:
            scored = score_name(
                ticker=ticker,
                name=cecs_row["name"] or str(factor_row.get("name") or ""),
                score_q=_float_or_none(factor_row.get("score_q")),
                score_v=_float_or_none(factor_row.get("score_v")),
                score_sr=_float_or_none(factor_row.get("score_sr")),
                score_r=_float_or_none(factor_row.get("score_r")),
                cecs=cecs_value,
                cecs_inputs=cecs_inputs,
                system_cfg=dry_cfg,
            )
        except (TypeError, ValueError) as exc:
            report_rows.append(
                _excluded_row(
                    ticker=ticker,
                    name=cecs_row["name"],
                    status=cecs_row["status"],
                    is_held=ticker in held,
                    reason=f"스코어 계산 불가: {exc}",
                    gate_pass=True,
                )
            )
            continue

        sector = str(sector_map.get(ticker, "") or "")
        scored.sector = sector
        model_scores.append(scored)
        report_rows.append(
            {
                "ticker": ticker,
                "name": scored.name,
                "status": cecs_row["status"],
                "is_held": ticker in held,
                "gate_pass": True,
                "total_score": scored.total_score,
                "cutoff": cutoff,
                "eligibility": scored.eligibility,
                "weight_input": scored.weight_input,
                "sector": sector,
                "selected": False,
                "dry_weight_pct": 0.0,
                "reason": scored.eligibility_reason,
            }
        )

    eligible_count = sum(s.eligibility is True for s in model_scores)
    allocation = allocate_tranche(
        dry_cfg,
        tranche_id=TrancheId.T1,  # overridden full-book budget
        scores=model_scores,
        existing_weights={},
        tranche_budget=1.0,
    )
    selected = {
        a.ticker: a.incremental_weight
        for a in allocation.allocated
        if a.incremental_weight > 0
    }

    for row in report_rows:
        ticker = row["ticker"]
        if ticker in selected:
            row["selected"] = True
            row["dry_weight_pct"] = round(selected[ticker] * 100.0, 4)
            row["reason"] = "선정: eligibility 통과 + sector 캡 + weight_input 상위"
        elif row["is_held"] and row["eligibility"] is not True:
            row["reason"] = f"탈락 보유: {row['reason']}"
        elif row["is_held"] and row["eligibility"] is True:
            row["reason"] = "탈락 보유: 적격이나 상위 편입·섹터 캡 밖"

    frame = pd.DataFrame(report_rows)
    if not frame.empty:
        frame = frame.sort_values(
            by=["selected", "total_score", "ticker"],
            ascending=[False, False, True],
            na_position="last",
        ).reset_index(drop=True)
        frame.insert(0, "rank", range(1, len(frame) + 1))

    blocked_reason = None
    # Ops A: CECS finals do not block dry selection (rank is quant-only).
    if not model_scores:
        blocked_reason = "계산 가능한 후보 없음"
    elif not selected:
        blocked_reason = "eligibility 통과 후보 없음"

    warnings = tuple(allocation.warnings)
    return DryRunResult(
        as_of=as_of,
        cutoff=cutoff,
        cutoff_source=cutoff_source,
        final_count=final_count,
        template_count=template_count,
        scored_count=len(model_scores),
        eligible_count=eligible_count,
        selected_count=len(selected),
        blocked_reason=blocked_reason,
        rows=frame,
        warnings=warnings,
    )


def write_dry_report(
    result: DryRunResult,
    *,
    csv_path: Path,
    md_path: Path,
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    result.rows.to_csv(csv_path, index=False, encoding="utf-8-sig")
    md_path.write_text(_render_markdown(result, csv_path), encoding="utf-8")


def _render_markdown(result: DryRunResult, csv_path: Path) -> str:
    status = "차단" if result.blocked_reason else "DRY · 미승인"
    lines = [
        "# 스크린 → 객관 6종 dry 리포트",
        "",
        f"- status: **{status}**",
        f"- as_of: `{result.as_of.isoformat()}`",
        f"- selection_policy: **{SELECTION_POLICY}**",
        "- ranking: **점수·eligibility만 (is_held 가산·강제 포함 없음)**",
        f"- cutoff: **{result.cutoff:g}** ({result.cutoff_source})",
        f"- CECS final: **{result.final_count}/{result.template_count}**",
        f"- scored / eligible / selected: **{result.scored_count} / {result.eligible_count} / {result.selected_count}**",
        f"- CSV: `{csv_path.as_posix()}`",
        "- operational target write: **없음**",
        "",
    ]
    if result.blocked_reason:
        lines.extend(["## 차단 사유", "", result.blocked_reason, ""])

    selected = result.rows[result.rows["selected"] == True] if not result.rows.empty else result.rows  # noqa: E712
    lines.extend(["## 선정 6종 (dry · 미승인)", ""])
    if selected.empty:
        lines.append("- 없음")
    else:
        for _, row in selected.iterrows():
            held = " · 기존 보유" if bool(row["is_held"]) else ""
            lines.append(
                f"- `{row['ticker']}` {row['name']} — score {row['total_score']:.2f}, "
                f"dry {row['dry_weight_pct']:.2f}%{held}"
            )

    dropped = (
        result.rows[(result.rows["is_held"] == True) & (result.rows["selected"] == False)]  # noqa: E712
        if not result.rows.empty
        else result.rows
    )
    lines.extend(["", "## 탈락 보유", ""])
    if dropped.empty:
        lines.append("- 없음")
    else:
        for _, row in dropped.iterrows():
            score = "—" if pd.isna(row["total_score"]) else f"{row['total_score']:.2f}"
            lines.append(f"- `{row['ticker']}` {row['name']} — score {score}; {row['reason']}")

    if result.warnings:
        lines.extend(["", "## 경고", ""])
        lines.extend(f"- {warning}" for warning in result.warnings)

    # Name-level scale-in preview (approved SCALE_IN_OPS_RULE)
    selected_rows: list[tuple[str, str, float]] = []
    if not selected.empty:
        for _, row in selected.iterrows():
            selected_rows.append(
                (
                    str(row["ticker"]),
                    str(row["name"]),
                    float(row["dry_weight_pct"] or 0.0),
                )
            )
    plan = build_scale_in_plan(result.as_of)
    lines.extend(["", render_plan_markdown(plan, rows=selected_rows)])

    lines.extend(
        [
            "",
            "---",
            "",
            "이 리포트는 Review-only입니다. `target_portfolio.csv`와 `positions.csv`를 변경하지 않습니다.",
            "",
        ]
    )
    return "\n".join(lines)


def _resolve_cutoff(
    cfg: AlphaSystemConfig,
    assumed_cutoff: float | None,
) -> tuple[float, str]:
    if assumed_cutoff is not None:
        return float(assumed_cutoff), "dry 가정값"
    if cfg.scoring.score_cutoff is None:
        raise ValueError(
            "scoring.score_cutoff이 null입니다. --assumed-cutoff를 명시하세요."
        )
    return float(cfg.scoring.score_cutoff), "config 확정값"


def _prepare_scores(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "ticker" not in frame.columns:
        raise ValueError("alpha_scores.csv에 ticker가 필요합니다.")
    out = frame.copy()
    out["ticker"] = out["ticker"].map(_ticker)
    return out


def _prepare_cecs(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "ticker" not in frame.columns:
        raise ValueError("CECS template에 ticker가 필요합니다.")
    out = frame.copy()
    out["ticker"] = out["ticker"].map(_ticker)
    if "name" not in out.columns:
        out["name"] = ""
    if "status" not in out.columns:
        out["status"] = "draft"
    out["name"] = out["name"].fillna("").astype(str)
    out["status"] = out["status"].fillna("draft").astype(str).str.lower()
    return out


def _held_tickers(frame: pd.DataFrame) -> set[str]:
    if frame.empty or "ticker" not in frame.columns:
        return set()
    if "asset_group" in frame.columns:
        frame = frame[frame["asset_group"] == "kr_alpha"]
    return {_ticker(value) for value in frame["ticker"]}


def _cecs_value_or_inputs(
    row: pd.Series,
) -> tuple[float | None, CatalystInputs | None]:
    computed = _float_or_none(row.get("cecs_computed"))
    if computed is not None:
        return computed, None
    values = {key: _float_or_none(row.get(key)) for key in REQUIRED_CECS_INPUTS}
    if any(value is None for value in values.values()):
        return None, None
    return (
        None,
        CatalystInputs(
            ticker=row["ticker"],
            name=row["name"],
            execution_continuity=float(values["execution_continuity"]),
            pension_flow_score=float(values["pension_flow_score"]),
            investment_purpose_flag=float(values["investment_purpose_flag"]),
            policy_dependency_flag=float(
                _float_or_none(row.get("policy_dependency_flag")) or 0.0
            ),
        ),
    )


def _excluded_row(
    *,
    ticker: str,
    name: str,
    status: str,
    is_held: bool,
    reason: str,
    gate_pass: bool | None = None,
) -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "status": status,
        "is_held": is_held,
        "gate_pass": gate_pass,
        "total_score": None,
        "cutoff": None,
        "eligibility": None,
        "weight_input": None,
        "selected": False,
        "dry_weight_pct": 0.0,
        "reason": reason,
    }


def _ticker(value: object) -> str:
    text = str(value).strip()
    return text.zfill(6) if text.isdigit() else text


def _float_or_none(value: object) -> float | None:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    return float(value)


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}
