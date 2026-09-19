# Track UU2 v10 — Error Handling Phase 2 (lint rule + retroactive scan)

**Branch**: `rc-1.5-curated` @ `c048103`
**Method**: AST + grep, read-only. `./venv/bin/python` for AST walks.
**Scope**: `backend/**/*.py` excluding tests, `__pycache__`, migrations are still in scope.
**Inputs**: V9 UU census (`artifacts/audit/v9_reports/track_uu_error_handling_consistency.md`), V10 prompt §1-§7.

---

## 1. Updated census (post wave-41 .. wave-49)

| Metric                                              | V9 (`ccba97f`) | V10 (`c048103`) |  Δ |
|-----------------------------------------------------|---------------:|----------------:|----:|
| Total `except` handlers                             |          1,487 |           1,483 |  -4 |
| Bare `except:`                                      |              0 |               0 |   0 |
| `except Exception` (broad)                          |          1,065 |           1,067 |  +2 |
| `except ...: pass` (single-stmt swallow)            |            161 |             158 |  -3 |
| `except X as e: pass` (named, bound, dropped)       |              — |               0 |   — |
| `except ...: logger.debug(...)`                     |             35 |              33 |  -2 |
| `except ...: logger.info(...)`                      |              2 |               2 |   0 |
| `except ...: logger.warning(...)`                   |            116 |             115 |  -1 |
| `except ...: logger.error(...)` (single-stmt, no exc_info=True call shape varies) | (not measured) | 83 | n/a |
| logger f-string inside handler                      |            513 |             459 | -54 |
| logger `%s/%d/%r` inside handler                    |            131 |             149 | +18 |

**Wave-41..49 closed**: UU-1 (daily-max-loss alert dispatch — uses `dispatch_alert_from_thread` now), UU-2 first half (login_failed audit rollback now logs at ERROR), UU-3 (brain-save-blocked alert + lock-release now warning-logged).

**Net pass-only delta = -3** (V9 expected reduction matches: UU-1 + UU-3-alert + UU-3-lock = 3 sites). UU-2's *successful*-login branch was **not** fixed (see Finding UU2-A below).

### Pass-only sites by subsystem (V10)

| Subsystem               | pass | Δ vs V9 |
|-------------------------|-----:|--------:|
| `backend/organism/`     |   49 |      -2 |
| `backend/api/`          |   40 |      -1 |
| `backend/infra/`        |   18 |       0 |
| `backend/config/`       |    9 |       0 |
| `backend/services/`     |    7 |       0 |
| `backend/integrations/` |    6 |       0 |
| `backend/ml/`           |    6 |       0 |
| `backend/risk/`         |    5 |       0 |
| Other                   |   18 |       0 |
| **Total**               |  158 |      -3 |

### Cargo-cult heuristic — try body has > 1 statement

The "cargo-cult" pattern V9 UU-4 named is *try-body has multiple statements (so the catch could mask many distinct failure modes) but the handler does nothing*. Of the 158 pass-only sites, **81 have a try-body of >1 statement** — these are the high-value lint targets. Top concentrations:

| File                                            | Multi-stmt pass-only sites |
|-------------------------------------------------|---------------------------:|
| `backend/organism/live_engine.py`               | 10 |
| `backend/organism/ml_signal.py`                 |  6 |
| `backend/api/lifespan.py`                       |  6 |
| `backend/api/websocket_manager.py`              |  6 |
| `backend/infra/users.py`                        |  5 |
| `backend/risk/risk_manager.py`                  |  4 |
| `backend/organism/ensemble_models.py`           |  3 |
| `backend/organism/brain_persistence.py`         |  3 |

Notable single-statement sites are usually defensible best-effort cleanup (e.g. `tmp_path.unlink()` during error rewind in `_write_csv_atomic`). The multi-stmt ones are where audit attention belongs.

---

## 2. Finding UU2-A (Tier 1) — successful-login audit rollback still silent

**File**: `backend/api/routes/auth.py:340-345`

