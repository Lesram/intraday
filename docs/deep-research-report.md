# Independent Audit of Live-Trading Readiness for Lesram/intraday

## Executive Summary

**Readiness grade:** **D+**  
**Go / No-Go for live (real money):** **NO-GO** (paper-only is appropriate right now)

This audit cross-checked the platform’s documented behavior against the **actual implementation** in the connected repo. The big picture: the platform has many strong building blocks (outbox pattern, circuit breaker, exit engine, governance, extensive tests), but a few **safety-critical control-flow and state-integrity flaws** can plausibly strand positions unmanaged or allow the system’s internal state to diverge from the broker—both unacceptable when trading real capital.

### Top findings

- **Critical: drawdown kill halts the tick before exits run**, which can strand existing positions in a worsening drawdown if broker-side protective orders are not guaranteed. In `backend/organism/live_engine.py`, drawdown kill returns from the tick at lines **683–690**, while exits only begin at line **698**. fileciteturn20file0L683-L700  
- **Critical: “trading halted” returns early before *any* risk/exits logic**, which can disable position management during a halt window. `backend/organism/live_engine.py` lines **590–598**. fileciteturn20file0L590-L598  
- **High: sector-limit enforcement is scan-time-only and can be violated within a single tick** because it checks only *current* open positions, not “current + planned entries.” `sector_gate_allows()` counts only `open_symbols` (no “planned entries” accumulator). fileciteturn22file0L12-L77 and the gate is applied during candidate filtering. fileciteturn20file0L878-L896  
- **High: the market/streaming layer can drop messages under load**, risking state divergence, missed fills, and incorrect reconciliation—especially dangerous for exits and wash-trade prevention logic. `backend/integrations/alpaca_stream.py` uses a bounded queue and explicitly drops messages when full. fileciteturn35file0L71-L75 fileciteturn35file0L318-L324  
- **High: documented order-state machine/audit trail logic contains a structurally flawed transition map** (duplicate dict keys for `BROKER_UPDATE`), and the tests don’t assert correctness for these multi-target transitions. `backend/models/order_integrity.py` defines `VALID_TRANSITIONS` with repeated triggers. fileciteturn39file0L145-L205 The “broker update” test asserts only that a boolean is returned. fileciteturn27file0L517-L529  

### Top strengths

- The live tick is serialized with `_tick_lock`, reducing concurrent mutation risk in the core loop. fileciteturn20file0L566-L568  
- The organism has a real, explicit “absolute max loss” safety net gate (15%) for positions lacking reconstructed exit state (and adaptive exits include max-loss checks too). fileciteturn20file0L698-L755 fileciteturn29file0L221-L240  
- The broker/order pipeline follows the **transactional outbox** + **idempotent submission** concept, and the `OrderService` includes per-symbol async locks and a circuit breaker. fileciteturn38file0L48-L62 fileciteturn38file0L724-L845  
- The ML feature builder appears **lookahead-free** (rolling windows, no forward shifts), with consistent NaN handling (final NaN fill to 0.0). fileciteturn31file0L44-L50 fileciteturn31file0L436-L441  
- Extensive test footprint is real, and the repo documents known exclusions/skips (which is better than silent gaps). fileciteturn26file0L45-L51 fileciteturn25file0L8-L22  

## Findings by Area

### Algorithm logic

**Status:** **Fail** (because of halt/drawdown control-flow that can suppress exit management)

**Critical — drawdown kill prevents exit checks on the same tick**  
- **Evidence:** In `backend/organism/live_engine.py`, portfolio drawdown is computed and `trigger_drawdown_kill()` is called (lines **683–686**). If halted, the tick returns immediately (lines **687–690**). Exit management begins after that (line **698**). fileciteturn20file0L683-L700  
- **Why it matters:** A drawdown kill is meant to be a *safety mechanism*. If it stops **risk reduction (exits)** along with new entries, it can amplify losses during exactly the scenario you’re trying to contain.  
- **Fix:** Split governance into two flags: **halt_entries** vs **halt_all_processing**. During drawdown kill, continue:  
  - exit checks,  
  - broker reconciliation,  
  - emergency liquidation (optional),  
  but block new entries/pyramids/training/evolution.

