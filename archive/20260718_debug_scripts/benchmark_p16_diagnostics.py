"""P1.6 diagnostics-only 2-run benchmark (warmup + cache hit)."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from src.runtime.diagnostics_cache import run_diagnostics_with_cache
from src.runtime.profiler import RuntimeProfiler

DATA = Path("data")
OUT = Path("outputs")


def one(run_id: str, label: str) -> None:
    t0 = time.perf_counter()
    prof = RuntimeProfiler(run_id=run_id, run_mode="standard")
    result = run_diagnostics_with_cache(
        DATA,
        OUT,
        run_id=run_id,
        run_full_diag=True,
        run_mode="standard",
        profiler=prof,
    )
    elapsed = time.perf_counter() - t0
    prof.write(OUT)
    prof_path = OUT / f"runtime_profile_standard_p16_{label}.json"
    shutil.copy(OUT / "runtime_profile.json", prof_path)
    print(
        label,
        "elapsed",
        round(elapsed, 2),
        "diag_hits",
        result.cache_hit_count,
        "diag_miss",
        result.cache_miss_count,
        "kosis_exec",
        prof.kosis_refresh_executed,
        "kosis_skip",
        prof.kosis_refresh_skip_reason,
        "kosis_saved",
        prof.kosis_refresh_seconds_saved_estimate,
    )


if __name__ == "__main__":
    one("p16-warmup", "warmup")
    one("p16-cache-hit", "cache_hit")
    print("done")