V9 UU-2 flagged TWO instances of the same bug, calling out that the *successful* login branch (line 333 in V9, line 340 now) is "more problematic" because a token is issued but no audit row is written. Wave-41 fixed the FAILED-login branch (lines 289-301 — rollback failure now logs at ERROR with explicit "session may be poisoned" wording) but left the SUCCESSFUL-login branch untouched:

```python
340       except Exception as _audit_err:
341           logger.warning("AA-H-3: login audit failed: %s", _audit_err)
342           try:
343               await db.rollback()
344           except Exception:
345               pass                  # ← still silent
```

The asymmetry is now explicit: failed-login audit-rollback failure is `ERROR` + explanatory text; successful-login audit-rollback failure is silent `pass`. The compliance argument from V9 is unchanged — SOX/SOC-2 treat authentication audit rows as mandatory, and the success branch is the more important of the two because the user is now actually inside the system. **Recommended**: mirror the lines 295-301 pattern (try/rollback / except as `_rb_err` / `logger.error("UU-2: db.rollback() after auth audit failure also failed: %s — db session may be poisoned", _rb_err)`).

This is a one-line oversight in Wave-41, not a new finding; it's just unfinished. Listed Tier 1 because the compliance argument is unchanged from V9.

---

## 3. Finding UU2-B (core deliverable) — proposed V11 ruff config

`pyproject.toml` currently enables `E W F I B UP SIM PTH PL` and ignores `B008 C901 PLR0913 PLR0912 TRY003 PERF203 UP007`. It does **not** enable any of:

- `BLE` (flake8-blind-except)  → catches `except Exception` / `except BaseException` (1,067 sites)
- `S` Bandit security  → `S110` (try-except-pass), `S112` (try-except-continue)
- `TRY` `tryceratops` (besides ignoring `TRY003`)  → `TRY002 TRY200 TRY300 TRY400 TRY401`
- `LOG` flake8-logging  → `LOG002 LOG007`
- `G` flake8-logging-format  → `G001 G003 G004` (catches `logger.info(f"...")`)

The right combination — surgical (does not enable BLE for the entire 1,067-site backlog) but catches the cargo-cult pattern V9 UU-4 named — is:

```toml
[tool.ruff]
# (existing) ...

[tool.ruff.lint]
# (existing select / ignore) ...
extend-select = [
    "S110",      # try-except-pass detected           (158 sites, 0 noqa today)
    "S112",      # try-except-continue detected       (21 sites)
    "BLE001",    # blind-except catch                 (1067 sites — see ratchet below)
    "G001",      # logging-string-format
    "G003",      # logging-string-concat
    "G004",      # logging-f-string                   (459 sites in handlers)
    "LOG007",    # use-of-logger-exception-with-exc-info
    "TRY401",    # verbose log-message in handler (don't pass exc when logger.exception captures)
]

[tool.ruff.lint.per-file-ignores]
# (existing) ...

# UU2 ratchet baseline — current sites are grandfathered, new code must comply.
# Each entry has an issue # for the corresponding remediation; remove from
# the list as the file is brought into compliance.
"backend/organism/live_engine.py"           = ["S110", "BLE001", "G004"]  # UU-4, UU-1
"backend/organism/ml_signal.py"             = ["S110", "BLE001"]
"backend/organism/brain_persistence.py"     = ["S110", "BLE001"]
"backend/organism/background_trainer.py"    = ["S110", "BLE001"]
"backend/organism/ensemble_models.py"       = ["S110"]                   # ImportError soft-deps
"backend/api/lifespan.py"                   = ["S110"]                   # task-cleanup paths
"backend/api/websocket_manager.py"          = ["S110"]                   # CancelledError waiters
"backend/api/routes/**/*.py"                = ["G004"]                   # f-string logger backlog
"backend/infra/users.py"                    = ["S110"]
"backend/integrations/alpaca_stream.py"     = ["S110"]
# ... (one entry per file in §1 table; total 28 files)
```

Why this shape:

