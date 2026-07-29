# Work Order — Operational Recovery (Post-Freeze), 2026-07-23

**Audience:** Claude Code, run locally at the repo root on branch `intra-2.0-phase1`.
**Author:** Cowork (Claude), facts verified against the repo and live brain state on 2026-07-23.
**Purpose:** The platform build is DONE and frozen (2026-07-07T20:36:49Z, `artifacts/phase2/param_freeze.json`, running==frozen proven). What is broken now is everything *around* the frozen instrument: the engine was dark 07-08→07-23 (~10 sessions), restarted today at 11:46 ET, and since restart it ticks but (a) the brain has not saved once, (b) sidecar telemetry files are gone again, (c) zero orders fire, and (d) the forward-verdict corpus has **zero rows since the freeze**. This work order fixes operations without touching the frozen decision surface.

**How to run this file:** execute tasks strictly in order. Each task ends with its acceptance gate green and a commit (AGENTS.md PR flow for `backend/**`). Stop and report at anything marked **DECISION ITEM** — those belong to Marsel, not to you.

---

## Global rules (every task, no exceptions)

1. **The frozen decision surface is untouchable.** No edits to entry direction logic, gates, exit engine, sizing, regime detector, `strategy_config`, exit env, or the data-feed setting. If a fix seems to require touching one of these, STOP and write it up as a DECISION ITEM instead. Any drift re-stamps `FROZEN_AT` and throws away the forward clock.
2. **Prove no drift after every task.** `scripts/phase2_freeze.py` re-stamps on drift (that is a clock reset, not a check). First add a read-only `--verify` mode to it (recompute source hashes, compare to `artifacts/phase2/param_freeze.json`, exit non-zero on mismatch, never write). The freeze script is tooling, not surface — this is allowed. Then run `python scripts/phase2_freeze.py --verify` at the end of every task; it must pass.
3. **Full test suite green before every commit**; structural guard tests (source pins, LOC ceilings) stay green. Do not touch `_live_tick_inner` — none of these tasks needs it.
4. Paper account only. No live-order-path edits anywhere in this work order.
5. Timezone discipline in log forensics: word-boundary matching for auth errors (naive "401"/"403" greps false-positive on microsecond timestamps — verified twice).

---

## Task 1 — Brain persistence: no save has landed since restart (highest priority)

**Verified state:** container cold-booted 2026-07-23 15:46:48Z; ticks/evidence flow all day; but `organism_brain/manifest.json` still carries `saved_at` 2026-07-08T19:46Z, gen 389, and `learning_state.json` mtime 07-08. A full session produced no checkpoint. Boot log also shows `cumulative_pnl reconciliation drift on load state=-675.46 csv_sum=-673.31`.

