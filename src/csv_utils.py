from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def read_csv_optional(path: Path, **kwargs: Any) -> pd.DataFrame | None:
    """Read CSV; return None when file is missing, empty, or has no columns."""
    if not path.exists():
        return None
    if path.stat().st_size == 0:
        return None
    try:
        df = pd.read_csv(path, **kwargs)
    except pd.errors.EmptyDataError:
        return None
    if df.empty and len(df.columns) == 0:
        return None
    return df


def write_dataframe_csv(path: Path, df: pd.DataFrame, *, columns: list[str] | None = None) -> None:
    """Write CSV; preserve column headers even when df has no rows."""
    out = df
    if out.empty:
        cols = columns or list(out.columns)
        if cols:
            out = pd.DataFrame(columns=cols)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False, encoding="utf-8-sig")
