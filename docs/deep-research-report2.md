# Independent Verification Audit — Intra Trading Platform

## Executive Summary

**Updated readiness grade:** **D (NO‑GO for real‑money trading)**

**Bottom line:** The team did fix several previously critical issues (notably: the Alpaca trade‑update stream no longer drops updates; the order‑integrity FSM transition table is structurally repaired; intra‑tick sector gating is materially improved). However, **a core safety invariant is still violated in the live tick loop**: there remains at least one realistic pathway where the tick returns early **before positions are fetched and before exits are processed**, which can leave live risk unmanaged during partial data outages. Until “exits always run” is true under *all* degraded‑data conditions, this platform is not safe for real capital.

**Go / No‑Go decision:** **NO‑GO** for live trading with real money on entity["company","Alpaca Markets","broker api platform"].

### Top findings

1. **P0 — Exits can still be skipped entirely** if the tick returns early on insufficient features (the guard `len(features_by_symbol) < 3` occurs before fetching broker positions, before exit processing, before reconciliation, and before state persistence).
2. **P0 — “Exits still active during halts” is only conditionally true**: the code correctly gates entries with `entries_blocked`, but early‑return paths still bypass the exit loop entirely.
3. **P1 — Smart TIF “day by default” fix is undermined by upstream defaults**: outbox logic defaults to `day` *only when TIF is absent*, but at least one order submission path still defaults TIF to `gtc`, meaning “day by default” is not consistently achieved end‑to‑end.
4. **P1 — Evolution can override intraday exit parameters with large effective step‑changes**: `apply_evolved_params()` maps scales onto absolute exit parameters using baseline constants that do not match the live engine’s “intraday/HFT” configuration, enabling material exit‑behavior shifts that are not constrained the way the 20% “max shift” narrative implies.
5. **P2 — entity["organization","Prometheus","metrics system"] invariant monitors are partially wired**: counters exist, but at least one is never incremented and another’s semantics do not match its help text.

### Top strengths

- **Trade‑update ingestion is now lossless by design** (unbounded async queue + no drop policy), reducing silent desync risk in order state reconciliation.
- **Order‑integrity state machine transition structure is repaired** (valid transitions represented as sets; broken broker‑update transitions appear to be present and tested).
- **Intra‑tick sector gating uses a planned‑entries accumulator** across both alpha and breakout loops, materially reducing same‑tick sector breaches.
- **Exit fallback exists for per‑symbol feature gaps** (broker‑price safety‑net path).
- **Order submission path includes per‑symbol async locks and an idempotent DB upsert + outbox workflow**, a solid foundation for execution safety.

## Verification Matrix

**Important note on evidence format:** The GitHub connector returns plain file bodies without stable line‑number metadata. To keep findings verifiable, each item includes (a) exact file paths and (b) unique “search strings” that locate the relevant code unambiguously (e.g., `if len(features_by_symbol) < 3:`). Where I cite tests, I name test files and the exact test function(s) to search.

