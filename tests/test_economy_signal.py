"""Review-only 5-stage equity sleeve from FRED tightening scores."""

from __future__ import annotations

from pathlib import Path

from alpha_system.economy_signal import (
    EconomySignal,
    SignalInput,
    assemble_signal,
    refresh_economy_signal,
    score_curve,
    score_hy_oas_bp,
    score_rate_change,
    score_real_yield,
    stage_from_scores,
    three_month_change,
)


def test_hy_and_hike_bands() -> None:
    assert score_hy_oas_bp(275) == 0
    assert score_hy_oas_bp(400) == 1
    assert score_hy_oas_bp(600) == 2
    assert score_rate_change(-0.1) == 0
    assert score_rate_change(0.10) == 1
    assert score_rate_change(0.50) == 2
    assert score_real_yield(0.8) == 0
    assert score_curve(-0.5) == 2


def test_stage_needs_three_known_metrics() -> None:
    stage, tightening, known = stage_from_scores([0, None, None, None, None])
    assert stage is None
    assert known == 1
    assert tightening == 0
    stage, _, known = stage_from_scores([2, 2, 2, 2, 2])
    assert stage == 5
    assert known == 5
    stage, _, _ = stage_from_scores([0, 0, 0, 0, 0])
    assert stage == 1


def test_three_month_change_uses_80d_lookback() -> None:
    rows = [
        {"date": "2026-09-01", "value": 5.50},
        {"date": "2026-08-01", "value": 5.40},
        {"date": "2026-06-01", "value": 5.00},
    ]
    assert three_month_change(rows) == 0.5


def test_assemble_keeps_book_default_when_unknown() -> None:
    signal = assemble_signal([])
    assert signal.stage is None
    assert signal.equity_share == 0.90
    assert signal.target_portfolio_written is False


def test_refresh_writes_cache_without_target(tmp_path: Path) -> None:
    class _Obs:
        def __init__(self, date: str, value: float) -> None:
            self.date = date
            self.value = value

    class _Res:
        def __init__(self, values: list[tuple[str, float]]) -> None:
            self.error = None
            self.observations = [_Obs(d, v) for d, v in values]

    series = {
        "DFF": [("2026-09-01", 5.33), ("2026-06-01", 5.33)],
        "DFII10": [("2026-09-01", 1.8)],
        "BAMLH0A0HYM2": [("2026-09-01", 3.1)],
        "T10Y2Y": [("2026-09-01", 0.35)],
        "IRSTCI01JPM156N": [("2026-09-01", 0.5), ("2026-06-01", 0.5)],
    }

    def get_fred(series_id: str, limit: int = 120) -> _Res:
        del limit
        return _Res(series[series_id])

    signal = refresh_economy_signal(tmp_path, api_key="dummy", get_fred=get_fred)
    assert signal.stage == 1
    assert signal.equity_share == 0.90
    assert signal.target_portfolio_written is False
    cache = tmp_path / "data" / "local" / "economy_signal.json"
    assert cache.exists()
    text = cache.read_text(encoding="utf-8")
    assert '"target_portfolio_written": false' in text
    assert '"stage": 1' in text


def test_missing_key_fail_open(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    signal = refresh_economy_signal(tmp_path, api_key="")
    assert isinstance(signal, EconomySignal)
    assert signal.stage is None
    assert signal.equity_share == 0.90


def test_display_hides_fred_tickers_and_utc() -> None:
    from datetime import date

    from alpha_system.ui.services.economy_display import (
        format_as_of,
        format_fetched_at,
        format_metric_value,
        hero_copy,
        metric_hint,
        metric_reading,
        metric_rows,
        metric_slider,
        metric_title,
        stress_label,
    )

    assert stress_label(0) == "여유"
    assert stress_label(2) == "긴축"
    assert format_fetched_at("2026-09-07T11:31:07Z") == "2026-09-07 20:31"
    item = SignalInput(
        key="hy_oas",
        label="미국 HY OAS",
        value=265.0,
        unit="bp",
        score=0,
        note="신용 스프레드",
    )
    assert metric_title(item) == "하이일드 스프레드"
    assert "DFII" not in metric_hint(item)
    assert "IRSTCI" not in metric_hint(item)
    assert format_metric_value(item) == "265 bp"
    assert "신용" in metric_reading(item)
    assert "DFII" not in metric_reading(item)
    slide = metric_slider(item)
    assert slide is not None
    assert 0 <= float(slide["pct"]) <= 100
    assert len(slide["ticks"]) == 2
    assert slide["ticks"][0]["label"] == "350"
    assert any(s["tone"] == "ok" for s in slide["segments"])
    fed = SignalInput(
        key="fed_hike",
        label="연준",
        value=0.0,
        unit="%p",
        note="DFF 수준 3.63",
        score=0,
    )
    assert format_metric_value(fed) == "변동 없음"
    assert "기준금리" in metric_hint(fed)
    assert "DFF" not in metric_hint(fed)
    assert "지연" in format_as_of("2026-06-01", today=date(2026, 9, 7))
    signal = assemble_signal(
        [
            item,
            SignalInput(key="real_us", label="실질금리", value=2.42, unit="%", score=2, as_of="2026-09-03"),
            fed,
            SignalInput(
                key="boj_hike",
                label="일본 콜",
                value=0.113,
                unit="%p",
                score=1,
                note="IRSTCI01JPM156N 수준 0.841",
                as_of="2026-06-01",
            ),
            SignalInput(key="curve", label="커브", value=0.41, unit="%p", score=0, as_of="2026-09-04"),
        ],
        fetched_at="2026-09-07T11:31:07Z",
    )
    hero = hero_copy(signal)
    assert hero["kicker"] == "2단계"
    assert hero["equity"] == "75%"
    assert "target" not in hero["why"].lower()
    rows = metric_rows(signal)
    blob = " ".join(f"{r['title']} {r['hint']} {r['reading']} {r['value']}" for r in rows)
    assert "DFII" not in blob
    assert "IRSTCI" not in blob
    assert "0/2" not in blob
    assert all(r.get("reading") for r in rows)
    assert all(r.get("slider") for r in rows)
    real_row = next(r for r in rows if str(r["title"]).startswith("미국 10년 실질"))
    assert "할인" in str(real_row["reading"])
    assert float(real_row["slider"]["pct"]) > 50  # 2.42% past the 2% cut on -0.5..4 scale
    page = Path(__file__).resolve().parents[1].joinpath(
        "alpha_system", "ui", "pages", "economy.py"
    ).read_text(encoding="utf-8")
    assert "st.dataframe" not in page
    assert "DFII" not in page
    assert "점수" not in page
    assert "eco-m-read" in page
    assert "eco-slide" in page
    assert "_slider_html" in page