1. **`S110` / `S112` are body-pattern-based, not type-pattern-based** — they fire only on the cargo-cult shape (`except <anything>: pass` or `: continue`) regardless of the exception type. The 158 + 21 sites already enumerated by AST in §1 will match exactly. New code introducing `except: pass` fails CI immediately. This is the primary lint goal.

2. **`BLE001` flags blind-except regardless of body** — 1,067 sites in the codebase. This is much larger than UU2 can refactor in one pass, so it goes into the ratchet baseline. New code must use a specific exception (`(ValueError, TypeError)` etc.) or `# noqa: BLE001 — <reason>`. Three sites already use this idiom (`backend/config/base_settings.py:1284`, `1582`, `backend/utils/utilities.py:362` — *intentional retry helper*). Existing files in the per-file-ignores remain quiet; new files do not.

3. **`G004` (f-string in `logger.<level>`)** addresses V9's "513 eager f-strings inside handlers" finding. 459 sites in v10 — same backlog approach. The Prometheus / log-aggregator argument is unchanged: `logger.info("trade %s filled at %.2f", sym, price)` produces one log template that aggregators can group; `logger.info(f"trade {sym} filled at {price:.2f}")` produces one new template per call site.

4. **`TRY401`** catches the common `except Exception as e: logger.error("foo: %s", e)` pattern when `logger.exception("foo")` would do the same with traceback. Several waves use the latter form already; this rule keeps new code consistent.

5. **Why NOT `S110` un-ignored across the board**: 158 sites is too many for a hot ratchet. The per-file-ignores list above is the *minimal grandfathering set* — every file outside that list is already clean today. Once added, the rule prevents regression and gives PR reviewers an explicit list of files that owe cleanup.

**Cargo-cult-specific super-rule (NOT a stock ruff rule, but worth a custom plugin)**: a flake8 plugin or AST hook in `scripts/ci/check_spec_drift.py` that flags
```
try:
    <stmt 1>
    <stmt 2>          # 2+ stmts: catch could mask multiple failure modes
    ...
except Exception:
    pass              # ... and handler does nothing
```
The 81 multi-stmt sites enumerated in §1 are the targets. Suggested implementation: extend the existing `scripts/ci/post_edit_verify` check to count multi-stmt try / pass-handler pairs and fail if a PR adds new ones (delta-check against base).

---

## 4. Finding UU2-C (Tier 2) — Wave-43 LotTracker rollback still uses `except: pass`

**File**: `backend/integrations/alpaca_stream.py:643-653`

The Wave-43 LotTracker block — added during V9 DD3-2 to fix duplicate `position_lots` rows from cumulative-fill semantics — has the rollback path:

```python
643   except Exception as _lot_err:
644       # Don't fail order processing on lot-tracking error.
645       logger.warning(
646           "BB-8: lot-tracking failed for order %s: %s",
647           order.id, _lot_err,
648           exc_info=True,
649       )
650       try:
651           await session.rollback()
652       except Exception:
653           pass
```

Outer `except` is correct (warning + exc_info=True). Inner rollback is silent. V9 already named this in the fail-open path inventory ("alpaca_stream._handle_trade_update rollback DB rollback failure on lot-tracking errors swallowed (line 614-617) → fail-OPEN (low blast radius — minor)") and the line numbers shifted to 650-653 in V10. **Same fix as UU-2**: inner rollback should be `except Exception as _rb_err: logger.error("BB-8: rollback after lot-tracking failure also failed: %s — session may be poisoned", _rb_err)`. Tier 2 because the order processing is best-effort here and a poisoned session would surface on the next request inside the same WS handler — visible, just delayed.

---

## 5. Wave-41..49 fail-open audit (none introduced)

