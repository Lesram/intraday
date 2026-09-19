# Full Platform Audit — Intra Trading System
**Date:** 2026-06-09 · **Scope:** full independent re-audit (architecture, risk controls, ML pipeline, strategies) + edge evidence (live trade history, fresh out-of-sample backtests) · **Goal:** assess readiness for live capital and locate "the edge."

---

## 1. Executive verdict

**Do not go live yet.** The platform is a mature, safety-conscious *framework*, but this audit found (a) several new, serious defects not in the 2026-06-08 audit — including an **unauthenticated HTTP endpoint that can submit live orders while bypassing every organism safety gate** — and (b) **direct quantitative evidence that no strategy currently has a deployable edge**:

- **556 live paper trades: −$771 total, 33.1% win rate, profit factor 0.71.** The recent era (414 trades, Mar 30–May 20) is +$173 with t-stat 0.76 — statistically indistinguishable from zero. The last 30 days: 259 trades, **+$2.06 total**.
- Signal quality is noise: direction accuracy 33.1%, corr(confidence, correct) = **0.023**, corr(predicted_return, actual_return) = **−0.020**. Confidence quintiles show no monotonic relationship to win rate.
- A fresh out-of-sample replay of the mean-reversion strategy (798 trades, 23 cached sessions, exact production rules) shows **+2.2bps/trade gross** but **−3.8bps/trade after 3bps/side costs** (PF 0.67, 21 of 23 days negative). **The gross edge is smaller than round-trip transaction costs.**
- The production model-promotion path (`background_trainer.py`) **does not perform the same-holdout comparison** the system's own design documents require — it can promote models against a stale baseline.

The honest summary: the engineering is genuinely good in places (causal bar truncation, lifespan isolation, exploration blocking), the risk scaffolding is mostly real, but **the alpha layer measurably does not work**, and the system has live-money defects that must be fixed regardless. Section 8 gives the edge roadmap; Section 9 gives the quantitative go-live gates.

---

## 2. Method

Four independent code audits (architecture, risk controls, ML/leakage, strategies) run against source — prior audit docs used only as claim lists to verify, not as evidence. Trade history analyzed from `organism_brain/trade_history.csv` (564 rows; 8 reconciliation artifacts excluded). Fresh backtest: production mean-reversion rules re-implemented exactly from `mean_reversion_scanner.py` and replayed over all cached minute bars in `artifacts/` (408 symbol-days, 2026-04-10 → 2026-05-20), with conservative same-bar stop-first resolution and three fill/cost scenarios. Key claims spot-verified directly in source before publication; two agent findings corrected against the deployed `.env` (noted inline).

---

## 3. Critical defects (fix before anything else)

### 3.1 Unauthenticated live-order endpoint — CRITICAL
`POST /multi-strategy-live/run-once` (`backend/api/routes/multi_strategy_live.py:31-36`) has **no auth dependency** — only `Depends(get_order_service)`. Verified directly. It submits orders via `order_service.plan_and_submit` (`services/multi_strategy_live_runner.py:240`) through a path that never touches `_passes_entry_gates`, the `_authorize_live_entry_order` governor, the EOD block, the Kelly sizer, or the organism kill switch (`POST /organism/halt` only halts the organism). Any caller who can reach the API can trade arbitrary symbols. **Fix: add `require_admin`, or delete the route; extend the kill switch to cover this path.**

### 3.2 Model promotion in production compares different holdout windows — CRITICAL
The synchronous path is honest: `_validate_new_model` (`continuous_learner.py:491-556`) re-scores the old model on the new model's identical validation set and disables relative promotion when same-holdout fails (`:544-554`). But the **production** route is the background trainer (`background_trainer.py`, self-described "primary evolution route"), which reconstructs the old model from a **stored metrics dict** (`:143-162`) and calls `acceptance_gate(metrics, old_metrics=old_metrics_obj)` (`:164-167`) with `allow_relative` left at its default `True` (`continuous_learner.py:43`). Verified directly. The old model's artifacts are never sent to the worker, so same-holdout comparison is structurally impossible there. A new model can be promoted by beating a stale, different-period baseline — exactly the "great in validation, loses live" mechanism. **Fix: ship old clf/reg to the worker for true same-holdout eval, or set `allow_relative=False` in the background path.**

