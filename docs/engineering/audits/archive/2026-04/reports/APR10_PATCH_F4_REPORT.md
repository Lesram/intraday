# Patch F4/4 — LiveEngine forensic guard + bypass audit — STRUCTURAL CLOSURE COMPLETE

**Commit**: `7d36b61`
**Parent**: `9e7c9a9` (F3)
**Status**: COMMITTED, not deployed. Full Patch F is complete.

## Files changed

| File | +/- |
|---|---|
| `backend/organism/live_engine.py` | +51 |
| `backend/organism/brain_persistence.py` | +6 / -1 (audit comment) |
| `tests/test_apr10_patch_f4_forensic_guard.py` | +286 (new) |

## What F4 adds

### LiveEngine forensic guard
- `__init__` captures `id(self.signal_gen)` and `id(self.learner)` as forensic fingerprints.
- `_save_brain()` checks:
  1. **Object identity**: if `id(self.signal_gen)` or `id(self.learner)` differs from the init-time fingerprint → logs CRITICAL with full stack trace. Does NOT abort (the persistence-layer guard handles the actual block).
  2. **Learner regression**: if `self.learner.state.total_trades == 0` while disk manifest shows `total_trades > 0` → logs CRITICAL and ABORTS the save entirely. This is the last line of defense before the persistence layer.

### Bypass audit — 2 callsites, both accounted for
| Line | Location | Status | Reason |
|---:|---|---|---|
| 824 | `_write_manifest_guarded` | **GUARDED** | The unified helper with trained-state guard, break-glass, instrumentation, and read-back invariant |
| 1316 | `_load_manifest` (migration) | **SAFE NON-LIVE** | Only writes `self._manifest` (read from disk at line 1282) with `brain_format_version` bumped. Only fires during `load()` on older-format brains. Never synthesizes from learner/signal_gen. |

Automated test (`test_bypass_audit_manifest_write_callsites`) asserts exactly 2 callsites. Any future direct write will fail the test.

### Full-stack wipe simulation
Test seeds a trained brain, then attempts the exact Apr 8/9 wipe pattern via `save_essential_state` with fresh learner/signal_gen. Asserts:
- Disk manifest preserved (total_trades=195, ml_is_trained=True)
- `BRAIN SAVE BLOCKED` or `SUSPICIOUS MANIFEST WRITE` log fires
- No silent success

## Full Patch F commit chain (complete)

```
7d36b61 fix(brain): LiveEngine forensic guard + bypass audit [F4/4]
9e7c9a9 fix(brain): break-glass reset + suspicious-write instrumentation + read-back invariant [F3/4]
3a694ee fix(brain): route save_essential_state through _write_manifest_guarded [F2/4]
eaa4b2f fix(brain): introduce _write_manifest_guarded helper, route save() through it [F1/4]
3528162 fix(brain): extend trained-state overwrite guard to save_essential_state [F-lite]
62256d7 fix(brain): refuse to overwrite trained manifest with untrained state [E]
c5fb0ed fix(scripts): default standalone scripts to organism_brain_sandbox/ [D]
be2eee8 feat(brain): force-save admin route for ML artifact recovery [A]
50b2513 fix(brain): save manifest from live learner.state and signal_gen [B]
93593a2 fix(brain): walk_forward_gate reads authoritative learner.state.best_sharpe [C]
```

## What is now STRUCTURALLY PREVENTED

1. **Trained→fresh manifest overwrite via save()** — blocked by _check_trained_overwrite_guard in both save()'s early guard AND the helper's defense-in-depth guard
2. **Trained→fresh manifest overwrite via save_essential_state()** — blocked by the same helper (F2 routing)
3. **Trained→fresh overwrite even with force=True alone** — blocked; requires full break-glass triad (force + allow_reset + reset_reason)
4. **Silent wipe without forensic trail** — impossible: _log_suspicious_manifest_write captures traceback, pid, thread, existing/incoming summary on every regressive attempt
5. **Post-write corruption going undetected** — read-back invariant compares written manifest against live learner/signal_gen state
6. **Object replacement going undetected** — LiveEngine forensic guard logs CRITICAL with stack trace on id() change
7. **Learner regression going undetected** — LiveEngine forensic guard aborts save when learner.state regresses while disk shows trained
8. **New direct manifest writes slipping in** — bypass audit test asserts exactly 2 callsites; new writes will fail CI

## What remains DIAGNOSTIC only

1. **The exact wipe trigger caller** — still unidentified. The suspicious-write stack-trace instrumentation will identify it on the next attempt. Until then, we know the MECHANISM but not the TRIGGER.
2. **transfer_knowledge.json missing after force_save_brain** — low severity, cosmetic, not persistence-critical.
3. **Exact timing pattern of the recurrence** — Apr 8 02:08, Apr 9 02:58, Apr 10 clean. Pattern inconclusive. May not recur at all if Patch D (script sandbox) or F-lite was already sufficient.

## Tests — 174/174 passed

| Test file | Count | Status |
|---|---:|---|
| F4 forensic guard | 5 | PASS |
| F3 break-glass/instrumentation | 7 | PASS |
| F2 unified essential save | 4 | PASS |
| F1 guarded helper | 7 | PASS |
| F-lite essential guard | 3 | PASS |
| Patch E trained-state guard | 8 | PASS |
| Patch A force-save | 13 | PASS |
| Patch B manifest sync | 8 | PASS |
| Apr-7 P0/P1 fixes | 12 | PASS |
| Organism regression (5 files) | 107 | PASS |
| **Total** | **174** | **ALL PASS** |

## Deploy/verify is now the only remaining structural step

Full Patch F is committed. The next and final step is:
1. Deploy `7d36b61` in the next maintenance window (market close, positions flat)
2. Verify all F1-F4 + A-E patch signatures in the running container
3. Force-save + artifact verification
4. Post-deploy report
5. FREEZE structural persistence work. Return focus to the trading algorithm.
