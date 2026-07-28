# Cleanup B+D — 2026-07-18

Replaced APIs and one-shot scripts archived (not deleted).

## B — replaced APIs

| Item | Location | Replacement |
|------|----------|-------------|
| `ai_verification_report.py` | `archive/20260718_replaced_apis/` | weekly qual / approval hub |
| `test_ai_verification_report.py` | `archive/20260718_tests/` | — |
| CECS-only request writer (`write_cecs_ai_research_report`) | snapshot in `cecs_ai_research_FULL_BEFORE_B.py` | `weekly_qual_report.write_weekly_qual_report` |
| `save_cecs_score` | `save_cecs_score_SNAPSHOT.py` | `approve_ai_suggestions` / weekly domain gates |

**Kept live:** `parse_cecs_ai_research_markdown`, `USAGE_WARNING`, `CecsResearchSubject`, `reopen_final_for_rescoring`, import/approve path.

## D — one-shot scripts

Moved to `archive/20260718_oneshot_scripts/`:

- `remove_030190_clean_run.py` (target write)
- `apply_kr_alpha_hybrid_scenario_b.py` (target write)
- `align_071050_satellite_cap.py`
- `resync_kr_alpha_bands.py`
- `fix_pykrx_data.py`
- `diagnose_kr_alpha_minmax_bands.py`
- `alpha_sector_mapping_diagnostic.py`
- `build_top10_sector_candidates.py`

Re-run only via explicit path under `archive/` after review — do not restore to `scripts/` casually.