| Wave  | Path                                              | Risk?            | Verdict |
|-------|---------------------------------------------------|------------------|---------|
| 41    | `brain_persistence._write_csv_atomic` fsync       | best-effort fsync swallows OSError | Acceptable — fsync is durability hint; replace + raise outer |
| 41    | `brain_persistence._write_csv_atomic` tmp cleanup | swallows during error rewind | Acceptable — original exception re-raised |
| 41    | `brain_persistence` UU-3 alert + lock release     | now WARNING-logged | Fixed |
| 41    | `live_engine` UU-1 daily-max-loss                 | now uses `dispatch_alert_from_thread` | Fixed |
| 42    | `security.is_token_blacklisted` in `get_current_user` | fails open if Redis down — explicit comment | Documented decision (defense-in-depth layer) |
| 42    | `auth.py` refresh-rotation + revoke               | DB writes propagate; no new pass swallows | Clean |
| 43    | `alpaca_stream` LotTracker rollback               | inner rollback `except: pass` | **UU2-C above** |
| 44    | `live_engine` EOD pending-entry cancel            | logs at WARNING per cancellation | Clean (good level) |
| 44    | `pyramider` DD3-1 max-level keying                | no new error paths | Clean |
| 45    | `streaming_data_provider` per-symbol staleness    | no new error paths | Clean |
| 46    | `live_engine` TT-2 watchdog timeout               | re-raises asyncio.TimeoutError | Clean |
| 47    | `data/alpaca_client` TT-4 retry helpers           | exhausts retries → raises | Clean |
| 47    | `infra/security` AA3-4 leeway                     | parameter only | Clean |
| 48    | `ml/__init__` Z7-1 export removal                 | no error path | Clean |
| 49    | docs only                                         | n/a              | n/a |

No NEW silent-swallow paths were added in waves 41-49. The two follow-ups are UU2-A (Wave-41 forgot the success branch) and UU2-C (Wave-43's pre-existing rollback wasn't tightened when DD3-2 touched the surrounding code).

---

## 6. ValidationError consistency

Only one pydantic constructor exists on the request path: `UserClaims(**payload)` at `backend/infra/security.py:657`. Wave-32 (V8 AA2-NEW-2) wrapped it. The handler at line 666 catches by class-name string (`exc.__class__.__name__ == "ValidationError"`) because the pydantic import surface is conditional — that pattern is correct for the deferred-import case but won't trip BLE001 since the surrounding `except Exception` doesn't pass-swallow; it raises HTTPException. No new findings.

---

## 7. CancelledError consistency

20 `except (asyncio.CancelledError | CancelledError | TimeoutError, asyncio.CancelledError)` handlers found. Of those:

- **5** re-raise / break / return (correct cancellation propagation in tasks that should die)
- **15** are body-`pass` only

All 15 pass-only sites are **`await task` join points after `task.cancel()`** — i.e. the calling code requested the cancellation and is waiting for the task to acknowledge it. Swallowing `CancelledError` here is the correct pattern (the cancellation has already been delivered to the cancelled task; the joiner just doesn't want the propagation). Not findings.

The one structural risk pattern would be a *task body* that catches `CancelledError: pass` and continues running — none found.

---

## 8. TL;DR

After waves 41-49 closed three V9 UU sites (-3 pass-only, -54 f-string-in-handler), the codebase has 158 pass-only swallow sites, 1,067 blind-except sites, and 459 eager-f-string-in-handler sites. The core V11 lint deliverable is enabling **`S110` + `S112`** (cargo-cult body shapes — fail CI on `except *: pass`/`continue` regardless of exception type) plus **`BLE001`** (blind-except) and **`G004`** (f-string in logger) with a per-file-ignores ratchet baseline so the existing backlog is grandfathered and only new code must comply; `S110`/`S112` together exactly cover the 158+21 sites V9 UU-4 wanted catchable. Two narrow remediation gaps remain: UU-2's *successful*-login audit rollback was missed by Wave-41 (Finding UU2-A, Tier 1, one-line fix to mirror the failed-login branch six lines above) and Wave-43's LotTracker rollback retains the same silent-rollback pattern the new V11 lint would flag (Finding UU2-C, Tier 2). No new fail-open paths were introduced in waves 41-49.
