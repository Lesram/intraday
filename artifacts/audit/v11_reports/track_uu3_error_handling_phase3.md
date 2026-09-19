# Track UU3 v11 — Error-Handling Phase 3 (Lint Ratchet Validation)

**Repo**: `/Users/marselkei/VS/intra`
**Branch**: `rc-1.5-curated`
**HEAD**: `3778344` (V10 plan/prompts; lint rule itself shipped in `a943e26` wave-57)
**Ruff**: `0.15.12` (installed for this audit)
**Mode**: Read-only.  AST + ruff.

---

## TL;DR

The V10 wave-57 lint rule is **wired in `pyproject.toml` but is not enforceable as currently configured**, and post-V10 code already drifted past it.  Three findings:

| # | Severity | Finding |
|---|----------|---------|
| 1 | **HIGH**  | Two of seven grandfather entries reference **non-existent files** (`backend/services/realtime_risk_analytics.py`, `backend/ml/ensemble_model.py`) — silent dead ratchet rows; the actual files (`backend/analytics/realtime_risk_analytics.py`, `backend/organism/ensemble_models.py`, `backend/models/ensemble_model.py`) are NOT grandfathered. |
| 2 | **HIGH**  | Project-wide `ruff check .` with the new rules reports **3,542 errors across 296 files** (BLE001=1973, G004=1279, S110=268, S112=19, TRY401=3).  Only 7 files are grandfathered → CI lint job (`ci.yml` runs `ruff check --no-fix .`) **cannot pass against this configuration**.  The rule is technically registered but is not actually enforced as a passing baseline; the wave-57 deliverable was merged without an end-to-end `ruff check .` run. |
| 3 | **MEDIUM** | Post-V10 (waves 50-65) introduced **+9 net new violations** of the very rules wave-57 added — most notably `backend/organism/background_trainer.py` +5 (S110/S112/BLE001), `backend/monitoring/slo_monitor.py` +2, `backend/api/lifespan.py` +1, `backend/organism/governance.py` +1, `backend/services/risk_manager.py` +1, `backend/api/routes/health.py` +1.  Confirms the rule isn't actually gating PRs. |

CancelledError audit (post-V10 changed files): **3 sites**, all correct cleanup-of-child-task patterns (`alpaca_stream.py:261/269`, `lifespan.py:483`).
`dispatch_alert_from_thread` audit: **0 raw `asyncio.create_task(send_alert(...))`** sites — discipline holds.

---

## 1. Ruff config + grandfather list

`pyproject.toml` lines 113-119 (top-level deprecated form, but still effective on ruff 0.15):

```toml
select = [..., "S110", "S112", "BLE001", "G004", "TRY401", "LOG007"]
```

Lines 172-191 — `[tool.ruff.lint.per-file-ignores]` ratchet:

```toml
"backend/organism/live_engine.py"             = [<6 rules>]
"backend/organism/brain_persistence.py"       = [<6 rules>]
"backend/integrations/alpaca_stream.py"       = [<6 rules>]
"backend/services/audit_service.py"           = [<6 rules>]
"backend/api/socketio_server.py"              = [<6 rules>]
"backend/services/realtime_risk_analytics.py" = [<6 rules>]   # path does not exist
"backend/ml/ensemble_model.py"                = [<6 rules>]   # path does not exist
"tests/**/*.py"                               = [<6 rules>]
```

Per-grandfathered-file violation counts (running ruff with `--isolated` to bypass the ignore):

| File (as listed in pyproject) | Exists? | Pre-V10 violations | Notes |
|-------------------------------|---------|--------------------|-------|
| `backend/organism/live_engine.py`             | yes | 78 BLE001 + 13 S110 = 91 | Top cleanup target |
| `backend/organism/brain_persistence.py`       | yes | 39 BLE001 + 9 S110 = 48 | |
| `backend/integrations/alpaca_stream.py`       | yes | 24 BLE001 + 4 G004 + 3 S110 = 31 | |
| `backend/services/audit_service.py`           | yes | 2 BLE001 | Already ~clean; could remove from ratchet |
| `backend/api/socketio_server.py`              | yes | 32 G004 + 15 BLE001 = 47 | |
| `backend/services/realtime_risk_analytics.py` | **NO** | n/a | Real path: `backend/analytics/realtime_risk_analytics.py` (38 viol) |
| `backend/ml/ensemble_model.py`                | **NO** | n/a | Real candidates: `backend/organism/ensemble_models.py` + `backend/models/ensemble_model.py` (84 viol combined) |