### 3.3 Risk breakers default to disabled — HIGH (config-dependent)
`MAX_NOTIONAL_PER_TRADE` and `MAX_DAILY_LOSS` default to **0.0 = disabled** (`live_engine.py:235-236`), and the breaker logic only runs `if MAX_DAILY_LOSS > 0` (`:2648`). The deployed `.env` does arm them (`ORGANISM_MAX_DAILY_LOSS=5500`, `ORGANISM_MAX_NOTIONAL=2000`) — but 5500 on ~$111.5k equity is a **4.9% daily-loss tolerance**, far above the ~0.2% median trade notional impact and excessive for go-live. Also `trading_execution_mode` maps `paper`/`live` → `execute` by default (`config/settings.py:458`): a missing env var means *send orders*, not *stand down*. **Fix: make unsafe defaults fail-closed (refuse to start live with breakers at 0); set daily loss ≤ 1% of equity for Stage 1.**

### 3.4 EOD flatten has no failure escalation — HIGH
Entry block 15:45, flatten 15:58–16:00, pending-cancel — all present (`live_engine.py:2265-2291, 3124-3178`). But on broker reject/outage/partial fill the symbol is re-queued with a 3-tick TTL, and past 16:00 retries stop with only `logger.warning`. An un-flattened position carries overnight gap risk silently. **Fix: alert (page/Slack) + persistent retry + next-open forced exit on any position open past 16:00.**

### 3.5 Pyramid adds skip the full entry gate set — MEDIUM
Adds (`live_engine.py:3368-3416`) check only `_symbol_banned` and `_entries_blocked`, skipping liquidity/fitness/sector gates, despite a comment claiming otherwise. Entry-vs-pyramid idempotency keys can also collide same-tick (`:5571-5584` vs `:3409` — key omits intent/side/qty). **Fix: route adds through `_passes_entry_gates`; include intent in the idempotency key.**

### 3.6 Live brain corruption events — HIGH (operational)
Five `corrupt_head_20260609_*` snapshots sit inside the **live** `organism_brain/` — brain-state corruption/recovery events dated the day before this audit. Root-cause before live: `.brain.lock` is the only concurrency guard on 256MB of mutable state.

---

## 4. Architecture & structure (independent re-verify)

Confirms the 2026-06-08 audit's broad shape, with corrections:

- **Monolith confirmed, size corrected:** `live_engine.py` is **7,180 lines** (not ~7,900), one class + 5 mixins, 53 methods, ~55 intra-backend imports, 27 inbound importers. Single point of failure for the entire trading path; nothing in it unit-testable in isolation. Decomposition seams (Entry/Exit orchestrators, LearningManager, persistence, feature feeder) remain the right plan.
- **Dual independent settings systems — worse than previously reported:** `config/base_settings.py` (1,755 lines) and `config/settings.py` both expose `get_settings()`; `AppSettings` reads `os.getenv` directly (`settings.py:367-462`) rather than delegating — the two trees can diverge silently. Six distinct settings entry symbols; three config directories; four env files.
- **Shadowed dead modules:** flat `backend/database.py` and flat `backend/infra/repositories.py` are unreachable (package shadows the module — verified via `find_spec`); prior audit's "2 importers" was wrong, the real number is zero. Three overlapping DB-config implementations. `brokers/` and `optimization/` are empty scaffolding.
- **Build health good:** all 304 backend files compile; pytest config sane. `requirements.txt` floors diverge badly from `requirements.lock` pins (e.g. `fastapi>=0.100` vs `==0.129`) — lock must be authoritative for deploys.
- **Refactor constraint:** 62 test files pin source text via `inspect.getsource` markers. Any decomposition must update these guards in lockstep (they will fail loudly, which is by design).
- **Repo hygiene:** `organism_brain_archive/` is 5.7GB; 30+ point-in-time reports at root. Cosmetic, but it buries living docs.

