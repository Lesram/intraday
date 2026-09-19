# Work Order — Exit-Logic Experiment, Next Steps (for Claude Code)

**Author:** prior Cowork session (Opus 4.8), 2026-06-20. **Branch:** `refactor/lifespan-decompose`.
**Read first:** `EXIT_EXPERIMENT_RESULTS_2026-06-20.md`, `EXIT_LOGIC_EXPERIMENT_SPEC_2026-06-19.md`, `AUDIT_2026-06-09_FULL_PLATFORM.md` (§8 edge roadmap, §9 gates).

This is a precise, self-contained brief. Do the tasks in order. Each has a **Goal / Why / Where / Steps / Acceptance / Guardrails**. Don't improvise beyond scope; log side-findings as TODOs.

---

## Background (what already exists)

We are trying to recover the largest measured inefficiency in the live book: active exits (stop/trail/failure-to-follow) give back favorable excursion. Live history (567 trades, Mar 30–Jun 18, net **−$792**, PF 0.70): active exits −$1,760 vs passive +$968; 63% of positive-MFE trades close red; ~$1,425 of MFE given back.

A costed-replay A/B harness exists and runs the **real** engine:
- `scripts/edge_experiments.py` — arms run in subprocesses over cached minute bars (`artifacts/**/bars*.pkl`) under `ReplayEngine(cost_profile="realistic")` (next-open fills + auto spread + ≥1 bps slippage). Per-arm JSON now reports real `th_*` metrics read from each arm's `brain_dir/trade_history.csv`.
- `backend/organism/experimental/alt_exit_engine.py` — **non-production** `AltExitEngine` (policies `time_only`, `retracement`), swapped in **for replay only** via an env-gated monkeypatch in `run_arm` (rebinds `backend.organism.live_engine.AdaptiveExitEngine`). Inline exits (`ml_reversal`, `eod_flatten`, `pyramid_*`) are NOT affected — they bypass the exit engine.

**Tier-2 result (2026-06-20):** on the only cached bars (~Apr 15–30, **8 days, 34 trades**, where the current engine already nets +$160) the changes did not help: `time_only` ≈ baseline; `retracement` worse (+$87, t=1.42 — cut trending winners before the 18-bar learning horizon); `chop_standdown`/`combined` collapsed to 1 trade; **`wide_exits` was byte-identical to baseline (inert).** The test window was wrong/too small; two harness defects (below) must be fixed before the result means anything.

---

## Global guardrails (apply to ALL tasks)

1. **Do NOT edit the live execution path.** Specifically do not modify `backend/organism/live_engine.py` `_live_tick_inner` (heavily guarded; LOC baseline 2802 / ceiling 2805) or the live entry/exit dispatch. All experiment behavior goes through replay-only seams (env flags, `AltExitEngine`, monkeypatches in `scripts/`).
2. **Structural guards:** ~62 test files pin source text via `inspect.getsource` markers (see `AUDIT_2026-06-09_FULL_PLATFORM.md` §4). If you must change a guarded source file (e.g. `adaptive_exits.py`), update the corresponding guard markers **in lockstep with written justification**, and keep default (env-unset) behavior byte-identical.
3. **Costed fills only.** Always use `cost_profile="realistic"`. Never present same-bar-close / zero-cost runs as evidence (the harness self-labels these as OPTIMISTIC).
4. **Default-safe.** Any new env var must default to current production behavior when unset.
5. **Verify before committing:** `bash scripts/verify_live_engine_seam.sh && bash scripts/verify_promotion_gate.sh && bash scripts/verify_lifespan_refactor.sh`. Use conventional commits (`refactor(...)`, `fix(...)`, `test(...)`, `feat(...)`).
6. **No live capital / no deploy.** This is offline research toward Gate 2; the platform is not go-live (see `GO_LIVE_READINESS_2026-06-19.md`).

---

## Task A — Re-run on a representative bar corpus (the test window was wrong)

**Goal:** get a Gate-2-meaningful replay sample (≥60 sessions of trades, varied regimes) and re-compare `baseline` vs `time_only` vs `retracement`.

**Why:** the cached corpus is 8 benign April days / 34 trades. `scripts/find_losing_sessions.py` (already written, run it) shows the live book lost across Apr–May. **Caveat the replay re-runs the *current* engine, so it will NOT reproduce historical live losses** — the comparison is forward-looking (current engine over varied regimes), which is what we want; do not expect to "see the −$792".