| Claimed fix | Status | What I verified in code | What is still concerning / incomplete |
|---|---|---|---|
| Drawdown kill / halt still processes exits | **Partially Verified** | `entries_blocked = True` is used (not an immediate return) when governance halt is active and when drawdown kill triggers; exit loop runs before the `if entries_blocked:` gate; reconcile is called inside the entries‑blocked gate. Search in `backend/organism/live_engine.py` for `entries_blocked = False`, `if self.governance.is_trading_halted:`, `trigger_drawdown_kill`, and `# 5. CHECK EXITS`. | **P0:** early return on insufficient features still occurs *before* `get_all_positions()` and before exit processing (search: `if len(features_by_symbol) < 3:`). Also, “brain save always needed” is asserted in comments but the save is still periodic (`if self._tick_count % 50 == 0:`). The entries‑blocked pathway returns before equity curve update + Prometheus export + invariant checks, weakening monitoring during failsafe mode. |
| Stream never drops trade updates | **Verified (with operational risk)** | In `backend/integrations/alpaca_stream.py`, `update_queue` is `asyncio.Queue()` with no `maxsize`; `_handle_message()` uses `await self.update_queue.put(...)` and does not drop; it tracks `_queue_high_water_mark` and `_queue_overflow_count`. Search: `self.update_queue = asyncio.Queue()`, `_queue_high_water_mark`, `_queue_overflow_count`, `await self.update_queue.put`. | Unbounded queue can become **unbounded memory growth** if processing falls behind. For a 30‑symbol intraday system, trade updates should be low volume in “normal” operation, but adverse scenarios (reconnect storms, duplicate streams, broker bursts) can still cause backlog. The “warning threshold” pattern increments overflow counters but does not actively backpressure or shed load. |
| Sector limits enforced intra‑tick | **Verified (minor caveats)** | `backend/organism/sector_map.py`’s gate accepts `planned_symbols` and counts open+planned. In `backend/organism/live_engine.py`, `_planned_entries: set[str] = set()` exists and is updated after passing the gate; gate is applied in both candidate loop and breakout loop. Search: `def sector_gate_allows(`, `planned_symbols`, `_planned_entries: set[str] = set()`, `sector_gate_allows(`, `_planned_entries.add`. | If an order is later rejected, `_planned_entries` still blocks other same‑tick candidates in that sector. That’s likely acceptable, but it should be explicitly treated as “tick‑local pessimism,” not “true sector exposure.” Also, the Prometheus counter named for sector blocking exists but appears not to be incremented at the block site. |
| Order integrity FSM fixed | **Partially Verified** | In `backend/models/order_integrity.py`, `VALID_TRANSITIONS` maps trigger → **set[OrderState]**. `can_transition()` is simplified to membership in allowed set. Required transitions appear present: SUBMITTED→PENDING_EXECUTION (BROKER_UPDATE), PENDING_EXECUTION→FILLED/PARTIALLY_FILLED (BROKER_UPDATE), PARTIALLY_FILLED→FILLED (BROKER_UPDATE), UNDER_REVIEW→VALIDATED (MANUAL_OVERRIDE). Search: `VALID_TRANSITIONS =`, `BROKER_UPDATE`, `MANUAL_OVERRIDE`, `can_transition`. Tests in `tests/test_order_integrity_comprehensive.py` assert broker‑update transitions explicitly—search for `test_transition_...` and `BROKER_UPDATE`. | The FSM still appears to be used inconsistently at order creation: `create_order()` calls a transition from `from_state=None` (search in `order_integrity.py` for `create_order` and `from_state=None`). With the current `can_transition()` structure, that initial transition may be treated as invalid unless special‑cased. Even if non‑fatal, it undermines audit‑trail integrity. |
| Exits not skipped on missing features | **Partially Verified** | In `backend/organism/live_engine.py`, the exit loop checks `feat_df is None or len(feat_df) < 1`, then falls back to broker’s `current_price` and `avg_entry_price` and will submit an exit with reason `safety_net_no_features` if loss exceeds `_MAX_LOSS_PCT`. Search: `if feat_df is None or len(feat_df) < 1:`, `broker_price`, `avg_entry`, `safety_net_no_features`. | **P0:** This fix is bypassed by the earlier tick‑level early return (search: `if len(features_by_symbol) < 3:`). Also: if broker reports `avg_entry_price` missing/0, the code logs and continues—meaning no safety exit is attempted for that position. Finally, fallback behaves as “safety net only,” not “full exit logic”; stops/trailing/time exits are not evaluated without features. |
| NaN guard on alpha scanner | **Verified** | In `backend/organism/alpha_scanner.py`, factors are guarded with finiteness checks and sensible fallbacks (0.0 for signal‑style scores, 0.5 for “neutral” style components). Composite score is checked for finiteness and skipped if invalid. `_rank_momentum()` guards against NaNs in `ret_20`. Search: `np.isfinite`, `not np.isfinite(composite)`, `_rank_momentum`, `ret_20`. | Remaining concern is more about **risk model semantics** than NaNs: fallback values should be documented as policy (and tested), because they change ranking behavior during partial feature corruption. |
| Smart TIF defaults to `day` | **Partially Verified** | In `backend/integrations/alpaca_outbox.py`, `get_smart_tif()` returns `day` by default when `requested_tif` is missing/invalid; `gtc` is no longer used as implicit fallback. Tests in `tests/unit/test_alpaca_outbox_comprehensive.py` assert `day` in off‑hours/weekend/error scenarios. Search: `def get_smart_tif`, `return "day"`, test names containing `tif`. | End‑to‑end behavior is not guaranteed because at least one order submission path defaults to `tif="gtc"` upstream. In `backend/services/order_service.py`, `_submit_order_with_session()` uses `tif = order_data.get("tif", "gtc")`, which means many orders will still hit outbox with explicit `gtc` even when the caller did not intend to request it. This is a policy mismatch that can resurrect “orders linger overnight” risk. |
| Documentation matches code | **Not Verified (regressions remain)** | Some intraday parameters in `backend/organism/live_engine.py` match the claims (e.g., KellySizer instantiated with `max_position_pct=0.08` and `min_position_usd=500.0`; AdaptiveExitEngine uses `trailing_start_atr=2.0`, `partial_tp_pct=0.40`, `partial_tp_r=2.0`). Search those literals in `live_engine.py`. | `docs/PLATFORM_COMPLETE_GUIDE.md` still contains inconsistent feature counts (it states “68 features” in one place while `backend/organism/ml_features.py` enumerates a larger set and advertises 70+). Additionally, the evolution engine can change the “documented constants” at runtime (exit parameters are overwritten by `apply_evolved_params()`), so docs that present them as static are misleading. |
| Prometheus safety monitors | **Partially Verified** | In `backend/organism/live_engine.py`, counters are declared under a `try: import prometheus_client` block and guarded by `_PROMETHEUS_AVAILABLE` at increment sites. Search: `try: from prometheus_client import`, `_PROMETHEUS_AVAILABLE`, `ORGANISM_...`. | At least one counter appears to have no increment path (sector cap blocked). Another counter’s help string implies “fell back to broker price due to missing features,” but the increment occurs only when the safety net triggers, not for every fallback exit evaluation. This prevents monitors from answering the question they purport to monitor. |

