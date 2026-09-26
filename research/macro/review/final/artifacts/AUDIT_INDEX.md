# Final research audit index

Generated 2026-09-20T17:56:43.755464+00:00. Checked workspace: `ffc0e5c0595bb21e1c71f0ba7e5d6f55af7fc189`. Delivery branch: `codex/macro-review-002`; existing draft [PR #21](https://github.com/Lesram/intraday/pull/21). The branch is separate from the detached, dirty platform checkout; final delivery adds only this research directory through an isolated index.

| Check | Status and receipt |
|---|---|
| Final evidence, denominator and integrity checks | **pass** — [final_validation.json](final_validation.json) |
| Controlled quantitative completion | **PASS** — [quantitative validation](../evidence/quantitative_validation.json) |
| Canonical contract | 21 rows, 42 fields; 24 exact count joins; five calendar-dependency examples — [contract validation](../evidence/contract_validation.json) |
| Cross-agent peer review | [Findings and closure](../PEER_REVIEW.md); AI analytical review, not external human certification |
| Original and consolidation files | [Pre-finalization hashes](source_integrity_before.json), [after-check](source_integrity_after.json); 1,200 research files and 14 pre-existing modified tracked files |
| Frozen decision surface | **pass** — [verification](freeze_after.log), [read-only runtime snapshot](runtime_config_snapshot.json) |
| New order paths / local credential patterns | [Research assertions](grep_assertions.json), [credential scan](secret_scan.json) |
| Prior prototype tests | Historical 35/35 pass; unchanged code, not rerun or presented as proof of future tool validity |
| Platform regression / replay | Not run; prior collection lacked FastAPI; no platform changes or new passing claim |
| Hosted checks | Existing blockers documented in [prior CI receipt](../../artifacts/ci_status.json); final-head status, when available, in [delivery status](delivery_status.json) |

## Scope and reproduction

[Task plan](task_plan.json), [task report](task_report.json), [changed files](changed_files.json), [test summary](test_summary.json) and [replay scope](replay_summary.json) form the research artifact pack. Exact research reproduction requirements are in [the quantitative supplement](../evidence/quantitative_completion.md). Local companion inputs remain necessary; no claim is made that all raw inputs are in the public PR.

The task writes inside `research/macro/review/final/`. Root `generate_artifacts.py full` and `generate_audit_index.py` would mutate outside the explicit review boundary and invoke platform suites; they were not run. These scoped receipts are not represented as the platform's full artifact pack. No runtime, dashboard, automatic schedule, order submission, protected parameter or source historical judgment was changed.

The existing freeze timestamp is `2026-09-19T21:55:01.857005+00:00`, which differs from July7 in the supplied operating instructions. Verification passes against the existing baseline. This finalization did not create, reset or reconcile that earlier discrepancy. The snapshot is imported configuration and source hashes, not observation of a running broker process.

## Remaining limits

- No validated forecasting or investment-performance edge; revised histories and dependent small samples.
- AI cross-agent review is not independent human peer review; some reviewers authored component evidence.
- Original/paid corpus and vintage/portfolio records are incomplete; companion inputs are not all publicly packaged.
- Final contract supersedes prior prose but is not implemented in the existing prototype.
- Platform regression/replay and full root artifact generators were not run; no platform behavior changed.
- Hosted CI blockers are pre-existing and remain outside this research-only/frozen-surface task.
