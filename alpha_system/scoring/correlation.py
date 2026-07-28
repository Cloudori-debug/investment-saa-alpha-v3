"""Factor correlation analysis — never fabricates results without data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from alpha_system.scoring.factors import FIVE_FACTORS, load_scoring_config


@dataclass
class CorrPair:
    factor_a: str
    factor_b: str
    rho: float
    n: int


@dataclass
class SectorFallbackRow:
    ticker: str
    sector: str
    sector_sample_n: int
    sector_peer_fallback: bool


@dataclass
class CorrelationReport:
    status: str  # OK | SKIPPED
    as_of: date
    method: str
    threshold: float
    n_names: int
    high_pairs: list[CorrPair] = field(default_factory=list)
    matrix: Optional[pd.DataFrame] = None
    data_requirements: list[str] = field(default_factory=list)
    skip_reasons: list[str] = field(default_factory=list)
    simplification_notes: list[str] = field(default_factory=list)
    sector_min_sample: int = 5
    sector_fallback_rows: list[SectorFallbackRow] = field(default_factory=list)


def data_requirements() -> list[str]:
    return [
        f"DataFrame with columns: ticker + {', '.join(FIVE_FACTORS)}",
        "Each factor column numeric on a comparable scale "
        "(Q/V/SR/R typically 0~100; cecs 0~100).",
        "One row per name; NaN rows are dropped pairwise per correlation cell.",
        f"Minimum distinct names: scoring.yaml correlation.min_names "
        f"(default 20) after dropping all-NaN factor rows.",
        "Point-in-time / same as_of snapshot recommended "
        "(do not mix fiscal years across columns).",
        "Do not impute missing factors with peer means for this report — "
        "missingness should remain visible (pairwise complete).",
        "disclosure_status / independent_catalyst_flag are NOT score factors "
        "(mapped to T2 event_candidate_sources).",
        "Optional columns: ticker, sector — when present, report flags names "
        "whose sector peer group has < sector_min_sample rows in this snapshot "
        "(Q/V percentile uses market-wide fallback for those names).",
    ]


def compute_sector_fallback_flags(
    df: pd.DataFrame,
    *,
    min_sector_sample: int = 5,
    ticker_col: str = "ticker",
    sector_col: str = "sector",
) -> list[SectorFallbackRow]:
    """Flag tickers in under-sampled sector peer groups (alpha_portfolio Q/V rule)."""
    if ticker_col not in df.columns or sector_col not in df.columns:
        return []

    work = df[[ticker_col, sector_col]].copy()
    work[ticker_col] = work[ticker_col].astype(str).str.zfill(6)
    work[sector_col] = work[sector_col].astype(str).str.strip()
    work = work[work[sector_col].ne("") & work[sector_col].str.lower().ne("unknown")]

    counts = work.groupby(sector_col, dropna=False).size().to_dict()
    rows: list[SectorFallbackRow] = []
    for _, row in work.iterrows():
        sector = str(row[sector_col])
        n = int(counts.get(sector, 0))
        rows.append(
            SectorFallbackRow(
                ticker=str(row[ticker_col]),
                sector=sector,
                sector_sample_n=n,
                sector_peer_fallback=n < min_sector_sample,
            )
        )
    return sorted(rows, key=lambda r: (r.sector, r.ticker))


def analyze_factor_correlation(
    df: pd.DataFrame | None,
    *,
    as_of: date | None = None,
    scoring_cfg: dict[str, Any] | None = None,
) -> CorrelationReport:
    """
    Compute pairwise Pearson correlations among FIVE_FACTORS.

    If data is missing or insufficient, status=SKIPPED and high_pairs stays empty.
    Never invents correlation numbers.
    """
    scfg = scoring_cfg or load_scoring_config()
    corr_cfg = dict(scfg.get("correlation") or {})
    threshold = float(corr_cfg.get("high_abs_corr_threshold", 0.70))
    min_names = int(corr_cfg.get("min_names", 20))
    min_sector_sample = int(corr_cfg.get("sector_min_sample", 5))
    method = str(corr_cfg.get("method", "pearson"))
    as_of_d = as_of or date.today()
    reqs = data_requirements()

    if df is None or df.empty:
        return CorrelationReport(
            status="SKIPPED",
            as_of=as_of_d,
            method=method,
            threshold=threshold,
            n_names=0,
            data_requirements=reqs,
            skip_reasons=["no factor DataFrame provided (or empty)"],
            simplification_notes=[
                "Cannot propose merges until a real cross-section is supplied."
            ],
        )

    missing_cols = [c for c in FIVE_FACTORS if c not in df.columns]
    if missing_cols:
        return CorrelationReport(
            status="SKIPPED",
            as_of=as_of_d,
            method=method,
            threshold=threshold,
            n_names=len(df),
            data_requirements=reqs,
            skip_reasons=[f"missing columns: {missing_cols}"],
        )

    work = df.loc[:, list(FIVE_FACTORS)].apply(pd.to_numeric, errors="coerce")
    # Drop rows that are entirely NaN across factors
    work = work.dropna(how="all")
    n_names = len(work)
    fallback_rows: list[SectorFallbackRow] = []
    if "ticker" in df.columns and "sector" in df.columns:
        aligned = df.loc[work.index, ["ticker", "sector"]]
        fallback_rows = compute_sector_fallback_flags(
            aligned,
            min_sector_sample=min_sector_sample,
        )
    if n_names < min_names:
        return CorrelationReport(
            status="SKIPPED",
            as_of=as_of_d,
            method=method,
            threshold=threshold,
            n_names=n_names,
            data_requirements=reqs,
            skip_reasons=[
                f"n_names={n_names} < min_names={min_names} — refuse underpowered estimate"
            ],
            sector_min_sample=min_sector_sample,
            sector_fallback_rows=fallback_rows,
        )

    matrix = work.corr(method=method)
    high: list[CorrPair] = []
    cols = list(FIVE_FACTORS)
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            rho = matrix.loc[a, b]
            if pd.isna(rho):
                continue
            # pairwise n
            pair_n = int(work[[a, b]].dropna().shape[0])
            if abs(float(rho)) >= threshold:
                high.append(
                    CorrPair(factor_a=a, factor_b=b, rho=float(rho), n=pair_n)
                )

    notes = [
        "Score axes are FIVE_FACTORS after CECS-T2 overlap cleanup "
        "(disclosure_status / independent_catalyst_flag → T2 candidates).",
        "Prefer merging among atomic axes when |rho| stays high out-of-sample.",
    ]
    if high:
        notes.append(
            "High pairs listed below are candidates only — decide simplification "
            "after reviewing economic overlap (e.g. value vs shareholder_return)."
        )
    else:
        notes.append(
            f"No pair with |rho| >= {threshold} in this snapshot."
        )
    fb_n = sum(1 for r in fallback_rows if r.sector_peer_fallback)
    if fallback_rows:
        notes.append(
            f"sector_peer_fallback: {fb_n}/{len(fallback_rows)} names have sector "
            f"peer sample < {min_sector_sample} in this CSV — Q/V percentile uses "
            "market-wide fallback for those rows (see gate_pass pool: ~32 sectors)."
        )

    return CorrelationReport(
        status="OK",
        as_of=as_of_d,
        method=method,
        threshold=threshold,
        n_names=n_names,
        high_pairs=sorted(high, key=lambda p: -abs(p.rho)),
        matrix=matrix,
        data_requirements=reqs,
        simplification_notes=notes,
        sector_min_sample=min_sector_sample,
        sector_fallback_rows=fallback_rows,
    )


def render_correlation_markdown(report: CorrelationReport) -> str:
    lines = [
        "# 알파 시스템 — 5팩터 상관 점검 리포트",
        "",
        f"- as_of: `{report.as_of.isoformat()}`",
        f"- status: **{report.status}**",
        f"- method: `{report.method}`",
        f"- high_|rho|_threshold: `{report.threshold}`",
        f"- n_names: `{report.n_names}`",
        "",
        "## 데이터 요건",
        "",
    ]
    for req in report.data_requirements:
        lines.append(f"- {req}")
    lines.append("")

    if report.skip_reasons:
        lines.append("## SKIP 사유")
        lines.append("")
        for reason in report.skip_reasons:
            lines.append(f"- {reason}")
        lines.append("")
        lines.append(
            "> 가짜 상관·합성 표본으로 수치를 채우지 않음. "
            "요건을 충족하는 스냅샷을 넣은 뒤 재실행할 것."
        )
        lines.append("")

    lines.append("## 높은 상관 쌍 (후보)")
    lines.append("")
    if report.status != "OK":
        lines.append("_분석 미실행 — 쌍 목록 없음._")
        lines.append("")
    elif not report.high_pairs:
        lines.append("_임계값 이상인 쌍 없음._")
        lines.append("")
    else:
        lines.append("| factor_a | factor_b | rho | pairwise_n |")
        lines.append("|---|---|---:|---:|")
        for p in report.high_pairs:
            lines.append(
                f"| {p.factor_a} | {p.factor_b} | {p.rho:.3f} | {p.n} |"
            )
        lines.append("")

    if report.matrix is not None and report.status == "OK":
        lines.append("## 상관 행렬")
        lines.append("")
        mat = report.matrix.round(3)
        header = "| factor | " + " | ".join(mat.columns.astype(str)) + " |"
        sep = "|---|" + "|".join(["---:" for _ in mat.columns]) + "|"
        lines.append(header)
        lines.append(sep)
        for idx, row in mat.iterrows():
            cells = " | ".join(f"{v:.3f}" if pd.notna(v) else "" for v in row.tolist())
            lines.append(f"| {idx} | {cells} |")
        lines.append("")

    if report.sector_fallback_rows:
        fb = [r for r in report.sector_fallback_rows if r.sector_peer_fallback]
        lines.append("## 섹터 백분위 fallback (표본<5)")
        lines.append("")
        lines.append(
            f"- `sector_min_sample`: **{report.sector_min_sample}** "
            "(alpha_portfolio Q/V percentile peer rule)"
        )
        lines.append(
            f"- fallback 적용 종목: **{len(fb)}** / {len(report.sector_fallback_rows)} "
            f"(이 CSV 스냅샷 내 동일 sector 표본 < {report.sector_min_sample})"
        )
        lines.append(
            "- gate_pass 159 풀 기준 약 32개 업종이 fallback 대상 — "
            "상관 해석 시 V/Q peer 품질 참고"
        )
        lines.append("")
        lines.append(
            "| ticker | sector | sector_sample_n | sector_peer_fallback |"
        )
        lines.append("|---|---|---:|:---:|")
        for row in report.sector_fallback_rows:
            flag = "Y" if row.sector_peer_fallback else ""
            lines.append(
                f"| {row.ticker} | {row.sector} | {row.sector_sample_n} | {flag} |"
            )
        lines.append("")

    lines.append("## 통합·단순화 제안 메모")
    lines.append("")
    for note in report.simplification_notes:
        lines.append(f"- {note}")
    lines.append("")
    lines.append(
        "최종 팩터 단순화 여부는 **OK 리포트의 high_pairs**를 보고 사용자가 판단한다."
    )
    lines.append("")
    return "\n".join(lines)


def write_correlation_report(
    report: CorrelationReport,
    path: Path,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_correlation_markdown(report), encoding="utf-8")
    return path
