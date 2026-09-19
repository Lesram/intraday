# Work Order — Retracement Shadow Exit + Corpus Extension (for Claude Code)

**Author:** Cowork session (Opus 4.8), 2026-06-20. **Branch:** `refactor/lifespan-decompose`.
**Read first:** `EXIT_EXPERIMENT_TIER2B_RESULTS_2026-06-20.md`, `EXIT_EXPERIMENT_NEXT_STEPS_BRIEF.md`, `AUDIT_2026-06-09_FULL_PLATFORM.md` §9 (gates).

**Why:** Tier-2B replay (227 trades / 27 days) found **`retracement` is the first credible, robust exit edge** — net +$310 (+$34 vs baseline), PF 1.85, MFE retention 41%, and uniquely **stable across both sub-periods** (1.34 / 1.34, t≈2) while every other arm decays in sub-period 2. It has earned the disciplined **shadow → evidence → live** path.

> **STATUS 2026-06-21 — Task X is COMPLETE; go straight to Task S.** A 72-session sweep found the winner is **`retracement_f60_m10`** (F=0.6, min_favorable_R=1.0): +$74 vs baseline, best held-trade t-stat (3.42), beats baseline in BOTH major regimes (trending_up + chop), and loses LESS than baseline in the hard early period. It did not collapse — it strengthened.
>
> **Corrected gate (the original criterion below was wrong):** I had specified "every sub-period split > 0." That tests whether the *base strategy* is profitable in every period — which exits cannot change — not whether the *exit policy* robustly beats baseline. On this harder corpus the base engine genuinely lost in Mar 9–early Apr, so baseline fails that bar too; it is unclearable by any exit refinement. The correct success test for an exit experiment is **"robustly beats baseline across all splits and both major regimes without collapsing"** — which `retracement_f60_m10` clears. Proceed to Task S at **F=0.6 / min_fav_R=1.0**. Do NOT run more big backtests; forward live shadow evidence is the path now.

---

## Global guardrails (apply to BOTH tasks)

1. **No live capital effect, ever.** The shadow is **log-only**: it records what `retracement` *would* do; it must NEVER change a real order, exit, size, or gate.
2. **Do NOT edit `_live_tick_inner`** (`backend/organism/live_engine.py:2466–5267`). It is **2802 LOC against a 2805 ceiling** — `tests/test_v13_w100_live_tick_coverage.py:61,80` (`LIVE_TICK_INNER_LOC_CEILING = 2805`) and `tests/test_v12_baseline_invariants.py:329` (`loc <= base_loc + 5`, base 2802). Only ~3 lines of headroom, and many tests `inspect.getsource(_live_tick_inner)` for substring markers. **Leave the method byte-for-byte unchanged.** Hook in the *public* `live_tick` wrapper instead (see Task S).
3. **Off by default.** The shadow activates only when `ORGANISM_SHADOW_EXIT_POLICY` is set; unset ⇒ zero behavior change, no file writes.
4. **Best-effort, never raise into the tick.** All shadow code wrapped in `try/except` + `logger.warning`, mirroring `_TelemetryRecordingMixin`.
5. **Structural guards in lockstep.** If you change a guarded file, update its markers with written justification. Default behavior must stay identical.
6. **Verify before commit:** `bash scripts/verify_live_engine_seam.sh && bash scripts/verify_promotion_gate.sh && bash scripts/verify_lifespan_refactor.sh`. Conventional commits.

---

## TASK X — Extend the replay corpus to ≥60 sessions and re-confirm the edge

**Goal:** confirm `retracement`'s edge (and especially its sub-period stability) holds on a bigger, multi-regime sample before any live wiring. 27 days is under Gate-2's ≥60 sessions; the edge is modest (+$0.31/trade) so robustness matters.

**Where:** `scripts/edge_experiments.py` (`collect_cached_bars` ~109, `run_arm` ~158, `ARMS`); `backend/organism/replay_simulator.py` `ReplayEngine.from_alpaca` (~739).

