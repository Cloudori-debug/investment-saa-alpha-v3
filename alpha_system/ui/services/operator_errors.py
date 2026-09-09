"""Operator-facing error copy. Does not change scores or target files.

Windows Smart App Control / WDAC cannot be relaxed from this app.
"""

from __future__ import annotations

import traceback
from typing import Any

from alpha_system.ui.services.ui_copy import copy_get
from alpha_system.win_sac_pyarrow import is_blocked_native_dll


_CONTROL_EXC = frozenset({"RerunException", "StopException"})


def is_streamlit_control(exc: BaseException) -> bool:
    return type(exc).__name__ in _CONTROL_EXC


def classify_operator_error(exc: BaseException) -> str:
    text = str(exc)
    low = text.lower()
    if is_blocked_native_dll(exc) and (
        "pyarrow" in low
        or "while importing lib" in low
        or _mentions_pyarrow(exc)
    ):
        return "pyarrow_dll"
    if is_blocked_native_dll(exc):
        return "dll_policy"
    if isinstance(exc, ModuleNotFoundError):
        return "missing_module"
    if isinstance(exc, PermissionError) or "permission denied" in low:
        return "permission"
    return "generic"


def _mentions_pyarrow(exc: BaseException) -> bool:
    tb = exc.__traceback__
    while tb is not None:
        filename = (tb.tb_frame.f_code.co_filename or "").replace("\\", "/").lower()
        if "pyarrow" in filename or filename.endswith("/arrow.py"):
            return True
        tb = tb.tb_next
    return False


def _copy_pair(kind: str) -> tuple[str, str]:
    title = copy_get("errors", f"{kind}_title", default="화면을 그리는 중 오류가 났습니다.")
    body = copy_get(
        "errors",
        f"{kind}_body",
        default="아래 기술 내용을 확인하세요. 이 오류만으로 점수·target 파일은 바뀌지 않습니다.",
    )
    return title, body


def help_for_exception(exc: BaseException) -> tuple[str, str]:
    return _copy_pair(classify_operator_error(exc))


def render_operator_exception(exc: BaseException) -> None:
    import streamlit as st

    if is_streamlit_control(exc):
        raise exc
    title, body = help_for_exception(exc)
    st.error(title)
    st.markdown(body)
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    with st.expander(copy_get("errors", "tech_expand", default="기술 내용"), expanded=False):
        st.code(detail)


def safe_page(render: Any, ctx: Any) -> None:
    try:
        render(ctx)
    except Exception as exc:
        render_operator_exception(exc)
