"""Top10 sector unknown extraction and manual mapping candidate generation."""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from src.alpha.sector_mapping import (
    SECTOR_MAPPING_COLUMNS,
    compute_sector_coverage_for_tickers,
    infer_sector_from_name,
    load_krx_sector_mapping,
    resolve_sector,
)
from src.field_normalize import normalize_sector

CANDIDATE_SOURCE = "manual_candidate"
MANUAL_PATH = "krx_sector_mapping_manual.csv"
CANDIDATE_PATH = "krx_sector_mapping_manual_candidate.csv"


def _file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_low_confidence_infer(resolved: dict[str, Any]) -> bool:
    return resolved.get("source") in {"unknown", "name_infer"} or resolved.get("trust") == "YELLOW"


def extract_top10_unknown_rows(
    top10_graded: list[dict[str, Any]],
    data_dir: Path,
    *,
    mapping: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Return top10 rows where sector is not resolved via manual/krx_official."""
    mapping = mapping or load_krx_sector_mapping(data_dir)
    manual = _read_csv_rows(data_dir / MANUAL_PATH)
    rows: list[dict[str, Any]] = []
    for rank, item in enumerate(top10_graded, start=1):
        ticker = str(item.get("ticker", "")).zfill(6)
        name = str(item.get("name") or "")
        sector_info = resolve_sector(ticker, name, str(item.get("sector") or ""), mapping)
        if sector_info["resolved"]:
            continue
        rows.append({
            "rank": rank,
            "ticker": ticker,
            "name": name,
            "total_score": float(item.get("total_score") or 0),
            "grade": str(item.get("grade") or ""),
            "sector_known": sector_info["resolved"],
            "sector": sector_info.get("sector", "unknown"),
            "sector_source": sector_info.get("source", "unknown"),
            "sector_group": sector_info.get("sector_group", "unknown"),
            "trust": sector_info.get("trust", "LOW"),
            "in_manual_file": ticker in manual,
        })
    return rows


def build_manual_candidate_rows(
    unknown_rows: list[dict[str, Any]],
    *,
    as_of: str,
    data_dir: Path,
) -> list[dict[str, str]]:
    """Build candidate mapping rows — does not write to manual file."""
    manual = _read_csv_rows(data_dir / MANUAL_PATH)
    candidates: list[dict[str, str]] = []
    for item in unknown_rows:
        ticker = item["ticker"]
        if ticker in manual:
            continue
        name = item["name"]
        inferred = infer_sector_from_name(name)
        internal = inferred["internal_sector"]
        group = inferred["sector_group"]
        krx = inferred["krx_sector"]
        notes = "top10_unknown"
        if normalize_sector(internal) == "unknown":
            internal = "review_needed"
            group = "review_needed"
            krx = ""
            notes = "manual_review_required"
        elif inferred["source"] == "name_infer":
            notes = "auto_inferred_review"
        candidates.append({
            "ticker": ticker,
            "name": name,
            "market": "KOSPI",
            "krx_sector": krx,
            "internal_sector": internal,
            "sector_group": group,
            "source": CANDIDATE_SOURCE,
            "asof": as_of[:10],
            "is_manual": "false",
            "notes": notes,
        })
    return candidates


def simulate_coverage_with_candidates(
    top10_graded: list[dict[str, Any]],
    data_dir: Path,
    candidate_rows: list[dict[str, str]],
) -> dict[str, Any]:
    """Hypothetical coverage if candidates were promoted to manual."""
    mapping = load_krx_sector_mapping(data_dir)
    for row in candidate_rows:
        tk = row["ticker"]
        if normalize_sector(row.get("internal_sector", "")) == "review_needed":
            continue
        mapping[tk] = {
            **row,
            "source": "manual",
            "is_manual": "true",
        }
    return compute_sector_coverage_for_tickers(top10_graded, data_dir, mapping=mapping)


def write_top10_sector_candidate_artifacts(
    top10_graded: list[dict[str, Any]],
    data_dir: Path,
    output_dir: Path,
    *,
    as_of: str | None = None,
    sector_coverage_before: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write unknown list + manual candidate file. Never touches manual mapping."""
    as_of = (as_of or date.today().isoformat())[:10]
    output_dir.mkdir(parents=True, exist_ok=True)
    manual_path = data_dir / MANUAL_PATH
    candidate_path = data_dir / CANDIDATE_PATH
    manual_hash_before = _file_hash(manual_path)

    unknown_rows = extract_top10_unknown_rows(top10_graded, data_dir)
    candidate_rows = build_manual_candidate_rows(unknown_rows, as_of=as_of, data_dir=data_dir)

    unknown_path = output_dir / "top10_sector_unknown.csv"
    _write_csv(
        unknown_path,
        unknown_rows,
        fieldnames=[
            "rank", "ticker", "name", "total_score", "grade",
            "sector_known", "sector", "sector_source", "sector_group", "trust", "in_manual_file",
        ],
    )

    _write_csv(candidate_path, candidate_rows, fieldnames=SECTOR_MAPPING_COLUMNS)

    cov_before = sector_coverage_before or compute_sector_coverage_for_tickers(top10_graded, data_dir)
    cov_after = simulate_coverage_with_candidates(top10_graded, data_dir, candidate_rows)

    review_needed = [
        f"{r['ticker']} {r['name']}"
        for r in candidate_rows
        if r.get("notes") == "manual_review_required" or r.get("internal_sector") == "review_needed"
    ]

    meta = {
        "as_of": as_of,
        "unknown_top10_count": len(unknown_rows),
        "top10_sector_coverage_before": float(cov_before.get("coverage_pct") or 0),
        "top10_sector_coverage_after_candidate": float(cov_after.get("coverage_pct") or 0),
        "candidate_count": len(candidate_rows),
        "manual_review_required": review_needed,
        "manual_mapping_hash_unchanged": _file_hash(manual_path) == manual_hash_before,
        "paths": {
            "top10_sector_unknown": str(unknown_path),
            "manual_candidate": str(candidate_path),
        },
    }

    review_path = output_dir / "top10_sector_candidate_review.json"
    review_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta


def format_top10_sector_candidate_report_lines(meta: dict[str, Any]) -> list[str]:
    lines = [
        "## Top10 Sector Mapping Review",
        "",
        f"- **unknown_top10_count**: {meta.get('unknown_top10_count', 0)}",
        f"- **top10_sector_coverage_before**: {meta.get('top10_sector_coverage_before', '—')}%",
        f"- **top10_sector_coverage_after_candidate**: {meta.get('top10_sector_coverage_after_candidate', '—')}%",
        f"- **candidate_count**: {meta.get('candidate_count', 0)}",
        f"- **manual mapping unchanged**: {meta.get('manual_mapping_hash_unchanged', True)}",
    ]
    review = meta.get("manual_review_required") or []
    if review:
        lines.append(f"- **manual_review_required**: {', '.join(review)}")
    lines.append("")
    lines.append(
        "> `data/krx_sector_mapping_manual_candidate.csv`는 후보입니다. "
        "확인 후 `krx_sector_mapping_manual.csv`에만 반영하세요."
    )
    lines.append("")
    return lines


def _read_csv_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            tk = str(row.get("ticker", "")).zfill(6)
            if tk:
                out[tk] = row
    return out


def _write_csv(path: Path, rows: list[dict[str, Any]], *, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
