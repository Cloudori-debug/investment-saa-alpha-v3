"""Regime override divergence (AC-05b) + persistence escalation — visibility only."""



from __future__ import annotations



import json

from pathlib import Path



from src.validation.acceptance_check import _check_regime_override, _check_regime_override_divergence

from src.validation.regime_override_divergence import (

    append_regime_divergence_log,

    assess_regime_divergence_with_persistence,

    assess_regime_override_divergence,

    count_consecutive_divergence_days,

    regime_divergence_log_path,

    regime_override_gap,

    regime_severity,

)





def test_regime_severity_order():

    assert regime_severity("RISK_ON") == 0

    assert regime_severity("YELLOW_STABLE") == 1

    assert regime_severity("CAUTION") == 2

    assert regime_severity("RISK_OFF") == 3

    assert regime_severity("CRISIS") == 4





def test_gap_crisis_to_yellow_stable_is_3():

    assert regime_override_gap("CRISIS", "YELLOW_STABLE") == 3





def test_assess_gap3_warns():

    a = assess_regime_override_divergence(

        computed_regime="CRISIS",

        applied_regime="YELLOW_STABLE",

        override_active=True,

        override_reason="BOK FSR",

        regime_set_date="2026-06-24",

        warn_gap=2,

    )

    assert a.warn is True

    assert a.status == "warn"

    assert a.gap == 3

    assert "gap=3" in a.message

    assert "자동 해제" in a.message

    assert a.detail["regime_override_reason"] == "BOK FSR"





def test_assess_gap1_no_warn():

    a = assess_regime_override_divergence(

        computed_regime="CAUTION",

        applied_regime="YELLOW_STABLE",

        override_active=True,

        warn_gap=2,

    )

    assert a.warn is False

    assert a.status == "pass"

    assert a.gap == 1

    assert "정보" in a.message





def test_assess_gap0_no_warn():

    a = assess_regime_override_divergence(

        computed_regime="YELLOW_STABLE",

        applied_regime="YELLOW_STABLE",

        override_active=True,

        warn_gap=2,

    )

    assert a.warn is False

    assert a.status == "pass"

    assert a.gap == 0





def test_ac05b_from_compass_regime_json(tmp_path: Path):

    data = tmp_path / "data"

    out = tmp_path / "outputs"

    data.mkdir()

    out.mkdir()

    (out / "compass_regime.json").write_text(

        json.dumps(

            {

                "computed_regime": "CRISIS",

                "applied_regime": "YELLOW_STABLE",

                "override": {"active": True, "reason": "BOK FSR"},

            }

        ),

        encoding="utf-8",

    )

    (data / "market_indicators.csv").write_text(

        "date,regime,regime_set_date,regime_expires_date,regime_override_reason\n"

        "2026-07-12,YELLOW_STABLE,2026-06-24,2026-09-24,BOK FSR\n",

        encoding="utf-8-sig",

    )

    item = _check_regime_override_divergence(data, out)

    assert item.id == "AC-05b"

    assert item.status == "warn"

    assert item.detail.get("gap") == 3

    assert (out / "regime_divergence_log.jsonl").exists()





def test_ac05_time_based_still_warns_on_age(tmp_path: Path):

    """AC-05 시간 기반 회귀 — 오래된 override는 계속 warn."""

    data = tmp_path / "data"

    out = tmp_path / "outputs"

    data.mkdir()

    out.mkdir()

    (out / "compass_regime.json").write_text(

        json.dumps(

            {

                "computed_regime": "YELLOW_STABLE",

                "applied_regime": "YELLOW_STABLE",

                "override": {"active": True, "reason": "test"},

            }

        ),

        encoding="utf-8",

    )

    (data / "market_indicators.csv").write_text(

        "date,regime,regime_set_date,regime_expires_date,regime_override_reason,"

        "kospi,kospi_ma200,vix,usdkrw,us_10y,credit_spread,export_yoy,pmi\n"

        "2026-07-12,YELLOW_STABLE,2026-06-01,2026-09-24,test,"

        "8000,7500,15,1300,4.0,1.0,5.0,50\n",

        encoding="utf-8-sig",

    )

    item = _check_regime_override(data, out, as_of="2026-07-12")

    assert item.id == "AC-05"

    assert item.status == "warn"

    assert "영업일" in item.message





def _write_log(out: Path, rows: list[dict]) -> None:

    path = regime_divergence_log_path(out)

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:

        for row in rows:

            handle.write(json.dumps(row, ensure_ascii=False) + "\n")





def test_count_consecutive_divergence_days_three(tmp_path: Path):

    out = tmp_path / "outputs"

    _write_log(

        out,

        [

            {
                "date": "2026-07-10",
                "gap": 3,
                "override_active": True,
                "applied_regime": "YELLOW_STABLE",
            },

            {
                "date": "2026-07-11",
                "gap": 3,
                "override_active": True,
                "applied_regime": "YELLOW_STABLE",
            },

            {
                "date": "2026-07-12",
                "gap": 3,
                "override_active": True,
                "applied_regime": "YELLOW_STABLE",
            },

        ],

    )

    assert count_consecutive_divergence_days(

        regime_divergence_log_path(out),

        warn_gap=2,

        as_of="2026-07-12",

    ) == 3





