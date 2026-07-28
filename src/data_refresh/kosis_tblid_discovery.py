"""KOSIS tblId discovery — search + validate candidates for cpi_kr_yoy / pmi_kr."""
from __future__ import annotations

import csv
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from src.config import load_yaml
from src.data_refresh.kosis_client import fetch_kosis_field, fetch_kosis_series, kosis_yoy_pct
from src.data_refresh.tier2_refresh import _period_to_iso, _stale_reference_date

DISCOVERY_JSON = "outputs/kosis_tblid_discovery.json"
CANDIDATES_CSV = "outputs/kosis_tblid_candidates.csv"

SEARCH_URL = "https://kosis.kr/openapi/statisticsSearch.do"
DATA_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

CPI_SEARCH_TERMS = [
    "전년동월비",
    "소비자물가지수",
    "소비자물가상승률",
    "전국 소비자물가",
    "소비자물가",
]
PMI_SEARCH_TERMS = [
    "구매관리자지수",
    "제조업 PMI",
    "PMI",
    "기업경기실사지수",
    "업황전망",
    "경기종합지수",
    "제조업",
]
PMI_ALT_SEARCH_TERMS = [
    "기업경기실사지수",
    "업황전망",
    "경기종합지수",
    "BSI",
]

INVALID_TBL_IDS = frozenset({"DT_1J20001", "DT_1C8013"})

# Known-good CPI tbl from KOSIS search (org 101) — validated at discovery time
CPI_PREFERRED_KEYWORDS = (
    "소비자물가",
    "전년동월",
    "상승률",
    "물가상승률",
)
CPI_PREFERRED_TBL_IDS = frozenset({"DT_1J22042", "DT_1J22003"})
CPI_RATE_ITEM = "T03"  # 전년동월비(%)
CPI_TOTAL_OBJ = "0"    # 총지수
PMI_EXACT_KEYWORDS = ("구매관리자지수", "PMI")
PMI_ALT_KEYWORDS = ("경기실사", "업황전망", "경기종합", "BSI", "기업체감")


@dataclass
class TblCandidate:
    field: str
    candidate_tbl_id: str
    org_id: str
    stat_id: str
    table_name: str
    period: str = ""
    unit: str = ""
    latest_value_date: str = ""
    latest_update_date: str = ""
    source_api: str = SEARCH_URL
    confidence: str = "low"
    selected: bool = False
    rejection_reason: str = ""
    recommended_mapping: str = ""
    search_term: str = ""
    itm_id: str = ""
    obj_l1: str = ""
    transform: str = ""
    latest_value: float | None = None
    fetch_error: str = ""
    role: str = "candidate"  # candidate | pmi_kr_alt_candidate

    def to_row(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "candidate_tbl_id": self.candidate_tbl_id,
            "org_id": self.org_id,
            "stat_id": self.stat_id,
            "table_name": self.table_name,
            "period": self.period,
            "unit": self.unit,
            "latest_value_date": self.latest_value_date,
            "latest_update_date": self.latest_update_date,
            "source_api": self.source_api,
            "confidence": self.confidence,
            "selected": self.selected,
            "rejection_reason": self.rejection_reason,
            "recommended_mapping": self.recommended_mapping,
            "search_term": self.search_term,
            "itm_id": self.itm_id,
            "obj_l1": self.obj_l1,
            "transform": self.transform,
            "latest_value": self.latest_value,
            "fetch_error": self.fetch_error,
            "role": self.role,
        }