## 5. Risk controls — invariant verdicts

| Invariant | Verdict | Evidence |
|---|---|---|
| No live exploration execution | **Enforced** | execution block removed; log-only (`live_engine.py:4709-4713`); flag default False (`:232`) |
| Learning mode: ML out of gate, fixed ATR-dollar sizing | **Enforced** | `DROP_ML_FROM_GATE=True` (`:307`); 0.10%-equity risk + 5% notional caps (`kelly_sizer.py:578-592`) |
| All entries share hard gates | **Partial** | five organism paths do (`:3616-4292` → `:4586`); **pyramids and multi-strategy path do not** (§3.1, §3.5) |
| EOD block/flatten | **Partial** | present but no failure escalation (§3.4) |
| Evolution freeze ≥300 trades | **Enforced** | `background_trainer.py:200-203, 639-640`; restore-path honors freeze (`live_engine.py:1306-1326`) |
| Circuit breakers | **Partial** | position-count (8), sector cap, symbol bans, 10%-per-position and 0.25%-equity-ATR caps all pre-submission; dollar breakers env-dependent (§3.3) |
| Kelly bounds | **Enforced** | breakout bonus capped 2.0× then clamped by the 10% and ATR-risk caps (`kelly_sizer.py:544, 603-610, 696-714`) |
| Order idempotency | **Partial** | keys exist but collide entry-vs-pyramid same-tick (§3.5); silent market-order fallback on stale quotes (`:5602-5603`) |
| Live/paper separation + kill switch | **Partial** | mode override is process-local (`trading_execution_mode.py:6-8`); halt doesn't cover multi-strategy path |
| API auth on mutating routes | **Partial** | orders/organism/models routes properly gated; **one unauthenticated order route** (§3.1) |

## 6. ML pipeline — structurally unable to prove an edge

The good: feature engineering is largely causal (no `shift(-N)` into features — `create_leads` is hard-guarded, `feature_engineering.py:348-353`; trailing windows throughout; SPY alignment reindex-by-timestamp, `ml_features.py:277-313`); per-symbol temporal splits (`ml_signal.py:765-803`); rollback on rejection is real.

The decisive problems, beyond §3.2:

- **No gate measures realized predictive power.** Acceptance checks direction-accuracy, precision, calibration *monotonicity* — all satisfiable by a no-edge model. The project's own forensics (182 live trades) found corr(confidence, direction) ≈ 0.056 and **anti-predictive high-confidence tails (−0.112)**; nothing in the live loop monitors this. My refresh on all 556 trades: corr = **0.023**. The signal is noise and the pipeline cannot detect that.
- **No purge/embargo** between train/val (hard index cut; the boundary bar leaks one label per symbol per split — grows with horizon).
- **Survivorship in training universe:** symbols enter training via performance-rotated selection (`market_scanner.py:87-88`) — recent winners are over-represented in both training and allocation.
- **Retrained artifacts bypass the shadow→canary `PromotionController`** (`promotion.py` stages policy weights only); new model pickles swap directly into live inference (`background_trainer.py:585-596`).
- Secondary paths: `ensemble_model.py` fits its scaler on full data before TimeSeriesSplit (`:516-523`) — classic leakage, though not the organism's primary model. Self-evolution can re-enable shorts from a 10-trade EMA (`self_evolution.py:928-991`) and scale regime sizing to 1.5× with no portfolio-level recheck.

## 7. Strategy-by-strategy edge assessment

**Configuration note (corrected from agent finding):** `LIVE_TIMEFRAME` *defaults* to `1Day` (`live_engine.py:199`) which would leave every intraday scanner dormant — but the deployed `.env` sets `1Min`, so the strategies are active in your deployment. The hazard is that nothing asserts the timeframe matches strategy requirements; an env regression silently turns the intraday book off. Add a startup assert.

