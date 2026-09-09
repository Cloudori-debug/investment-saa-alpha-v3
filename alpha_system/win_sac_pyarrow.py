"""Windows application control vs PyArrow (Smart App Control / WDAC).

pandas 2.3 imports ``pyarrow.compute`` when pyarrow is installed. Windows can
block unsigned ``_compute*.pyd`` (WinError 4551) while ``pyarrow.lib`` still
loads — hide pyarrow only during ``import pandas``.

If ``pyarrow.lib`` itself is blocked, Streamlit ``st.dataframe`` crashes on
import. Then we keep pandas, skip Arrow, and draw an HTML table instead.
Score ranks and target files are unchanged.
"""

from __future__ import annotations

import sys
from html import escape
from typing import Any, Final

_SHIELDED: bool = False
_LIB_OK: bool | None = None

_PYARROW_PREFIXES: Final[tuple[str, ...]] = ("pyarrow", "pyarrow.")


class _HidePyarrowFinder:
    def find_spec(self, fullname: str, path: object, target: object = None):
        if fullname == "pyarrow" or fullname.startswith("pyarrow."):
            raise ImportError(
                "pyarrow hidden while pandas imports "
                "(Windows blocked pyarrow._compute)"
            )
        return None


def _drop_pyarrow_modules() -> None:
    for key in list(sys.modules):
        if key == "pyarrow" or key.startswith("pyarrow."):
            sys.modules.pop(key, None)


def _compute_importable() -> bool:
    try:
        import pyarrow._compute  # noqa: F401
    except (ImportError, OSError):
        _drop_pyarrow_modules()
        return False
    return True


def pyarrow_lib_ok() -> bool:
    """False when Windows blocks pyarrow.lib (st.dataframe cannot start)."""
    global _LIB_OK
    if _LIB_OK is not None:
        return _LIB_OK
    try:
        import pyarrow.lib  # noqa: F401
    except (ImportError, OSError):
        _drop_pyarrow_modules()
        _LIB_OK = False
        return False
    _LIB_OK = True
    return True


def shield_pandas_from_blocked_compute() -> bool:
    """Return True if pyarrow.compute is usable (or not Windows / already imported)."""
    global _SHIELDED
    if _SHIELDED or "pandas" in sys.modules:
        return True
    if sys.platform != "win32":
        return True
    if _compute_importable():
        return True

    saved = {
        key: sys.modules.pop(key)
        for key in list(sys.modules)
        if key == "pyarrow" or key.startswith("pyarrow.")
    }
    finder = _HidePyarrowFinder()
    sys.meta_path.insert(0, finder)
    try:
        import pandas  # noqa: F401
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)
        sys.modules.update(saved)
    _SHIELDED = True
    return False


def as_plain_frame(data: Any):
    import pandas as pd

    if data is None:
        return pd.DataFrame()
    if isinstance(data, pd.DataFrame):
        return data
    if type(data).__name__ == "Styler":
        return data.data
    return pd.DataFrame(data)


def _cell_text(value: Any) -> str:
    if value is None:
        return "—"
    try:
        import pandas as pd

        if pd.isna(value):
            return "—"
    except (TypeError, ValueError):
        pass
    return str(value)


def _is_num_col(series: Any) -> bool:
    import pandas as pd

    return bool(pd.api.types.is_numeric_dtype(series))


def _fmt_num(value: Any) -> str:
    import pandas as pd

    if value is None or pd.isna(value):
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return _cell_text(value)
    if abs(num - round(num)) < 1e-9:
        return f"{int(round(num)):,}"
    if abs(num) >= 100:
        return f"{num:,.1f}"
    return f"{num:,.2f}"


def _http_url(raw: Any) -> str:
    text = str(raw or "").strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return ""


def _shortcut_cell(col: object, raw: Any) -> tuple[str, str] | None:
    """HTML shortcut + sort key. None = not a link cell."""
    url = _http_url(raw)
    if not url:
        return None
    href, _, frag = url.partition("#")
    if not href.startswith("http"):
        return None
    col_name = str(col)
    if col_name == "차트" or "fchart.naver" in href:
        label = "차트"
    else:
        label = "바로가기"
    html = (
        f'<a href="{escape(url, quote=True)}" target="_blank" '
        f'rel="noopener noreferrer">{escape(label)}</a>'
    )
    return html, frag or label


def _sticky_col_index(cols: list[Any]) -> int:
    names = [str(c) for c in cols]
    if "종목" in names:
        return names.index("종목")
    if "이름" in names:
        return names.index("이름")
    return 0