**Critical — global halt returns before position safety**  
- **Evidence:** At tick start, if `governance.is_trading_halted` the function returns fast (lines **590–598**). fileciteturn20file0L590-L598  
- **Fix:** Same as above: allow exit-management path to run even during a halt. If you intend “halt = don’t submit any orders at all,” you still need a separate “emergency exit allowed” mode or guarantee broker-native protective orders.

**High — open positions can skip exit checks when features are missing**  
- **Evidence:** If no features for an open position, exit check is skipped with a warning (lines **702–708**). fileciteturn20file0L701-L709  
- **Worst case:** A data outage (or a single-symbol fetch failure) becomes “no exit logic runs” for that symbol.  
- **Fix:** Add a fallback price source for exit checks for open positions: broker last price, last known close, or streamed quotes. Do not skip exits solely because feature computation failed.

**Medium — composite scoring weights are mathematically valid but diverge from docs**  
- **Evidence (code):** `AlphaScanner.WEIGHTS` sum to 1.0 (0.25+0.20+0.15+0.15+0.10+0.10+0.05). fileciteturn17file0L54-L71  
- **Evidence (docs):** The platform guide describes a different weighting scheme (and even a different factor layout). fileciteturn24file0L225-L232 fileciteturn26file0L196-L204  
- **Fix:** Treat the docs as a versioned contract—update docs to match code, or parameterize weights via config and surface in telemetry.

### Order execution and broker integration

**Status:** **Concerns** (strong primitives, but reliability hazards remain)

**High — streaming/outbox reliability gaps can cause state divergence**  
- **Evidence:** `backend/integrations/alpaca_stream.py` uses a bounded queue (maxsize=1000). fileciteturn35file0L71-L75 When full, it drops messages. fileciteturn35file0L318-L324  
- **Why it matters:** Dropped **fill/cancel/reject** updates can lead to:  
  - believing an order is still pending when it filled,  
  - re-submitting (duplicate exposure),  
  - missing an exit fill (stranded risk).  
- **Fix:** Never drop trade updates silently. Options: backpressure + durable persistence; write raw stream events to DB; and add periodic full reconciliation against broker `/v2/orders` and `/v2/positions`.

**Medium — broker idempotency approach is directionally correct**  
- **Evidence:** `alpaca_broker.py` includes client-order-id based duplicate detection flows. fileciteturn34file0L568-L633 Alpaca explicitly supports querying by client-provided order IDs and recommends streaming for state. citeturn1search0turn1search1  
- **Risk:** If your duplicate-detection only checks a limited recent-window list, you can miss older duplicates; use the direct “get by client order id” endpoint where possible. citeturn1search5  

**Low — outbox “smart TIF” can create unwanted overnight exposure**  
- **Evidence:** Out-of-hours defaults to `gtc`. fileciteturn37file0L20-L68  
- **Fix:** For an intraday system, default should usually be “do not place new orders outside market hours,” unless explicitly configured.

### Risk management

**Status:** **Fail** (because kill-switch behavior undermines exit control)

**Critical — drawdown kill doesn’t guarantee liquidation or ongoing exit management**  
- **Evidence:** Tick returns immediately when drawdown kill is triggered. fileciteturn20file0L683-L690  
- **Required behavior for live capital:** On drawdown kill:  
  - continue running exits, or  
  - immediately flatten positions, or  
  - guarantee broker-native protective orders already exist (brackets/stop orders) for every open position.

**High — sector limit is not enforced at order-time and can be exceeded intra-tick**  
- **Evidence:** Sector gate is a pure function of current `open_symbols` and env-configured cap. fileciteturn22file0L12-L77 Live engine applies it during candidate filtering. fileciteturn20file0L890-L896  
- **Worst case:** You can open 4 tech positions already, then select multiple more tech candidates in the same tick because `open_symbols` hasn’t been updated to include “orders about to be submitted.”  
- **Fix:** Maintain an `intended_sector_counts` accumulator during candidate selection, and re-check in the final pre-submit gate (ideally in the risk manager or order planner).

