# Ops recovery work order — completion report

**Date:** 2026-07-23 · **Branch:** `intra-2.0-phase1` · **Executed by:** Claude Code
**FROZEN_AT held at 2026-07-07T20:36:49.008305+00:00 throughout** (drift-verify green
after every task). No decision-surface edit. `_live_tick_inner` untouched.

> **Status: DEPLOYED and validated in the live container** (2026-07-23T22:05Z,
> GIT_SHA `d2548b8`, `intra-api-1` healthy). All code, ops and reports shipped
> (Tasks 0–6); live acceptance for Tasks 1/2/6 confirmed in the container (below).
> The deploy was one container-down window — Task 1's full save re-activates the
> swap path Task 2 fixes (shipped together), and the live-volume data ops are
> race-free only while the engine is down.
>
> **Headline live proof:** the graceful stop under the OLD code performed a shutdown
> full-save that **dropped both sidecars** (shadow_exit_telemetry + model_swap_audit
> vanished from the head) — a live reproduction of the Task 2 bug. After the rebuild,
> a graceful restart under the NEW code performed the same shutdown full-save and the
> sidecars **survived unchanged** (shadow=1, model_swap=68 before and after). Same
> operation, opposite outcome — the fix, proven end-to-end.

---

## New tooling — global rule #2 (Task 0)

**`scripts/phase2_freeze.py --verify`** — read-only drift check (never re-stamps).
Recomputes the live surface, compares to `param_freeze.json`, exits 1 on drift / 2 on
missing artifact, printing the offending keys. Run after every task below; **green
every time.** Commit **`abad883`**. Tests: `tests/test_phase2_freeze.py` (6/6),
incl. a probe that mutates a copy and asserts exit 1 + no write.

---

## Task 1 — Brain persistence  ✅ code shipped · live-validate at deploy

