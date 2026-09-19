# Full Patch F — Planning Document

**Status**: PLAN ONLY. Not yet scoped for implementation. No code changes in this document.
**Author**: Drafted 2026-04-09 after the first clean session on the F-lite hardening stack.
**Prerequisite**: Commit `3528162` (Patch F-lite) must be deployed and verified live. ✅ Deployed at 07:57:54 UTC Apr 9, verified via force-save + 151-test suite.
**Deployment window**: NOT tonight. Next maintenance window after F-lite has been observed for ≥1 session and the recurrence test is conclusive (post ~04:30 UTC Apr 10). Target window: Fri 2026-04-10 20:00 UTC (post-market) or a subsequent clean window.
**Overall posture**: This is the LAST structural persistence-hardening project before focus returns to the trading algorithm. After Full Patch F lands, structural work on brain persistence freezes.

## Why Full Patch F and not F-lite

F-lite closes the specific proven path (trained→fresh overwrite via `save_essential_state`). It does NOT:

1. **Identify the caller** — F-lite blocks but does not capture a stack trace. If the wipe recurs via a variant path, we won't know which code called `save_essential_state` with a fresh learner.
2. **Cover all save paths** — F-lite guards `save_essential_state` only. If a wipe writer uses `save(force=True)` with fresh state, F-lite doesn't help.
3. **Cover direct manifest writes** — if some code path bypasses both save methods and calls `_write_json(manifest_path, ...)` directly, F-lite doesn't catch it.
4. **Detect manifest drift** — F-lite does not verify that what was written matches what should have been written.
5. **Detect live-engine object replacement** — if something swaps out `self.learner` or `self.signal_gen` on the live engine mid-session, F-lite doesn't flag it.

Full Patch F addresses all five gaps.

## Scope — F1 through F4 slices

Each slice is an independently committable, independently rollback-able commit. Each slice must pass its tests and the full regression subset before the next slice proceeds.

### F1 — Single guarded manifest write helper + `save()` consolidation

**Goal**: Create ONE private method that is the ONLY code path allowed to write `manifest.json`. Route `save()` through it. Dedup the Patch E guard logic.

**Changes in `backend/organism/brain_persistence.py`**:
- New method `_write_manifest_guarded(target, signal_gen, learner, *, caller, force=False, allow_reset=False, reset_reason=None) -> bool`
  - Resolves existing state from `self._manifest` OR on-disk manifest.json OR empty default (in that order)
  - Computes `total_runs` from the SAME uniform source for both save paths
  - Builds the manifest dict via `_apply_live_manifest_fields` (Patch B helper, unchanged)
  - Applies the trained-state overwrite guard (Patch E semantics, consolidated)
  - Writes via `_write_json(target / MANIFEST_FILE, manifest)`
  - Syncs `self._manifest = dict(manifest)` after successful write
  - Returns `True` on success, `False` on guard block
- Modify `_save_manifest()` to delegate to the new helper
- Remove the inline Patch E guard from `save()` (relocated into the helper)
- Add `force: bool = False, allow_reset: bool = False, reset_reason: str | None = None` pass-through params on `save()` (F3 will activate the break-glass logic; F1 just adds the parameters)

**Critical refactoring decision**: The existing Patch E guard in `save()` includes explicit `lock.release()` on block path. The relocation must preserve this. Two refactoring patterns:
- **Pattern A**: Keep the block check at the top of `save()` but extract it into a small helper `_check_trained_overwrite_guard(signal_gen, learner, force) -> tuple[bool, str]`. Both `save()` and (later in F2) `save_essential_state()` call it. The `lock.release()` stays in `save()`.
- **Pattern B**: Do the guard check INSIDE `_write_manifest_guarded`. `save()` must handle the case where the helper returns `False` by aborting the atomic swap cleanly. Requires more lock/finally refactoring.

**Recommended**: Pattern A. Smaller blast radius. Preserves lock semantics exactly.

**Tests (F1)**:
- All existing Patch E tests must still pass via the new shared check method (update `tests/test_apr8_patch_e_trained_state_guard.py` if the guard moved but the behavior is preserved)
- New test: `_write_manifest_guarded` returns True on normal write, updates `self._manifest`
- New test: `_save_manifest` delegates correctly to the helper