## Independent Re‑Audit of Critical Paths

### Exit safety: can a position be entered but never exited?

This is the most important question. Based on the current `backend/organism/live_engine.py` structure, **there is still at least one repeatable pathway where exit checks do not run**:

- The tick fetches features early and then performs an early‑return if too few symbols produced features (`if len(features_by_symbol) < 3: ... return result`). This return happens **before**:
  - fetching broker positions (`get_all_positions()`),
  - running the exit loop,
  - running reconciliation,
  - checkpointing brain state.
- In real trading, “features_by_symbol < 3” can occur due to partial data outage, intermittent REST throttling, or a broken upstream feed. This is *exactly* the time when a safety engine must still attempt broker‑based exits.

Even with the new per‑position fallback (“safety net with broker price when feature df missing”), that fallback is irrelevant if the tick returns before it reaches positions.

**Worst‑case impact:** a sustained partial data outage causes the engine to repeatedly return early, leaving open positions unmanaged. If price gaps against you during this window, you can blow through the intended max loss.

### Kelly sizing: can it exceed risk limits?

The `backend/organism/kelly_sizer.py` implementation does apply caps:

- Raw Kelly fraction is capped at 1.0, then halved.
- Final `target_weight` is clipped to `max_position_pct`.
- A portfolio cap (`max_portfolio_pct`) is applied to the weights of *the sized candidate list*.

However, there are still meaningful risk caveats:

- **Exposure accounting omission:** `size_positions()` does not appear to incorporate current portfolio exposure from existing open positions; it caps only weights allocated to the candidates it is sizing. This is partially mitigated by the live engine’s **small per‑position cap** (`0.08`) and a max position count (8) in its current configuration; but if those values change upward, or if other strategies can hold additional positions, the sizer’s “95% portfolio cap” is not a true portfolio cap.
- **Data dependency:** candidates are skipped if `df is None or len(df) < 30`. During degraded data periods, sizing drops candidates entirely. This lowers trading frequency but can also cause unstable behavior if the engine alternates between “size nothing” and “size aggressively” across consecutive ticks.

### Evolution safety: can parameters explode or cause a death spiral?

`backend/organism/self_evolution.py` contains real safety clamps:

- Evolution is skipped unless at least `min_trades` are present (default 8).
- EMA smoothing exists and `_ema_update()` clamps per‑epoch delta (`max_shift`).

However, there is a critical nuance: **the “20% max shift” narrative applies to the internal *scales*, not necessarily to the actual trading parameters**.

`apply_evolved_params()` maps “scale parameters” onto absolute trading parameters using baseline constants (e.g., `exit_engine.trailing_start_atr = 3.0 * params.trailing_start_atr_scale`). The live engine initializes `AdaptiveExitEngine` with different intraday baselines (`trailing_start_atr=2.0`, `partial_tp_r=2.0`, etc.). As a result, the first time evolution is applied, you can get **effective step changes** in live exit behavior that are larger than intended.

**Death‑spiral scenario:** after a small losing streak, regime scoring or threshold calibration can become more selective, reducing trade count; the engine then evolves on sparse samples (still above 8 trades), potentially pushing thresholds in the wrong direction; performance worsens; the walk‑forward save gate may block brain saves, increasing restart fragility. The clamps mitigate “explosion,” but do not guarantee “safe evolution trajectory.”