_GRID_CSS = """
.saa-grid-wrap{overflow:auto;max-height:28rem;border:1px solid #d8d2c4;background:#faf8f3;}
.saa-grid{border-collapse:separate;border-spacing:0;font:13px/1.25 Pretendard,"Noto Sans KR",sans-serif;min-width:100%;color:#1c1a16;}
.saa-grid th,.saa-grid td{padding:6px 10px;border-bottom:1px solid #e8e2d6;white-space:nowrap;background:#faf8f3;}
.saa-grid th{position:sticky;top:0;z-index:3;font-size:11px;font-weight:650;color:#5c574e;text-align:left;cursor:pointer;user-select:none;border-bottom:1px solid #cfc8b8;}
.saa-grid th:hover{color:#1c1a16;}
.saa-grid td.num,.saa-grid th.num{text-align:right;font-variant-numeric:tabular-nums;}
.saa-grid tbody tr:nth-child(even) td{background:#f3efe6;}
.saa-grid tbody tr:hover td{background:#ebe4d4;}
.saa-grid .sticky-col{position:sticky;left:0;z-index:2;border-right:1px solid #e8e2d6;}
.saa-grid th.sticky-col{z-index:4;}
.saa-grid a{color:#1d4a3c;font-weight:650;text-decoration:none;padding:2px 8px;border:1px solid #c5d4c8;background:#e8efe8;}
"""


def dataframe_to_html(data: Any) -> str:
    frame = as_plain_frame(data)
    cols = list(frame.columns)
    sticky = _sticky_col_index(cols) if cols else 0
    num_flags = [_is_num_col(frame[c]) if len(frame.columns) else False for c in cols]
    head_cells: list[str] = []
    for i, col in enumerate(cols):
        cls = []
        if num_flags[i]:
            cls.append("num")
        if i == sticky:
            cls.append("sticky-col")
        attr = f' class="{" ".join(cls)}"' if cls else ""
        head_cells.append(
            f'<th{attr} data-col="{i}" data-num="{1 if num_flags[i] else 0}">{escape(str(col))}</th>'
        )
    body_rows: list[str] = []
    for _, row in frame.iterrows():
        cells: list[str] = []
        for i, col in enumerate(cols):
            raw = row[col]
            inner: str
            if num_flags[i]:
                shown = _fmt_num(raw)
                inner = escape(shown)
                try:
                    import pandas as pd

                    dv = "" if raw is None or pd.isna(raw) else str(float(raw))
                except (TypeError, ValueError):
                    dv = shown
            else:
                shortcut = _shortcut_cell(col, raw)
                if shortcut is not None:
                    inner, dv = shortcut
                else:
                    shown = _cell_text(raw)
                    inner = escape(shown)
                    dv = shown
            cls = []
            if num_flags[i]:
                cls.append("num")
            if i == sticky:
                cls.append("sticky-col")
            attr = f' class="{" ".join(cls)}"' if cls else ""
            cells.append(
                f'<td{attr} data-v="{escape(dv, quote=True)}">{inner}</td>'
            )
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return (
        f'<div class="saa-grid-wrap"><table class="saa-grid">'
        f'<thead><tr>{"".join(head_cells)}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody></table></div>'
    )


def dataframe_grid_document(data: Any) -> str:
    inner = dataframe_to_html(data)
    script = """
<script>
(function(){
  const table=document.querySelector('.saa-grid');
  if(!table) return;
  table.querySelectorAll('th').forEach(function(th){
    th.addEventListener('click', function(){
      const col=Number(th.getAttribute('data-col'));
      const numeric=th.getAttribute('data-num')==='1';
      const tbody=table.tBodies[0];
      const rows=[].slice.call(tbody.rows);
      const key=col+':'+(table.dataset.sort===col+':asc'?'desc':'asc');
      const dir=key.split(':')[1];
      rows.sort(function(a,b){
        const va=a.cells[col].getAttribute('data-v')||'';
        const vb=b.cells[col].getAttribute('data-v')||'';
        let cmp=0;
        if(numeric){
          const na=parseFloat(va), nb=parseFloat(vb);
          if(isNaN(na)&&isNaN(nb)) cmp=0;
          else if(isNaN(na)) cmp=1;
          else if(isNaN(nb)) cmp=-1;
          else cmp=na-nb;
        } else {
          cmp=va.localeCompare(vb,'ko');
        }
        return dir==='desc'?-cmp:cmp;
      });
      rows.forEach(function(r){tbody.appendChild(r);});
      table.dataset.sort=key;
    });
  });
})();
</script>
"""
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<style>{_GRID_CSS}</style></head><body style='margin:0'>"
        f"{inner}{script}</body></html>"
    )


def default_selected_rows(selection_default: Any) -> list[int]:
    if not selection_default:
        return []
    if isinstance(selection_default, dict):
        sel = selection_default.get("selection") or selection_default
        if isinstance(sel, dict):
            return [int(i) for i in (sel.get("rows") or [])]
    return []