- **Alpha composite (the live book): no edge as implemented.** With ML zeroed out (correctly, given anti-predictiveness), what remains is hand-tuned momentum/breakout heuristics with stacked magic multipliers (`alpha_scanner.py:230-249, 307-309`). Live evidence (all 556 trades are this book, long-only): PF 0.71 lifetime, ~breakeven recently. Exit autopsy: **stop_loss + failure_to_follow + trailing_stop = −$1,115** while passive exits (max_holding_period, ml_reversal, horizon_timeout, eod) = **+$739** — the system makes money by *holding* and loses it on its *active* exits; 63% of trades that reached positive MFE still closed negative (median giveback 1.16). Regime cells: chop (n=364) ≈ $0; trending_up + high_vol positive but tiny n (36 trades, +$184).
- **Mean-reversion: no deployable edge — costs exceed gross edge.** Fresh OOS replay, exact production rules, 798 trades / 23 sessions: gross +2.2bps/trade (t=2.27), **net −3.8bps/trade at 3bps/side** (PF 0.67; 21/23 days negative). Breakeven cost is ~1.1bps/side — thinner than the half-spread on most of the universe. Its parameters (4.0 ATR, 0.8 retrace, 1.0 ATR stop) were tuned on the same Apr replay window — in-sample fitting confessed in code comments (`mean_reversion_scanner.py:44-59`). The 22% win rate vs structural 3:1 R:R nets out to roughly zero.
- **ORB stocks-in-play: thesis plausible, implementation can't express it.** The causal-bar engineering is genuinely careful (`orb_scanner.py:181-205`), but the paper's effect is cross-sectional — top-20 in-play names from a ~1000 universe; this implementation ranks top-10 of **22 hand-picked liquid names** (`ORB_PROMOTION_CRITERIA.md:49` admits this). The headline "Sharpe 2.81→0.85 after haircut" is **borrowed from the paper, not measured here** — no completed Phase-C simulation exists in the repo. Exits are delegated to the generic engine; the convex let-winners-run payoff isn't implemented.
- **EOD engines: contradictory and unvalidated.** A continuation engine (`eod_scanner.py`, HKS intraday momentum — literature supports index ETFs only) and a reversal engine (`engines/eod_reversal_shadow.py`, single names — unsupported) trade the same window in opposite directions, both shadow-only.
- **Backtest infrastructure gap:** the replay harness drives the real engine (good fidelity) but defaults to same-bar close fills, flat 5bps slippage, **no spread, no commission** (`replay_simulator.py:88-135, 807`); the rigorous walk-forward harness (`walk_forward.py`) validates a *different, legacy* strategy set — it never tests the strategies that actually trade. Prior replay artifacts confirm: `backtest_exp5` Sharpe −0.75 to −0.95.

## 8. Where the edge has to come from

No audit can hand you a guaranteed edge — anyone who claims otherwise is selling something. What the evidence supports:

1. **Make cost the first-class constraint.** Every current strategy generates many small trades (median notional ~$2k, gross edge ≤2bps) in a regime where round-trip cost is 4–8bps. Either the per-trade gross edge must exceed ~10bps or the trade count must collapse. Concretely: fewer, larger, longer-held positions. Your own data says holding works (passive exits +$739) and churning loses (active exits −$1,115).
2. **Exploit the one measured asymmetry you have: exit behavior.** Before hunting new entry signals, fix the exits on the existing book — the MFE giveback (63% of green trades closing red) is the largest single recoverable sum in your data. Test: replace stop/trailing logic with time-based + retracement-fraction exits in replay; this is cheap to validate with the harness you already own.
3. **Trade the regime cells that paid.** trending_up and high_vol were the only profitable cells (+$184 on 36 trades vs $0 on 364 chop trades). A regime gate that *stands down in chop* — most of your volume — likely improves expectancy more than any new signal. Validate with ≥100 trades per cell before trusting it.
4. **Give ORB its actual prerequisites or drop it.** The in-play effect needs a wide scan universe (hundreds of names filtered daily by relative volume/news), not 22 statics, plus the convex exit. That's a data-pipeline investment (full-market minute bars), not a parameter tweak. If you fund one new edge effort, the literature and your own promotion doc point here.
5. **Restrict EOD continuation to index ETFs** (SPY/QQQ — matching the literature), kill the single-name reversal variant, and measure for 60+ sessions in shadow.
6. **Fix the measurement instruments before trusting any of the above:** costed fills in replay (next-bar open + spread + slippage), walk-forward pointed at the real scanners, purge/embargo in splits, and a realized-correlation monitor. Until the instruments are honest, every "edge" found is suspect.

