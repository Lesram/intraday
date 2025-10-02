# Phase 1 Consolidation Matrix (Keep/Merge/Delete)

This matrix operationalizes the duplicate test consolidation plan. Scope: only files under `/test`. All new/merged tests remain under `/test`. Use existing `/venv`.

Legend
- Golden: Test file chosen as base to keep and merge into
- Merge: Unique test cases to copy over from other files
- Delete: Redundant/obsolete files to remove after merge
- Target Path: Final consolidated file path under `/test` mirroring app module

---

## Family A — Backend API Main (`backend.api.main`)

Candidates (observed):
- test/module/test_Module94_backend_api_main.py
- test/module/test_Module95_backend_api_main_fixed.py
- test/module/test_Module96_backend_api_main_simple.py
- test/module/test_Module97_backend_api_main_100_coverage.py
- test/module/test_Module98_backend_api_main_focused.py
- test/module/test_Module99_backend_api_main_final.py
- test/module/test_Module100_backend_api_main_100_coverage.py
- test/module/test_Module101_backend_api_main_targeted.py
- test/module/test_Module102_backend_api_main_ultimate.py
- test/module/module5A_api_main.py

Decision:
- Golden: test/module/test_Module102_backend_api_main_ultimate.py (broadest scope)
- Merge: any unique edge cases from 94/95/96/98/99/101 not present in Golden
- Delete: remaining API Main files after merge
- Target Path: /test/backend/api/test_main.py

Notes:
- Ensure fixtures consistent; parametrize overlapping cases; keep endpoint coverage comprehensive.

---

## Family B — Feature Engineering (`backend.features.feature_engineering`)

Candidates (observed):
- test/module/test_Module25_backend_features_feature_engineering.py
- test/module/test_Module127_backend_features_feature_engineering.py
- test/module/test_Module127_backend_features_feature_engineering_part2.py
- test/module/test_Module128_backend_features_feature_engineering.py
- test/module/test_Module129_backend_features_feature_engineering_final.py
- test/module/test_Module130_backend_features_feature_engineering_working.py

Decision:
- Golden: test/module/test_Module130_backend_features_feature_engineering_working.py
- Merge: edge transforms from 25, 127, 128, 129 if not covered
- Delete: remaining duplicates after merge
- Target Path: /test/backend/features/test_feature_engineering.py

Notes:
- Verify expected outputs align with current implementation; parametrize variants.

---

## Family C — Utils/Helpers (`backend.utils.helpers`)

Candidates (observed):
- test/module/test_Module29_backend_utils_helpers.py
- test/module/test_Module29_backend_utils_helpers_complete.py
- test/module/test_Module29_backend_utils_helpers_simplified.py
- test/module/test_Module29_100_percent_coverage.py
- test/module/test_Module29_complete_100.py
- test/module/test_Module29_final_100_percent.py
- test/module/test_Module29_final_numpy_coverage.py
- test/module/test_Module29_missing_lines.py
- test/module/test_Module29_ultimate_100.py

Decision:
- Golden: test/module/test_Module29_backend_utils_helpers_complete.py (tentative)
- Merge: any novel input variations from other 29-series files
- Delete: remaining helpers files after merge
- Target Path: /test/backend/utils/test_helpers.py

Notes:
- Prefer small, focused tests; deduplicate via @pytest.mark.parametrize.

---

## Family D — Risk Manager (`backend.risk.risk_manager`)

Candidates (observed):
- test/module/test_Module28_backend_risk_risk_manager.py
- test/module/test_Module117_backend_risk_risk_manager.py
- test/module/test_Module114_backend_services_risk_manager.py (services-level; review overlap)
- test/module/test_Module117_additional_coverage.py
- test/module/test_Module117_enhanced_coverage.py

Decision:
- Golden: test/module/test_Module28_backend_risk_risk_manager.py
- Merge: additional scenarios from 117 variants (extreme market, thresholds)
- Delete: redundant risk manager test files post-merge
- Target Path: /test/backend/risk/test_risk_manager.py

Notes:
- Align expected outputs with current risk rules; include edge and fallback branches.

---

## Family E — Signals Repository (`backend.infra.repositories.signals`)

Candidates (observed):
- test/module/test_Module48_backend_infra_repositories_signals.py
- test/module/test_backend_infra_repositories_signals_100_coverage.py
- test/module/test_signals_repo_complete_coverage.py
- test/module/test_signals_repo_corrected_100.py
- test/module/test_signals_repo_final_100_coverage.py

Decision:
- Golden: test/module/test_signals_repo_final_100_coverage.py
- Merge: any missing CRUD/edge scenarios from other files
- Delete: remaining signals repo tests after merge
- Target Path: /test/backend/infra/repositories/test_signals.py

Notes:
- Explicitly hit the single missing branch to secure 100% branch coverage.

---

## Additional Families (to triage during inventory)
- Backend API routes (orders, models, strategy, signals routes) — consolidate per route module
- Observability (logging/metrics/tracing) — centralize per submodule
- Database repositories (orders, executions, positions, models) — consolidate per repository module

---

## Consolidation Procedure (per family)
1) Select Golden file and open a working branch section
2) Merge unique tests; convert duplicates into parametrized cases
3) Normalize fixtures and imports; use common helpers where possible
4) Run targeted tests for the family; ensure passing locally
5) Delete redundant files; re-run collection to ensure no import errors
6) Commit with message: "test(consolidation): <family> merge into <target path>"

## Validation Criteria
- Test count reduced significantly for the family (ideally → 1 file)
- All unique scenarios preserved; no coverage regressions
- File placed under the proposed Target Path under `/test`
- Collection runs clean; no import or fixture errors

## Open Questions/Assumptions
- If any legacy tests live outside `/test` (e.g., artifacts/legacy_tests/tests), they are excluded from consolidation and can be archived separately.
- Final naming mirrors app modules but remains under `/test` (per constraint).