**Where:** `scripts/edge_experiments.py` (`collect_cached_bars` at ~109, `run_arm` at ~158, `ReplayEngine.from_alpaca` at `backend/organism/replay_simulator.py:~739`). `scripts/find_losing_sessions.py`. Universe is 22 symbols (do not change it).

**Steps:**
1. Run `./venv/bin/python scripts/find_losing_sessions.py` → `artifacts/losing_sessions.json`. Note the dated span (Mar 30–Jun 18) and the 22-symbol set.
2. Build a broad corpus — pick one:
   - **(a) from_alpaca (preferred if paper creds available):** add an `edge_experiments.py` option to drive `ReplayEngine.from_alpaca(symbols, start, end, timeframe="1Min", cost_profile="realistic", slippage_bps=1.0)` for a date range covering the full live span (or ≥2 chop-heavy months), instead of `collect_cached_bars()`. Keep `collect_cached_bars` as the default.
   - **(b) cache pkls:** fetch & write `artifacts/<window>/bars.pkl` (dict[symbol→DataFrame with timestamp/close/…]) for the broad window so `collect_cached_bars` picks them up.
3. Re-run **only** `baseline,time_only,retracement` (defer `wide_exits`/`chop_standdown`/`combined` until Task B): `./venv/bin/python scripts/edge_experiments.py --arms baseline,time_only,retracement`.
4. Analyze `report.json` + per-arm `th_*`: net, expectancy, **t-stat of per-trade pnl**, PF, win, MFE-giveback, and **split into two non-overlapping sub-periods** for stability (Gate 2).

**Acceptance:** a report over **≥~300 trades / ≥60 sessions**, with a clear table (baseline vs each arm: net, expectancy, t-stat, PF, giveback, sub-period stability) and a one-line verdict per arm against Gate-2 thresholds (expectancy>0 at t≥2 after costs, PF≥1.3, stable across sub-periods).

**Log as a separate TODO (do not fix here):** 142/567 live trades have a **blank `closed_at`** (−$945, the bulk of losses) — a measurement-integrity gap. Trace where `closed_at` is written (`TradeRecord` at `backend/organism/continuous_learner.py:~208`; populated in `backend/organism/live_engine.py:~6374`; persisted by `brain_persistence.py`) and file a ticket; it breaks any per-session P&L attribution.

---

## Task B — Fix the inert exit-parameter knobs (`wide_exits` == baseline)

**Goal:** make the `ORGANISM_EXIT_*` exit-parameter overrides actually bind, so parametric exit arms (wider stops/trails/holds) can be tested.

**Why (root cause, confirmed):** `backend/organism/adaptive_exits.py` defines **hardcoded class dicts** `REGIME_STOP_ATR`, `REGIME_TP_R`, `REGIME_TRAIL_ATR`, `REGIME_MAX_BARS`, `REGIME_DECAY_START` (lines ~140–187), each WITH a `chop` key. The engine selects via `self.REGIME_STOP_ATR.get(regime, self.atr_multiplier)` (and siblings) at lines ~322, 326, 378–379, 509, 585, 625, 733. The `ORGANISM_EXIT_*` env scalars (read in `for_timeframe`, line ~232) only set the **fallback** scalars (`self.atr_multiplier`, `self.max_bars_held`, `self.time_decay_start`, …) — which are never reached for any regime present in the dict. Replay windows are ~100% `chop`, so the knobs never bind ⇒ `wide_exits` is byte-identical to `baseline`.

**Where:** `backend/organism/adaptive_exits.py` (`for_timeframe` ~232; the REGIME dicts ~140–187).

