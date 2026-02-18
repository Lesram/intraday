# Services and API Deep Audit — 2026-02-16

## Scope
- backend/services/**/*.py
- backend/api/**/*.py
- Organism integration touchpoints in backend/organism/routes.py and backend/organism/live_engine.py

## Method
1. Static deep audit (critical/high/medium defects only)
2. Focused runtime verification via pytest markers: `api or services`

## Runtime Verification
Command:
- `venv/Scripts/python.exe -m pytest tests/ -q --tb=short -m "api or services" --maxfail=10`

Result:
- 23 passed, 0 failed, 7562 deselected

## Findings (Static Audit)

### CRITICAL
1) Organism control endpoint authorization scope too broad
- Files:
  - backend/organism/routes.py
  - backend/api/factory.py
- Risk:
  - Mutating endpoints (/freeze, /halt, /resume, /promote, /rollback, /tick) are reachable via generic auth but not explicitly admin/governance role-scoped.
- Direction:
  - Add explicit role dependency for mutating organism routes; return 403 for insufficient privileges.

### HIGH
2) Response model contract mismatch in governance-block path
- File:
  - backend/api/routes/multi_strategy_live.py
- Risk:
  - Response expects list for `submitted`, blocked path returns integer (`0`) -> response validation error risk.
- Direction:
  - Return `submitted=[]` in blocked path; add test for blocked response schema.

3) Idempotency key collision risk in organism order submission
- Files:
  - backend/organism/live_engine.py
  - backend/services/order_service.py
- Risk:
  - Second-level timestamp keying can collide for same symbol in same second and drop intended orders.
- Direction:
  - Include UUID/monotonic component in idempotency key.

4) Async retrain path may create unawaited coroutine and stale fallback
- File:
  - backend/organism/live_engine.py
- Risk:
  - Sync retrain path attempts async positions fetch and may fallback to stale cache.
- Direction:
  - Make retrain path async or pass current positions snapshot from caller.

### MEDIUM
5) Scheduler lifecycle stored in module globals
- File:
  - backend/services/multi_strategy_live_scheduler.py
- Risk:
  - Multi-app/test interference due to shared global task state.
- Direction:
  - Store scheduler state in app.state.

6) Scheduler suppresses persistent failure signal
- File:
  - backend/services/multi_strategy_live_scheduler.py
- Risk:
  - Service can appear alive while repeatedly failing each tick.
- Direction:
  - Add consecutive failure counters and health-state escalation.

7) Routes couple to private internals
- File:
  - backend/organism/routes.py
- Risk:
  - Refactors break API due to private field access.
- Direction:
  - Expose stable status/snapshot APIs from organism modules.

8) Broadcast errors silently swallowed
- File:
  - backend/organism/routes.py
- Risk:
  - Missed websocket updates with no surfaced signal to clients.
- Direction:
  - Return/broadcast status metadata and warn-log with context.

## Integration Conclusion
- Runtime API/services tests pass.
- Static audit still flags authorization and robustness hardening items for organism-integration paths.
- Recommended next patch order:
  1. Authorization hardening for organism mutating routes
  2. Response schema mismatch fix in multi_strategy_live blocked path
  3. Idempotency key uniqueness hardening
  4. Async retrain/refactor

## Status
- Previous progress item "Deep audit: services & API" is now completed with both static and runtime evidence.
