# Track DD4 v10 — Strategy Logic Phase 4

**Branch**: `rc-1.5-curated` @ `c048103` (workdir HEAD; instructions reference `35a1fe9` baseline). **Method**: read-only; brain manifest reads + `./venv/bin/python` for arithmetic; no writes.

Brain snapshot inspected:
- `organism_brain/manifest.json` — `total_trades=498`, `generation=168`, `saved_at=2026-05-03T06:11:45Z`.
- `organism_brain/evolved_params.json` — `symbol_fitness={}` (still empty at gen 168), `symbol_trade_counts` 17 entries summing to **62**.
- `organism_brain/trade_history.csv` — 498 rows; 491 non-reconciliation; `symbol_trade_counts` (real) sums to **491** (e.g. QQQ=61, NVDA=46, XLE=39, XLK=32, AMZN=27).

The 62-vs-491 gap is the central finding. It is structural (gating-related), not arithmetic.

---

## Finding DD4-1 — `evolved_params.json` is promotion-gated; `symbol_trade_counts` chronically lags trade_history, breaking the wave-44 fitness gate

**Severity**: HIGH (silently neuters DD3-5 fix and the entire fitness-gate mechanism)

**Citation chain**:
- `backend/organism/live_engine.py:5542-5545` — increments `evolved_params.symbol_trade_counts[sym]` in-memory per non-reconciliation trade.
- `backend/organism/brain_persistence.py:798-801` — `evolved_params.json` is **explicitly listed as promotion-gated** in the `save_essential_state` docstring: *"NOT written (promotion-gated): … evolved_params.json (evolved strategy params — only on gate pass)"*.
- `backend/organism/brain_persistence.py:455` — `_save_evolved_params` is only called inside the full atomic-swap `save()` path, behind the walk-forward gate.
- `backend/organism/live_engine.py:870-894` — wave-44 DD3-5 fix reads `self.evolved_params.symbol_trade_counts` (in-memory), so during a single process run the counter can grow. But on every restart, the gated file is the only restore source, and it is stale.

**Empirical evidence**:
- trade_history.csv non-recon: 491 trades across 30+ symbols, many ≥10.
  - QQQ=61, NVDA=46, XLE=39, XLK=32, AMZN=27, SPY=26, AVGO=24, XOM=23, IWM=22, TSLA=19, CRM=15, WMT=15, MSFT=15, AAPL=13, COIN=12, GOOGL=11, PSQ=11, PLTR=10, AMD=10.
- Persisted `evolved_params.symbol_trade_counts`: 17 entries summing to 62. Only XLE=10 reaches the `_MIN_TRADES_FOR_FITNESS_GATE=10` threshold (`live_engine.py:3058`).

**Behavioral consequence**:
- Brain has effectively never had `symbol_fitness` populated (gen 168, `symbol_fitness={}`) because each evolve cycle reads the gated-stale `symbol_trade_counts` of <10 → `_evolve_symbol_fitness` short-circuits at `self_evolution.py:662-665` (`sym_count < _MIN_TRADES_FOR_FITNESS: keep at neutral 0.5; continue`).
- The wave-44 DD3-5 hard-block at `live_engine.py:874-886` only triggers when `_sym_trade_count >= 10`. Because the persisted counter resets toward zero on every brain reload (after a process restart), the gate engages for at most one symbol (XLE) at any given time.
- Fitness gate is **defeated by stale data**: a fix that reads stale state from a promotion-gated file can never converge. `symbol_trade_counts` should be runtime-truth (companion to learning_state.json), not promotion-gated.

**Suggested follow-up (out of scope)**: split `symbol_trade_counts` and `symbol_fitness` — counters are runtime truth (always-saved like learning_state); fitness EMAs remain promotion-gated. Or: gate full save more loosely so trade-counter persistence keeps pace.

---

## Finding DD4-2 — Pyramid Layer-2 R-multiple inflated by reconcile-fill collapse; Layer 2 effectively unreachable for typical trades

**Severity**: HIGH (Layer 2 path was the wave-44 DD3-1 closure target; collapse design re-opens it)

**Citation chain**:
- `backend/organism/pyramider.py:237` — `entry = position.layers[0].entry_price`.
- `backend/organism/pyramider.py:289, 308` — Layer 1 keys on `max_level == 0`, Layer 2 keys on `max_level == 1` (wave-44 fix).
- `backend/organism/live_engine.py:5325-5340` — `_reconcile_fills` collapses `pyr.layers` into a *single* PyramidLevel whose `entry_price = broker_avg_entry_price`. The wave-44 patch at line 5333 advances `highest_level` from 0→1 when broker qty grew, which fixes max_level reachability but does **not** fix the entry-price baseline.

