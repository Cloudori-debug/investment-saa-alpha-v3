"""CECS scoring workbench: atomic CSV writes, correlation, cutoff approval."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal, Mapping, Sequence

import pandas as pd

from alpha_system.journal import append_record
from alpha_system.loader import load_config
from alpha_system.scoring.cecs import CatalystInputs, calculate_cecs
from alpha_system.scoring.correlation import (
    CorrelationReport,
    analyze_factor_correlation,
    write_correlation_report,
)
from alpha_system.ui.services.cecs_ai_research import ParsedResearchSuggestion

ScoreStatus = Literal["draft", "ai_suggested", "final"]
_WRITE_LOCK = Lock()
_SCORE_FIELDS = (
    "execution_continuity",
    "pension_flow_score",
    "investment_purpose_flag",
)
_RATIONALE_FIELDS = (
    "execution_rationale",
    "pension_rationale",
    "investment_purpose_rationale",
)
_AI_COLUMNS = (
    "execution_sources",
    "pension_sources",
    "investment_purpose_sources",
    "ai_suggested_at",
    "ai_report_name",
    "ai_approved_at",
)


@dataclass(frozen=True)
class CecsProgress:
    final: int
    total: int
    draft_tickers: tuple[str, ...]


@dataclass(frozen=True)
class CecsBatchImportResult:
    imported_tickers: tuple[str, ...]
    failures: tuple[str, ...]


@dataclass(frozen=True)
class CecsApprovalResult:
    approved_tickers: tuple[str, ...]
    final: int
    total: int


@dataclass(frozen=True)
class CutoffRankOption:
    """Relative cutoff: choose top-N, derive absolute score_cutoff afterwards."""

    rank_n: int
    cutoff: float
    eligible_count: int
    margin_below: float | None
    boundary_ticker: str
    boundary_name: str
    next_ticker: str | None
    next_name: str | None
    next_score: float | None
    is_natural_break: bool


def cutoff_actions_enabled(progress: CecsProgress, *, factor_exists: bool) -> bool:
    return (
        progress.total >= 30
        and progress.final >= progress.total
        and factor_exists
    )


def load_cecs_template(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if "ticker" not in frame.columns or "status" not in frame.columns:
        raise ValueError("CECS template에는 ticker와 status 열이 필요합니다.")
    frame["ticker"] = frame["ticker"].map(_ticker)
    return frame


def cecs_progress(path: Path) -> CecsProgress:
    frame = load_cecs_template(path)
    final_mask = frame["status"].str.lower().eq("final")
    return CecsProgress(
        final=int(final_mask.sum()),
        total=len(frame),
        draft_tickers=tuple(frame.loc[~final_mask, "ticker"].tolist()),
    )


def import_ai_suggestions(
    *,
    path: Path,
    suggestions: Sequence[ParsedResearchSuggestion],
    report_name: str,
    as_of: date,
    journal_path: Path | None = None,
    allow_reopen_final: bool = False,
) -> CecsBatchImportResult:
    """Atomically import valid parsed rows as non-final AI suggestions.

    Existing ``final`` rows are skipped unless ``allow_reopen_final`` is True
    (explicit reopen path). Final must never be silently demoted by AI import.
    """
    failures: list[str] = []
    imported: list[str] = []
    skipped_final: list[str] = []
    with _WRITE_LOCK:
        frame = _ensure_ai_columns(load_cecs_template(path))
        for suggestion in suggestions:
            ticker = _ticker(suggestion.ticker)
            hits = frame.index[frame["ticker"] == ticker].tolist()
            if len(hits) != 1:
                failures.append(f"{ticker}: CECS template 단일 행 없음")
                continue
            idx = hits[0]
            current_status = str(frame.at[idx, "status"] or "").strip().lower()
            if current_status == "final" and not allow_reopen_final:
                skipped_final.append(ticker)
                failures.append(
                    f"{ticker}: final 상태 — 재개방 없이 AI 제안 덮어쓰기 금지"
                )
                continue
            axes = (
                (
                    suggestion.execution,
                    "execution_continuity",
                    "execution_rationale",
                    "execution_sources",
                ),
                (
                    suggestion.pension,
                    "pension_flow_score",
                    "pension_rationale",
                    "pension_sources",
                ),
                (
                    suggestion.purpose,
                    "investment_purpose_flag",
                    "investment_purpose_rationale",
                    "investment_purpose_sources",
                ),
            )
            for axis, score_col, rationale_col, sources_col in axes:
                frame.at[idx, score_col] = f"{axis.score_100 / 100.0:.2f}"
                frame.at[idx, rationale_col] = axis.rationale.strip()
                frame.at[idx, sources_col] = "\n".join(axis.sources)
            values = {
                key: float(frame.at[idx, key])
                for key in _SCORE_FIELDS
            }
            policy = _float_or_default(
                frame.at[idx, "policy_dependency_flag"],
                0.5,
            )
            cecs = calculate_cecs(
                CatalystInputs(
                    ticker=ticker,
                    name=str(frame.at[idx, "name"]),
                    execution_continuity=values["execution_continuity"],
                    pension_flow_score=values["pension_flow_score"],
                    investment_purpose_flag=values["investment_purpose_flag"],
                    policy_dependency_flag=policy,
                )
            )
            frame.at[idx, "cecs_computed"] = f"{cecs:.2f}"
            frame.at[idx, "scored_by"] = "external_ai_suggestion"
            frame.at[idx, "scored_at"] = as_of.isoformat()
            frame.at[idx, "status"] = "ai_suggested"
            frame.at[idx, "ai_suggested_at"] = as_of.isoformat()
            frame.at[idx, "ai_report_name"] = report_name
            frame.at[idx, "ai_approved_at"] = ""
            imported.append(ticker)
        if imported:
            _atomic_csv_write(frame, path)

    append_record(
        action_kind="CECS_BATCH_IMPORT",
        as_of=as_of,
        subject=report_name,
        rationale=(
            f"CECS AI batch import: {len(imported)} imported, "
            f"{len(failures)} rejected"
        ),
        payload={
            "imported_tickers": imported,
            "failures": failures,
            "skipped_final": skipped_final,
            "status": "ai_suggested",
            "allow_reopen_final": allow_reopen_final,
        },
        journal_path=journal_path,
    )
    return CecsBatchImportResult(
        imported_tickers=tuple(imported),
        failures=tuple(failures),
    )


def reopen_final_for_rescoring(
    *,
    path: Path,
    tickers: Sequence[str],
    reopened_by: str,
    as_of: date,
    reason: str,
    journal_path: Path | None = None,
) -> list[str]:
    """Explicitly reopen final CECS rows to draft so AI import may overwrite.

    Does not write AI scores — only clears final lock. Requires non-empty reason.
    """
    if not str(reason or "").strip():
        raise ValueError("재개방 사유(reason)가 필요합니다.")
    if not str(reopened_by or "").strip():
        raise ValueError("재개방자(reopened_by)가 필요합니다.")
    reopened: list[str] = []
    with _WRITE_LOCK:
        frame = _ensure_ai_columns(load_cecs_template(path))
        for raw in tickers:
            ticker = _ticker(raw)
            hits = frame.index[frame["ticker"] == ticker].tolist()
            if len(hits) != 1:
                continue
            idx = hits[0]
            if str(frame.at[idx, "status"] or "").strip().lower() != "final":
                continue
            frame.at[idx, "status"] = "draft"
            frame.at[idx, "ai_approved_at"] = ""
            reopened.append(ticker)
        if reopened:
            _atomic_csv_write(frame, path)
    if reopened:
        append_record(
            action_kind="CECS_FINAL_REOPEN",
            as_of=as_of,
            subject=",".join(reopened),
            rationale=reason.strip(),
            payload={
                "tickers": reopened,
                "reopened_by": reopened_by.strip(),
                "new_status": "draft",
            },
            journal_path=journal_path,
        )
    return reopened


def approve_ai_suggestions(
    *,
    path: Path,
    tickers: Sequence[str],
    reviewed_tickers: Sequence[str],
    approved_by: str,
    as_of: date,
    overrides: Mapping[str, Mapping[str, Any]] | None = None,
    journal_path: Path | None = None,
) -> CecsApprovalResult:
    """Finalize AI suggestions only after an explicit per-ticker source review."""
    requested = tuple(dict.fromkeys(_ticker(value) for value in tickers))
    reviewed = {_ticker(value) for value in reviewed_tickers}
    missing_review = [ticker for ticker in requested if ticker not in reviewed]
    if missing_review:
        raise ValueError(
            "출처 확인이 필요한 종목: " + ", ".join(missing_review)
        )
    if not requested:
        raise ValueError("승인할 종목이 없습니다.")
    if not approved_by.strip():
        raise ValueError("승인자 이름이 필요합니다.")

    approved: list[tuple[str, dict[str, float], float]] = []
    with _WRITE_LOCK:
        frame = _ensure_ai_columns(load_cecs_template(path))
        for ticker in requested:
            hits = frame.index[frame["ticker"] == ticker].tolist()
            if len(hits) != 1:
                raise ValueError(f"{ticker}: CECS template 단일 행 없음")
            idx = hits[0]
            if str(frame.at[idx, "status"]).strip().lower() != "ai_suggested":
                raise ValueError(f"{ticker}: ai_suggested 상태가 아닙니다.")
            override = dict((overrides or {}).get(ticker, {}))
            values = {
                "execution_continuity": float(
                    override.get(
                        "execution_continuity",
                        frame.at[idx, "execution_continuity"],
                    )
                ),
                "pension_flow_score": float(
                    override.get(
                        "pension_flow_score",
                        frame.at[idx, "pension_flow_score"],
                    )
                ),
                "investment_purpose_flag": float(
                    override.get(
                        "investment_purpose_flag",
                        frame.at[idx, "investment_purpose_flag"],
                    )
                ),
            }
            if any(not 0.0 <= value <= 1.0 for value in values.values()):
                raise ValueError(f"{ticker}: 승인 점수는 0.0~1.0이어야 합니다.")
            rationales = {
                field: str(override.get(field, frame.at[idx, field])).strip()
                for field in _RATIONALE_FIELDS
            }
            if any(not value for value in rationales.values()):
                raise ValueError(f"{ticker}: 승인 근거 3개가 모두 필요합니다.")
            source_columns = (
                "execution_sources",
                "pension_sources",
                "investment_purpose_sources",
            )
            sources = {
                column: str(frame.at[idx, column]).strip()
                for column in source_columns
            }
            missing_sources = [
                column for column, value in sources.items() if not value
            ]
            if missing_sources:
                raise ValueError(f"{ticker}: 출처 3축이 모두 필요합니다.")

            approval_tag = f"AI 제안 기반, 사용자 승인일 {as_of.isoformat()}"
            for position, rationale_field in enumerate(_RATIONALE_FIELDS):
                source_text = sources[source_columns[position]]
                frame.at[idx, rationale_field] = (
                    f"{rationales[rationale_field]}\n\n"
                    f"출처:\n{source_text}\n\n[{approval_tag}]"
                )
            for key, value in values.items():
                frame.at[idx, key] = f"{value:.2f}"
            policy = _float_or_default(
                frame.at[idx, "policy_dependency_flag"],
                0.5,
            )
            cecs = calculate_cecs(
                CatalystInputs(
                    ticker=ticker,
                    name=str(frame.at[idx, "name"]),
                    execution_continuity=values["execution_continuity"],
                    pension_flow_score=values["pension_flow_score"],
                    investment_purpose_flag=values["investment_purpose_flag"],
                    policy_dependency_flag=policy,
                )
            )
            frame.at[idx, "cecs_computed"] = f"{cecs:.2f}"
            frame.at[idx, "scored_by"] = approved_by.strip()
            frame.at[idx, "scored_at"] = as_of.isoformat()
            frame.at[idx, "status"] = "final"
            frame.at[idx, "ai_approved_at"] = as_of.isoformat()
            approved.append((ticker, values, cecs))
        _atomic_csv_write(frame, path)

    progress = cecs_progress(path)
    for ticker, values, cecs in approved:
        append_record(
            action_kind="CECS_SCORE_APPROVED",
            as_of=as_of,
            subject=ticker,
            rationale="AI 제안 출처 확인 후 사용자 승인",
            score_snapshot={**values, "cecs": cecs},
            payload={
                "approved_by": approved_by.strip(),
                "approval_date": as_of.isoformat(),
                "final": progress.final,
                "total": progress.total,
            },
            journal_path=journal_path,
        )
    return CecsApprovalResult(
        approved_tickers=tuple(ticker for ticker, _, _ in approved),
        final=progress.final,
        total=progress.total,
    )


def generate_correlation_report(
    *,
    cecs_path: Path,
    factor_path: Path,
    output_path: Path,
    as_of: date,
) -> tuple[CorrelationReport, Path]:
    cecs = load_cecs_template(cecs_path)
    progress = cecs_progress(cecs_path)
    if progress.total < 30 or progress.final < progress.total:
        raise ValueError(
            f"CECS 채점 완료 후 활성화됩니다 ({progress.final}/{progress.total})."
        )
    if not factor_path.exists():
        raise FileNotFoundError(factor_path)
    factors = pd.read_csv(factor_path, dtype=str)
    required = {"ticker", "score_q", "score_v", "score_sr", "score_r"}
    missing = sorted(required - set(factors.columns))
    if missing:
        raise ValueError(f"팩터 CSV 필수 열 누락: {missing}")

    cecs["ticker"] = cecs["ticker"].map(_ticker)
    factors["ticker"] = factors["ticker"].map(_ticker)
    merged = cecs[cecs["status"].str.lower() == "final"].merge(
        factors,
        on="ticker",
        how="left",
        suffixes=("_cecs", ""),
    )
    merged["cecs"] = pd.to_numeric(merged["cecs_computed"], errors="coerce")
    sector_col = "sector_cecs" if "sector_cecs" in merged.columns else "sector"
    report_frame = merged[
        ["ticker", sector_col, "score_q", "score_v", "score_sr", "score_r", "cecs"]
    ].rename(columns={sector_col: "sector"})
    report = analyze_factor_correlation(report_frame, as_of=as_of)
    return report, write_correlation_report(report, output_path)


def build_relative_cutoff_ladder(
    scored_names: Sequence[Mapping[str, Any]],
    *,
    min_rank: int = 6,
) -> tuple[CutoffRankOption, ...]:
    """Build rank→cutoff options from the current shortlist scores (no hardcoded cutoff)."""
    cleaned: list[tuple[str, str, float]] = []
    for row in scored_names:
        score = row.get("total_score")
        if score is None:
            continue
        try:
            value = float(score)
        except (TypeError, ValueError):
            continue
        cleaned.append(
            (
                _ticker(row.get("ticker")),
                str(row.get("name") or ""),
                value,
            )
        )
    cleaned.sort(key=lambda item: (-item[2], item[0]))
    if not cleaned:
        return ()

    start = max(1, min(min_rank, len(cleaned)))
    margins = []
    for index in range(len(cleaned) - 1):
        margins.append(cleaned[index][2] - cleaned[index + 1][2])
    top_breaks = set()
    if margins:
        ranked = sorted(range(len(margins)), key=lambda i: margins[i], reverse=True)
        for index in ranked[:3]:
            if margins[index] > 0:
                top_breaks.add(index + 1)  # rank_n after which the gap sits

    options: list[CutoffRankOption] = []
    for rank_n in range(start, len(cleaned) + 1):
        ticker, name, cutoff = cleaned[rank_n - 1]
        eligible = sum(1 for _, _, score in cleaned if score >= cutoff)
        if rank_n < len(cleaned):
            next_ticker, next_name, next_score = cleaned[rank_n]
            margin = cutoff - next_score
        else:
            next_ticker = next_name = next_score = None
            margin = None
        options.append(
            CutoffRankOption(
                rank_n=rank_n,
                cutoff=round(cutoff, 4),
                eligible_count=eligible,
                margin_below=None if margin is None else round(margin, 4),
                boundary_ticker=ticker,
                boundary_name=name,
                next_ticker=next_ticker,
                next_name=next_name,
                next_score=None if next_score is None else round(next_score, 4),
                is_natural_break=rank_n in top_breaks,
            )
        )
    return tuple(options)


def default_relative_cutoff_rank(
    options: Sequence[CutoffRankOption],
) -> int:
    """Prefer the largest natural score gap; else keep the widest eligible pool."""
    breaks = [option for option in options if option.is_natural_break]
    if breaks:
        return max(breaks, key=lambda option: option.margin_below or 0.0).rank_n
    if options:
        return options[-1].rank_n
    return 6


def confirm_score_cutoff(
    *,
    config_path: Path,
    cecs_path: Path,
    cutoff: float,
    confirm_understood: bool,
    confirm_final: bool,
    as_of: date,
    journal_path: Path | None = None,
    eligible_count: int | None = None,
    rank_n: int | None = None,
    method: str = "manual",
    target_names: int | None = None,
) -> Path:
    """Persist cutoff (and optional portfolio count) after explicit confirmation."""
    if not (confirm_understood and confirm_final):
        raise ValueError("컷오프 확정에는 2단계 확인이 모두 필요합니다.")
    # Ops A: cutoff is quant-only; CECS finals no longer gate confirmation.
    cutoff_f = float(cutoff)
    if not 0.0 <= cutoff_f <= 100.0:
        raise ValueError("score_cutoff은 0~100 범위여야 합니다.")
    if target_names is not None and not 5 <= int(target_names) <= 8:
        raise ValueError("편입 종목 수는 초기 설계 범위 5~8이어야 합니다.")

    text = config_path.read_text(encoding="utf-8")
    cutoff_pattern = re.compile(r"(?m)^(\s{2}score_cutoff:\s*).*$")
    if len(cutoff_pattern.findall(text)) != 1:
        raise ValueError("config에서 scoring.score_cutoff 단일 행을 찾을 수 없습니다.")
    changed = cutoff_pattern.sub(rf"\g<1>{cutoff_f:g}", text, count=1)
    if target_names is not None:
        names_pattern = re.compile(r"(?m)^(\s{2}target_names:\s*).*$")
        if len(names_pattern.findall(changed)) != 1:
            raise ValueError("config에서 sizing.target_names 단일 행을 찾을 수 없습니다.")
        changed = names_pattern.sub(
            rf"\g<1>{int(target_names)}",
            changed,
            count=1,
        )
    if changed == text:
        raise ValueError("편입 종목 수와 score_cutoff 값이 이미 동일합니다.")

    with _WRITE_LOCK:
        backup_dir = config_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = backup_dir / f"{config_path.stem}_before_cutoff_{stamp}.yaml"
        shutil.copy2(config_path, backup)

        temp_path = _temp_path(config_path)
        try:
            temp_path.write_text(changed, encoding="utf-8")
            load_config(temp_path)  # schema validation before replacement
            os.replace(temp_path, config_path)
        finally:
            temp_path.unlink(missing_ok=True)

    append_record(
        action_kind=(
            "PORTFOLIO_COUNT_CUTOFF_CONFIRMED"
            if target_names is not None
            else "SCORE_CUTOFF_CONFIRMED"
        ),
        as_of=as_of,
        subject="scoring.score_cutoff",
        rationale=(
            "CECS 30/30 후 절대 score_cutoff 확정 + 편입 수(5~8) 2단계 승인"
            if target_names is not None
            else "CECS 30/30 및 상관 검토 후 절대 score_cutoff 2단계 승인"
        ),
        payload={
            "cutoff": cutoff_f,
            "backup": str(backup),
            "eligible_count": eligible_count,
            "rank_n": rank_n,
            "method": method,
            "target_names": target_names,
        },
        journal_path=journal_path,
    )
    return backup


def _atomic_csv_write(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _temp_path(path)
    try:
        frame.to_csv(temp_path, index=False, encoding="utf-8-sig")
        # Read-back contract check before replacing the source.
        checked = pd.read_csv(temp_path, dtype=str, keep_default_na=False)
        if list(checked.columns) != list(frame.columns) or len(checked) != len(frame):
            raise ValueError("CECS 임시 파일 검증 실패")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _ensure_ai_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in _AI_COLUMNS:
        if column not in result.columns:
            result[column] = ""
    return result


def _temp_path(path: Path) -> Path:
    handle, raw = tempfile.mkstemp(
        prefix=f".{path.stem}_",
        suffix=path.suffix,
        dir=path.parent,
    )
    os.close(handle)
    return Path(raw)


def _ticker(value: object) -> str:
    text = str(value).strip()
    return text.zfill(6) if text.isdigit() else text


def _float_or_default(value: object, default: float) -> float:
    try:
        text = str(value).strip()
        return float(text) if text else default
    except (TypeError, ValueError):
        return default
