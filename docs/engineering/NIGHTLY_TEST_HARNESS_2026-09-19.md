# Nightly test harness repair — 2026-09-19

This change repairs reproduced test setup errors. It does not change application code, trading configuration, data feeds, the frozen decision surface, or the forward-verdict clock.

## Evidence and changes

The older nightly run [35463873530](https://github.com/Lesram/intraday/actions/runs/35463873530), source `d5cf78c20ddc2da167179af6ed00c3f39bda3fa9`, reached its 45-minute test deadline without a JUnit summary. Its partial log reached 70%, with 5,504 passed, 90 failed, 62 error, 406 skipped and 2 xfail status lines. These are incomplete log counts, not a full-suite result. That source predates the final CI environment parity fixes.

The repaired test/backend modules were unchanged between that source and accepted base `02ba1afff73e1f05902b9fe71f13170d618d6d5e`.

| Demonstrated setup error | Test-only correction |
| --- | --- |
| Test subprocesses assume a repository-local `venv/bin/python`, absent on hosted setup-python runners. | Use the interpreter executing pytest, `sys.executable`. Existing subprocess assertions and limits remain. |
| Legacy token tests provide the production security setting but omit the legacy helper's `JWT_SECRET_KEY`. | Provide a synthetic key only within the token test class; additionally verify that absent keys still raise outside development. |
| StrategyEngine tests configure 60 seconds but assert 10; incomplete generic mocks cannot be converted to numeric settings. | Use explicit typed numeric settings and isolate host environment overrides; assert the configured 60 seconds and preserve custom-config checks. |
| Netting/sizing tests request `TEST` and `GOOG` without quotes. The application correctly refuses unknown prices. | Inject deterministic quote dependencies; additionally verify an unquoted symbol still rejects sizing. No production price fallback was added. |
| Lifecycle smoke tests construct the actual external market scanner. | Substitute an empty scanner only for this test module; verify ten ticks cross the scan boundary and do not expand the universe. |
| Freeze tests run under general CI defaults, missing four certified routing/data inputs. | Supply explicit certified inputs only within the freeze test module; verify each absent input is detected and verification never rewrites the freeze record. |

## Validation

The isolated targeted run passed **170 tests, zero skipped**, in 39.047 seconds. It includes all cases in the modified fixture modules and portable-subprocess modules, except `test_v12_baseline_invariants.py`, where only the two changed classifier CLI cases ran. The unrelated private-history baseline was not exercised or bypassed. Commands, exact node selections, counts, JUnit and logs are retained under `artifacts/nightly_test_harness/`.

Tests used synthetic credentials, temporary SQLite and brain paths, and an operating-system sandbox denying all network access and access to the installed `.env` and brain. They did not use the running paper containers.

The full artifact pack passed in 215.796 seconds: 168 ordinary safety/state/sizing cases, 28 replay cases and 20 semantic invariant cases, with snapshot, grep and spec-drift checks green. Workflow contract tests passed 46 cases; actionlint reported no errors. The six order-integrity, reconciliation, settings and system-integration regression modules also passed, with counts retained in `validation_summary.json`.

The dedicated readiness step runs the same 170 repaired cases against pull requests to `intra-2.0-phase1`, including after an earlier failure. Its 10-minute bound preserves the existing 30-second per-case timeout. Fresh JUnit and raw output are always uploaded; an old JUnit is removed before execution and pipeline failures remain fatal. The job has 90 minutes to cover all bounded steps and reporting. Ruff uses the existing exact pin from `requirements-dev.txt`.

The standalone frozen-surface check passed. `artifacts/phase2/param_freeze.json` remains byte-identical, SHA-256 `0f2e6048cd08df5d113fc4f7613fe4beea242cf020552d6070e471c78a0c6697`. This is an isolated source/configuration check; deployed runtime health remains separate operational evidence.

## Open baseline gaps

This change does **not** claim a green full nightly or certify all platform tests. Remaining work requires its own evidence:

- Start and seed a disposable local API/PostgreSQL environment for actual HTTP endpoint tests. The nightly starts PostgreSQL and Redis but no API process; shared auth fixtures seed their expected user only for SQLite.
- Diagnose the PostgreSQL strategies suite from complete traces before changing schema or fixture behavior.
- Declare external-provider test prerequisites explicitly. Direct Alpaca data tests require credentials and bypass the mock-data flag. Secret-free CI must report them as not executed, never as passed; paper secrets are not a substitute for test isolation.
- Resolve genuine archived Git-ref and historical trade-data provenance. Do not manufacture an evidence branch at HEAD, rewrite the historical baseline, or copy the private installed brain into CI.
- Retain and diagnose the remaining timeout and unclassified failures. A partial timeout log does not establish a failed behavioral assertion or rule out a defect.

No skips, xfails, weaker trading assertions, frozen-source edits, or parked frontend/security/Quality Summary cleanup are part of this repair.