### Regime handling: can misclassification cause catastrophic behavior?

The regime detector in `backend/organism/regime.py` is heuristic and uses EMA smoothing of probability vectors. That is structurally stabilizing, but the platform’s safety depends on what the exit engine does when regime flips. Since exits are evaluated each tick with the current regime, misclassification can lead to:

- exits tightening too much (premature churn) if a “stress/high_vol” regime is falsely detected, or
- exits loosening too much (bleeding losses) if “trending” is falsely detected in chop.

Given the earlier P0 finding (tick early return can entirely skip exits), the catastrophic regime risk is currently secondary; the “exits always run” invariant must be solved first.

### ML lookahead bias risk

`backend/organism/ml_features.py` computes features using rolling windows that include the current bar. That is not automatically “lookahead” if labels are future returns (t+1) and training aligns features at t with labels at t+1. But the file’s header claims “No lookahead bias” as a blanket statement.

I did not verify label generation / alignment logic in `ml_signal.py` and the learner pipeline in this pass. Given the platform’s dependence on ML confidence and predicted returns (used by Kelly sorting and confidence scaling), **ML alignment verification remains a material open risk** until the training pipeline is inspected end‑to‑end.

### Order execution safety

From `backend/services/order_service.py`:

- There is a per‑symbol async lock to reduce same‑symbol double submits.
- There is an idempotent DB upsert by client key and an outbox event enqueue.
- A circuit breaker exists and can block order flow after failure bursts.

But there are still policy inconsistencies:

- The “smart TIF defaults to day” intent is not guaranteed if upstream defaults to `gtc` (`tif = order_data.get("tif", "gtc")` in one submission path). This can reintroduce overnight persistence of orders unless every caller always passes TIF explicitly.

### State persistence and recovery

I verified that `backend/organism/live_engine.py` persists rich state via `_save_brain()` including `exit_levels`, `entry_metadata`, tick counters, and calibration artifacts.

However, I was unable to fetch `backend/organism/brain_persistence.py` via the connector in this session due to tool output blocking, so I could not independently verify:

- atomic save semantics,
- backup rotation correctness,
- NaN/Inf sanitization,
- crash‑consistency claims.

This leaves a meaningful uncertainty in “restart safety,” especially given that the tick loop mutates exit‑level state on every tick but only saves periodically.

## Test Coverage Assessment

The new tests that exist are conceptually meaningful for the fixes they target:

- `tests/test_order_integrity_comprehensive.py` asserts specific transitions, including broker‑update transitions and manual override transitions (good test shape: explicit valid/invalid cases).
- `tests/unit/test_alpaca_stream_comprehensive.py` checks that the queue is unbounded and messages are enqueued (validating “no drop” intent).
- `tests/unit/test_alpaca_outbox_comprehensive.py` asserts that `day` is selected in common off‑hours/weekend/error conditions.

But the most important safety paths are still not convincingly tested. The **top five most dangerous untested (or under‑tested) paths**:

1. **Tick early return safety invariant:** there should be a test that simulates `features_by_symbol < 3` while positions exist and asserts exit processing still runs (currently, the code returns early).
2. **Entries‑blocked still processes exits:** there should be a test that sets governance halt/drawdown kill and verifies exits + reconciliation run in the same tick (not just that `entries_blocked` is set).
3. **Sector planned‑entries accumulator correctness:** there should be a test that ensures `_planned_entries` blocks a second candidate in the same sector and that both alpha loop and breakout loop contribute to planned entries.
4. **Evolution application safety:** there should be tests validating that applying evolved params cannot create discontinuous changes to live exit parameters beyond allowed bounds (especially given the baseline mismatch).
5. **End‑to‑end TIF policy:** there should be an integration test that starts at order request → DB upsert → outbox → broker payload and asserts the resulting TIF matches the intended policy when the caller does not specify TIF.

I did not verify the global “7,156 tests passing” claim or the “684 skipped tests” inventory in this pass, because that requires CI artifacts or a test runner transcript, neither of which were accessible via the connector tools available in this session.

## Updated Go‑Live Checklist

**Core logic:** **Blocked** — exits not guaranteed to run under degraded data conditions.

**Risk management:** **Blocked** — “exits always run” invariant not met; evolution can induce large effective exit behavior shifts.

**Order execution:** **Needs Work** — good primitives exist (locks, idempotency, outbox, circuit breaker), but TIF policy is inconsistent across call paths.