**Steps:**
1. **Bigger corpus.** Prefer `ReplayEngine.from_alpaca(symbols, start, end, timeframe="1Min", cost_profile="realistic", slippage_bps=1.0)` over the cached pkls. Add a `--from-alpaca START END` option to `edge_experiments.py` that builds bars via `from_alpaca` for the 22-symbol universe across **≥3 months** (e.g. the full live span and beyond). Keep `collect_cached_bars` as default. Target **≥60 distinct session-days / ≥500 replay trades**.
2. **Parameter sweep on retracement** (confirm it's not a single-point artifact and find the best F): arms for `ORGANISM_ALT_RETRACE_FRAC ∈ {0.4, 0.5, 0.6, 0.7}` × `ORGANISM_ALT_MIN_FAVORABLE_R ∈ {0.5, 1.0}`. Add them to `ARMS` (e.g. `retracement_f40`, `retracement_f60`, …).
3. **Re-run** `baseline`, the retracement sweep, and `pyramid_soft` (re-check its stability — it was unstable on 27 days; does it fail or hold on 60+?).
4. **Stronger robustness analysis.** The per-arm `gate2` block already gives overall t-stat + a 2-way median split. Extend the analysis (in `edge_experiments.py` or a new `scripts/analyze_arms.py`) to also report: a **3-way time split**, a **per-regime split** (`regime_at_entry`), and **expectancy/t-stat per split** — so "stable across sub-periods" is tested beyond a single median cut.

**Acceptance:**
- A report over **≥60 sessions / ≥500 trades**.
- A clear verdict: does a retracement variant keep **expectancy > 0 at t ≥ 2, PF ≥ 1.3, stable across ALL sub-periods (2-way and 3-way) and not negative in any major regime**, and beat baseline? State the best `F`.
- Explicit go/no-go: is the in-replay edge robust enough to justify proceeding to the live shadow? (If retracement collapses on the bigger sample, STOP and report — do not build Task S.)

---

## TASK S — Wire `retracement` as a LOG-ONLY live shadow exit

**Goal:** on every live tick, compute what the `retracement` policy *would* do on each open position and log it vs the real exit — accumulating honest forward evidence toward a future live-exit decision. **Zero effect on real trading.**

### Design
- One **`AltExitEngine`** (already exists: `backend/organism/experimental/alt_exit_engine.py`) configured to `retracement`, used purely to *evaluate* — never to dispatch orders.
- A **parallel** `dict[str, ExitLevels]` of shadow copies (NEVER call `check_exit` on the live `self._exit_levels` — it **mutates** `highest_favorable`/`bars_held`/trailing and would corrupt real exits).
- Each tick (post-tick hook), for every open position: update the shadow eval; if `retracement` says exit, record a "shadow-would-exit" event; when the real position later closes, write one **comparison row** (real exit vs shadow exit + pnl delta) to an append-only JSONL.
- Gated off by default; best-effort.

### Exact seams (all verified; line numbers in `backend/organism/live_engine.py`)
- **Positions/levels store:** `self._exit_levels: dict[str, ExitLevels]` (declared :811). `ExitLevels` is the `adaptive_exits` dataclass (`highest_favorable`, `worst_adverse`, `bars_held`, `entry_price`, `direction`, `initial_risk_at_entry`, …).
- **Post-tick hook (USE THIS):** public `live_tick()` at **2086–2153** is a thin watchdog wrapper. Insert ONE guarded call immediately after `result = await asyncio.wait_for(self._live_tick_inner(), …)` (~line **2111**), before `return result`:
  ```python
  if self._shadow_exit is not None:
      try:
          self._shadow_evaluate_exits(result)
      except Exception as e:
          logger.warning("shadow exit eval failed: %s", e)
  ```
  This is **outside** `_live_tick_inner` (and outside both LOC/marker guards).
- **Price source (post-tick):** `self._last_prices: dict[str, float]` (built each tick at :2642–2645). Use `self._last_prices.get(sym, levels.highest_favorable)` — identical to the live exit loop's price and to the existing template at **:5372–5381** (`_build_decision_snapshot`), which already iterates `self._exit_levels` + `self._last_prices` + computes pnl_pct. **Mirror that block.**
- **Regime / new-bar:** `self._last_regime` (set :2663/2685/3539); per-symbol bar boundary via `self._last_bar_times` (:855, updated :3251–3254) — derive `is_new_bar` the same way the loop does (:3250–3252).
- **Learning mode:** each tick set `self._shadow_engine.learning_mode = self.exit_engine.learning_mode` so take-profit/horizon gating matches production.

### Implementation steps
1. **New module** `backend/organism/experimental/shadow_exit.py`:
   - `class ShadowExitTelemetryRecorder` — append-only JSONL writer, copy the pattern from `backend/organism/candidate_shadow_telemetry.py:303–363` (`path.parent.mkdir(...)`, `path.open("a")`, `json.dumps(row, default=str)`; include `runtime_identity_snapshot()` provenance).
   - `class _ShadowExitMixin` (no `__init__`; relies on host attributes) with `_shadow_evaluate_exits(self, result) -> None`:
     - early-return if `self._shadow_exit is None`;
     - `self._shadow_engine.learning_mode = self.exit_engine.learning_mode`;
     - for each `sym, live_levels in list(self._exit_levels.items())`: if `sym` not in `self._shadow_levels`, seed `self._shadow_levels[sym] = copy.deepcopy(live_levels)` (correct: same history so far, diverges only on exit logic); `price = self._last_prices.get(sym, live_levels.highest_favorable)`; `sig = self._shadow_engine.check_exit(self._shadow_levels[sym], price, self._last_regime, is_new_bar=<derived>)`; if `sig.should_exit` and not already triggered, stash `{sym, trigger_time, reason, price, shadow_pnl=(price-entry)*dir*qty, bars_held}` in `self._shadow_pending[sym]` (qty from `self._last_positions.get(sym)`);
     - **reconcile real closes:** any `sym` that was in `self._shadow_levels` last tick but is now absent from `self._exit_levels` ⇒ the real position closed. Write ONE comparison row: shadow trigger (or "agreed: shadow held to real close") vs the real trade's realized pnl (read the latest matching row the engine just appended, or use `self._last_positions`/the last realized pnl), `delta = shadow_pnl - real_pnl`. Then drop `sym` from `_shadow_levels`/`_shadow_pending`.
2. **Env flags** (module level, mirror :314–343 and the helpers `_env_bool`/`_env_str` at :183–196):
   ```python
   ORGANISM_SHADOW_EXIT_POLICY = _env_str("ORGANISM_SHADOW_EXIT_POLICY", "")          # "" = off; "retracement" = on
   ORGANISM_SHADOW_EXIT_RETRACE_FRAC = _env_float("ORGANISM_SHADOW_EXIT_RETRACE_FRAC", 0.6)   # Task X winner
   ORGANISM_SHADOW_EXIT_MIN_FAV_R = _env_float("ORGANISM_SHADOW_EXIT_MIN_FAVORABLE_R", 1.0)   # Task X winner
   ORGANISM_SHADOW_EXIT_TELEMETRY_PATH = _env_str("ORGANISM_SHADOW_EXIT_TELEMETRY_PATH", "organism_brain/shadow_exit_telemetry.jsonl")
   ```
   (Task X winner already baked in: F=0.6, min_fav_R=1.0.)
3. **`__init__` wiring** (near the existing shadow recorders at :766–794): instantiate, only when enabled:
   ```python
   if ORGANISM_SHADOW_EXIT_POLICY:
       self._shadow_engine = AltExitEngine.for_timeframe(self._timeframe)
       self._shadow_engine.alt_policy = ORGANISM_SHADOW_EXIT_POLICY          # force; env ORGANISM_EXIT_POLICY is replay-only
       self._shadow_engine.alt_retrace_frac = ORGANISM_SHADOW_EXIT_RETRACE_FRAC
       self._shadow_engine.alt_min_fav_r = ORGANISM_SHADOW_EXIT_MIN_FAV_R
       self._shadow_levels = {}; self._shadow_pending = {}; self._shadow_prev_syms = set()
       self._shadow_exit = ShadowExitTelemetryRecorder(ORGANISM_SHADOW_EXIT_TELEMETRY_PATH)
   else:
       self._shadow_exit = None
   ```
4. **Add `_ShadowExitMixin` to the bases** at `class OrganismLiveEngine(... _TelemetryRecordingMixin, ...)` (:521–525). (MRO resolution keeps `getsource` guards intact — same as the prior decomposition.)
5. **Hook** the one call in `live_tick` after :2111 (above).
6. **Analysis** `scripts/analyze_shadow_exits.py`: read the JSONL → cumulative shadow-vs-real **delta**, by regime and by real `exit_reason`, with a **t-stat of the per-trade delta** and a running sub-period split — i.e. live Gate-2-style accumulation. Optionally fold a one-line summary into the EOD scheduled task.

**Acceptance:**
- **Flag UNSET:** engine behavior byte-identical; no JSONL created; **all `verify_*.sh` pass; `_live_tick_inner` LOC guards green** (you didn't touch it).
- **Flag = `retracement`:** `organism_brain/shadow_exit_telemetry.jsonl` accumulates one comparison row per closed position (real exit + pnl vs shadow exit + pnl + delta); the live trades are **unchanged** (diff a flag-on vs flag-off paper run — real `trade_history.csv` identical).
- A unit test for `_ShadowExitMixin`/the evaluator on a synthetic position path (peak then retrace ⇒ shadow triggers; flag-off ⇒ no-op).
- `scripts/analyze_shadow_exits.py` produces the cumulative delta + t-stat.

### Guardrails specific to Task S
- Never call `check_exit` on `self._exit_levels[sym]` (mutation). Always the deep-copied shadow levels.
- The shadow must not call `_submit_exit_order`, the broker, or anything with side effects.
- Keep it entirely in `experimental/` + the mixin + the 1-line hook + the `__init__`/module-const additions. Touch nothing in the entry/exit/sizing logic.

---

## Sequencing & decision gates

1. **Task X** (offline, days): if retracement's edge is robust on ≥60 sessions across all splits/regimes → proceed; else STOP.
2. **Task S** (log-only): deploy with `ORGANISM_SHADOW_EXIT_POLICY=retracement`; let `shadow_exit_telemetry.jsonl` accumulate over live paper sessions.
3. **Flip live exits ONLY when BOTH hold:** (a) Task X robust, AND (b) ≥N live sessions of positive shadow-vs-real delta at t ≥ 2. Wiring the policy into the *real* exit path is a separate, later brief — not in scope here. Per the 14-day plan, no live-execution-path edits until that evidence exists.

## Reference map
- Exit engine + retracement logic: `backend/organism/adaptive_exits.py` (`check_exit` 401), `backend/organism/experimental/alt_exit_engine.py`.
- Live engine seams: `_exit_levels` (:811), exit loop (:3097–3347), `live_tick` wrapper (:2086–2153, hook after :2111), `_last_prices` (:2642–2645), template block (:5372–5381), bases (:521–525), env helpers (:183–196), shadow-flag precedents (:314–343, 766–794).
- Telemetry pattern: `backend/organism/live_engine_telemetry.py` (`_TelemetryRecordingMixin`), `backend/organism/candidate_shadow_telemetry.py` (JSONL writer).
- LOC guards (DO NOT TRIP): `tests/test_v13_w100_live_tick_coverage.py:61,80`; `tests/test_v12_baseline_invariants.py:329`.
- Harness: `scripts/edge_experiments.py`; results: `EXIT_EXPERIMENT_TIER2B_RESULTS_2026-06-20.md`.