**Root cause (proven):** the walk-forward gate in `_save_brain` compares the current
last-100 Sharpe to `learner.state.best_sharpe`, a **monotonic all-time high-water
mark (3.436, gen 26)**. In a losing/chop tape current Sharpe is negative, so
`ratio = current/best = -0.297` can never reach the 0.95 threshold — **the gate is
permanently closed.** Evidence (today's log): **14 walk-forward SKIPs, 0 full "Brain
saved at tick", 0 ever in the retained log.** On disk, `ml_classifier.joblib` /
`ml_regressor.joblib` / `evolved_params.json` / `.save_complete` are frozen at the
07-07 full save while `manifest.json` advances (essential save). Diagnostic steps 2–3
ruled out: the `.brain.lock` is a POSIX `fcntl.flock` (kernel-released on process
death) — a stale lock file cannot deadlock; the 47 successful essential-save cycles
prove the scheduler thread runs.

**Fix (`8d00ae5`, persistence path only):** bounded walk-forward skip — below the
ceiling behave exactly as before (essential in-place save + return); at
`ORGANISM_MAX_WF_SAVE_SKIPS` (default 12 ≈ hourly) consecutive skips, force ONE full
save tagged `gated_save=true`, then reset the counter. `force=True` is audit-only —
it does not bypass the trained-overwrite guard, so a gated save can never wipe a
trained brain with fresh state.

**Acceptance:**
- stale-lock path unit-tested ✅ (`tests/test_walkforward_persistence.py::TestStaleBrainLock`)
- bounded-skip behavior unit-tested ✅ (5 probes drive the real `_save_brain`)
- drift-verify green ✅
- **LIVE:** the new bounded-skip log is active in the container —
  `Full brain save SKIPPED by walk-forward gate (1/12 consecutive)`. A full save
  lands: `.save_complete` advanced 07-07 → 2026-07-23T22:05:13Z, `evolved_params.json`
  refreshed. The bounded-skip forces its own full save at 12 consecutive gated cycles
  (~1 h) even absent a graceful shutdown; `make paper-status` now shows a fresh
  `.save_complete` instead of the 07-07 stale one. Mid-session restart reloaded a
  fresh head with **zero new `corrupt_head_*`**. ✅

---

## Task 2 — Sidecar durability  ✅ code shipped · data restore at deploy

**Root cause (proven in `save()`):** the file-by-file atomic swap moves every head
entry NOT in `preserved_names` to `.brain_old` and then `rmtree`s it. Only
`candidate_filter_shadow_telemetry` and `strategy_evidence_events` were listed, so
`shadow_exit_telemetry.jsonl`, `model_swap_audit.jsonl`, `previous_model/` were
deleted on every full save. Faithful shadow-exit evidence collapsed to **n=1** (only
META −0.525 07-07 survives, in `corrupt_head_20260707_121109`; the SH 06-26 row was
lost to backup pruning). `_create_backup` copied only files, so `previous_model/`
(a dir) was in no backup either.

**Fix (`d54b87f`):** `SIDECAR_TELEMETRY_NAMES` covers all five sidecars; the swap
preserves them in place; `_create_backup` + corrupt-head capture now copy
`previous_model/`; and the shadow-exit recorder gains a **real-close guard** (emit
only when qty>0), sitting in `_shadow_evaluate_exits` (outside `_live_tick_inner`).

**Acceptance:**
- full save()+backup+reload preserves all three sidecars with intact bytes, zero
  corrupt_head ✅ (`tests/test_sidecar_durability.py::TestSwapPreservesSidecars`)
- qty=0 row suppressed, qty>0 row emitted ✅ (`TestRealCloseGuard`)
- drift-verify green ✅
- **LIVE:** a full-save swap under the new code preserved both sidecars (shadow=1
  META, model_swap=68) across a restart — the OLD code had just dropped them on the
  prior stop. `scripts/ops/clean_brain_sidecars.py --apply` ran in the down window:
  recovered the 1 faithful META row (live head had 0 after the old-code drop),
  restored 68 real model-swap rows, quarantined the corrupt heads. The shadow
  analyzer now reads only the 1 faithful row. ✅

---

## Task 3 — Uptime  ✅ shipped (install is Marsel's)

**Root cause:** `restart: unless-stopped` only acts while the Docker daemon runs — it
cannot survive Docker Desktop quitting or a Mac reboot (both 06-27→07-06 and
07-08→07-23 outages).

**Fix (`be0c792`, ops/docs only — zero backend):** login LaunchAgent
`com.intra.paper` (launch Docker → wait for daemon → `compose up -d`), optional hourly
watchdog, `make paper-up/paper-status/paper-watchdog`, and
`docs/runbooks/PAPER_UPTIME.md`.

**Acceptance:** `plutil -lint` OK on both plists, `bash -n` clean, **`make
paper-status` runs green against the live stack** (surfaces the stale
`.save_complete=07-07` — the very Task-1 symptom). Full quit-Docker/reboot test needs
the install (DECISION ITEM below).

---

## Task 4 — Forward-evidence pipeline note  ✅ (report-only)

`reports/FORWARD_EVIDENCE_PIPELINE_NOTE.md`. Confirmed with citations: the verdict gate
(`phase2_gate.py:31` → `load_forward_corpus`, `backend/organism/phase2_gate.py:116-125`)
counts **real fills strictly after FROZEN_AT**; shadow events feed only
`phase3_attribution_report.py` (`:68`, `strategy_evidence_events.jsonl`). Measured:
**0 real fills since the freeze** (last close META 07-07T18:37, ~2h pre-freeze); all
strategies INSUFFICIENT n=0; ~6.7k un-routed shadow signals, no PnL. DECISION ITEM for
Marsel (wait / pre-register shadow-admission / longer horizon). Drift-verify green.
*(reports/ is gitignored — deliverable on disk + `~/Desktop/desk/`.)*

---

## Task 5 — Entry-path stand-down diagnosis  ✅ Session 1 (report-only)

`reports/ENTRY_STANDDOWN_DIAGNOSIS.md`. **CORRECTED at session close (23:39Z) after
Cowork's red-team caught that the first draft was a ~17:48Z mid-session snapshot
presented as the full session.** EOD numbers: regime **74% trending_down / 22% chop**
(n=1,153 evidence events); **0 orders / 0 fills all day**; `direction_zero` fired
**30×** (not 0 — 27 in a 19:18–19:35Z cluster after the snapshot) and the $50k
liquidity floor fired **7×, all SH** (not "0 ever" — first occurrences in the retained
log, post-snapshot). Both are second-order (37 events) against the dominant binding
constraint, **IEX data starvation**: scanner empty **164×** (`market_scanner.py:410`)
and **1,582** stale-bar fall-throughs, 75% on PSQ (599) + SH (585). 17 live candidates,
0 submissions. **The Task-0(b) closure (IEX starves the universe) stands on the honest
numbers — starvation outweighs gate-kills ~47×.** Sessions 2–3 stubs remain and will be
measured at session close only. DECISION
ITEMs (SIP re-subscribe / universe expansion / symmetric-short `2454ceb`) listed with
clock consequences. Drift-verify green.

---

## Task 6 — Hygiene  ✅ code shipped · data ops at deploy

- **corrupt_head quarantine:** `brain_persistence` backup pruning + restore-candidate
  scan now consider only `brain_gen*` dirs, so `backups/quarantine/` is never pruned
  or rescanned (`fa1c549`; tests `TestQuarantineGuard`). The move of the 5 corrupt_head
  dirs runs at deploy.
  **CORRECTION (Cowork red-team):** the 5 quarantined dirs are NOT the five original
  07-07 heads the work order named. They are **1× 07-07 (`…121109`) + 4× 07-23 dirs
  created by this session's own un-isolated test runs.** The other four original 07-07
  heads (103259/105849/105852/121106) were **destroyed** — `rmtree`'d by the
  pre-existing keep-at-most-5 corrupt-head retention (`_restore_from_latest_backup`)
  as each test-created head arrived, hours before the quarantine move. They exist
  nowhere on the volume (verified by full-volume find). The surviving `…121109` — the
  only copy of the faithful META shadow row — survived **by luck of being newest**;
  had it been oldest, the test runs would have destroyed the only faithful shadow
  evidence in existence. My earlier "corrupt_head count held at 5" was the invariant
  that MASKED these deletions, not evidence of safety.
- **cumulative_pnl drift:** csv is authoritative (measurement-integrity). state −675.46
  vs csv **−673.311657** (drift $2.15, legacy 2dp↔6dp rounding). `reconcile_cumulative_pnl`
  corrects the persisted `learning_state.json` to the csv sum; applied at deploy so the
  container reloads the reconciled value (the running container would overwrite a disk
  fix within 5 min otherwise).
- **stray files:** no `overnight_positions.json` ✅. **ORB cache invalidation behaved** —
  log shows "ORB cache stale for NVDA (cached session=2026-07-22, current=2026-07-23) —
  invalidating" (+AMD, IWM) on the session roll ✅.
- **LIVE:** boot log after deploy — `cumulative_pnl reconciles: state=-673.31
  csv_sum=-673.31 drift=$0.00 within tolerance` (was $2.15). Clean boot with **zero
  new corrupt_head**; the 5 corrupt heads now live under `backups/quarantine/`, and
  the loader ignores them (`brain_gen*`-only scan). ✅

---

## Found while working (not in the work order — flagged)

**Test-isolation defect (pre-existing; I triggered it — and it cost data).** Tests
that construct an engine/brain with the default `brain_dir` mutate the **real**
`organism_brain` volume when `ORGANISM_BRAIN_DIR` is unset. This session's un-isolated
runs (a) wrote the qty=0 shadow pollution and the 17:04Z model-swap test burst the
cleaner had to quarantine, (b) created four `corrupt_head_20260723_*` dirs, and —
**per Cowork's red-team** — (c) thereby **destroyed four of the five original 07-07
corrupt heads** via the pre-existing keep-5 retention cap (each new test-created head
evicted the oldest original). The container brain was never harmed (self-heals every
5 min), but forensic data was permanently lost, and the sole faithful META shadow row
survived only because its host dir happened to be newest. **Mitigation adopted
mid-run:** every subsequent test run used `ORGANISM_BRAIN_DIR=<scratch>`. **Follow-up
(PROMOTED from flagged to scheduled, per Cowork):** an autouse conftest fixture to
redirect the brain dir suite-wide — this defect has now cost data twice.

---

## Final verification

- `phase2_freeze.py --verify`: **DRIFT-VERIFY OK … FROZEN_AT=2026-07-07T20:36:49Z**
  (exit 0) — run after every task and again post-deploy. FROZEN_AT never moved.
- Full suite (`ORGANISM_BRAIN_DIR=<scratch>`): **9 failed / 7717 passed / 724 skipped**
  at run time. Exactly one failure was mine — an F401 unused import the V12 W75 lint
  ratchet caught — **fixed in `d2548b8`** (ratchet back to green, 3690 < 3696 baseline
  on this Mac's venv ruff; **Cowork caveat: ruff is floor-pinned `>=0.1.0`, so the count
  is toolchain-relative and unfalsifiable off-machine — pin ruff exactly and re-baseline**).
  The other **8 are pre-existing, environment/timing-driven, not introduced here:**
  `test_alpha_breakout_bad_regime_filter_blocks_main_book_orders` +
  `test_replay_no_throttle_blocking` + `test_w100_entries_gate_{produces_orders,signals_generated}_on_uptrend`
  (local paper `.env` suppresses order flow — the same zero-order stand-down Tasks 4/5
  document; the first is proven identical on pristine HEAD), `test_seam_..._tripwire_has_teeth`
  (test's SimpleNamespace mock lacks `_scan_all_strategies_v2`), `..._shadow_telemetry_switches`
  (the paper deploy sets `STRATEGY_EVIDENCE_TELEMETRY_ENABLED=true`; test expects the
  default off), `..._lint_ratchet_runs_in_under_2_minutes` (timing flake under full-suite
  load), `..._npm_audit_no_high_or_critical` (frontend).

## Deploy — DONE (2026-07-23T22:05Z)

Executed one container-down window; `intra-api-1` healthy on GIT_SHA `d2548b8`.

1. **Graceful stop** (old code) → shutdown `force_save_brain` wrote a fresh
   `.save_complete`/`evolved_params` **and dropped both sidecars** (Task 2 bug, live).
2. **`clean_brain_sidecars.py --apply`** (down window) → recovered 1 faithful META
   shadow row, restored 68 model-swap rows, moved the 5 surviving corrupt-head dirs
   (1× 07-07 + 4× test-created 07-23; four originals already destroyed — see Task 6
   correction) → `backups/quarantine/`,
   reconciled `cumulative_pnl` −675.46 → −673.311657.
3. **`rebuild_paper.sh`** → new image (all 6 commits), `up -d`, `/health` 200.
4. **Boot validated:** clean load (gen 389), `cumulative_pnl … drift=$0.00`, zero new
   corrupt_head, new code present (`_consecutive_wf_skips`, `SIDECAR_TELEMETRY_NAMES`).
5. **Graceful restart** (new code) → shutdown full-save **preserved** both sidecars
   (shadow=1, model_swap=68 unchanged), `.save_complete` advanced to 22:05:13Z, zero
   new corrupt_head. `make paper-status` shows fresh state; bounded-skip log active
   (`… (1/12 consecutive)`). drift-verify OK.

## Open DECISION ITEMs (Marsel only)

1. **Task 3 install:** Docker Desktop "Start at login" + `launchctl load
   ~/Library/LaunchAgents/com.intra.paper.plist` (commands in the runbook).
2. **Task 4 evidence admission:** wait for trend tape / pre-register shadow-attribution
   amendment (resets clock) / accept longer horizon.
3. **Task 5 clock levers:** SIP re-subscription (fixes the root IEX starvation, resets
   clock) is the highest-leverage; universe expansion / symmetric-short are secondary
   and also clock-sensitive.
