"""Economy page — dividend / SR candidates (Review-only).

Reads the market mid-book alpha_scores + dividend_yield. Does not change
QVM ranks, write target_portfolio.csv, or mix Core score_m.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from alpha_system.screen_book import alpha_data_dir, normalize_market, source_data_dir


@dataclass(frozen=True)
class DividendCandidate:
    ticker: str
    name: str
    score_sr: float
    composite: Optional[float] = None
    dividend_yield: Optional[float] = None
    sector: str = ""


@dataclass(frozen=True)
class DividendSleeveHint:
    """Rate-regime hint for the dividend sleeve — not an order."""

    tone: str  # favor | neutral | caution
    title: str
    detail: str


def dividend_sleeve_hint(stage: int | None) -> DividendSleeveHint:
    """Map economy ladder stage → how to read dividend candidates."""
    if stage is None:
        return DividendSleeveHint(
            tone="neutral",
            title="단계 없음",
            detail="경제 시그널을 다시 계산한 뒤, 배당·환원 후보를 참고하세요.",
        )
    s = int(stage)
    if s <= 2:
        return DividendSleeveHint(
            tone="favor",
            title="배당·환원 상대 매력↑",
            detail=(
                "금리·신용이 여유인 구간입니다. 중기 SR·배당 상위는 "
                "저가 추격이 아니라 중기 논지·목표가와 같이 보세요. Review-only."
            ),
        )
    if s == 3:
        return DividendSleeveHint(
            tone="neutral",
            title="중립 · 배당은 참고",
            detail="비중 단계가 중립입니다. 배당 후보는 중기 북 SR만 참고하고 추격하지 마세요.",
        )
    return DividendSleeveHint(
        tone="caution",
        title="긴축·방어 · 고배당 추격 자제",
        detail=(
            "금리·신용 압력이 큰 구간입니다. 배당수익률만 보고 담지 말고, "
            "중기 본전·현금 비중을 우선하세요. Review-only."
        ),
    )


def _f(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        import math

        x = float(val)
        if math.isnan(x):
            return None
        return x
    except (TypeError, ValueError):
        return None


def _norm_ticker(raw: object) -> str:
    text = str(raw or "").strip()
    if text.isdigit():
        return text.zfill(6)
    return text


def _load_dividend_yields(root: Path, market: object | None) -> dict[str, float]:
    out: dict[str, float] = {}
    paths = [
        alpha_data_dir(Path(root), normalize_market(market)) / "input" / "screening_universe.csv",
        source_data_dir(Path(root), normalize_market(market)) / "fundamentals.csv",
    ]
    try:
        import pandas as pd
    except ImportError:
        return out
    for path in paths:
        if not path.is_file():
            continue
        try:
            df = pd.read_csv(path, dtype=str)
        except (OSError, ValueError):
            continue
        if df.empty or "ticker" not in df.columns:
            continue
        dy_col = "dividend_yield" if "dividend_yield" in df.columns else None
        if dy_col is None:
            continue
        for _, row in df.iterrows():
            tk = _norm_ticker(row.get("ticker"))
            dy = _f(row.get(dy_col))
            if tk and dy is not None and tk not in out:
                out[tk] = dy
    return out


def load_dividend_candidates(
    root: Path,
    *,
    market: object | None = "KOSPI",
    limit: int = 8,
    min_score_sr: float = 55.0,
    min_dividend_yield: float | None = None,
) -> tuple[DividendCandidate, ...]:
    """Top mid-book names by score_sr (gate_pass preferred)."""
    path = alpha_data_dir(Path(root), normalize_market(market)) / "output" / "alpha_scores.csv"
    if not path.is_file():
        return ()
    try:
        import pandas as pd

        df = pd.read_csv(path, dtype=str)
    except (OSError, ValueError):
        return ()
    if df.empty or "ticker" not in df.columns or "score_sr" not in df.columns:
        return ()

    work = df.copy()
    work["ticker"] = work["ticker"].map(_norm_ticker)
    work["score_sr"] = pd.to_numeric(work["score_sr"], errors="coerce")
    work["composite_score"] = pd.to_numeric(
        work.get("composite_score", work.get("composite_raw")), errors="coerce"
    )
    work = work.dropna(subset=["score_sr"])
    if "gate_pass" in work.columns:
        gp = work["gate_pass"].astype(str).str.lower().str.strip()
        passed = work[gp.isin({"true", "1", "1.0", "yes"})]
        if not passed.empty:
            work = passed
    work = work[work["score_sr"] >= float(min_score_sr)]
    if work.empty:
        return ()

    dy_map = _load_dividend_yields(Path(root), market)
    rows: list[DividendCandidate] = []
    for _, row in work.sort_values(["score_sr", "ticker"], ascending=[False, True]).iterrows():
        tk = _norm_ticker(row.get("ticker"))
        dy = dy_map.get(tk)
        if min_dividend_yield is not None and (dy is None or dy < float(min_dividend_yield)):
            continue
        rows.append(
            DividendCandidate(
                ticker=tk,
                name=str(row.get("name") or tk).strip() or tk,
                score_sr=float(row["score_sr"]),
                composite=_f(row.get("composite_score")),
                dividend_yield=dy,
                sector=str(row.get("sector") or "").strip(),
            )
        )
        if len(rows) >= int(limit):
            break
    return tuple(rows)