### F2 — Route `save_essential_state` through the helper + unify total_runs

**Goal**: Close the total_runs divergence between `save_essential_state` (reads from disk) and `_save_manifest` (reads from `self._manifest`). Route essential-save through the same guarded helper as full save.

**Changes in `backend/organism/brain_persistence.py`**:
- Modify `save_essential_state()` to delegate its manifest write to `_write_manifest_guarded(caller="save_essential_state")`
- Remove the inline manifest-build logic from `save_essential_state` (lines 608–618 in post-F-lite version)
- Remove the F-lite inline guard from `save_essential_state` — replaced by the guard inside `_write_manifest_guarded` (dedup, no behavior change)
- Add `allow_reset: bool = False, reset_reason: str | None = None` params to `save_essential_state` (F3 activates)

**Tests (F2)**:
- All existing F-lite tests must still pass via the new path
- New test: `save()` and `save_essential_state` produce identical `total_runs` behavior — 3 sequential saves alternating between the two methods produces `total_runs` 1, 2, 3 with no drift
- New test: fresh `OrganismBrain` instance with an existing trained on-disk manifest.json — both save paths read from disk fallback correctly

### F3 — Break-glass reset semantics + suspicious-write instrumentation + read-back invariant

**Goal**: Tighten the force-save security model, add the diagnostic that identifies the unknown wipe caller on recurrence, and add a post-write sanity check.

**Changes**:

**Break-glass tightening**:
- `force=True` alone no longer permits trained→fresh overwrite
- Required combination: `force=True AND allow_reset=True AND reset_reason` (non-empty string)
- `LiveEngine.force_save_brain()` continues to pass ONLY `force=True` — does NOT use break-glass because the live engine's learner is not in a fresh state during a normal force-save. The force-save endpoint is for recovery, not reset.
- Logs `BRAIN BREAK-GLASS RESET (caller): intentionally overwriting trained manifest... Reason: <reason>` at WARNING level when break-glass is used

**Suspicious-write instrumentation**:
- New helper `_log_suspicious_manifest_write(caller, existing, learner, signal_gen, force, allow_reset, reset_reason)`
- Captures: `traceback.format_stack()`, `os.getpid()`, `threading.current_thread().name`, existing manifest summary, incoming state summary
- Fires via WARNING log on EVERY regressive manifest write attempt, regardless of whether the break-glass path then allows it
- This is the **missing diagnostic** that would identify the unknown caller on the next wipe attempt

**Read-back invariant**:
- After every `_write_json(manifest_path, manifest)` call inside `_write_manifest_guarded`:
  1. Read manifest.json back from disk via `_read_json`
  2. Compare to live `learner.state` and `signal_gen` values
  3. On mismatch, log `CRITICAL: BRAIN MANIFEST READ-BACK INVARIANT FAILED (<caller>): <mismatches>` and return `False`
- Catches: partial writes, filesystem bugs, race conditions, and any silent corruption between write and read
- Best_sharpe comparison: allow `np.isfinite` fallback semantics (matches Patch B)