**Medium — “15% safety net” exists but has edge-case holes**  
- **Evidence:** If `exit_levels` is missing, it computes PnL% using broker `avg_entry_price`; if loss exceeds 15%, submits exit. fileciteturn20file0L714-L755  
- **Edge case:** If broker position data lacks/zeros `avg_entry_price`, the safety net will not trigger. fileciteturn20file0L718-L755  
- **Fix:** Persist entry prices redundantly (DB + brain + broker order fills) and fall back to last known entry when broker data is incomplete.

### State persistence and recovery

**Status:** **Concerns** (good design intent; some critical sections couldn’t be fully validated)

**Medium — brain restoration attempts to restore exit levels and metadata**  
- **Evidence:** `live_engine.py` restores exit levels and entry metadata from persisted `extra_counters`, and reconstructs positions on init. fileciteturn20file0L433-L466 fileciteturn20file0L524-L526  
- **Concern:** The internal implementation of `_reconstruct_position_state()` is beyond the accessible excerpt window in this audit pass, so I could not verify:  
  - how it resolves missing ATR,  
  - how it handles partial fills and pyramids,  
  - how it validates broker-vs-brain consistency end-to-end.  
  Those pieces are **mandatory to validate** before live trading.

**Medium — brain persistence uses locking and atomicity primitives (positive), but save-skip behavior must be audited**  
- **Evidence:** Brain persistence defines file-locking and atomic save/backup semantics. fileciteturn33file0L150-L161 fileciteturn33file0L171-L240  
- **Concern:** If non-blocking locks cause saves to be skipped under load, restarts may roll back state unexpectedly.

### Security

**Status:** **Concerns** (good primitives, but production modes must “fail closed”)

**Medium — JWT verification is strict (good), but token revocation can degrade in multi-process scenarios if Redis is unavailable**  
- **Evidence:** JWT decode enforces signature/exp/issuer/audience requirements. fileciteturn28file0L187-L227 Token blacklist supports Redis + in-memory fallback. fileciteturn28file0L51-L104  
- **Risk:** If multiple workers/instances run and Redis is down/uninitialized, revocation becomes process-local, and the system may accept tokens revoked elsewhere. The code explicitly warns it “cannot verify token revocation status” when Redis is unavailable. fileciteturn28file0L129-L144  
- **Fix:** In production: require Redis for revocation, or disable token revocation claims entirely and shorten token TTL dramatically.

### Test coverage

**Status:** **Concerns** (high volume, but risk is in the untested edges)

**High — test totals are strong, but important suites are skipped/excluded**  
- **Evidence:** Third-party report claims 7,021 backend / 134 frontend passed (684 skipped). fileciteturn26file0L45-L52 Platform status shows a different run profile and lists excluded/hanging tests and integration tests that auto-skip. fileciteturn25file0L8-L22  
- **Fix:** Make “live trading gate” depend on an explicit test tier that includes:  
  - order lifecycle integration tests,  
  - stream reconnection tests,  
  - exit safety net tests under data outage.

**High — order integrity tests don’t assert correctness of the complex BROKER_UPDATE multi-target transitions**  
- **Evidence:** The test acknowledges the broker-update result “depends on configuration” and asserts only a boolean. fileciteturn27file0L517-L529  
- **Fix:** Add explicit assertions for each allowed BROKER_UPDATE transition, and correct the transition map structure.

### Infrastructure

**Status:** **Unknown-to-Concerns** (insufficient direct verification in this pass)

The audit report claims production Docker hardening, non-root users, CI gates, and security scanning. fileciteturn26file0L496-L519 I did not re-verify `Dockerfile.production`, workflows, and runtime user/permissions in this pass due to time and excerpt constraints. Treat this as **must-confirm** before live.

### Data integrity and performance

**Status:** **Concerns**

**High — “skip exits when data missing” is unacceptable for real money**  
- **Evidence:** exit checks are skipped when features are not available for an open position. fileciteturn20file0L701-L709  
- **Fix:** data-quality failures must degrade to a “risk-off” mode that still manages open risk (or flattens).

### Documentation and completeness

**Status:** **Fail** (material inconsistencies between docs and code)

