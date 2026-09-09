from __future__ import annotations

from alpha_system.ui.services.operator_errors import classify_operator_error, help_for_exception
from alpha_system.ui.services.ui_copy import load_ui_copy
from alpha_system.win_sac_pyarrow import is_blocked_native_dll


def test_pyarrow_dll_is_classified_and_has_copy() -> None:
    load_ui_copy.cache_clear()
    exc = ImportError(
        "DLL load failed while importing lib: "
        "애플리케이션 제어 정책에서 이 파일을 차단했습니다."
    )
    assert is_blocked_native_dll(exc)
    assert classify_operator_error(exc) == "pyarrow_dll"
    title, body = help_for_exception(exc)
    assert "PyArrow" in title
    assert "스마트 앱 제어" in body
    assert "대신 넣을 수는 없습니다" in body


def test_generic_and_module_errors() -> None:
    load_ui_copy.cache_clear()
    assert classify_operator_error(ModuleNotFoundError("foo")) == "missing_module"
    assert classify_operator_error(RuntimeError("boom")) == "generic"
    _, body = help_for_exception(RuntimeError("boom"))
    assert "target" in body
