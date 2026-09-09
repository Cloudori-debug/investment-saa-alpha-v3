from __future__ import annotations

from alpha_system.win_sac_pyarrow import (
    DataframeFallbackEvent,
    as_plain_frame,
    dataframe_to_html,
    default_selected_rows,
    shield_pandas_from_blocked_compute,
)


def test_pandas_imports_when_pyarrow_compute_blocked() -> None:
    shield_pandas_from_blocked_compute()
    import pandas as pd

    frame = pd.DataFrame({"a": [1, 2]})
    assert list(frame["a"]) == [1, 2]


def test_dataframe_to_html_escapes_and_skips_index() -> None:
    import pandas as pd

    html = dataframe_to_html(
        pd.DataFrame({"종목": ["<x>"], "합계": [1.5]})
    )
    assert "종목" in html
    assert "&lt;x&gt;" in html
    assert "saa-grid" in html
    assert "data-v=" in html
    assert "<th>0</th>" not in html
    html = dataframe_to_html(
        pd.DataFrame(
            {
                "차트": ["https://finance.naver.com/item/fchart.naver?code=005930"],
                "종목": ["삼성전자"],
            }
        )
    )
    assert ">차트</a>" in html
    assert "fchart.naver" in html
    assert ">https://" not in html


def test_styler_uses_underlying_frame() -> None:
    import pandas as pd

    styled = pd.DataFrame({"종목": ["삼성전자"]}).style
    frame = as_plain_frame(styled)
    assert list(frame["종목"]) == ["삼성전자"]


def test_selection_default_and_event() -> None:
    rows = default_selected_rows({"selection": {"rows": [0, 2]}})
    assert rows == [0, 2]
    event = DataframeFallbackEvent([1])
    assert event.selection.rows == [1]


def test_dashboard_installs_arrow_fallback() -> None:
    from pathlib import Path

    dash = Path(__file__).resolve().parents[1].joinpath("alpha_dashboard.py").read_text(
        encoding="utf-8"
    )
    assert "install_streamlit_dataframe_fallback" in dash
    assert "safe_page" in dash


def test_bound_dataframe_wrap_catches_policy_dll() -> None:
    from alpha_system import win_sac_pyarrow as mod

    seen: dict = {}

    def fake_fb(data, **kwargs):
        del kwargs
        seen["data"] = data
        return mod.DataframeFallbackEvent([])

    orig_fb = mod.render_dataframe_fallback
    mod.render_dataframe_fallback = fake_fb  # type: ignore[assignment]
    try:

        def orig(*args, **kwargs):
            del args, kwargs
            raise ImportError(
                "DLL load failed while importing lib: "
                "애플리케이션 제어 정책에서 이 파일을 차단했습니다."
            )

        wrapped = mod._wrap_bound_dataframe(orig)
        wrapped([{"종목": "x"}])
        assert seen["data"] == [{"종목": "x"}]
    finally:
        mod.render_dataframe_fallback = orig_fb