→ **V12 surgical-cleanup target = `backend/organism/live_engine.py`** (91 violations of the 6 rules; concentrated in BLE001 + S110).

---

## 2. Project-wide enforcement check

Ran exactly what CI runs (`.github/workflows/ci.yml` step `Lint with ruff` → `ruff check --no-fix . --output-format=github`):

```
$ ./venv/bin/ruff check . --no-fix --select S110,S112,BLE001,G004,TRY401,LOG007 --statistics
1973  BLE001  blind-except
1279  G004    logging-f-string
 268  S110    try-except-pass
  19  S112    try-except-continue
   3  TRY401  verbose-log-message
Found 3542 errors.   (296 unique files)
```

LOG007 = 0.  TRY401 sites: `backend/api/routes/signals.py:379` and `:468` (and one more) — all `logger.exception(f"...{e}")` with redundant `e`; trivial fix.

The ratchet only suppresses 7 files.  3,542 violations remain reachable to CI.  Two interpretations:

  a. **CI lint is currently red on every PR** — but recent merges are getting through, which means the lint job is being ignored, the workflow is disabled, or the rule was never actually exercised by a PR run after wave-57 landed.
  b. **CI runs against a different config** — but `ci.yml` invokes `ruff check --no-fix .` with no explicit config flag, so it uses `pyproject.toml`.

`.pre-commit-config.yaml` pins ruff to `v0.1.6` (released 2023-11) which **does not know rules `S110/S112/BLE001/G004/TRY401/LOG007` selected by name in their current form** in the same way the modern ruff does — so the local hook cannot enforce the new rules either.  Pre-commit and CI are out of sync with the pyproject ruleset.

→ **Wave-57's lint ratchet is ornamental until either (a) the grandfather list is expanded to the full 296-file backlog, or (b) the CI workflow is re-run and shown to pass at HEAD, or (c) the pre-commit ruff version is bumped past 0.5+.**  None of these has happened.

---

## 3. Post-V10 compliance (waves 50-65)

For every backend `.py` modified since `e0df067..HEAD`, ran ruff with the new rules and diffed against the pre-V10 contents.  Net new violations introduced *after* the wave-57 ratchet shipped:

| File | Pre-V10 | Post-V10 (HEAD) | Δ |
|------|--------:|----------------:|--:|
| `backend/organism/background_trainer.py` | 18 | 23 | **+5** |
| `backend/monitoring/slo_monitor.py`      | 17 | 19 | **+2** |
| `backend/api/lifespan.py`                | 51 | 52 | **+1** |
| `backend/organism/governance.py`         |  1 |  2 | **+1** |
| `backend/api/routes/health.py`           |  6 |  7 | **+1** |
| `backend/services/risk_manager.py`       | 17 | 18 | **+1** |
| `backend/api/routes/auth.py`             | 33 | 32 | -1 |
| (others: 0 delta) | | | |

→ **Net +9** new violations introduced by wave-50–65 *of rules wave-57 was supposed to enforce*.  The ratchet leaks.  Sample of newly-added violations:

```
backend/organism/background_trainer.py:254  S110 + BLE001  try/except/pass on bare Exception
backend/organism/background_trainer.py:346  S112 + BLE001  try/except/continue on bare Exception
backend/organism/background_trainer.py:442/468/491/552/602  S110 + BLE001 (5 sites)
backend/organism/governance.py:251 / :293   BLE001 (new blind-except)
backend/services/risk_manager.py:208/251/382/554/700  BLE001 (existing-pattern repeats)
backend/monitoring/slo_monitor.py:241/365/378/389  BLE001 + G004
```

`background_trainer.py` was not on the grandfather list and is a hot path (ML feedback loop).  Five new pass-only handlers there is a real regression of error-handling discipline.

---

## 4. CancelledError audit (post-V10 changed files)

```
backend/api/lifespan.py:483               # awaiting outbox-worker cancellation — correct
backend/integrations/alpaca_stream.py:261 # awaiting queue_processor_task cancel — correct
backend/integrations/alpaca_stream.py:269 # awaiting heartbeat_task cancel       — correct
```

All three are the canonical "I cancelled this child task and I'm awaiting it; CancelledError is the expected resolution" pattern.  None swallow CancelledError inside their *own* run loop.  No re-raise needed.

Project-wide there are 19 CancelledError handlers; spot-checked 5 (`cache.py:85`, `cache.py:233`, `lifespan.py:483`, `scheduled_reconciliation.py:188`, `websocket_manager.py:544`) — all clean child-task cleanup contexts.

---

## 5. dispatch_alert_from_thread audit

