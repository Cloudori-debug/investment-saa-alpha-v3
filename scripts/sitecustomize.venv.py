"""Copy to venv or embed ``Lib/site-packages/sitecustomize.py``.

Finds the folder that contains alpha_dashboard.py so a copied tree still
puts the repo on sys.path. Windows Smart App Control can block unsigned
``pyarrow._compute``; pandas is shielded on import.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _app_root() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "alpha_dashboard.py").is_file():
            return parent
    return None


_root = _app_root()
if _root is not None:
    root_s = str(_root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)

try:
    from alpha_system.win_sac_pyarrow import shield_pandas_from_blocked_compute
except (ImportError, KeyError):
    pass
else:
    shield_pandas_from_blocked_compute()