**Diagnose in this order:**
1. The walk-forward save-skip gate — `backend/organism/live_engine.py:7438` ("Full brain save SKIPPED by walk-forward gate") was already intermittently skipping saves in late June on negative current_sharpe. Determine whether it has been skipping **every** save since restart (count occurrences in today's `application.log` vs save attempts). A guard that can gate 100% of saves indefinitely is a persistence bug, not a guard.
2. If not the gate: check whether the save loop/scheduler thread started at all post-boot (log the scheduler's save-cycle heartbeat), and whether the save lock from the 06-25 corruption fix (Task E, commit `1b1147b`) can deadlock after a dirty shutdown (stale lock/sentinel from the 07-08 power-off).
3. Rule out disk/permission issues on the volume mount (a failed write should be loud — if saves fail silently, add the error log).

**Fix constraints:** persistence path only (`brain_persistence.py`, save scheduling in `live_engine.py` outside `_live_tick_inner`, lock/sentinel files). If the root cause is the walk-forward gate being permanently closed, the fix is a bounded skip (e.g. the gate may skip at most N consecutive full saves, then a save is forced with a `gated_save=true` tag) — that changes *when state persists*, not any trading decision. Justify in the commit message.

**Acceptance:** during a live (or replayed) session, `manifest.json` `saved_at` advances on the expected cadence; a `docker restart` mid-session reloads the fresh head with **zero new `corrupt_head_*`**; the stale-lock path is unit-tested; drift-verify green.

---

## Task 2 — Sidecar durability: telemetry files vanish on save/restart (second time)

**Verified state:** `organism_brain/` today contains `candidate_filter_shadow_telemetry.jsonl` but **no** `shadow_exit_telemetry.jsonl`, no `model_swap_audit.jsonl`, no `previous_model/`. This is the second recurrence. Faithful shadow-exit evidence to date is only n≈2 rows (SH −$0.59 on 06-26; META −$0.53 on 07-07) and the only copy of the META row lives in `organism_brain/backups/brain_gen389_20260707_200640_962513/` (locate it; if absent, search all `organism_brain/backups/brain_gen389_*` for `shadow_exit_telemetry.jsonl` rows with qty>0). A 07-23 backup exists (`brain_gen389_20260723_155204_525384`) — inspect what it captured.

**Root-cause hypothesis to confirm:** the full-save/swap path writes a known-file manifest and the restore/swap step drops files not on that list — sidecars survive in `backups/` snapshots but not in the live head after a save cycle or quarantine event. Confirm by reading the save/swap file list in `brain_persistence.py` and the quarantine (corrupt_head) mover.

**Build:**
1. Restore into the live head: `shadow_exit_telemetry.jsonl` (faithful rows only — see 3), `model_swap_audit.jsonl`, `previous_model/` from the best backup copies.
2. Make sidecars first-class in the save/swap/quarantine paths: either include them in the swap manifest or exclude them from swap entirely (append-only files that persistence never moves/deletes). Choose the simpler one and document it.
3. Clean the pollution: the surviving shadow file holds ~178–286 Jan-2026-timestamped qty=0 replay artifacts. Move them to `shadow_exit_telemetry_quarantined.jsonl`; keep only faithful rows. Then guard the writer (`live_engine.py`) so a shadow row is emitted **only** for a real close (qty>0 and a matching `trade_history.csv` row) — this is logging hygiene, not a trading change.

**Acceptance:** full save cycle + container restart + a simulated quarantine each leave all three sidecars present and intact; the analyzer reads only faithful rows; unit test for the real-close guard; drift-verify green.

---

## Task 3 — Uptime: the container must survive Marsel's Mac, not just Docker

**Verified state:** `docker-compose.paper.yml` already sets `restart: unless-stopped` (lines 140/197/238) — yet the engine was down 06-27→07-06 and 07-08→07-23. Both outages are consistent with **Docker Desktop itself quitting / Mac reboot**, which no compose policy survives. The 06-27 log end was an orderly lifespan shutdown.

**Build (ops/ + docs only, zero backend code):**
1. `ops/launchd/com.intra.paper.plist` — a LaunchAgent that, at login: waits for Docker Desktop (`open -a Docker` + poll `docker info`), then runs `docker compose -f docker-compose.paper.yml up -d`. Plus `make paper-up`, `make paper-status` (prints container state, manifest `saved_at` age, last trade_history row) and `make paper-watchdog` (one-shot: if `docker info` OK but `intra-api-1` not running → `up -d`; optionally installable as an hourly LaunchAgent).
2. A one-page runbook `docs/runbooks/PAPER_UPTIME.md`: enable Docker Desktop "Start when you log in", install the LaunchAgent (`launchctl load`), System Settings → prevent sleep while plugged in (or `caffeinate` note), and the two recovery one-liners for the observed failure modes.
3. **DECISION ITEM (small):** Marsel must actually install the LaunchAgent and tick the Docker Desktop login setting — print the exact commands at the end of your run.

**Acceptance:** simulated test — quit Docker Desktop, log out/in (or reboot), container returns without human action; `make paper-status` correct; nothing in `backend/**` changed.

---

## Task 4 — Forward-evidence pipeline: verify and report (REPORT ONLY — no changes)

**Verified fact to build on:** `backend/organism/phase2_gate.py::load_forward_corpus()` reads **`trade_history.csv` filtered to rows strictly after FROZEN_AT** — i.e. the verdict corpus counts **real fills only**. The phase-9 `fw_momentum`/`fw_mean_reversion`/`fw_orb` shadow events (`phase9_shadow_only_no_order_path`) and the RC-1.5/ORB shadow scanners do **not** feed it; they feed `scripts/phase3_attribution_report.py` separately.

**Produce `reports/FORWARD_EVIDENCE_PIPELINE_NOTE.md`:**
1. Confirm the above by citing the exact call sites (gate reader, attribution reader, their file inputs).
2. Current per-strategy forward n since FROZEN_AT (expected: 0 across the board) and what the attribution report shows for the shadow strategies since 07-07 (n, gross, costed net per regime — run it).
3. State the structural consequence plainly: **in a chop tape where the frozen live path stands down (`direction_zero`), the verdict corpus accrues nothing, indefinitely.** Enumerate the three honest options *without implementing any*: (a) wait for trending/high-vol tape (zero-risk, slow — the plan's default); (b) pre-register an amendment that admits shadow-attribution outcomes as per-strategy evidence (methodology change → document + conscious re-freeze); (c) accept a longer horizon. **DECISION ITEM** for Marsel.

**Acceptance:** the note exists with real numbers and file:line citations; no code changed; drift-verify green.

---

## Task 5 — Entry-path stand-down: quantify, don't "fix" (REPORT ONLY)

**Verified state today:** 16 evidence events = 13 phase-9 shadow + 3 live `alpha` candidates each killed by `direction_zero`; scanner logs "no stocks passed initial filters"; regime mostly chop with high_vol intervals. This is the frozen system behaving as designed (`DROP_ML_FROM_GATE=True`; `_observable_direction` returns 0 in chop) — but 12 straight zero-fill sessions is also the reason Task 4's corpus is empty.

**Produce `reports/ENTRY_STANDDOWN_DIAGNOSIS.md` over the next 2–3 live sessions:**
1. Per session: regime mix (ticks per regime), candidate counts per kill reason (`direction_zero`, filter stages), and the universe picture on IEX — how many symbols clear the `$50k` `ORGANISM_MIN_AVG_DOLLAR_VOLUME` floor per hour, and whether the in-play universe is starved (this closes the deferred Task-0(b) validation from `docs/architecture/phase3_task0_data_decision.md`).
2. Answer one question with numbers: **on a trending/high-vol session, does the live path actually fire?** If yes, the system is healthy and merely waiting for its regime; if no even then, isolate which gate kills the candidates on that tape.
3. Touch nothing. The flag-gated symmetric-short paths (commit `2454ceb`), any gate loosening, universe expansion, or SIP re-subscription are all decision-surface/clock items → list them as **DECISION ITEMs** with expected effect, cost, and clock consequence.

**Acceptance:** memo with per-session tables; zero code/config changes; drift-verify green.

---

## Task 6 — Hygiene (quick)

1. Move the five `organism_brain/corrupt_head_20260707_*` dirs into `organism_brain/backups/quarantine/` (out of the live head; loader must not rescan them).
2. Resolve the boot-time `cumulative_pnl` drift (state −675.46 vs csv −673.31): document which is authoritative (csv, per the measurement-integrity rules), reconcile the state value via the existing reconciliation path, and log the correction — accounting hygiene, not a trading change.
3. Confirm no stray `overnight_positions.json`, and that ORB cache invalidation on boot behaved (07-22→07-23 session roll).

**Acceptance:** clean boot with zero quarantine events; reconciliation logged; drift-verify green.

---

## Completion

Write `reports/OPS_WORKORDER_COMPLETION_2026-07-XX.md`: per task — root cause found, fix shipped (commit SHAs), acceptance evidence (paste the proof lines), and the open DECISION ITEMs (Task 3 install steps; Task 4 evidence-admission question; Task 5 clock-sensitive levers). Run the full suite + `phase2_freeze.py --verify` one final time and paste both results. Cowork will red-team the completion report against the live brain state from this side.

**Definition of done for this work order:** the engine stays up without a human, saves its brain on cadence through restarts, never loses a sidecar again, and Marsel has one page telling him exactly which decisions only he can make — with the forward clock still intact at FROZEN_AT 2026-07-07T20:36:49Z.