```
$ grep -rn "asyncio.create_task(send_alert\|_aio.create_task(send_alert" backend/ --include='*.py'
(0 hits)
```

Sole alert dispatch site outside of `backend/infra/alerting.py` is `backend/infra/outbox_worker.py:175`, which uses `dispatch_alert_from_thread(lambda: send_alert(...))` correctly.  The cross-thread invariant from V5 wave-17a (`S-J3-1`) holds.

---

## 6. exc_info hygiene (sample of 5)

`logger.error(...)` calls without `exc_info=` total **499** project-wide.  Sampled five inside `except` blocks:

| Site | In `except`? | `exc_info` would help? |
|------|-------------:|-----------------------:|
| `backend/database.py:52`     | yes | yes — `Failed to initialize database: {e}` loses traceback |
| `backend/database.py:67`     | yes | yes |
| `backend/websocket.py:111`   | yes | yes |
| `backend/websocket.py:152`   | yes | yes |
| `backend/websocket.py:176`   | yes | yes |

LOG007 (which would catch these) is **selected** but reports **0 violations** because in modern ruff LOG007 only fires for the *specific* pattern `logger.error("…", exc)` (positional exception arg), not f-string-based error logs.  G004 catches the f-string, but the missing-`exc_info` follow-on is invisible to the current rule set.

→ Adding `LOG014` / `TRY400` (or a custom rule) would close the gap, but this is a future-V12 nicety, not a UU3 finding.

---

## 7. Findings (final 3)

### UU3-1 (HIGH) — Dead grandfather entries hide ~120 violations
Two of seven `[tool.ruff.lint.per-file-ignores]` rows reference paths that don't exist (`backend/services/realtime_risk_analytics.py`, `backend/ml/ensemble_model.py`).  The actual files (`backend/analytics/realtime_risk_analytics.py` 38 viol, `backend/organism/ensemble_models.py` + `backend/models/ensemble_model.py` ≈ 84 viol combined) are NOT grandfathered, so they leak into the global error count and they were never the target of cleanup tracking.

**Fix**: rewrite those two rows to the real paths (`backend/analytics/realtime_risk_analytics.py` and the two `ensemble_model*.py` files) — or remove them if cleanup is preferred to ratcheting.

### UU3-2 (HIGH) — Lint rule unenforced; CI cannot pass against pyproject as written
Project-wide, the six newly-selected rules generate **3,542 errors across 296 files**, but the per-file-ignore covers only 7 files.  CI's `lint` job (`ci.yml`) runs `ruff check --no-fix .` which uses pyproject — it must currently fail.  Either CI doesn't run on rc-1.5-curated, the lint job is disabled, or post-wave-57 PRs have been merging without re-running it.  Pre-commit pins ruff `v0.1.6` which doesn't enforce these rules consistently with modern ruff, so local commits are also not gated.

**Fix**: either expand the grandfather list to all 296 files (turn the rule into a true ratchet — new files comply, existing files are silenced), or accept the rule as advisory by moving the six S110/S112/BLE001/G004/TRY401/LOG007 selectors into a `lint.extend-select` block scoped only to a `paths-to-clean.txt` allow-list.  Bump `.pre-commit-config.yaml` ruff to ≥ 0.5 to keep parity with CI.

### UU3-3 (MEDIUM) — Post-V10 waves leaked +9 new violations of the wave-57 rules
Despite wave-57 (`a943e26`, "lint rule + ratchet") being labeled "deliverable", waves 50-65 introduced new violations of those exact rules: `background_trainer.py +5` (S110×5, S112×1, BLE001×6 added), `slo_monitor.py +2`, `lifespan.py +1`, `governance.py +1`, `health.py +1`, `risk_manager.py +1`.  Concrete proof the ratchet isn't gating PRs; combined with UU3-2 this is mechanically expected (the rule isn't running) but it confirms the *behavioral* impact: developers are still writing `try/except/pass` on bare `Exception` and shipping it.  Highest-risk site: `backend/organism/background_trainer.py:254/346/442/468/491/552/602` — five new pass-only handlers in the ML training loop, where silent-swallow can mask data-quality regressions.

**Fix**: after UU3-2 is closed (so CI is actually red on new violations), open a small follow-up PR converting the 9 new sites in `background_trainer.py` / `slo_monitor.py` / `governance.py` / `risk_manager.py` / `lifespan.py` / `health.py` to either logged warns or typed exceptions.

---

## V12 surgical-cleanup target (per spec §6)

`backend/organism/live_engine.py` — 91 violations of the six rules (78 BLE001 + 13 S110), highest concentration of any backend file.  Largest blast radius for one file's worth of cleanup.