- Docs state different feature counts (68 vs 79) and different exit parameters (e.g., partial at 3R, trail activation at 3×ATR). fileciteturn24file0L37-L41 fileciteturn24file0L204-L213  
- Code instantiates intraday-tuned values (e.g., tighter trailing at 2×ATR, partial at 2R) and smaller min position ($500). fileciteturn20file0L258-L273  
- Docs claim `ORGANISM_MAX_POSITIONS` default 15; code default is 8. fileciteturn26file0L533-L536 fileciteturn20file0L141-L142  

### Compliance and audit trail

**Status:** **Fail** (as implemented today)

Even though an “append-only audit log” and state machine are defined, the transition map structure is flawed for multi-target triggers and the tests don’t validate correctness beyond “returns a bool.” fileciteturn39file0L145-L205 fileciteturn27file0L517-L529  
If you are relying on this for regulatory-style reconstruction, you need either:  
- a corrected FSM + verified persisted audit log path actually used by order execution, or  
- a simpler dedicated event-sourcing trail for orders/fills/cancels/decisions.

## Algorithm Deep Dive

### Composite scoring math correctness

**What code does:** `AlphaScanner` computes a 7-factor composite using fixed weights summing to 1.0. fileciteturn17file0L54-L71  
**Key correctness checks:**
- **Weights sum to 1.0:** ✅ (verified directly). fileciteturn17file0L54-L71  
- **NaN/Inf guards:** partial; some factors clamp and use defaults, but the scanner does not globally sanitize NaNs for all raw factor inputs before composing. fileciteturn17file0L84-L115  
**Why it matters:** In live systems, NaNs can create “silent non-trading” or unstable candidate sets.

**Recommendation:** Add a final `np.isfinite()` guard per factor and for the final composite; also log factor-level NaNs by count.

### Kelly criterion correctness

`KellySizer` implements a half-Kelly base, applies regime/confidence/vol scaling, and caps per-position and portfolio exposure. fileciteturn28file0L247-L379  
**Key safety properties:**
- **Per-position cap exists:** ✅ `max_position_pct` clamps. fileciteturn28file0L321-L333  
- **Max portfolio cap exists:** ✅ `max_portfolio_pct`. fileciteturn28file0L464-L479  
- **Live engine overrides to 8% and $500 min:** may be safe for risk, but must be documented and deliberate. fileciteturn20file0L258-L263  

**Primary risk:** The sizing math is only as safe as the **state integrity** of “total_weight” and “existing_positions.” Any broker/DB/state mismatch can cause the sizer to think exposure is lower than it is.

### Exit parameter reasonableness

`AdaptiveExitEngine` includes stop, take-profit, trailing, partial TP, time-based rules, and a max-loss safety net. fileciteturn29file0L155-L264  
The live engine also enforces a 15% “no exit_levels” safety net. fileciteturn20file0L714-L755  

**Death-spiral edge:** If governance halts the tick before exits are evaluated (as currently), the intended safety net is irrelevant. fileciteturn20file0L683-L700  

### Regime detection stability

The regime detector uses SMA slope + vol ratio heuristics and probability smoothing. fileciteturn30file0L291-L371  
**Risk:** Misclassification can tighten stops (more churn) or increase size (if regime scales are aggressive). The current system’s biggest risk is less “wrong label” and more “wrong behavior when halted / data missing.”

### Evolution engine constraints

The live engine constructs `EvolutionEngine(alpha=0.30, max_shift=0.20, min_trades=8)`. fileciteturn20file0L281-L287 Those clamps are directionally correct.

**But:** this pass could not fully verify the internal implementation of `self_evolution.py` beyond the excerpt window. Given the audit report explicitly flags `self_evolution.py` as a high-risk module lacking dedicated tests. fileciteturn26file0L586-L606 treat “evolution correctness under adversarial outcomes” as **unproven** until you add targeted property tests.

### Death spiral scenarios to defend against

The most realistic pathways in the current codebase are:

- **Drawdown-kill stops exits** → positions continue bleeding without active management. Evidence: early return before exit loop. fileciteturn20file0L683-L700  
- **Stream update drops** → fills/cancels missed → state divergence → duplicate orders / missed exits. fileciteturn35file0L318-L324  
- **Data outage for a symbol** → exit checks skip that symbol. fileciteturn20file0L701-L709  
- **Sector-limit drift intra-tick** → concentrated book forms silently. fileciteturn22file0L70-L77 fileciteturn20file0L878-L896  

## Completeness vs Blueprint

**Blueprint baseline:** `docs/blueprints/EVOLVING_ORGANISM_BLUEPRINT.md` (dated 2026-02-15) lays out core modules and a staged organism design. fileciteturn23file0L1-L6  

### Implementation estimate

Based on the blueprint’s “What Exists” inventory and the presence of referenced modules in `live_engine.py`, core organism components exist (ML, scanners, exits, Kelly, governance, persistence hooks, scanner/universe selector). fileciteturn23file0L160-L188 fileciteturn20file0L248-L306  

**Estimated blueprint implementation:** **~80%** implemented in code, **but only ~55–60% “live-safe”** until the safety-critical gaps below are closed.

### Documented but not safely implemented (or not verified)

- **Kill-switch semantics:** Blueprint/docs describe governance as a safety layer; code currently returns before exits, which contradicts “fail-safe” behavior. fileciteturn24file0L187-L213 fileciteturn20file0L683-L700  
- **Order state machine “explicit valid transitions”:** Documented heavily, but `VALID_TRANSITIONS` structure is flawed for multi-target triggers. fileciteturn39file0L145-L205  
- **Promotion pipeline enforcement in live organism path:** The docs emphasize promotion, but the live engine imports no promotion manager/controller in the visible implementation. fileciteturn24file0L285-L313 fileciteturn20file0L38-L74  

### Implemented but undocumented (or mismatched)

- **Intraday-tuned parameterization:** Live engine uses tighter trailing and earlier partial TP (2R, 40%), and smaller min position size ($500). fileciteturn20file0L258-L273 This materially differs from the guide’s narrative (3R partial, 3×ATR trailing activation, $2,000 min). fileciteturn24file0L204-L213 fileciteturn24file0L225-L232  
- **Max positions mismatch:** Code default is 8; docs/report claim 15. fileciteturn20file0L141-L142 fileciteturn26file0L533-L536  

## Go-Live Checklist

**Core logic:** **Blocked** (halt/drawdown control-flow must be corrected). fileciteturn20file0L683-L700  
**Risk management:** **Blocked** (sector/correlation enforcement; exit-on-halt semantics). fileciteturn22file0L70-L77  
**Order execution:** **Needs Work** (outbox/circuit breaker are strong; stream-drop/reconciliation must be hardened). fileciteturn38file0L731-L749 fileciteturn35file0L318-L324  
**State persistence & recovery:** **Needs Work** (strong intent; must validate reconstruction and correctness under failure). fileciteturn20file0L524-L526  
**Monitoring:** **Needs Work** (Prometheus metrics exist, but you need “risk off / state divergence” alarms as first-class). fileciteturn20file0L78-L111  
**Security:** **Needs Work** (JWT is strict; production must fail closed for revocation). fileciteturn28file0L129-L144  
**Tests:** **Needs Work** (breadth is strong; the failures are in the missing edge assertions and skipped tiers). fileciteturn25file0L19-L22 fileciteturn27file0L517-L529  
**Documentation:** **Blocked** (material mismatches with code). fileciteturn24file0L204-L213 fileciteturn20file0L258-L273  
**Incident response:** **Not Started** (not evidenced in reviewed sources; must be explicit).  
**Rollback procedures:** **Needs Work** (brain backups exist conceptually; must ensure “safe rollback without trading against stale state”). fileciteturn26file0L169-L176  

## Prioritized Action Items

### P0 Blockers

**Make drawdown kill and halt modes “risk-reducing,” not “blind”**  
- **Files:** `backend/organism/live_engine.py` (halt early-return; drawdown kill early-return). fileciteturn20file0L590-L598 fileciteturn20file0L683-L700  
- **Fix:** Refactor the tick so that exit checks + reconciliation always run unless explicitly in “emergency do-nothing” mode (which should *not* exist for live capital unless broker-side stops are guaranteed).  
- **Effort:** 1–2 days (plus tests).  
- **Risk if ignored:** catastrophic loss amplification during drawdown events.

