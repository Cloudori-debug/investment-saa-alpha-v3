import json
import math
from pathlib import Path

import pandas as pd
import pytest

from src.field_normalize import normalize_sector, normalize_ticker_export, sanitize_json_value
from src.validation.ai_export import _dataframe_records_for_export, write_ai_export_json

DATA = Path(__file__).resolve().parents[1] / "data"
OUT = Path(__file__).resolve().parents[1] / "outputs"


def test_normalize_ticker_export_preserves_leading_zeros():
    assert normalize_ticker_export(8500) == "008500"
    assert normalize_ticker_export("3080") == "003080"
    assert normalize_ticker_export("008500") == "008500"


def test_normalize_sector_maps_nan_to_unknown():
    assert normalize_sector("") == "unknown"
    assert normalize_sector("nan") == "unknown"
    assert normalize_sector(float("nan")) == "unknown"
    assert normalize_sector("telecom") == "telecom"


def test_dataframe_records_for_export_strict_json():
    df = pd.DataFrame(
        [
            {"ticker": 8500, "name": "일정실업", "sector": float("nan"), "score": 57.4},
        ]
    )
    records = _dataframe_records_for_export(df)
    assert records[0]["ticker"] == "008500"
    assert records[0]["sector"] == "unknown"
    json.dumps(records, allow_nan=False)


def test_write_ai_export_json_no_nan(tmp_path):
    path = tmp_path / "ai_export_bundle.json"
    bundle = {
        "tables_summary": {
            "alpha_candidates_top10": [
                {"ticker": "008500", "sector": "unknown", "score": 1.0},
            ]
        },
        "nested": {"bad": math.nan},
    }
    write_ai_export_json(bundle, path)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["nested"]["bad"] is None
    json.dumps(loaded, allow_nan=False)


def test_build_ai_export_bundle_tables_summary_tickers(tmp_path):
    from src.validation.ai_export import build_ai_export_bundle

    out = tmp_path / "outputs"
    out.mkdir()
    pd.DataFrame(
        [
            {
                "rank": 1,
                "ticker": "008500",
                "name": "일정실업",
                "sector": "",
                "total_score": 57.4,
                "grade": "B",
                "eligible_action": "WATCH",
            }
        ]
    ).to_csv(out / "alpha_candidates.csv", index=False)

    bundle = build_ai_export_bundle(DATA, out, include_health=False)
    row = bundle["tables_summary"]["alpha_candidates_top10"][0]
    assert row["ticker"] == "008500"
    assert row["sector"] == "unknown"
    json.dumps(bundle["tables_summary"], allow_nan=False)


def test_gpt_context_sectors_normalized(tmp_path):
    from src.alpha.gpt_context import build_gpt_context
    from src.alpha.schemas import AlphaCandidate, AlphaPipelineResult

    candidate = AlphaCandidate.model_validate(
        {
            "rank": 1,
            "ticker": "008500",
            "name": "일정실업",
            "sector": "",
            "quality_score": 60.0,
            "valuation_score": 70.0,
            "momentum_score": 50.0,
            "shareholder_return_score": 60.0,
            "base_score": 57.0,
            "penalty": 0.0,
            "total_score": 57.0,
            "grade": "B",
            "key_reason": "test",
            "eligible_action": "WATCH",
        }
    )
    result = AlphaPipelineResult(
        as_of="2026-06-24",
        candidates=[candidate],
        excluded=[],
        holdings_review=[],
        data_gate="YELLOW",
        limitations=[],
    )
    ctx = build_gpt_context(
        result,
        portfolio_proposal=[{"ticker": "008500", "name": "일정실업", "sector": ""}],
    )
    assert ctx["top_candidates"][0]["sector"] == "unknown"
    assert ctx["portfolio_proposal"][0]["sector"] == "unknown"

    from src.alpha.data_gate import adjust_gate_for_sector_coverage

    gate, notes = adjust_gate_for_sector_coverage(
        "GREEN",
        {"sector_weights": {"unknown": 12.0, "telecom": 20.0}},
        unknown_threshold=0.20,
    )
    assert gate == "YELLOW"
    assert notes

    gate2, notes2 = adjust_gate_for_sector_coverage(
        "GREEN",
        {"sector_weights": {"telecom": 20.0, "consumer": 15.0}},
    )
    assert gate2 == "GREEN"
    assert not notes2
