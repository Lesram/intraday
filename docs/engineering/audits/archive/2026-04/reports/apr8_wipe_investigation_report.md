# Apr 8 02:08 UTC Brain Wipe — Targeted Investigation Report

See chat transcript for full narrative. Key conclusions:

## Ruled out
- Fresh `OrganismBrain()` instantiation by another backend code path (only one exists)
- ML lifecycle scheduler (no references to organism_brain)
- Background trainer subprocess (no brain writes)
- Nightly scheduler / TrainingOrchestrator (candidate-weights pipeline only)
- `backend/api/routes/signals.py` (mock market data, no brain writes)

## Ruled in
- Wipe manifest byte-for-byte matches output of pre-Patch-B `_save_manifest()` at `backend/organism/brain_persistence.py:661–680` (from commit 93593a2) when called with a freshly-instantiated learner and signal_gen
- Writer path: `live_engine._save_brain() → brain.save() → _save_manifest()`
- total_runs=214 in wipe = self._manifest["total_runs"]=213 + 1, confirming it was the live engine's self.brain instance, not a new one

## Unproven
- What caused `self.learner` / `self.signal_gen` on the live engine to be in fresh/default state at 02:08 UTC
- Most plausible single-fire explanation: manual invocation of `scripts/run_hft_organism.py` or `scripts/run_breakout_organism.py` (both default to `brain_dir="organism_brain"`, shared with live container bind mount)
- No cron, launchd, or running process evidence of script execution

## Patch coverage gap
Patches A/B/C do NOT fully close this failure mode. If something reinitializes the live engine's learner/signal_gen mid-session, or if the scripts are re-run against the shared brain directory, the wipe CAN recur.

## Recommended follow-ups (not executed)
1. Change default brain_dir in `scripts/run_hft_organism.py` and `scripts/run_breakout_organism.py` to `organism_brain_sandbox/`
2. Add a "refuse to overwrite trained state with untrained state unless explicit" guard to `brain.save()`
3. Upgrade `_BrainLock` to `fcntl.flock` for cross-process safety
4. Instrument suspicious save (gen=0 + trades=0 after previously having trades) with WARNING + stack trace

Non-blocking. Platform is operationally durable for normal paths.
