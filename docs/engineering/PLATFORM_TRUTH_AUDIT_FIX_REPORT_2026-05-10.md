# Platform Truth Audit Fix Report - 2026-05-10

Source audit: `artifacts/audit/PLATFORM_TRUTH_AUDIT_2026-05-10.md`

## Verdict

All concrete code-level issues from the Platform Truth Audit were remediated in
this slice. The only remaining red/yellow state is evidence availability, not a
known code defect: historical `strategy_evidence_events.jsonl` rows predate
this fix and cannot honestly be retrofitted with real `git_sha`,
`runtime_config_hash`, `signal_id`, or Phase 9 engine provenance. The new
observer therefore still refuses a promotion-grade verdict until a fresh market
session produces first-class Phase 9 telemetry.

## Fixes

| Audit issue | Fix |
| --- | --- |
| Phase 9 evidence feed lacks chain-of-custody fields | Added shared runtime identity helpers and persisted `signal_id`, `strategy_id`, `engine_version`, `created_at`, `evidence_tier`, `shadow_only`, `git_sha`, `runtime_config_hash`, `image_sha`, and `build_time` on future legacy and Phase 9 telemetry rows. |
| `StrategyGovernor` was policy-only | Wired `StrategyGovernor.authorize_signal(..., live_intent=True)` into `_submit_entry_order` before `OrderService.submit_symbol_order`. Unknown, shadow-only, or live-disabled strategy IDs now block before broker submission. |
| Warehouse JSON/SQLite counts could diverge | Phase 8 warehouse builds now clear owned tables before insert, record SQLite counts, reconcile them against summary counts, and raise on mismatch. |
| Full-corpus marker-only gate failed | Converted the W82 rebuild-helper telemetry-default test into a behavioral script execution with fake docker/curl/git commands. |
| Replay/live causality depended on upstream frame discipline | Added a centralized as-of feature-frame boundary immediately after feature fetch, before ranking, sizing, and order construction. |
| `/close-shorts` could directly mutate broker state | Converted it to dry-run by default; live buy-to-cover now requires `dry_run=false&confirm=CLOSE_SHORTS`, logs operator host, and has behavioral tests. |
| Missing independent observer | Added `scripts/ci/platform_truth_observer.py`, which separates operational pass from promotion-grade truth and refuses green when first-class Phase 9 evidence is absent. |

## Validation

- Focused truth-audit fix tests: `62 passed`.
- Focused retest after docs/artifacts: `54 passed`.
- Organism live/replay/evolution pack: `138 passed`, `2 warnings`.
- Order/reconciliation/service pack: `155 passed`, `12 warnings`.
- Causality/evidence pack: `83 passed`.
- Full-corpus marker-only gate: PASS, `118/372 = 31.72%`, improved from baseline `122/334 = 36.53%`.
- Critical/High marker-only gate: PASS.
- Mutation smoke: PASS, `3/3` mutations caught.
- Lint ratchet: PASS.
- Findings ledger: PASS.
- Migration smoke: PASS.
- Artifact pack: generated.
- Audit index: regenerated.

## Observer State

`platform_truth_observer.py` currently reports:

- `warehouse.count_reconciliation_ok=true`
- `warehouse.sha_matches_head=true` before this commit is created
- `promotion_grade=false`
- blockers:
  - `no_first_class_strategy_events`
  - `no_phase9_forward_events`

That is expected until the newly deployed code observes a live/paper market
session and writes fresh telemetry. Do not backfill old rows with new provenance;
that would make the evidence trail less truthful, not more.
