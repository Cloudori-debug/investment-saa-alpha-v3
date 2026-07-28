from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from src.data_loader import load_positions, load_target_portfolio
from src.models import PositionRow, TargetRow
from src.portfolio_gap import consolidate_targets


def load_asset_group_labels(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "asset_group_labels.yaml"
    if not path.exists():
        return {}
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return doc.get("groups") or {}


def load_look_through_config(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "look_through_tags.yaml"
    if not path.exists():
        return {"defaults_by_asset_group": {}, "instruments": {}}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _tag_for_ticker(
    ticker: str,
    asset_group: str,
    *,
    config: dict[str, Any],
    sector: str = "",
    style: str = "",
) -> dict[str, Any]:
    instruments = config.get("instruments") or {}
    defaults = config.get("defaults_by_asset_group") or {}
    if ticker in instruments:
        inst = instruments[ticker]
        lt = dict((inst.get("look_through") or {}))
        lt.setdefault("asset_group", inst.get("asset_group", asset_group))
        return lt
    lt = dict(defaults.get(asset_group) or {})
    if sector and "sector" not in lt:
        lt["sector"] = sector
    if style and "style" not in lt:
        lt["style"] = style
    lt.setdefault("asset_group", asset_group)
    return lt


def _position_weight_pct(positions: list[PositionRow]) -> dict[str, float]:
    total = sum(float(p.current_value or 0) for p in positions) or 0.0
    if total <= 0:
        return {}
    return {p.ticker: round(float(p.current_value or 0) / total * 100, 2) for p in positions}


def _target_weight_map(targets: list[TargetRow]) -> dict[str, float]:
    consolidated = consolidate_targets(targets)
    return {t.ticker: round(float(t.target_weight), 2) for t in consolidated}


def _rollup(weights: dict[str, float], tags_by_ticker: dict[str, dict[str, Any]], key: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for ticker, w in weights.items():
        if w <= 0:
            continue
        dim = str(tags_by_ticker.get(ticker, {}).get(key, "unknown"))
        out[dim] = round(out.get(dim, 0) + w, 2)
    return dict(sorted(out.items(), key=lambda x: -x[1]))


def _rollup_asset_group(weights: dict[str, float], tags_by_ticker: dict[str, dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for ticker, w in weights.items():
        if w <= 0:
            continue
        g = str(tags_by_ticker.get(ticker, {}).get("asset_group", "unknown"))
        out[g] = round(out.get(g, 0) + w, 2)
    return dict(sorted(out.items(), key=lambda x: -x[1]))


def build_exposure_lookthrough(
    positions: list[PositionRow],
    targets: list[TargetRow],
    data_dir: Path,
    *,
    as_of: str = "",
) -> dict[str, Any]:
    """7자산군 target 계산 유지 · look-through 노출 진단만."""
    config = load_look_through_config(data_dir)
    labels = load_asset_group_labels(data_dir)
    pos_map = {p.ticker: p for p in positions}
    tgt_map = {t.ticker: t for t in consolidate_targets(targets)}

    tickers = sorted(set(pos_map) | set(tgt_map))
    tags_by_ticker: dict[str, dict[str, Any]] = {}
    instrument_rows: list[dict[str, Any]] = []

    for ticker in tickers:
        pos = pos_map.get(ticker)
        tgt = tgt_map.get(ticker)
        ag = (pos.asset_group if pos else tgt.asset_group if tgt else "kr_alpha")
        sector = (pos.sector if pos else tgt.sector if tgt else "")
        style = getattr(pos, "style", "") if pos else (tgt.role if tgt else "")
        lt = _tag_for_ticker(ticker, ag, config=config, sector=sector, style=style)
        tags_by_ticker[ticker] = lt
        instrument_rows.append({
            "ticker": ticker,
            "name": (pos.name if pos else tgt.name if tgt else ticker),
            "asset_group": ag,
            "look_through": lt,
        })

    current_w = _position_weight_pct(positions)
    target_w = _target_weight_map(targets)

    dimensions = ["region", "asset_class", "currency", "style"]
    by_dimension: dict[str, dict[str, Any]] = {}
    for dim in dimensions:
        by_dimension[dim] = {
            "current_pct": _rollup(current_w, tags_by_ticker, dim),
            "target_pct": _rollup(target_w, tags_by_ticker, dim),
        }

    return {
        "schema_version": "1.0",
        "as_of": as_of,
        "purpose": "노출 진단 — target 계산은 7자산군 유지",
        "asset_group_labels": labels,
        "by_asset_group": {
            "current_pct": _rollup_asset_group(current_w, tags_by_ticker),
            "target_pct": _rollup_asset_group(target_w, tags_by_ticker),
        },
        "by_dimension": by_dimension,
        "instruments": instrument_rows,
        "totals": {
            "current_weight_sum": round(sum(current_w.values()), 2),
            "target_weight_sum": round(sum(target_w.values()), 2),
        },
    }


def write_exposure_lookthrough(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summarize_exposure_concentration(report: dict[str, Any] | None, *, max_items: int = 3) -> str:
    """daily_report 상단용 — region 기준 현재 vs 목표 편중 한 줄."""
    if not report:
        return "—"
    block = ((report.get("by_dimension") or {}).get("region") or {})
    cur = block.get("current_pct") or {}
    tgt = block.get("target_pct") or {}
    if not cur and not tgt:
        return "—"
    keys = sorted(set(cur) | set(tgt), key=lambda k: -(cur.get(k, 0)))
    parts: list[str] = []
    for key in keys:
        c = float(cur.get(key, 0))
        t = float(tgt.get(key, 0))
        if c < 0.5 and t < 0.5:
            continue
        parts.append(f"{key} {c:.1f}% (목표 {t:.1f}%)")
        if len(parts) >= max_items:
            break
    return " · ".join(parts) if parts else "편중 없음"


def format_exposure_markdown(report: dict[str, Any]) -> str:
    lines = [
        "## Look-through 노출 (진단 전용)",
        "",
        "_계산·target은 7자산군 유지 · 아래는 region/asset/currency 노출 레이더_",
        "",
    ]
    by_dim = report.get("by_dimension") or {}
    for dim in ("region", "asset_class", "currency"):
        block = by_dim.get(dim) or {}
        cur = block.get("current_pct") or {}
        tgt = block.get("target_pct") or {}
        if not cur and not tgt:
            continue
        lines.append(f"### {dim}")
        lines.append("| 값 | 현재 % | 목표 % |")
        lines.append("|-----|--------|--------|")
        keys = sorted(set(cur) | set(tgt))
        for k in keys:
            lines.append(f"| {k} | {cur.get(k, 0):.1f} | {tgt.get(k, 0):.1f} |")
        lines.append("")
    return "\n".join(lines)


def build_from_data_dir(data_dir: Path, *, as_of: str = "") -> dict[str, Any]:
    positions = load_positions(data_dir / "positions.csv")
    targets = load_target_portfolio(data_dir / "target_portfolio.csv")
    return build_exposure_lookthrough(positions, targets, data_dir, as_of=as_of)
