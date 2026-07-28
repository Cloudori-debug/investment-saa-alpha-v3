from __future__ import annotations

from pathlib import Path
from typing import Any

from src.alpha.loaders import load_universe, load_universe_filter_config
from src.alpha.schemas import UniverseRecord
from src.alpha.universe_filter import filter_universe
from src.models import PositionRow, TargetRow


def build_evaluation_universe(
    data_dir: Any,
    *,
    positions: list[PositionRow],
    targets: list[TargetRow],
    prices_by_ticker: dict[str, Any],
    as_of: str,
    max_research: int = 50,
) -> tuple[list[UniverseRecord], list[Any]]:
    """kr_alpha 보유·목표 + 유니버스 필터 통과 상위 research 종목."""
    universe = load_universe(data_dir / "universe.csv")
    filter_cfg = load_universe_filter_config(data_dir / "universe_filter.yaml")
    passed, excluded = filter_universe(universe, prices_by_ticker, filter_cfg, as_of)

    tickers: set[str] = set()
    rec_map: dict[str, UniverseRecord] = {u.ticker: u for u in universe}

    for p in positions:
        if p.asset_group == "kr_alpha" and p.ticker.upper() != "CASH":
            tickers.add(p.ticker)
    for t in targets:
        if t.asset_group == "kr_alpha" and t.target_weight > 0:
            tickers.add(t.ticker)

    for rec in passed[:max_research]:
        tickers.add(rec.ticker)

    eval_rows: list[UniverseRecord] = []
    for ticker in sorted(tickers):
        if ticker in rec_map:
            eval_rows.append(rec_map[ticker])
        else:
            pos = next((p for p in positions if p.ticker == ticker), None)
            tgt = next((t for t in targets if t.ticker == ticker), None)
            name = (pos.name if pos else None) or (tgt.name if tgt else ticker)
            sector = (pos.sector if pos else None) or (tgt.sector if tgt else "")
            eval_rows.append(
                UniverseRecord(ticker=ticker, name=name, sector=sector or "")
            )

    return eval_rows, excluded
