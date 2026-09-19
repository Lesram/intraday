# Hard-Stop Checks

| # | Check | Result |
|---|---|---|
| 1 | deploy completed successfully | N/A — NOT PERFORMED (halted before rebuild) |
| 2 | running container is healthy | PASS (pre-existing container healthy, 19h uptime) |
| 3 | Apr-7 tick-counter fixes present in running container | FAIL — running container is pre-patch; host source has the patch but not yet deployed |
| 4 | Apr-7 watchdog fixes present in running container | FAIL — same as #3 |
| 5 | daily-decay best_sharpe fix present in running container | FAIL — same as #3 |
| 6 | daily-decay guard survives restart/redeploy | **FAIL** — field is in-memory only, not persisted, not restored |
| 7 | brain state survived deploy | N/A — no deploy performed |
| 8 | APP_ENVIRONMENT correct (development) | PASS (existing runtime) |
| 9 | account ACTIVE and unblocked | PASS (Alpaca account snapshot captured) |
| 10 | no blocker exists for next paper session | **FAIL** — blocker #6 |

## Verdict
**HARD STOP.**

Blocker: the Apr-7 P1 walk-forward best_sharpe daily-decay guard is
not restart-safe. `_last_sharpe_decay_date` is a transient instance
attribute that resets to `""` on every container start. Under
realistic restart conditions the "once per UTC day" invariant fails,
re-exposing the original compounding-decay failure mode (just at
restart cadence rather than tick cadence).

Required remediation before deploy: persist `_last_sharpe_decay_date`
into the brain manifest (or alongside `best_sharpe` in whatever
persistence channel hydrates that field) and restore it on load.