def parse_kosis_json(raw: str) -> Any:
    fixed = re.sub(r"([\{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', raw.strip())
    return json.loads(fixed)


def _kosis_api_key(data_dir: Path) -> str:
    from src.data_refresh.tier2_refresh import _kosis_api_key as _key

    return _key(data_dir)


def kosis_search(api_key: str, search_nm: str) -> list[dict[str, Any]]:
    params = {
        "method": "getList",
        "apiKey": api_key.strip(),
        "searchNm": search_nm,
        "format": "json",
        "content": "json",
    }
    url = f"{SEARCH_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "multi-asset-trigger-portfolio/2.2"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = parse_kosis_json(resp.read().decode("utf-8"))
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    return []


def _score_table_name(name: str, keywords: tuple[str, ...]) -> int:
    score = 0
    for kw in keywords:
        if kw in name:
            score += 10
    return score


def _dedupe_candidates(candidates: list[TblCandidate]) -> list[TblCandidate]:
    by_key: dict[tuple[str, str, str], TblCandidate] = {}
    for c in candidates:
        key = (c.field, c.candidate_tbl_id, c.org_id)
        prev = by_key.get(key)
        if prev is None or _score_table_name(c.table_name, CPI_PREFERRED_KEYWORDS + PMI_EXACT_KEYWORDS + PMI_ALT_KEYWORDS) > _score_table_name(prev.table_name, CPI_PREFERRED_KEYWORDS + PMI_EXACT_KEYWORDS + PMI_ALT_KEYWORDS):
            by_key[key] = c
    return list(by_key.values())


def _is_monthly_period(period: str) -> bool:
    p = str(period or "").strip()
    return len(p) == 6 and p.isdigit()


def _cpi_value_plausible(val: float) -> bool:
    return -5.0 <= val <= 25.0


def _param_grid(field: str, tbl_id: str = "") -> list[tuple[str, str, str]]:
    if field == "cpi_kr_yoy":
        grid: list[tuple[str, str, str]] = []
        if tbl_id == "DT_1J22042" or "상승률" in tbl_id:
            grid.extend([
                (CPI_RATE_ITEM, CPI_TOTAL_OBJ, "last"),
                ("T04", CPI_TOTAL_OBJ, "last"),
            ])
        if tbl_id in CPI_PREFERRED_TBL_IDS or tbl_id.startswith("DT_1J22"):
            grid.extend([
                ("ALL", "ALL", "yoy_pct"),
                ("T1", "ALL", "yoy_pct"),
            ])
        grid.extend([
            (CPI_RATE_ITEM, CPI_TOTAL_OBJ, "last"),
            ("ALL", "ALL", "last"),
            ("ALL", "ALL", "yoy_pct"),
            ("T10", "ALL", "yoy_pct"),
            ("T1", "ALL", "yoy_pct"),
        ])
        seen: set[tuple[str, str, str]] = set()
        out: list[tuple[str, str, str]] = []
        for row in grid:
            if row not in seen:
                seen.add(row)
                out.append(row)
        return out
    return [
        ("ALL", "ALL", "last"),
        ("T10", "ALL", "last"),
        ("T10", "00", "last"),
        ("T1", "ALL", "last"),
    ]


def validate_candidate(
    candidate: TblCandidate,
    *,
    api_key: str,
    field: str,
) -> TblCandidate:
    if candidate.candidate_tbl_id in INVALID_TBL_IDS:
        candidate.rejection_reason = "legacy_invalid_tblId_err_21"
        candidate.confidence = "rejected"
        return candidate

    best: TblCandidate | None = None
    for itm_id, obj_l1, transform in _param_grid(field, candidate.candidate_tbl_id):
        query = {
            "orgId": candidate.org_id,
            "tblId": candidate.candidate_tbl_id,
            "itmId": itm_id,
            "objL1": obj_l1,
            "prdSe": "M",
            "transform": transform,
        }
        val, period, err = fetch_kosis_field(DATA_URL, query, api_key=api_key)
        if err or val is None:
            candidate.fetch_error = err or "empty"
            continue
        if field == "cpi_kr_yoy" and not _is_monthly_period(period):
            candidate.fetch_error = f"non_monthly_period:{period}"
            continue
        if field == "cpi_kr_yoy" and not _cpi_value_plausible(float(val)):
            candidate.fetch_error = f"implausible_cpi_yoy:{val}"
            continue
        period_iso = _period_to_iso(period) if period else ""
        trial = TblCandidate(
            field=candidate.field,
            candidate_tbl_id=candidate.candidate_tbl_id,
            org_id=candidate.org_id,
            stat_id=candidate.stat_id,
            table_name=candidate.table_name,
            period="M",
            source_api=DATA_URL,
            confidence="medium",
            search_term=candidate.search_term,
            itm_id=itm_id,
            obj_l1=obj_l1,
            transform=transform,
            latest_value=val,
            latest_value_date=period_iso,
            latest_update_date=date.today().isoformat(),
            role=candidate.role,
        )
        score = 0
        if field == "cpi_kr_yoy":
            if candidate.candidate_tbl_id in CPI_PREFERRED_TBL_IDS:
                score += 20
            if itm_id == CPI_RATE_ITEM and transform == "last":
                score += 30
            if transform == "yoy_pct" and candidate.candidate_tbl_id not in {"DT_1J22003", "DT_1J22002"}:
                score -= 10
            if any(k in candidate.table_name for k in CPI_PREFERRED_KEYWORDS):
                score += 10
        trial_score = score
        if best is None or trial_score > getattr(best, "_score", -1):
            trial._score = trial_score  # type: ignore[attr-defined]
            best = trial
    if best is None:
        candidate.rejection_reason = candidate.fetch_error or "fetch_failed_all_param_grid"
        candidate.confidence = "rejected"
        return candidate

    best.search_term = candidate.search_term
    best.table_name = candidate.table_name
    best.stat_id = candidate.stat_id
    if field == "cpi_kr_yoy":
        if (
            best.candidate_tbl_id in CPI_PREFERRED_TBL_IDS
            and best.itm_id == CPI_RATE_ITEM
            and best.transform == "last"
        ):
            best.confidence = "high"
        elif any(k in best.table_name for k in CPI_PREFERRED_KEYWORDS):
            best.confidence = "high" if _is_monthly_period(best.latest_value_date.replace("-", "")[:6]) else "medium"
        else:
            best.confidence = "medium"
        if best.transform == "yoy_pct" and best.candidate_tbl_id not in CPI_PREFERRED_TBL_IDS:
            best.confidence = "low"
            best.rejection_reason = "yoy_pct_on_non_index_table"
            best.selected = False
    elif field == "pmi_kr":
        if any(k in best.table_name for k in PMI_EXACT_KEYWORDS):
            best.confidence = "high"
        else:
            best.rejection_reason = "not_exact_pmi_table"
            best.confidence = "low"
            best.role = "pmi_kr_alt_candidate"
            best.recommended_mapping = "pmi_kr_alt_candidate — do not auto-map to pmi_kr"
    return best


def discover_kosis_tblids(data_dir: Path) -> dict[str, Any]:
    api_key = _kosis_api_key(data_dir)
    cfg = load_yaml(data_dir / "tier2_sources.yaml") if (data_dir / "tier2_sources.yaml").exists() else {}
    current = (cfg.get("kosis") or {}).get("queries") or {}

    raw_candidates: list[TblCandidate] = []

    def collect(field: str, terms: list[str], *, role: str = "candidate") -> None:
        for term in terms:
            try:
                rows = kosis_search(api_key, term)
            except Exception as exc:
                raw_candidates.append(TblCandidate(
                    field=field,
                    candidate_tbl_id="",
                    org_id="",
                    stat_id="",
                    table_name="",
                    search_term=term,
                    rejection_reason=f"search_failed:{exc}",
                    role=role,
                ))
                continue
            for row in rows:
                org = str(row.get("ORG_ID") or "")
                tbl = str(row.get("TBL_ID") or "")
                if not tbl:
                    continue
                if field == "cpi_kr_yoy" and org != "101":
                    continue
                name = str(row.get("TBL_NM") or row.get("TBL_NM_ENG") or "")
                raw_candidates.append(TblCandidate(
                    field=field,
                    candidate_tbl_id=tbl,
                    org_id=org,
                    stat_id=str(row.get("STAT_ID") or ""),
                    table_name=name,
                    latest_update_date=str(row.get("SEND_DE") or row.get("WRT_TM") or ""),
                    search_term=term,
                    role=role,
                ))

    collect("cpi_kr_yoy", CPI_SEARCH_TERMS)
    collect("pmi_kr", PMI_SEARCH_TERMS)
    collect("pmi_kr_alt_candidate", PMI_ALT_SEARCH_TERMS, role="pmi_kr_alt_candidate")

    deduped = _dedupe_candidates([c for c in raw_candidates if c.candidate_tbl_id])

    validated: list[TblCandidate] = []
    for cand in deduped:
        if cand.role == "pmi_kr_alt_candidate":
            alt = validate_candidate(cand, api_key=api_key, field="pmi_kr")
            alt.field = "pmi_kr_alt_candidate"
            alt.role = "pmi_kr_alt_candidate"
            if alt.confidence != "rejected":
                alt.recommended_mapping = "pmi_kr_alt_candidate — do not auto-map to pmi_kr"
            validated.append(alt)
        else:
            validated.append(validate_candidate(cand, api_key=api_key, field=cand.field))

    cpi_candidates = [c for c in validated if c.field == "cpi_kr_yoy" and c.confidence != "rejected"]
    pmi_exact = [c for c in validated if c.field == "pmi_kr" and c.confidence == "high"]
    pmi_low = [c for c in validated if c.field == "pmi_kr" and c.confidence in {"medium", "low"}]
    pmi_alts = [c for c in validated if c.field == "pmi_kr_alt_candidate" and c.confidence != "rejected"]

    selected_cpi = None
    if cpi_candidates:
        cpi_candidates.sort(
            key=lambda c: (
                0 if c.confidence == "high" else 1,
                0 if c.candidate_tbl_id in CPI_PREFERRED_TBL_IDS else 1,
                -_score_table_name(c.table_name, CPI_PREFERRED_KEYWORDS),
            ),
        )
        top = cpi_candidates[0]
        if (
            top.confidence in {"high", "medium"}
            and top.latest_value is not None
            and top.rejection_reason not in {"yoy_pct_on_non_index_table"}
            and _cpi_value_plausible(float(top.latest_value))
        ):
            top.selected = True
            top.recommended_mapping = "cpi_kr_yoy"
            selected_cpi = top

    selected_pmi = None
    if pmi_exact:
        pmi_exact.sort(key=lambda c: -_score_table_name(c.table_name, PMI_EXACT_KEYWORDS))
        top = pmi_exact[0]
        if top.latest_value is not None:
            top.selected = True
            top.recommended_mapping = "pmi_kr"
            selected_pmi = top

    for c in validated:
        if c.candidate_tbl_id in INVALID_TBL_IDS:
            c.selected = False
            c.rejection_reason = "legacy_invalid_tblId_err_21"
            c.confidence = "rejected"

    pmi_kr_kosis_unavailable = selected_pmi is None

    return {
        "schema_version": "1.0",
        "as_of": date.today().isoformat(),
        "invalid_legacy_tbl_ids": sorted(INVALID_TBL_IDS),
        "current_tbl_ids": {
            k: str((v or {}).get("tblId") or "") for k, v in current.items() if isinstance(v, dict)
        },
        "search_api": SEARCH_URL,
        "data_api": DATA_URL,
        "cpi_kr_yoy": {
            "selected": selected_cpi.to_row() if selected_cpi else None,
            "candidates": [c.to_row() for c in cpi_candidates[:15]],
        },
        "pmi_kr": {
            "selected": selected_pmi.to_row() if selected_pmi else None,
            "pmi_kr_kosis_unavailable": pmi_kr_kosis_unavailable,
            "exact_pmi_candidates": [c.to_row() for c in pmi_exact[:10]],
            "non_exact_candidates": [c.to_row() for c in pmi_low[:10]],
        },
        "pmi_kr_alt_candidates": [c.to_row() for c in pmi_alts[:15]],
        "all_candidates": [c.to_row() for c in validated],
        "recommended_next_action": _recommended_actions(selected_cpi, selected_pmi, pmi_kr_kosis_unavailable),
        "diagnostics_path": DISCOVERY_JSON,
        "candidates_csv_path": CANDIDATES_CSV,
    }


def _recommended_actions(
    selected_cpi: TblCandidate | None,
    selected_pmi: TblCandidate | None,
    pmi_unavailable: bool,
) -> list[str]:
    actions: list[str] = []
    if selected_cpi:
        actions.append(
            f"Update tier2_sources.yaml cpi_kr_yoy tblId={selected_cpi.candidate_tbl_id} "
            f"(itmId={selected_cpi.itm_id}, objL1={selected_cpi.obj_l1})"
        )
    else:
        actions.append("cpi_kr_yoy: no selected tblId — keep manual_required")
    if selected_pmi:
        actions.append(
            f"Update tier2_sources.yaml pmi_kr tblId={selected_pmi.candidate_tbl_id} "
            f"(itmId={selected_pmi.itm_id}, objL1={selected_pmi.obj_l1})"
        )
    elif pmi_unavailable:
        actions.append("pmi_kr: KOSIS exact PMI not found — keep manual_required; review pmi_kr_alt_candidates")
    else:
        actions.append("pmi_kr: no high-confidence tblId — keep manual_required")
    actions.append("Re-run kosis_tier2_refresh after tier2_sources.yaml update")
    return actions


def apply_selected_to_tier2_sources(data_dir: Path, discovery: dict[str, Any]) -> list[str]:
    """Update tier2_sources.yaml only for selected=true with successful fetch."""
    path = data_dir / "tier2_sources.yaml"
    if not path.exists():
        return []
    import yaml

    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    kosis = doc.setdefault("kosis", {})
    queries = kosis.setdefault("queries", {})
    applied: list[str] = []

    for section_key, query_key in [("cpi_kr_yoy", "cpi_kr_yoy"), ("pmi_kr", "pmi_kr")]:
        section = discovery.get(section_key) or {}
        sel = section.get("selected")
        if not sel or not sel.get("selected"):
            continue
        tbl = str(sel.get("candidate_tbl_id") or "")
        if tbl in INVALID_TBL_IDS or not tbl:
            continue
        q = dict(queries.get(query_key) or {})
        q["orgId"] = str(sel.get("org_id") or "101")
        q["tblId"] = tbl
        q["itmId"] = str(sel.get("itm_id") or "ALL")
        q["objL1"] = str(sel.get("obj_l1") or "ALL")
        q["transform"] = str(sel.get("transform") or q.get("transform") or "last")
        q["target_field"] = query_key
        q["note"] = (
            f"KOSIS discovery selected {tbl} — {sel.get('table_name', '')} "
            f"(search={sel.get('search_term')})"
        )
        queries[query_key] = q
        applied.append(query_key)

    if applied:
        path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return applied


def write_kosis_tblid_discovery(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    doc = discover_kosis_tblids(data_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "kosis_tblid_discovery.json"
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows = doc.get("all_candidates") or []
    csv_path = output_dir / "kosis_tblid_candidates.csv"
    if rows:
        fields = list(rows[0].keys())
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
    else:
        csv_path.write_text("field,candidate_tbl_id\n", encoding="utf-8-sig")

    applied = apply_selected_to_tier2_sources(data_dir, doc)
    doc["tier2_sources_applied"] = applied
    json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    pmi = doc.get("pmi_kr") or {}
    sel = pmi.get("selected") or {}
    summary = {
        "pmi_kr_kosis_unavailable": pmi.get("pmi_kr_kosis_unavailable"),
        "tier2_sources_applied": applied,
        "pmi_kr_selected": sel if isinstance(sel, dict) else {},
        "pmi_kr_candidates_count": len(pmi.get("exact_pmi_candidates") or []),
        "pmi_kr_alt_candidates_count": len(pmi.get("non_exact_candidates") or []),
        "pmi_kr_applied": "pmi_kr" in applied,
        "cpi_kr_applied": "cpi_kr_yoy" in applied,
    }
    (output_dir / "pmi_kr_task_a_discovery_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    doc["task_a_summary_path"] = str(output_dir / "pmi_kr_task_a_discovery_summary.json")
    return doc


def run_kosis_tblid_discovery_pipeline(
    data_dir: Path,
    output_dir: Path,
    *,
    refresh_after_apply: bool = True,
) -> dict[str, Any]:
    doc = write_kosis_tblid_discovery(data_dir, output_dir)
    if refresh_after_apply and doc.get("tier2_sources_applied"):
        from src.validation.kosis_tier2_refresh_diagnostics import run_kosis_tier2_refresh_with_diagnostics

        run_kosis_tier2_refresh_with_diagnostics(data_dir, output_dir)
    return doc
