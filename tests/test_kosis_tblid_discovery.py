"""Tests for KOSIS tblId discovery."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

from src.data_refresh.kosis_tblid_discovery import (
    INVALID_TBL_IDS,
    TblCandidate,
    _cpi_value_plausible,
    _is_monthly_period,
    apply_selected_to_tier2_sources,
    validate_candidate,
    write_kosis_tblid_discovery,
)


def test_monthly_period_and_cpi_plausible() -> None:
    assert _is_monthly_period("202606")
    assert not _is_monthly_period("2026")
    assert _cpi_value_plausible(2.5)
    assert not _cpi_value_plausible(50.0)


def test_validate_rejects_legacy_tbl_id() -> None:
    cand = TblCandidate(
        field="cpi_kr_yoy",
        candidate_tbl_id="DT_1J20001",
        org_id="101",
        stat_id="",
        table_name="legacy",
    )
    out = validate_candidate(cand, api_key="k", field="cpi_kr_yoy")
    assert out.confidence == "rejected"
    assert "legacy_invalid" in out.rejection_reason


def test_validate_cpi_dt_1j22042(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    shutil.copy(
        Path(__file__).resolve().parents[1] / "data" / "tier2_sources.yaml",
        data / "tier2_sources.yaml",
    )
    from src.data_refresh.tier2_refresh import _kosis_api_key

    key = _kosis_api_key(data)
    if not key:
        return
    cand = TblCandidate(
        field="cpi_kr_yoy",
        candidate_tbl_id="DT_1J22042",
        org_id="101",
        stat_id="x",
        table_name="전국 소비자물가 상승률",
        search_term="전년동월비",
    )
    out = validate_candidate(cand, api_key=key, field="cpi_kr_yoy")
    assert out.confidence in {"high", "medium"}
    assert out.latest_value is not None
    assert _cpi_value_plausible(float(out.latest_value))
    assert out.itm_id == "T03"
    assert out.transform == "last"


def test_apply_selected_updates_yaml(tmp_path: Path) -> None:
    data = tmp_path / "data"
    out = tmp_path / "outputs"
    data.mkdir()
    out.mkdir()
    shutil.copy(
        Path(__file__).resolve().parents[1] / "data" / "tier2_sources.yaml",
        data / "tier2_sources.yaml",
    )
    discovery = {
        "cpi_kr_yoy": {
            "selected": {
                "selected": True,
                "candidate_tbl_id": "DT_1J22042",
                "org_id": "101",
                "itm_id": "T03",
                "obj_l1": "0",
                "transform": "last",
                "table_name": "전국 소비자물가 상승률",
                "search_term": "전년동월비",
            },
        },
        "pmi_kr": {"selected": None},
    }
    applied = apply_selected_to_tier2_sources(data, discovery)
    assert applied == ["cpi_kr_yoy"]
    from src.config import load_yaml

    cfg = load_yaml(data / "tier2_sources.yaml")
    q = cfg["kosis"]["queries"]["cpi_kr_yoy"]
    assert q["tblId"] == "DT_1J22042"
    assert q["itmId"] == "T03"
    assert q["transform"] == "last"


def test_invalid_tbl_ids_frozen() -> None:
    assert "DT_1J20001" in INVALID_TBL_IDS
    assert "DT_1C8013" in INVALID_TBL_IDS