**Steps:**
1. In `for_timeframe` (or `__init__`), after building the instance, apply env **multipliers/overrides to the regime dicts** (not just the scalars). Suggested new env vars (all default to 1.0 = no change):
   - `ORGANISM_EXIT_STOP_ATR_MULT` → scales every `REGIME_STOP_ATR` value
   - `ORGANISM_EXIT_TRAIL_ATR_MULT` → scales `REGIME_TRAIL_ATR`
   - `ORGANISM_EXIT_MAX_BARS_MULT` → scales `REGIME_MAX_BARS` (0 stays 0 = "no time limit")
   - `ORGANISM_EXIT_DECAY_START_MULT` → scales `REGIME_DECAY_START`
   - Make these **instance copies** (don't mutate the class dicts — that would leak across arms/instances).
2. Update the `wide_exits` and `combined` arms in `scripts/edge_experiments.py` to use the new `*_MULT` vars (e.g. `ORGANISM_EXIT_STOP_ATR_MULT=1.6`, `ORGANISM_EXIT_MAX_BARS_MULT=2.0`).

**Acceptance:**
- A unit test: with `ORGANISM_EXIT_STOP_ATR_MULT=2.0`, `AltExitEngine`/`AdaptiveExitEngine.for_timeframe("1Min")` yields an instance whose effective chop stop-ATR is doubled, and **unset ⇒ unchanged** from current values.
- In replay (Task A corpus), `wide_exits` now **diverges** from `baseline` (different trade set / pnl). Confirm it is no longer inert.

**Guardrails:** `adaptive_exits.py` is core and likely guarded — grep `tests/` for `getsource`/`adaptive_exits`; update markers in lockstep with justification. Default behavior (env unset) must be identical.

---

## Task C — Pyramider lever (the untouched bleed)

**Goal:** quantify, then design a replay test for, the pyramid-cut behavior — the single biggest live bleed bucket the exit experiment **cannot** reach.

**Why:** `pyramid_cut*` exits are inline in `live_engine.py` `_live_tick_inner` (reason built at ~3753; chop-suppression gate ~3725–3745), NOT in the exit engine — so `AltExitEngine` does not touch them. Tier-1 attributed ~$425 of recoverable giveback to pyramid cuts; in the Tier-2 replay, pyramid cuts still appeared among the worst trades. Audit §3.5 also flags that pyramid **adds** skip the full entry-gate set and can collide idempotency keys.

**Where:** `backend/organism/pyramider.py` (the `Pyramider` and its `close_partial`/cut actions); `live_engine.py` pyramid block (~3710–3765); `trade_history.csv` (`exit_reason` like `pyramid_cut_full_at_-1.7R`).

**Steps:**
1. **Quantify** from `organism_brain/trade_history.csv`: all `pyramid_cut*` trades — n, net, MFE-giveback, regime mix, and the distribution of the `-N.NR` cut thresholds. (Confirm the ~$425 and where it concentrates — expect chop.)
2. **Read** `pyramider.py` + the inline block; identify the cut decision and whether any existing env/config flag already gates it (grep `ORGANISM_*` pyramid flags, governance config at `live_engine.py:~7460`).
3. **Design (offline)** a replay-only arm that softens pyramid cuts in chop (e.g. wider cut threshold, or route adds through `_passes_entry_gates` per §3.5) — implemented like `AltExitEngine`: prefer an **env flag the engine already reads** or a **monkeypatch on `Pyramider` in the experiment runner**, NOT an edit to `_live_tick_inner`.
4. Add a `pyramid_soft` arm to `scripts/edge_experiments.py` and run it against the Task-A corpus.

**Acceptance:** a quantified pyramid-cut analysis (markdown or notebook cell) + a `pyramid_soft` replay arm with a baseline comparison and a recommendation (worth pursuing live-shadow or not), all offline, `_live_tick_inner` untouched.

---

## Reference map (file → what's there)

- Exit decisions: `backend/organism/adaptive_exits.py` — `check_exit` (401), `create_exit_levels` (287), `for_timeframe` (232), REGIME dicts (140–187).
- Engine wires exit engine: `backend/organism/live_engine.py:620` (`self.exit_engine = AdaptiveExitEngine.for_timeframe(...)`).
- Inline exits (leave alone): `ml_reversal` (`live_engine.py:3308–3333`), `eod_flatten` (3406–3438), `pyramid_*` (3710–3765).
- Replay harness: `backend/organism/replay_simulator.py` — `ReplayEngine.run` (609, builds engine at 642), `from_alpaca` (~739), `SimulatedBroker` cost model (~69), `cost_profile="realistic"`.
- Experiment runner: `scripts/edge_experiments.py` — `ARMS`, `run_arm` (monkeypatch + `_trade_history_metrics`), `collect_cached_bars`.
- Experimental exit policies: `backend/organism/experimental/alt_exit_engine.py`.
- Trade record schema: `closed_at, exit_reason, mfe, mae, pnl, regime_at_entry, bars_held_at_exit, …` (`continuous_learner.py:~208`).
- Gates & status: `AUDIT_2026-06-09_FULL_PLATFORM.md` §8–9, `GO_LIVE_READINESS_2026-06-19.md`.