## 9. Go-live gate plan

Hard gates — all must pass, in order. No gate is waivable by trade count alone.

**Gate 0 — Safety (code, this week):** §3.1 endpoint secured; §3.2 same-holdout fixed; fail-closed breaker defaults; EOD flatten escalation; pyramid gating; brain corruption root-caused. Each verified by a test.
**Gate 1 — Instrumentation:** replay harness costed (next-open fills, spread model, commissions); walk-forward runs the live scanners; live dashboard tracks rolling corr(predicted, realized), expectancy, PF by signal source and regime.
**Gate 2 — Evidence (per strategy, before it may trade live):** ≥60 sessions shadow or honest replay; net expectancy > 0 with t-stat ≥ 2 *after* costs; PF ≥ 1.3; max drawdown ≤ 3× daily-loss limit; results stable across two non-overlapping sub-periods. The whole-book version of the same test on paper: ≥3 months, net positive, t ≥ 2.
**Gate 3 — Staged capital:** start at 10% of intended size; daily loss limit ≤ 1.0% of equity (current $5,500 ≈ 4.9% is too loose); advance size only after each 20-session block re-passes Gate 2 metrics live; automatic stand-down to paper on a 2× breach of expected drawdown.
**Gate 4 — Operational:** kill switch covering *all* execution paths, tested live; overnight-position alerting tested; runtime config snapshot (breakers, mode, timeframe) asserted at startup and logged.

Today the system passes none of Gates 0–2. The fastest honest path to live is: Gate 0 fixes (~days), instrumentation (~1–2 weeks), then the exit-logic and regime-gate experiments from §8 — which use data you already have — while ORB-at-proper-scale is built as the medium-term edge bet.

---

## 10. Priority fix list (impact-ranked)

1. Auth on `multi_strategy_live.py` run-once + kill-switch coverage (§3.1)
2. Same-holdout comparison in `background_trainer.py`; `allow_relative=False` otherwise (§3.2)
3. Fail-closed risk defaults + tighten `ORGANISM_MAX_DAILY_LOSS` to ≤1% equity (§3.3)
4. EOD flatten escalation: alert + persistent retry + next-open forced exit (§3.4)
5. Pyramid adds through `_passes_entry_gates`; idempotency keys include intent/side/qty (§3.5)
6. Root-cause `corrupt_head_*` brain snapshots (§3.6)
7. Costed fills in `replay_simulator.py` defaults; point `walk_forward.py` at live scanners (§7)
8. Startup assert: `LIVE_TIMEFRAME` matches enabled strategies' requirements (§7)
9. Purge/embargo in `_temporal_split`; realized-correlation acceptance gate; route model artifacts through PromotionController (§6)
10. Exit-logic experiment (MFE giveback) + chop stand-down experiment in replay (§8.2–8.3)
11. Consolidate dual settings systems; delete shadowed flat modules (§4)
12. Decompose `live_engine.py` along the five seams, updating structural-guard tests in lockstep (§4)

*Sources: all file:line references verified against the working tree on 2026-06-09. Trade-history statistics computed from `organism_brain/trade_history.csv` (n=556 after excluding reconciliation artifacts). OOS backtest: `mr_oos_replay.py` (798 trades over 408 cached symbol-days, 2026-04-10→2026-05-20).*
