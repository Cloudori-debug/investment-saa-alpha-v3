"""Observation-pool watch board — display only (not proposal sizing).

Rank = names with a total_score, descending. Eligibility / book size only
color the rows; they do not shrink the observation pool (default 30).
Sector cap is NOT applied on this board.
Does not write target_portfolio or change selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from alpha_system.ui.services.context import ScoreboardRow

DEFAULT_WATCH_MAX = 30
_NAVER_FCHART = "https://finance.naver.com/item/fchart.naver?code={code}"


def naver_fchart_url(ticker: str) -> str:
    digits = "".join(ch for ch in str(ticker or "") if ch.isdigit())
    code = digits.zfill(6) if digits else ""
    return _NAVER_FCHART.format(code=code)


def naver_fchart_link(ticker: str, name: str | None = None) -> str:
    """Naver daily chart URL. Fragment is the name for Streamlit LinkColumn."""
    url = naver_fchart_url(ticker)
    label = str(name or ticker or "").strip() or ticker
    label = label.replace("#", " ").strip() or str(ticker)
    return f"{url}#{label}"

TONE_PROPOSAL = "제안"
TONE_ELIGIBLE = "적격"
TONE_WATCH = "관찰"


@dataclass(frozen=True)
class RankWatchRow:
    rank: int
    ticker: str
    name: str
    total_score: Optional[float]
    sector: str
    is_held: bool
    in_proposal: bool
    eligibility: Optional[bool]
    eligibility_reason: str = ""


@dataclass(frozen=True)
class RankWatchBoard:
    rows: tuple[RankWatchRow, ...]
    held_outside: tuple[RankWatchRow, ...]
    eligible_count: int
    proposal_band_max: int
    max_rows: int
    basis: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class WatchTableRow:
    """Observation-pool row with fundamentals for the portfolio table."""

    rank: int
    ticker: str
    name: str
    total_score: Optional[float]
    sector: str
    is_held: bool
    in_proposal: bool
    eligibility: Optional[bool]
    tone: str
    judgment: str
    per: Optional[float]
    pbr: Optional[float]
    roe: Optional[float]
    current_price: Optional[float]
    target_price: Optional[float]


def _norm_ticker(raw: object) -> str:
    text = str(raw or "").strip()
    if text.isdigit():
        return text.zfill(6)
    return text


def _as_float(val: object) -> Optional[float]:
    if val is None:
        return None
    try:
        if isinstance(val, str) and not val.strip():
            return None
        out = float(val)
    except (TypeError, ValueError):
        return None
    if out != out:  # NaN
        return None
    return out


def _overlay_collect_fundamentals(data: Path, slot_fn) -> None:
    """Fill blank ops PER/PBR/ROE from the collect file used to score names."""
    import pandas as pd

    from alpha_system.screen_book import resolve_quality_fundamentals_csv

    path = resolve_quality_fundamentals_csv(data)
    if path is None or not path.exists():
        return
    try:
        alpha = pd.read_csv(path, dtype={"ticker": str})
    except Exception:
        return
    if alpha.empty or "ticker" not in alpha.columns:
        return
    alpha["ticker"] = alpha["ticker"].astype(str).map(_norm_ticker)
    alpha = alpha.drop_duplicates("ticker", keep="last")
    for _, row in alpha.iterrows():
        slot = slot_fn(row["ticker"])
        if slot["roe"] is None:
            slot["roe"] = _as_float(row.get("roe"))
            if slot["roe"] is None:
                slot["roe"] = _as_float(row.get("roe_3y_avg"))
        if slot["per"] is None:
            slot["per"] = _as_float(row.get("per"))
        if slot["pbr"] is None:
            slot["pbr"] = _as_float(row.get("pbr"))


def watch_preview_tone(
    *,
    score: float | None,
    cutoff: float | None,
    eligible_rank: int | None,
    target_n: int,
    in_proposal: bool | None = None,
) -> str:
    """Color band for the observation table (preview, not yaml confirm).

    제안 = 실제 제안 북(있으면) 또는 컷 통과 중 상위 target_n.
    적격 = 컷 통과·북 밖. 관찰 = 컷 미달.
    cutoff is None → treat scored names as passing (provisional).
    """
    cap = max(1, int(target_n))
    if score is None:
        return TONE_WATCH
    if in_proposal is True:
        return TONE_PROPOSAL
    if cutoff is None:
        if in_proposal is False:
            return TONE_ELIGIBLE
        if eligible_rank is not None and eligible_rank <= cap:
            return TONE_PROPOSAL
        return TONE_ELIGIBLE
    if float(score) < float(cutoff):
        return TONE_WATCH
    if in_proposal is False:
        return TONE_ELIGIBLE
    if eligible_rank is not None and eligible_rank <= cap:
        return TONE_PROPOSAL
    return TONE_ELIGIBLE


def eligible_ranks_for_cutoff(
    rows: Sequence[RankWatchRow],
    cutoff: float | None,
) -> dict[str, int]:
    """1-based rank among names that pass the preview cutoff."""
    if cutoff is None:
        passing = [r for r in rows if r.total_score is not None]
    else:
        bar = float(cutoff)
        passing = [
            r for r in rows if r.total_score is not None and r.total_score >= bar
        ]
    passing.sort(key=lambda r: (-r.total_score, r.ticker))
    return {r.ticker: i for i, r in enumerate(passing, start=1)}


def build_rank_watchboard(
    scoreboard: Sequence[ScoreboardRow],
    *,
    proposal_tickers: set[str] | None = None,
    held_tickers: set[str] | None = None,
    proposal_band_max: int = 8,
    max_rows: int = DEFAULT_WATCH_MAX,
) -> RankWatchBoard:
    """Build top-N scored ranks for monitoring (observation pool).

    Parameters
    ----------
    proposal_tickers
        Current proposal_book tickers (highlight).
    held_tickers
        Ops holdings; if None, use ScoreboardRow.is_held.
    proposal_band_max
        UI hint for 'inside proposal band' (usually sizing.target_names).
    max_rows
        Cap board length (default 30 = CECS shortlist / observation pool).
        The live proposal book is sizing.target_names (5–8), not this cap.
        Below-cutoff names stay on the board; eligibility only colors them.
    """
    prop = {_norm_ticker(t) for t in (proposal_tickers or set())}
    held_override = None
    if held_tickers is not None:
        held_override = {_norm_ticker(t) for t in held_tickers}

    warnings: list[str] = []
    scored: list[tuple[ScoreboardRow, float]] = []
    unscored: list[ScoreboardRow] = []
    for row in scoreboard:
        if row.total_score is None:
            unscored.append(row)
            continue
        try:
            score = float(row.total_score)
        except (TypeError, ValueError):
            unscored.append(row)
            continue
        scored.append((row, score))

    if not scored and not unscored:
        return RankWatchBoard(
            rows=(),
            held_outside=(),
            eligible_count=0,
            proposal_band_max=int(proposal_band_max),
            max_rows=max(1, int(max_rows)),
            basis="total_score 내림차순 · 섹터캡 미적용 · 관찰 풀",
            warnings=("표시할 스코어가 없습니다.",),
        )

    true_n = sum(1 for row, _ in scored if row.eligibility is True)
    if true_n == 0:
        warnings.append(
            "eligibility=True 종목이 없어 점수 있는 전 종목 순위로 표시합니다 "
            "(score_cutoff·CECS를 확인하세요)."
        )

    def _held(row: ScoreboardRow) -> bool:
        ticker = _norm_ticker(row.ticker)
        if held_override is not None:
            return ticker in held_override
        return bool(row.is_held)

    def _item(
        rank: int, row: ScoreboardRow, score: float | None
    ) -> RankWatchRow:
        ticker = _norm_ticker(row.ticker)
        return RankWatchRow(
            rank=rank,
            ticker=ticker,
            name=(row.name or ticker).strip() or ticker,
            total_score=None if score is None else round(score, 2),
            sector=(row.sector or "").strip(),
            is_held=_held(row),
            in_proposal=ticker in prop,
            eligibility=row.eligibility,
            eligibility_reason=str(getattr(row, "eligibility_reason", "") or ""),
        )

    scored.sort(key=lambda x: (-x[1], _norm_ticker(x[0].ticker)))
    ranked: list[RankWatchRow] = []
    for i, (row, score) in enumerate(scored, start=1):
        ranked.append(_item(i, row, score))
    next_rank = len(ranked) + 1
    for row in unscored:
        ranked.append(_item(next_rank, row, None))
        next_rank += 1

    max_n = max(1, int(max_rows))
    board = tuple(ranked[:max_n])
    board_tickers = {r.ticker for r in board}
    held_outside = tuple(
        r for r in ranked if r.is_held and r.ticker not in board_tickers
    )

    return RankWatchBoard(
        rows=board,
        held_outside=held_outside,
        eligible_count=true_n,
        proposal_band_max=int(proposal_band_max),
        max_rows=max_n,
        basis="total_score 내림차순 · 섹터캡 미적용 · 관찰 풀 (컷오프는 색만)",
        warnings=tuple(warnings),
    )


def load_watch_metrics(
    root: Path, *, data_dir: Path | None = None
) -> dict[str, dict[str, Optional[float]]]:
    """Latest PER/PBR/ROE, last close, and exit/quant target per ticker."""
    import pandas as pd

    data = Path(data_dir) if data_dir is not None else Path(root) / "data"
    out: dict[str, dict[str, Optional[float]]] = {}

    def _slot(ticker: str) -> dict[str, Optional[float]]:
        tk = _norm_ticker(ticker)
        slot = out.get(tk)
        if slot is None:
            slot = {
                "per": None,
                "pbr": None,
                "roe": None,
                "price": None,
                "target": None,
            }
            out[tk] = slot
        return slot

    fund_path = data / "fundamentals.csv"
    if fund_path.exists():
        try:
            fund = pd.read_csv(fund_path, dtype={"ticker": str})
        except Exception:
            fund = None
        if fund is not None and not fund.empty and "ticker" in fund.columns:
            fund["ticker"] = fund["ticker"].astype(str).map(_norm_ticker)
            if "period_end" in fund.columns:
                fund = fund.sort_values("period_end").drop_duplicates(
                    "ticker", keep="last"
                )
            else:
                fund = fund.drop_duplicates("ticker", keep="last")
            for _, row in fund.iterrows():
                slot = _slot(row["ticker"])
                slot["per"] = _as_float(row.get("per"))
                slot["pbr"] = _as_float(row.get("pbr"))
                slot["roe"] = _as_float(row.get("roe"))

    _overlay_collect_fundamentals(data, _slot)

    price_path = data / "prices.csv"
    if price_path.exists():
        try:
            prices = pd.read_csv(price_path, dtype={"ticker": str})
        except Exception:
            prices = None
        if prices is not None and not prices.empty and "ticker" in prices.columns:
            prices["ticker"] = prices["ticker"].astype(str).map(_norm_ticker)
            if "date" in prices.columns:
                prices = prices.sort_values("date").drop_duplicates(
                    "ticker", keep="last"
                )
            close_col = "close" if "close" in prices.columns else None
            if close_col:
                for _, row in prices.iterrows():
                    _slot(row["ticker"])["price"] = _as_float(row.get(close_col))

    try:
        from alpha_system.ui.services.weekly_qual_report import (
            load_exit_target_entries,
        )

        exits = load_exit_target_entries(
            root, yaml_path=data / "kr_alpha_exit_targets.yaml"
        )
    except Exception:
        exits = {}

    for ticker, entry in (exits or {}).items():
        if not isinstance(entry, dict):
            continue
        slot = _slot(ticker)
        yaml_px = _as_float(entry.get("target_price"))
        val = entry.get("valuation") if isinstance(entry.get("valuation"), dict) else {}
        pbr_max = _as_float((val or {}).get("pbr_max"))
        if yaml_px is not None and yaml_px > 0:
            slot["target"] = yaml_px
        elif (
            pbr_max is not None
            and pbr_max > 0
            and slot.get("pbr")
            and slot["pbr"] > 0
            and slot.get("price")
            and slot["price"] > 0
        ):
            slot["target"] = round(float(slot["price"]) * (pbr_max / float(slot["pbr"])), 0)

    return out


def load_sector_labels(root: Path) -> dict[str, str]:
    """ticker → KRX 한글 업종 (표 표시용)."""
    import csv

    labels: dict[str, tuple[int, str]] = {}
    priority = {"manual": 0, "krx_official": 1, "name_infer": 2}
    for fname in ("krx_sector_mapping.csv", "krx_sector_mapping_manual.csv"):
        path = root / "data" / fname
        if not path.exists():
            continue
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for raw in csv.DictReader(handle):
                    ticker = _norm_ticker(raw.get("ticker"))
                    if not ticker:
                        continue
                    label = str(
                        raw.get("krx_sector") or raw.get("internal_sector") or ""
                    ).strip()
                    if not label:
                        continue
                    src = str(raw.get("source") or "")
                    rank = priority.get(src, 5)
                    prev = labels.get(ticker)
                    if prev is None or rank < prev[0]:
                        labels[ticker] = (rank, label)
        except Exception:
            continue
    return {tk: lab for tk, (_, lab) in labels.items()}


def build_watch_table_rows(
    board: RankWatchBoard,
    *,
    metrics: Mapping[str, Mapping[str, Any]] | None = None,
    extra_by_ticker: Mapping[str, Mapping[str, Any]] | None = None,
    sector_labels: Mapping[str, str] | None = None,
    cutoff: float | None = None,
    target_n: int = 6,
) -> tuple[WatchTableRow, ...]:
    """Join fundamentals + preview tone onto the observation board."""
    from alpha_system.ui.services.ko_display import format_ineligibility_reason

    metrics = metrics or {}
    extra_by_ticker = extra_by_ticker or {}
    sector_labels = sector_labels or {}
    ranks = eligible_ranks_for_cutoff(board.rows, cutoff)
    out: list[WatchTableRow] = []
    for row in board.rows:
        met = metrics.get(row.ticker) or {}
        extra = extra_by_ticker.get(row.ticker) or {}
        target = _as_float(met.get("target"))
        if target is None:
            target = _as_float(extra.get("quant_price_mid"))
        if target is None:
            target = _as_float(extra.get("target_price"))
        tone = watch_preview_tone(
            score=row.total_score,
            cutoff=cutoff,
            eligible_rank=ranks.get(row.ticker),
            target_n=target_n,
            in_proposal=row.in_proposal,
        )
        sector = str(sector_labels.get(row.ticker) or row.sector or "").strip()
        if row.eligibility is True:
            judgment = "적격"
        elif row.eligibility is False:
            judgment = format_ineligibility_reason(
                getattr(row, "eligibility_reason", "") or ""
            )
        else:
            judgment = "—"
        out.append(
            WatchTableRow(
                rank=row.rank,
                ticker=row.ticker,
                name=row.name,
                total_score=row.total_score,
                sector=sector,
                is_held=row.is_held,
                in_proposal=row.in_proposal,
                eligibility=row.eligibility,
                tone=tone,
                judgment=judgment,
                per=_as_float(met.get("per")),
                pbr=_as_float(met.get("pbr")),
                roe=_as_float(met.get("roe")),
                current_price=_as_float(met.get("price")),
                target_price=target,
            )
        )
    return tuple(out)
