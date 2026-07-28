"""KRX sector mapping v0.2 — manual > krx_official > name_infer > unknown."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from src.field_normalize import normalize_sector

SECTOR_MAPPING_COLUMNS = [
    "ticker",
    "name",
    "market",
    "krx_sector",
    "internal_sector",
    "sector_group",
    "source",
    "asof",
    "is_manual",
    "notes",
]

SOURCE_PRIORITY = {
    "manual": 0,
    "krx_official": 1,
    "name_infer": 2,
    "unknown": 9,
}

_NAME_KEYWORDS: list[tuple[tuple[str, ...], str, str]] = [
    (("금융지주", "증권", "은행", "KB금융", "신한지주"), "금융업", "financial"),
    (("보험", "손해", "생명"), "보험", "insurance"),
    (("화학", "KCC", "타이어"), "화학", "materials"),
    (("자동차", "기아", "현대차", "모비스", "에스엘"), "운수장비", "auto"),
    (("반도체", "하이닉스", "삼성전자"), "전기전자", "semiconductor"),
    (("항공", "해운", "팬오션", "대한항공"), "운수창고", "industrial_transport"),
    (("코웨이", "오리온", "동원", "식품"), "음식료품", "consumer_staples"),
    (("KT", "통신"), "통신업", "defensive_telecom"),
    (("홀딩스", "지주"), "금융업", "holding_company"),
    (("GS", "정유", "에너지"), "금융업", "holding_company"),
    (("해상",), "보험", "insurance"),
    (("단자",), "전기전자", "electronic_components"),
    (("오토", "모터"), "운수장비", "auto"),
    (("게임",), "서비스업", "gaming"),
    (("이노션",), "서비스업", "media_advertising"),
    (("전력", "한전"), "전기가스", "utilities"),
    (("은행", "기업은행", "금융지주"), "금융업", "financial"),
]


def infer_sector_from_name(name: str) -> dict[str, str]:
    text = str(name or "")
    for keywords, krx, group in _NAME_KEYWORDS:
        if any(k in text for k in keywords):
            return {
                "krx_sector": krx,
                "internal_sector": krx,
                "sector_group": group,
                "source": "name_infer",
            }
    return {
        "krx_sector": "",
        "internal_sector": "unknown",
        "sector_group": "unknown",
        "source": "unknown",
    }


def _normalize_row(row: dict[str, str]) -> dict[str, str]:
    ticker = str(row.get("ticker", "")).strip().zfill(6)
    source = str(row.get("source") or "unknown").strip()
    internal = str(row.get("internal_sector") or row.get("sector") or "").strip()
    group = str(row.get("sector_group") or internal or "unknown").strip()
    if not internal or normalize_sector(internal) == "unknown":
        internal = "unknown"
        group = "unknown"
        if source not in {"manual", "krx_official"}:
            source = "unknown"
    return {
        "ticker": ticker,
        "name": str(row.get("name") or ""),
        "market": str(row.get("market") or "KOSPI"),
        "krx_sector": str(row.get("krx_sector") or ""),
        "internal_sector": internal,
        "sector_group": group,
        "source": source,
        "asof": str(row.get("asof") or ""),
        "is_manual": str(row.get("is_manual") or "false").lower(),
        "notes": str(row.get("notes") or ""),
    }


def _read_mapping_file(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for raw in csv.DictReader(f):
            row = _normalize_row(raw)
            tk = row["ticker"]
            if not tk:
                continue
            out[tk] = row
    return out


def load_krx_sector_mapping(data_dir: Path) -> dict[str, dict[str, str]]:
    """Merged mapping: manual file > main file (by source priority)."""
    merged: dict[str, dict[str, str]] = {}
    for fname in ("krx_sector_mapping.csv", "krx_sector_mapping_manual.csv"):
        rows = _read_mapping_file(data_dir / fname)
        for tk, row in rows.items():
            existing = merged.get(tk)
            if existing is None:
                merged[tk] = row
                continue
            p_new = SOURCE_PRIORITY.get(row["source"], 5)
            p_old = SOURCE_PRIORITY.get(existing["source"], 5)
            if p_new < p_old:
                merged[tk] = row
            elif p_new == p_old and row.get("is_manual") == "true":
                merged[tk] = row
    return merged


def resolve_sector(
    ticker: str,
    name: str,
    universe_sector: str = "",
    mapping: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    mapping = mapping or {}
    tk = str(ticker).zfill(6)
    if tk in mapping:
        row = mapping[tk]
        internal = normalize_sector(row.get("internal_sector", ""))
        if internal != "unknown":
            group = row.get("sector_group") or row.get("internal_sector") or "unknown"
            return {
                "sector": row.get("internal_sector") or group,
                "sector_group": group,
                "krx_sector": row.get("krx_sector", ""),
                "internal_sector": row.get("internal_sector", ""),
                "source": row.get("source", "manual"),
                "resolved": True,
                "trust": "HIGH" if row.get("source") == "manual" else (
                    "MEDIUM" if row.get("source") == "krx_official" else "YELLOW"
                ),
            }
    uni = normalize_sector(universe_sector)
    if uni != "unknown":
        return {
            "sector": uni,
            "sector_group": uni,
            "krx_sector": uni,
            "internal_sector": uni,
            "source": "universe.csv",
            "resolved": True,
            "trust": "MEDIUM",
        }
    inferred = infer_sector_from_name(name)
    if inferred["source"] != "unknown":
        return {
            "sector": inferred["internal_sector"],
            "sector_group": inferred["sector_group"],
            "krx_sector": inferred["krx_sector"],
            "internal_sector": inferred["internal_sector"],
            "source": "name_infer",
            "resolved": True,
            "trust": "YELLOW",
        }
    return {
        "sector": "unknown",
        "sector_group": "unknown",
        "krx_sector": "",
        "internal_sector": "unknown",
        "source": "unknown",
        "resolved": False,
        "trust": "LOW",
    }


def compute_sector_coverage_for_tickers(
    tickers: list[dict[str, Any]],
    data_dir: Path,
    *,
    mapping: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    mapping = mapping or load_krx_sector_mapping(data_dir)
    if not tickers:
        return {
            "count": 0,
            "unknown_count": 0,
            "unknown_rate": 0.0,
            "coverage_pct": 0.0,
            "candidate_sector_coverage_pct": 0.0,
            "shortlist_unknown_rate": 0.0,
        }
    unknown = 0
    for item in tickers:
        res = resolve_sector(
            str(item.get("ticker", "")),
            str(item.get("name", "")),
            str(item.get("sector", "")),
            mapping,
        )
        if not res["resolved"]:
            unknown += 1
    n = len(tickers)
    rate = round(unknown / n, 4)
    cov = round(100 * (n - unknown) / n, 1)
    return {
        "count": n,
        "unknown_count": unknown,
        "unknown_rate": rate,
        "coverage_pct": cov,
        "candidate_sector_coverage_pct": cov,
        "shortlist_unknown_rate": rate,
    }


def merge_coverage_metrics(
    shortlist: dict[str, Any],
    top10: dict[str, Any],
    holdings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hold = holdings or {}
    return {
        "candidate_sector_coverage_pct": shortlist.get("coverage_pct", 0.0),
        "shortlist_unknown_rate": shortlist.get("unknown_rate", 0.0),
        "shortlist_unknown_count": shortlist.get("unknown_count", 0),
        "shortlist_count": shortlist.get("count", 0),
        "top10_unknown_rate": top10.get("unknown_rate", 0.0),
        "top10_unknown_count": top10.get("unknown_count", 0),
        "top10_count": top10.get("count", 0),
        "top10_sector_coverage_pct": top10.get("coverage_pct", 0.0),
        "holdings_sector_coverage_pct": hold.get("coverage_pct", 0.0),
        "holdings_unknown_rate": hold.get("unknown_rate", 0.0),
        "holdings_unknown_count": hold.get("unknown_count", 0),
        "holdings_count": hold.get("count", 0),
    }


def sector_risk_cap_status(sector_coverage: dict[str, Any]) -> str:
    top10_cov = float(sector_coverage.get("top10_sector_coverage_pct") or 0)
    hold_cov = float(sector_coverage.get("holdings_sector_coverage_pct") or 100)
    if top10_cov < 80:
        return "ALPHA_BUY_BLOCKED"
    if hold_cov < 100:
        return "YELLOW"
    return "GREEN"


def write_sector_mapping_template(data_dir: Path, tickers: list[dict[str, str]]) -> Path:
    """Append inferred rows to krx_sector_mapping.csv without overwriting manual rows."""
    path = data_dir / "krx_sector_mapping.csv"
    mapping = load_krx_sector_mapping(data_dir)
    existing = _read_mapping_file(path)
    manual = _read_mapping_file(data_dir / "krx_sector_mapping_manual.csv")
    existing.update(manual)

    for item in tickers:
        tk = str(item.get("ticker", "")).zfill(6)
        if not tk or tk in existing:
            continue
        resolved = resolve_sector(tk, item.get("name", ""), item.get("sector", ""), mapping)
        if resolved["source"] == "unknown":
            existing[tk] = _normalize_row({
                "ticker": tk,
                "name": item.get("name", ""),
                "market": "KOSPI",
                "krx_sector": "",
                "internal_sector": "unknown",
                "sector_group": "unknown",
                "source": "unknown",
                "asof": "",
                "is_manual": "false",
                "notes": "auto_template",
            })
        else:
            existing[tk] = _normalize_row({
                "ticker": tk,
                "name": item.get("name", ""),
                "market": "KOSPI",
                "krx_sector": resolved.get("krx_sector", ""),
                "internal_sector": resolved.get("internal_sector", ""),
                "sector_group": resolved.get("sector_group", ""),
                "source": resolved.get("source", "name_infer"),
                "asof": "",
                "is_manual": "false",
                "notes": "auto_template",
            })

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SECTOR_MAPPING_COLUMNS)
        writer.writeheader()
        for tk in sorted(existing):
            writer.writerow({k: existing[tk].get(k, "") for k in SECTOR_MAPPING_COLUMNS})
    return path
