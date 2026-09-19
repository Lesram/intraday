# Sharpe Daily-Decay Guard — Restart Survival Check

## Field
`BrainPersistence._last_sharpe_decay_date: str` — declared in `__init__`
at `backend/organism/brain_persistence.py:141`, default `""`.

## Read/Write Sites (host source, full grep)
```
backend/organism/brain_persistence.py:141:        self._last_sharpe_decay_date: str = ""
backend/organism/brain_persistence.py:1235:        if self._last_sharpe_decay_date != today:
backend/organism/brain_persistence.py:1238:            self._last_sharpe_decay_date = today
```
No other module in `backend/` references the field.

## Persistence Audit
- NOT written to `self._manifest`.
- NOT written by `save_essential_state`.
- NOT written by `save` / full brain save.
- NOT restored by `load`, `from_persistence_dict`, or any manifest read.
- NO disk file (`*.json`) holds this field.

## Restart Behavior
On every process start (and therefore on every container restart /
redeploy):
1. `BrainPersistence.__init__` runs.
2. `self._last_sharpe_decay_date = ""`.
3. The first walk-forward gate regression check on the same UTC day
   sees `"" != "<today>"` → decay fires → `best_sharpe *= 0.95`.
4. Guard then holds for the remainder of THAT process lifetime only.

## Conclusion
The "at most once per UTC day" invariant only holds **within a single
process lifetime**. Under the realistic operational pattern of this
platform — daily rebuilds, mid-session restarts, hot-fix redeploys —
the guard resets on every restart and `best_sharpe` can still decay
multiple times per UTC day.

The original failure mode (compounding 5% decay collapsing
`best_sharpe` from 2.776 → 0.011 in one session) is mitigated against
the *tick-cadence* trigger but is **not** mitigated against the
*restart-cadence* trigger. A single afternoon restart would still
allow a second 5% decay on the same day, and N restarts would allow N
decays.

## Verdict
**RESTART-SAFE: NO.**

To make the fix restart-safe, the field must be persisted in
`_manifest` (or a sibling JSON) and restored on `load`. Suggested key:
`"_last_sharpe_decay_date"` written alongside `"best_sharpe"` in
manifest, and read back in the same loader path that hydrates
`best_sharpe`.