**Math** (60% / 30% / 10% layer schedule, entry $100, ATR $1):
- Original L0 fill: 60 shares @ $100. R-baseline = $100. L1 trigger (+1.5R) = $101.50. L2 trigger (+3.0R) = $103.00.
- L1 fills: 30 shares @ ≈$101.50. Broker `avg_entry_price` = (60·100 + 30·101.5) / 90 = **$100.50**.
- After `_reconcile_fills` collapse: `pyr.layers = [PyramidLevel(shares=90, entry_price=100.50, level=1)]`.
- Pyramider next tick: `entry = layers[0].entry_price = 100.50`. To fire L2: `r_current = (P − 100.5) / 1 ≥ 3.0` ⇒ `P ≥ $103.50`.
- **Effective L2 trigger inflates by 0.5R for the Layer-1 schedule**, and would inflate by ~0.6R for typical pyramids (more if L1 fills above 1.5R from slippage).

**Empirical evidence**:
- 498 trades; zero `entry_source` rows tagged "pyramid Layer 2"; pyramider's `_pyramid_count` and `_max_layers_reached` counters (`pyramider.py:203-204, 296, 316-317`) are write-only — never read or telemetered (verified by `grep` returning only the definition + write sites).
- Pyramid-related exits in 498-trade sample: 133 `pyramid_cut_*` (L1 negative), 0 reaching pyramid-success exit reason.
- The wave-44 commit comment at `pyramider.py:286-288` claims the fix prevents Layer 1 from re-firing — but does not address the R-baseline inflation that makes Layer 2 itself harder to reach.

**Behavioral test**:
1. Set initial entry $100, ATR $1, target_total_shares=100.
2. Process L0 fill (60 shares).
3. Run `check_pyramid` at $101.5 → expect L1 add.
4. Simulate broker reconciliation collapsing layers to `[PyramidLevel(90, $100.50, level=1)]`.
5. Run `check_pyramid` at $103.00. Pre-fix expectation per docstring (`pyramider.py:181`): "Layer 2: 10% at +3.0R (parabolic move)" — should add. Actual: no add (r_current = 2.5R, below 3.0 threshold).

---

## Finding DD4-3 — Inverse-ETF regime-flip composability gap (DD2-6) remains open in Phase-4 audit window

**Severity**: MEDIUM (sizing + exits read non-flipped regime for SH/PSQ trades)

**Citation chain**:
- `backend/organism/alpha_scanner.py:82` — `INVERSE_ETFS = {"SH","PSQ","DOG","RWM"}`.
- `backend/organism/alpha_scanner.py:319-332` — `_regime_alignment` flips trending_up↔trending_down when `symbol in INVERSE_ETFS`.
- `backend/organism/kelly_sizer.py` — full file grep: zero references to `INVERSE_ETFS`, `SH`, `PSQ`, `inverse`. Kelly sizer reads the unflipped regime label.
- `backend/organism/adaptive_exits.py` — full file grep: zero references to inverse-ETFs. ATR scale `trending_down=2.5` vs `trending_up=3.5` (per memory) is applied to the *unflipped* regime — so a BUY of SH in `trending_down` (which alpha scanner correctly treats as aligned long) gets the trending_down ATR (tighter stop), inconsistent with the alpha-side semantics.

**Empirical evidence**:
- Brain `symbol_trade_counts` records SH=6, PSQ=4 (per `evolved_params.json`); recent trade_history shows 8 SH + 11 PSQ non-recon trades. Sample exits:
  - SH `max_holding_period` pnl=$9.36, PSQ `max_holding_period` pnl=$9.65, PSQ `pyramid_cut_full_at_-1.6R` pnl=−$1.47.
- For these trades, Kelly used the unflipped regime size scale and adaptive_exits set the unflipped ATR scale.

**Verdict**: DD2-6 (deferred from V8) remains entirely open in Phase 4. The inverse-ETF flip is implemented in exactly one file (`alpha_scanner.py`) and not propagated to Kelly, AdaptiveExits, or symbol_cooldown.

---

## Finding DD4-4 — `_pyramid_count` / `_max_layers_reached` counters are write-only; Layer-2 reachability cannot be observed from telemetry