class _Selection:
    def __init__(self, rows: list[int]):
        self.rows = rows
        self.columns: list[Any] = []


class DataframeFallbackEvent:
    def __init__(self, rows: list[int] | None = None):
        self.selection = _Selection(list(rows or []))


def _fallback_caption() -> str:
    try:
        from alpha_system.ui.services.ui_copy import copy_get

        return copy_get(
            "approval",
            "arrow_blocked",
            default=(
                "칸 제목을 누르면 정렬됩니다. 표 엔진 제한 · 점수·target 불변."
            ),
        )
    except Exception:
        return (
            "칸 제목을 누르면 정렬됩니다. 표 엔진 제한 · 점수·target 불변."
        )


def render_dataframe_fallback(data: Any = None, **kwargs: Any) -> DataframeFallbackEvent:
    import streamlit as st
    import streamlit.components.v1 as components

    frame = as_plain_frame(data)
    hint_key = "_saa_grid_hint"
    if not st.session_state.get(hint_key):
        st.caption(_fallback_caption())
        st.session_state[hint_key] = True
    on_select = kwargs.get("on_select", "ignore")
    selected: list[int] = []
    if on_select not in (None, "ignore", False) and not frame.empty:
        key = str(kwargs.get("key") or "saa_arrow_fb")
        defaults = set(default_selected_rows(kwargs.get("selection_default")))
        name_col = "종목" if "종목" in frame.columns else (
            frame.columns[0] if len(frame.columns) else None
        )
        labels: list[str] = []
        for pos, (_, row) in enumerate(frame.iterrows()):
            name = _cell_text(row[name_col]) if name_col is not None else str(pos + 1)
            labels.append(f"{pos + 1}. {name}")
        default_labels = [labels[i] for i in sorted(defaults) if i < len(labels)]
        from alpha_system.ui.services.ui_copy import copy_get

        picked = st.multiselect(
            copy_get("portfolio", "grid_hold_pick", default="보유로 둘 종목"),
            labels,
            default=default_labels,
            key=f"{key}_ms",
        )
        selected = [labels.index(item) for item in picked if item in labels]
    height = int(min(520, max(160, 48 + 33 * min(len(frame), 12))))
    components.html(dataframe_grid_document(frame), height=height, scrolling=True)
    return DataframeFallbackEvent(selected)


def is_blocked_native_dll(exc: BaseException) -> bool:
    """True for Windows Smart App Control / WDAC blocking a .pyd/.dll."""
    text = str(exc)
    low = text.lower()
    if "애플리케이션 제어 정책" in text:
        return True
    if "application control policy" in low:
        return True
    if "dll load failed" in low:
        return True
    if "winerror 4551" in low or "error 4551" in low:
        return True
    return False


def _fallback_from_call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> DataframeFallbackEvent:
    extra = dict(kwargs)
    data = extra.pop("data", None)
    if data is None and args:
        data = args[0]
    return render_dataframe_fallback(data, **extra)


def _wrap_bound_dataframe(orig: Any) -> Any:
    if getattr(orig, "_saa_arrow_fallback", False):
        return orig

    def dataframe(*args: Any, **kwargs: Any) -> Any:
        try:
            return orig(*args, **kwargs)
        except (ImportError, OSError) as exc:
            if not is_blocked_native_dll(exc):
                raise
            return _fallback_from_call(args, kwargs)

    dataframe._saa_arrow_fallback = True  # type: ignore[attr-defined]
    return dataframe


def _wrap_unbound_dataframe(orig: Any) -> Any:
    if getattr(orig, "_saa_arrow_fallback", False):
        return orig

    def dataframe(self: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return orig(self, *args, **kwargs)
        except (ImportError, OSError) as exc:
            if not is_blocked_native_dll(exc):
                raise
            return _fallback_from_call(args, kwargs)

    dataframe._saa_arrow_fallback = True  # type: ignore[attr-defined]
    return dataframe


def install_streamlit_dataframe_fallback() -> bool:
    """Always wrap st.dataframe. On blocked PyArrow DLL, draw an HTML table.

    ``st.dataframe`` is a bound method snapshot from import time, so patching
    ArrowMixin alone does not catch confirmation-page tables.
    """
    try:
        import streamlit as st
        from streamlit.delta_generator import DeltaGenerator
        from streamlit.elements.arrow import ArrowMixin
    except ImportError:
        return False

    st.dataframe = _wrap_bound_dataframe(st.dataframe)
    if hasattr(st, "data_editor"):
        st.data_editor = _wrap_bound_dataframe(st.data_editor)
    ArrowMixin.dataframe = _wrap_unbound_dataframe(ArrowMixin.dataframe)
    if "dataframe" in DeltaGenerator.__dict__:
        DeltaGenerator.dataframe = _wrap_unbound_dataframe(DeltaGenerator.dataframe)
    return True