**State persistence:** **Needs Work** — rich state is saved from the live engine, but brain persistence implementation could not be re‑verified.

**Monitoring:** **Needs Work** — Prometheus counters exist, but some appear incomplete/misaligned with semantics; entries‑blocked returns before normal metric export.

**Security:** **Not Assessed in this verification pass** — no full sweep for secrets/JWT/endpoint auth/CVEs performed here.

**Tests:** **Needs Work** — tests exist for some fixes, but the most dangerous live safety invariants are not validated.

**Documentation:** **Needs Work** — inconsistencies remain (feature counts and “static parameter” narratives vs runtime evolution).

**Incident response & rollback:** **Not Assessed in this verification pass** — would require operational runbooks / tooling confirmation.

## Final Prioritized Action Items

### P0 Blockers

**Guarantee exit processing regardless of feature availability**
- **Where:** `backend/organism/live_engine.py`
- **Problem:** Early return on `len(features_by_symbol) < 3` occurs before positions/exits/reconcile.
- **Fix:** Reorder the tick so that:
  - broker positions are fetched early (or last known positions are used),
  - exit loop always runs for tracked/broker positions even when features are missing,
  - broker‑price fallback is used for *all* positions when features are unavailable,
  - reconciliation and at least a minimal state checkpoint runs in “degraded mode.”
- **Risk if not fixed:** Open positions can be unmanaged during partial outages → real money loss beyond intended max‑loss.

**Constrain evolution so it cannot cause discontinuous exit‑parameter changes**
- **Where:** `backend/organism/self_evolution.py` (`apply_evolved_params`) and `backend/organism/live_engine.py` (initial exit engine configuration)
- **Problem:** Evolution maps scales to absolute exit parameters using baselines inconsistent with intraday configuration; “20% max shift” does not necessarily apply to the actual trading values.
- **Fix:** Either:
  - make evolution apply *multiplicative deltas relative to current live engine values*, or
  - align baselines so the first application is a small delta (not a structural reset), and enforce explicit hard bounds on absolute exit parameter ranges.
- **Risk if not fixed:** Exit behavior can change materially after evolution cycles, invalidating safety assumptions and documentation.

### P1 Critical

**Make TIF policy consistent end‑to‑end**
- **Where:** `backend/services/order_service.py` and `backend/integrations/alpaca_outbox.py`
- **Problem:** Outbox defaults to `day` only when TIF is absent, but upstream code paths default TIF to `gtc`.
- **Fix:** Set a single, explicit policy: if caller does not specify, default to `day` (or `ioc`) at the earliest layer; ensure the outbox layer enforces/validates allowed TIFs.
- **Risk if not fixed:** Unintended overnight/weekend orders.

**Ensure entries‑blocked mode still exports core observability**
- **Where:** `backend/organism/live_engine.py`
- **Problem:** Entries‑blocked path returns before equity curve update, Prometheus export, and invariant checks.
- **Fix:** Do not return early; instead set `result` flags and still execute metric export and invariant checks, or introduce a dedicated “degraded tick footer” that always runs.
- **Risk if not fixed:** The system is least observable during the conditions where you most need observability.

### P2 Important

**Wire Prometheus counters to match their semantic intent**
- **Where:** `backend/organism/live_engine.py`
- **Fix:** Increment `ORGANISM_SECTOR_CAP_BLOCKED` at the sector‑gate block site; treat “exits skipped no data” as “fallback used” (not only “safety net fired”), or rename counter to match actual behavior.
- **Risk if not fixed:** Monitoring won’t detect real‑world degradation patterns.

**Add tests for the true safety invariants**
- **Where:** test suite; at minimum add tests that:
  - simulate insufficient features with open positions and assert exits still run,
  - assert entries‑blocked runs exits + reconciliation,
  - validate planned‑entries sector logic across both candidate loops,
  - validate evolution clamp semantics at the level of absolute live parameters,
  - validate end‑to‑end TIF behavior.

### P3 Enhancements

**Clarify documentation boundaries**
- **Where:** `docs/PLATFORM_COMPLETE_GUIDE.md` and blueprint docs
- **Fix:** Align feature count statements; explicitly label which parameters are “initial defaults” vs “runtime‑evolved,” and document bounds/guards.

**State persistence verification**
- **Where:** `backend/organism/brain_persistence.py`
- **Fix:** Provide an explicit, testable “crash consistency contract” (atomic write, manifest validation, rollback rules) and add tests that simulate partial writes and restarts.