**Eliminate dropped order-update events or guarantee reconciliation correctness**  
- **Files:** `backend/integrations/alpaca_stream.py` (drop-on-full), plus whatever does reconciliation (not fully verified here). fileciteturn35file0L318-L324  
- **Fix:**  
  - Never drop execution updates; persist raw updates to DB or increase backpressure;  
  - Add periodic broker truth-sync (positions + orders) and reconcile to internal state.  
- **Effort:** 2–5 days.  
- **Risk if ignored:** duplicate exposure, missed exits, incorrect PnL, inability to reconstruct decisions.

**Enforce sector and concentration limits at final submit time**  
- **Files:** `backend/organism/sector_map.py`, `backend/organism/live_engine.py`. fileciteturn22file0L70-L77 fileciteturn20file0L890-L896  
- **Fix:** Track “planned entries” while building the entry plan; re-check at submit.  
- **Effort:** <1 day.  
- **Risk if ignored:** concentrated book and correlated losses.

### P1 Critical before scaling capital

**Repair the order-integrity FSM transition mapping (or remove it if it is not used)**  
- **Files:** `backend/models/order_integrity.py` `VALID_TRANSITIONS`. fileciteturn39file0L145-L205  
- **Fix:** Replace dict-of-trigger→state with dict-of-trigger→set[state] (or list), and update `can_transition()` accordingly. Add assertions in tests for each target transition (not just “returns bool”). fileciteturn27file0L517-L529  
- **Effort:** 1–2 days.  
- **Risk if ignored:** untrustworthy audit trail and broken lifecycle semantics.

**Stop skipping exits on data failure**  
- **Files:** `backend/organism/live_engine.py` exit loop. fileciteturn20file0L701-L709  
- **Effort:** 1 day.  
- **Risk if ignored:** open risk becomes unmanaged during transient outages.

### P2 Important within first month

**Clarify and unify configuration realities (docs, env vars, defaults)**  
- **Evidence:** max positions and parameters differ between docs and code defaults. fileciteturn20file0L141-L142 fileciteturn26file0L533-L536  
- **Fix:** Generate docs from config schema; surface “effective runtime config” in UI.

**Revisit outbox “smart TIF” default for an intraday organism**  
- **Files:** `backend/integrations/alpaca_outbox.py`. fileciteturn37file0L20-L68  
- **Fix:** Default to “day” (or reject off-hours), with explicit config allowing GTC.

### P3 Nice-to-have

**Add property tests and adversarial simulations for evolution**  
- **Files:** `backend/organism/self_evolution.py` (flagged as high risk in the repo’s own audit). fileciteturn26file0L597-L606  
- **Focus:** normalization invariants, clamp invariants, monotonic safety constraints, and “no single epoch can radically increase risk.”

## Architecture Recommendations

**Separate “risk management loop” from “alpha generation loop.”**  
Right now, `live_tick()` is a single pipeline. The safest production pattern is:

- A **Risk/Position Guardian loop** that always runs (even in halts) and only handles:  
  - broker reconciliation,  
  - exits,  
  - emergency liquidation,  
  - state sanity checks.  
- A separate **Strategy/Entry loop** that can be halted/frozen independently.

**Treat broker truth as the source of truth; treat internal state as a cache.**  
The presence of stream drop behavior means you must assume events can be missed. Build:  
- periodic order and position reconciliation (full diff),  
- idempotency keys everywhere,  
- “safe retry” semantics for exits.

**Instrument “safety invariants” as first-class monitors.**  
Add hard alerts for:  
- “tick halted while open positions exist,”  
- “exit checks skipped due to missing data,”  
- “stream queue drops > 0,”  
- “sector cap exceeded,”  
- “internal exposure differs from broker exposure,”  
- “governance halted but exits not running.”

**Align documentation to the actual runtime config.**  
The platform’s docs and third-party report are rich, but they currently conflict with code in critical parameters (max positions, exit/take-profit tuning). fileciteturn20file0L258-L273 fileciteturn24file0L204-L213