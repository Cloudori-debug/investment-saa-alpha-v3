"""Canonical core ETF ticker registry for target_portfolio validation."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.data_loader import _normalize_ticker

TARGET_PORTFOLIO_FIELDS = (
    "ticker",
    "name",
    "asset_group",
    "sector",
    "role",
    "target_weight",
    "min_weight",
    "max_weight",
)
WEIGHT_SUM_TOLERANCE = 0.05


def load_core_etf_registry(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "core_etf_ticker_registry.yaml"
    if not path.exists():
        return {"tickers": {}, "deprecated_replacements": {}}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw if isinstance(raw, dict) else {"tickers": {}, "deprecated_replacements": {}}


def canonical_etf_name(ticker: str, registry: dict[str, Any] | None = None) -> str:
    reg = registry or {}
    tickers = reg.get("tickers") or {}
    return str(tickers.get(_normalize_ticker(ticker), ""))


def validate_target_portfolio_structure(
    rows: list[dict[str, str]],
    *,
    data_dir: Path | None = None,
    weight_sum_tolerance: float = WEIGHT_SUM_TOLERANCE,
) -> dict[str, Any]:
    """Row shape, parseable weights, duplicate tickers, ~100% weight sum, core ETF presence."""
    issues: list[dict[str, str]] = []
    tickers_seen: set[str] = set()
    weight_sum = 0.0

    for idx, row in enumerate(rows, start=2):
        line_no = str(idx)
        overflow = row.get(None)
        if overflow:
            issues.append({
                "line": line_no,
                "ticker": str(row.get("ticker") or ""),
                "issue": "merged_row",
                "detail": f"extra CSV fields ({len(overflow)} overflow) — likely missing newline between rows",
            })

        ticker = _normalize_ticker(str(row.get("ticker") or ""))
        if not ticker:
            issues.append({"line": line_no, "ticker": "", "issue": "missing_ticker", "detail": "empty ticker"})
            continue
        if ticker in tickers_seen:
            issues.append({"line": line_no, "ticker": ticker, "issue": "duplicate_ticker", "detail": "duplicate row"})
        tickers_seen.add(ticker)

        for field in ("target_weight", "min_weight", "max_weight"):
            raw = str(row.get(field) or "").strip()
            if not raw:
                issues.append({
                    "line": line_no,
                    "ticker": ticker,
                    "issue": "missing_weight",
                    "detail": f"{field} empty",
                })
                continue
            try:
                val = float(raw)
            except ValueError:
                issues.append({
                    "line": line_no,
                    "ticker": ticker,
                    "issue": "invalid_weight",
                    "detail": f"{field}={raw!r} not numeric",
                })
                continue
            if field == "max_weight" and val > 25:
                issues.append({
                    "line": line_no,
                    "ticker": ticker,
                    "issue": "suspicious_max_weight",
                    "detail": f"max_weight={val} — possible merged-row corruption",
                })

        try:
            weight_sum += float(str(row.get("target_weight") or "0"))
        except ValueError:
            pass

    if abs(weight_sum - 100.0) > weight_sum_tolerance:
        issues.append({
            "line": "",
            "ticker": "",
            "issue": "weight_sum_mismatch",
            "detail": f"target_weight sum={weight_sum:.4f} (expected ~100.0 ±{weight_sum_tolerance})",
        })

    if data_dir is not None:
        registry = load_core_etf_registry(data_dir)
        canonical = registry.get("tickers") or {}
        for etf_ticker in canonical:
            if etf_ticker not in tickers_seen:
                issues.append({
                    "line": "",
                    "ticker": etf_ticker,
                    "issue": "missing_core_etf",
                    "detail": f"registry ETF {etf_ticker} absent from target rows",
                })

    return {
        "pass": not issues,
        "issue_count": len(issues),
        "weight_sum": round(weight_sum, 4),
        "row_count": len(rows),
        "issues": issues,
    }


def audit_target_portfolio_tickers(
    rows: list[dict[str, str]],
    *,
    data_dir: Path,
) -> dict[str, Any]:
    """Return mismatches between target rows and canonical ETF registry (non-kr_alpha)."""
    registry = load_core_etf_registry(data_dir)
    canonical = registry.get("tickers") or {}
    deprecated = registry.get("deprecated_replacements") or {}
    issues: list[dict[str, str]] = []

    for row in rows:
        ticker = _normalize_ticker(str(row.get("ticker") or ""))
        name = str(row.get("name") or "").strip()
        group = str(row.get("asset_group") or "")
        if not ticker or ticker == "CASH" or group == "kr_alpha":
            continue

        if ticker in deprecated:
            dep = deprecated[ticker]
            issues.append({
                "ticker": ticker,
                "name": name,
                "issue": "deprecated_ticker",
                "expected_ticker": str(dep.get("correct_ticker") or ""),
                "expected_name": str(dep.get("wrong_name") or canonical.get(dep.get("correct_ticker", ""), "")),
                "detail": str(dep.get("actual_product") or ""),
            })
            continue

        expected = canonical.get(ticker)
        if expected and name and expected not in name and name not in expected:
            issues.append({
                "ticker": ticker,
                "name": name,
                "issue": "name_mismatch",
                "expected_ticker": ticker,
                "expected_name": expected,
                "detail": "registry name differs from target row",
            })
        elif ticker not in canonical and group != "kr_alpha":
            issues.append({
                "ticker": ticker,
                "name": name,
                "issue": "unregistered_etf",
                "expected_ticker": "",
                "expected_name": "",
                "detail": "not in core_etf_ticker_registry.yaml",
            })

    return {
        "pass": not issues,
        "issue_count": len(issues),
        "issues": issues,
    }
