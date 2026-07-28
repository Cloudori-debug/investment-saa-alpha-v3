#!/usr/bin/env python3
"""Verify diagnostics cache on production outputs — run twice, compare timing."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
OUT = ROOT / "outputs"


def main() -> int:
    from src.runtime.diagnostics_cache import compute_dependency_hash, load_manifest, run_diagnostics_with_cache
    from src.runtime.profiler import RuntimeProfiler
    from src.report.execution_metrics import count_executable_actions
    from src.report.io_utils import read_output_json

    if not (OUT / "final_execution_decision.json").exists():
        print("SKIP: outputs missing")
        return 1

    dep_hash, _ = compute_dependency_hash(DATA, OUT)
    print(f"dependency_hash={dep_hash}")
    print(f"manifest_exists={(OUT / 'diagnostics_cache_manifest.json').exists()}")

    prof1 = RuntimeProfiler(run_id="verify-1", run_mode="standard", entrypoint="verify")
    t0 = time.perf_counter()
    r1 = run_diagnostics_with_cache(DATA, OUT, run_id="verify-run-1", run_full_diag=False, profiler=prof1)
    t1 = time.perf_counter() - t0

    prof2 = RuntimeProfiler(run_id="verify-2", run_mode="standard", entrypoint="verify")
    t0 = time.perf_counter()
    r2 = run_diagnostics_with_cache(DATA, OUT, run_id="verify-run-2", run_full_diag=False, profiler=prof2)
    t2 = time.perf_counter() - t0

    final = read_output_json(OUT / "final_execution_decision.json") or {}
    ab = int(count_executable_actions(final).get("actual_buy_allowed_count") or 0)

    print("\n=== RUN 1 (warm / may miss) ===")
    print(f"elapsed={t1:.2f}s hits={r1.cache_hit_count} misses={r1.cache_miss_count}")
    print(f"reused={r1.reused}")
    print(f"recomputed={r1.recomputed}")

    print("\n=== RUN 2 (expect hits) ===")
    print(f"elapsed={t2:.2f}s hits={r2.cache_hit_count} misses={r2.cache_miss_count}")
    print(f"saved_estimate={r2.saved_seconds_estimate:.0f}s")
    print(f"reused={r2.reused}")

    manifest = load_manifest(OUT)
    summary = manifest.get("summary") or {}
    print("\n=== CHECK ===")
    print(f"Actual Buy Allowed={ab}")
    print(f"manifest_hits={summary.get('cache_hit_count')}")

    ok = (
        r2.cache_hit_count >= 7
        and r2.cache_miss_count <= 1
        and r2.saved_seconds_estimate > 0
        and t2 < max(t1 * 0.5, 30)
    )
    print(f"\nVERDICT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