**Severity**: LOW (operational/observability — but blocks DD3-1 self-monitoring and any future DD verification)

**Citation chain**:
- `backend/organism/pyramider.py:203-204` — counters initialized.
- `backend/organism/pyramider.py:296, 316-317` — incremented on L1 / L2 adds.
- `grep -rn "_pyramid_count\|_max_layers_reached" backend/ --include='*.py'` returns **only** the four lines above. No reader, no telemetry, no log message, no brain persistence.

**Behavioral consequence**: Even if DD4-2's R-baseline inflation were fixed, there's no way to verify Layer-2 reach from the manifest or trade_history. Pyramid telemetry must be reconstructed by parsing `pyramid_add` order submissions in broker logs (`live_engine.py:2929` reason="pyramid_add"). The audit prompt's question 2 ("how many were Layer 1 vs Layer 2?") is unanswerable from current artifacts.

---

## Finding DD4-5 — Calibration counts post-Wave-33 look healthy (no anti-finding); confirms ML-axis fix held

**Severity**: INFO (positive verification — no defect)

**Citation chain**: `organism_brain/ml_state.json` → `calibration.counts`:
```
[[0, 0], [53, 168], [36, 134], [22, 52], [0, 2]]
```
Bin 0: empty (raw_confidence < 0.50 never recorded — expected since predict thresholds at ~0.50).
Bins 1-3: populated with 354 total observations, win-rates 31.5% / 26.9% / 42.3% — distribution is reasonable (bin 4 essentially empty with 2 obs is fine; high-confidence predictions are rare).

This rules out the "all observations in bin 4" pathology that would indicate axis confusion. The wave-33 raw_confidence pass at `live_engine.py:5622-5628` is correctly recording outcomes.

---

## Verification of items NOT flagged (positive checks)

- **ML-reversal one-shot guard** (audit prompt #5): `_ml_reversal_used.discard(sym)` is correctly called in both close paths — `live_engine.py:5417` (no-exit-price cleanup) and `live_engine.py:5633` (normal close). Symbol can re-trigger ML-reversal on subsequent positions.
- **Stop-loss precedence** (audit prompt #7): deterministic ordering verified.
  - `adaptive_exits.py:390-400` — max_loss_limit (priority 0) → stop_loss (priority 1), checked every tick before any new-bar logic.
  - `live_engine.py:2572-2602` — exit_engine first, ML reversal only fires `if not exit_sig.should_exit` (line 2580). Pyramid loop runs later (line 2880+) and short-circuits on `_exit_cooldown` (line 2892) so exit always wins over pyramid in the same tick. **Stop > ML reversal > pyramid is enforced.**
- **`_now_fn` re-grep** (audit prompt #10): `backend/organism/live_engine.py` clean — only 4 `datetime.now` references (lines 696, 2512, 6279, 6288). Lines 6279/6288 are inside `force_save_brain`, an admin/lifespan-triggered method (not in tick loop), so replay determinism is intact. No new violations from waves 41-49.

---

## TL;DR

The wave-44 DD3-5 fitness-gate fix is correct in code but *defeated in production* by a persistence-layer mismatch: `symbol_trade_counts` lives in `evolved_params.json`, which is promotion-gated by the walk-forward gate (`brain_persistence.py:798-801, 455`), so the counter persists at 62 across 17 symbols even though `trade_history.csv` shows 491 real trades across 30+ symbols. Only XLE clears the 10-trade threshold post-restart, meaning the gate hard-blocks at most one symbol at any time. Compounding this, `_evolve_symbol_fitness` reads the same stale counter and short-circuits to neutral 0.5 (`self_evolution.py:662-665`), explaining why `symbol_fitness` has stayed empty for 168 generations. Wave-44 also fixed pyramid Layer-2 max_level reachability (`pyramider.py:286-308`) but did not patch the deeper bug: `_reconcile_fills` collapses `pyr.layers` to a single layer at `broker_avg_entry_price` (`live_engine.py:5325-5340`), shifting `entry = layers[0].entry_price` upward by ~0.5R after Layer 1 fills, so the +3.0R Layer-2 trigger in price space is inflated to +3.5R measured from the original entry — Layer 2 effectively never fires for the standard 60/30/10 pyramid schedule. Inverse-ETF regime flip (DD2-6) remains a single-file feature in `alpha_scanner.py:319-332`; Kelly and AdaptiveExits still read the unflipped regime label for SH/PSQ trades. Calibration counts and replay-determinism greps came back clean.
