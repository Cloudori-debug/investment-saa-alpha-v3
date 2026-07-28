from __future__ import annotations

from pathlib import Path

import pytest

from src.validation.system_health import run_system_health
from src.validation.ai_export import build_ai_export_bundle, CROSS_VALIDATION_PROMPT

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUT = ROOT / "outputs"


def test_system_health_runs_on_sample_data():
    report = run_system_health(DATA, OUTPUT)
    assert report.overall in ("pass", "warn", "fail")
    assert report.checks
    assert report.summary["pass"] >= 1
    modules = {c.module for c in report.checks}
    assert "input" in modules
    assert "compass_tier1" in modules


def test_system_health_detects_required_files():
    report = run_system_health(DATA, OUTPUT)
    market_check = next(c for c in report.checks if c.name == "market_indicators.csv")
    assert market_check.status == "pass"


def test_ai_export_bundle_structure():
    bundle = build_ai_export_bundle(DATA, OUTPUT, include_health=False)
    assert bundle["export_schema_version"] == "1.0"
    assert bundle["validation_prompt"] == CROSS_VALIDATION_PROMPT
    assert "health_report" in bundle
    assert "limitations" in bundle


def test_ai_export_writes_health(tmp_path):
    out = tmp_path / "outputs"
    out.mkdir()
    bundle = build_ai_export_bundle(DATA, out)
    assert (out / "system_health.json").exists()