def test_count_resets_when_gap_below_threshold(tmp_path: Path):

    out = tmp_path / "outputs"

    _write_log(

        out,

        [

            {
                "date": "2026-07-12",
                "gap": 3,
                "override_active": True,
                "applied_regime": "YELLOW_STABLE",
            },

            {
                "date": "2026-07-11",
                "gap": 1,
                "override_active": True,
                "applied_regime": "YELLOW_STABLE",
            },

            {
                "date": "2026-07-10",
                "gap": 3,
                "override_active": True,
                "applied_regime": "YELLOW_STABLE",
            },

        ],

    )

    assert count_consecutive_divergence_days(

        regime_divergence_log_path(out),

        warn_gap=2,

        as_of="2026-07-12",

    ) == 1





def test_count_resets_when_override_inactive(tmp_path: Path):

    out = tmp_path / "outputs"

    _write_log(

        out,

        [

            {
                "date": "2026-07-12",
                "gap": 3,
                "override_active": True,
                "applied_regime": "YELLOW_STABLE",
            },

            {
                "date": "2026-07-11",
                "gap": 3,
                "override_active": False,
                "applied_regime": "YELLOW_STABLE",
            },

        ],

    )

    assert count_consecutive_divergence_days(

        regime_divergence_log_path(out),

        warn_gap=2,

        as_of="2026-07-12",

    ) == 1





def test_count_resets_when_applied_regime_changes(tmp_path: Path):

    out = tmp_path / "outputs"

    _write_log(

        out,

        [

            {
                "date": "2026-07-12",
                "gap": 2,
                "override_active": True,
                "applied_regime": "CAUTION",
            },

            {
                "date": "2026-07-11",
                "gap": 3,
                "override_active": True,
                "applied_regime": "YELLOW_STABLE",
            },

            {
                "date": "2026-07-10",
                "gap": 3,
                "override_active": True,
                "applied_regime": "YELLOW_STABLE",
            },

        ],

    )

    assert count_consecutive_divergence_days(

        regime_divergence_log_path(out),

        warn_gap=2,

        as_of="2026-07-12",

    ) == 1





def test_escalation_after_three_days(tmp_path: Path):

    out = tmp_path / "outputs"

    out.mkdir()

    _write_log(

        out,

        [

            {
                "date": "2026-07-10",
                "gap": 3,
                "override_active": True,
                "applied_regime": "YELLOW_STABLE",
            },

            {
                "date": "2026-07-11",
                "gap": 3,
                "override_active": True,
                "applied_regime": "YELLOW_STABLE",
            },

        ],

    )

    assessment = assess_regime_divergence_with_persistence(

        out,

        computed_regime="CRISIS",

        applied_regime="YELLOW_STABLE",

        override_active=True,

        override_reason="BOK FSR",

        regime_set_date="2026-06-24",

        as_of="2026-07-12",

        warn_gap=2,

    )

    assert assessment.warn is True

    assert assessment.status == "warn"

    assert assessment.consecutive_days == 3

    assert assessment.escalated is True

    assert assessment.recommended_review_by == "2026-07-14"

    assert "3일째 지속" in assessment.message

    assert "2026-07-14" in assessment.message





def test_no_escalation_with_one_log_day(tmp_path: Path):

    out = tmp_path / "outputs"

    out.mkdir()

    assessment = assess_regime_divergence_with_persistence(

        out,

        computed_regime="CRISIS",

        applied_regime="YELLOW_STABLE",

        override_active=True,

        as_of="2026-07-12",

        warn_gap=2,

    )

    assert assessment.warn is True

    assert assessment.escalated is False

    assert assessment.consecutive_days == 1

    assert assessment.recommended_review_by is None

    assert "일째 지속" not in assessment.message





def test_append_skips_unchanged_duplicate_date(tmp_path: Path):

    out = tmp_path / "outputs"

    first = append_regime_divergence_log(

        out,

        date="2026-07-12",

        computed_regime="CRISIS",

        applied_regime="YELLOW_STABLE",

        gap=3,

        override_active=True,

    )

    second = append_regime_divergence_log(

        out,

        date="2026-07-12",

        computed_regime="CRISIS",

        applied_regime="YELLOW_STABLE",

        gap=3,

        override_active=True,

    )

    assert first is not None

    assert second is None

    lines = regime_divergence_log_path(out).read_text(encoding="utf-8").strip().splitlines()

    assert len(lines) == 1





def test_append_upserts_when_values_change(tmp_path: Path):

    out = tmp_path / "outputs"

    first = append_regime_divergence_log(

        out,

        date="2026-07-12",

        computed_regime="CRISIS",

        applied_regime="YELLOW_STABLE",

        gap=3,

        override_active=True,

    )

    updated = append_regime_divergence_log(

        out,

        date="2026-07-12",

        computed_regime="CRISIS",

        applied_regime="CAUTION",

        gap=2,

        override_active=True,

    )

    assert first is not None

    assert updated is not None

    lines = regime_divergence_log_path(out).read_text(encoding="utf-8").strip().splitlines()

    assert len(lines) == 1

    row = json.loads(lines[0])

    assert row["applied_regime"] == "CAUTION"

    assert row["gap"] == 2