**Tests (F3)**:
- New test: `save(force=True)` without `allow_reset` on trained→fresh → BLOCKS (force alone isn't enough)
- New test: `save(force=True, allow_reset=True, reset_reason="test")` on trained→fresh → ALLOWS + logs WARNING
- New test: Suspicious-write instrumentation fires with correct stack, pid, thread, existing/incoming summary
- New test: Read-back invariant passes on healthy save
- New test: Read-back invariant detects mismatch (use mock/monkeypatch to write incorrect values, assert CRITICAL log + `False` return)

### F4 — LiveEngine forensic guard + bypass audit + final validation

**Goal**: Detect unexpected object replacement on the live engine, audit all remaining manifest write paths, and validate the complete Patch F stack end-to-end.

**Changes in `backend/organism/live_engine.py`**:
- In `LiveEngine.__init__`, after `self.signal_gen = ...` and `self.learner = ...`:
  ```python
  self._forensic_signal_gen_id = id(self.signal_gen)
  self._forensic_learner_id = id(self.learner)
  ```
- In `_save_brain()`, before any save call:
  1. Check `id(self.signal_gen) != self._forensic_signal_gen_id` or `id(self.learner) != self._forensic_learner_id` → log CRITICAL with stack trace (object replacement detected)
  2. Check `self.learner.state.total_trades == 0` while on-disk manifest shows `total_trades > 0` → log CRITICAL and ABORT the save (learner regression detected, prevents disk wipe even before the persistence-layer guard)

**Bypass audit**:
- Grep for every `_write_json(...MANIFEST_FILE...)` callsite in `backend/organism/`
- Known callsites:
  1. `_write_manifest_guarded` (the allowed helper)
  2. `_load_manifest` at ~line 963 — migration code only, writes an already-loaded manifest dict during format version bumping. MUST audit: can this fire during normal runtime? Only on load, which is only on boot. Safe.
- Any OTHER direct writes: route through the helper OR document why they can't regress a trained brain

**Tests (F4)**:
- New test: LiveEngine forensic guard logs CRITICAL when `signal_gen` id changes (mock replacement)
- New test: LiveEngine forensic guard logs CRITICAL + aborts save when `learner.state.total_trades = 0` but disk shows trained
- New test: Grep audit assertion — `_write_json.*MANIFEST_FILE` in brain_persistence.py returns only the expected N callsites (helper + migration). Fails loudly if a new direct write slips in.
- Final full-stack test: Simulate the exact Apr 8 02:08 wipe scenario (trained disk + fresh learner arg to `save_essential_state`) with `capfd`/`caplog` capture and assert:
  - Suspicious-write WARNING fires with stack trace
  - BRAIN SAVE BLOCKED ERROR fires
  - Manifest on disk is unchanged
  - No files deleted or corrupted

## Deployment strategy

**Target window**: Fri 2026-04-10 post-market (20:00 UTC onwards) or any subsequent clean window (market closed, positions flat). NOT tonight.

**Pre-deploy checklist**:
- [ ] F1-F4 all committed to `main` locally, ≥4 commits on top of `3528162` (F-lite)
- [ ] All 4 slices individually green (own tests + regression subset) at commit time
- [ ] Combined final test run green across all patch tests + organism regression subset
- [ ] `git status` clean in `backend/organism/` and `tests/`
- [ ] Container at `intra-api-1` healthy, positions flat, market closed
- [ ] Forensic snapshot untouched
- [ ] Disk brain state fully synced (generation, total_trades, ml_is_trained, feature_count, best_sharpe all consistent between manifest.json and learning_state.json)

**Deploy sequence** (same pattern as D+E and F-lite deploys):
1. Capture pre-deploy snapshot
2. `docker compose -f docker-compose.paper.yml up -d --build api`
3. Poll healthy within 120s
4. Verify all Patch F signatures in container via `docker exec grep`
5. Verify boot log shows clean brain load with gen 36+ (or whatever the then-current state is)
6. `POST /api/v1/organism/save?force=true` — verify response includes `success=true, forced=true` and correct gen/trades/best_sharpe/ml_is_trained
7. Verify all 13-14 brain files freshly rewritten with synced mtimes
8. Verify manifest fully synced with learning_state
9. Generate post-deploy report + bundle + Desktop export

**Rollback plan**:
- Any single slice can be reverted via `git revert <sha>`
- The stack is designed so F1 is the foundation; F2-F4 build on it
- If F4 verification fails but F1-F3 are good, the system is in a hardened state and F4 can be a follow-up patch
- Full rollback: `git reset --hard 3528162` (F-lite) if the entire Patch F must be abandoned

## Risk assessment

**Low risk**:
- F1 (helper extraction + dedup) — behavior-preserving refactor, extensive test coverage
- F4 forensic guard in LiveEngine (diagnostic only, doesn't change trading decisions)
- Bypass audit (read-only until any issues are found)

**Medium risk**:
- F2 (route `save_essential_state` through the helper) — changes the total_runs semantics. Could surface edge cases where save order/timing matters. Mitigation: explicit total_runs consistency test.
- F3 read-back invariant — false positives possible if the round-trip serialization changes values (e.g., float precision). Mitigation: use the same rounding helpers in both write and verify.

**Higher risk areas to watch**:
- Lock release semantics during guard blocks (the current Patch E inline pattern is subtle). Recommended refactoring pattern A above minimizes this risk.
- Read-back invariant's `best_sharpe` comparison must match `_apply_live_manifest_fields`'s exact rounding. Test explicitly.

**Non-risks** (explicitly):
- No strategy logic changes
- No trading decision changes
- No threshold/sizing/exit rule changes
- No scheduler behavior changes
- No walk-forward math changes
- No impact on the force-save endpoint's current semantics

## Test coverage summary

| Slice | New tests | Modified tests | Regression run |
|---|---:|---|---|
| F1 | 2 | test_apr8_patch_e_trained_state_guard.py (may need updates if guard location moves) | patch tests + organism regression |
| F2 | 3 | test_apr9_patch_f_lite_essential_state_guard.py (may need updates for helper routing) | + |
| F3 | 5 | — | + |
| F4 | 4 | — | + full-stack simulation |
| **Total** | **14 new** | 2 modified | All 4 subsets |

Final test gate: 151+ patch tests + 107 organism regression subset + 14 new Patch F tests = target 272+ passing.

## Execution guidance

**Delegation**: The three implementer refusals during the initial Full Patch F attempt were substantively correct. The scope is multi-hour structural refactor on a live-trading persistence path. Two options for execution:

1. **Fresh Claude Code session** (recommended) — a new session will see `HEAD=3528162` correctly (not the stale `2018999` from this session's starting gitStatus). The subagent's read-first, narrow-edit workflow should work cleanly in a fresh context without the "stale session-start snapshot" problem that tripped up three delegation attempts in this session.

2. **Direct execution in this session** — works but consumes session context across many turns (read files → plan → edit → test → commit per slice × 4 slices). Feasible but less efficient.

Either way, execute F1 → F2 → F3 → F4 sequentially with a green-test gate between each slice. Do NOT bundle into one commit.

## Dependencies and prerequisites

**Must exist before Patch F starts**:
- [x] `3528162` F-lite deployed and verified live ✅
- [x] Brain state fully synced on disk ✅
- [x] At least one full session observed on F-lite (first live validation) ✅ Apr 9 session complete, 0 wipe attempts observed
- [ ] Wipe recurrence window (~04:30 UTC Apr 10) passed with a clean or caught result — scheduled monitor `59060888`
- [x] Forensic snapshot preserved ✅

**Blocks Patch F from starting**:
- An active wipe that F-lite does NOT catch (would mean a variant path exists that needs dedicated investigation before structural closure)
- A deploy issue with F-lite (would need rollback first)
- Market being open (would need to wait for close)
- Active positions (would need EOD flatten)

## Success criteria

Full Patch F is complete and the structural work is frozen when:

1. All 4 slices committed and deployed
2. Post-deploy verification shows all patch signatures present in container
3. Force-save works end-to-end and produces synced manifest
4. ≥2 full sessions observed on the deployed Patch F stack with:
   - Zero wipe attempts OR
   - Wipe attempts caught and logged with full stack trace identification
5. If a caller is identified via the suspicious-write instrumentation, that caller is either (a) fixed in a follow-up patch, or (b) determined to be benign and documented

After success criteria met: structural persistence work is FROZEN. All future persistence changes go through the normal change-control process, not emergency patches. Focus returns to:
- Strategy algorithm improvements
- PSQ / inverse-ETF over-allocation in chop regimes
- Alpha scanner breadth (why only ETFs + 1-2 stocks trade per session)
- Exit fragmentation (multi-leg unwinds eating spread)
- Walk-forward gate calibration review

## Appendix — Rejected scope

Explicitly OUT of Patch F:

- ❌ `transfer_knowledge.json` missing after `force_save_brain` — cosmetic, queue as cleanup later
- ❌ Wash-trade reject bug from Apr 8 (XLE buy retries) — separate strategy issue
- ❌ Auto-breakout scanner timing — not persistence-related
- ❌ Any strategy/threshold/sizing/exit rule changes
- ❌ Universe selector tuning
- ❌ PSQ allocation investigation
- ❌ Any broad refactor beyond the specified 4 slices
