# Track DD5 v11 — Strategy Logic Phase 5

**Repo**: `/Users/marselkei/VS/intra`
**Branch**: `main` @ `3778344` (note: prompt asked for `rc-1.5-curated` @ `11c2275`; current HEAD is `main` @ `3778344` which contains all wave-53 / wave-60 fixes)
**Brain manifest**: `total_runs=1944, generation=168, total_trades=498, saved_at=2026-05-03T18:30:01Z`
**Trade-history range**: 2026-03-30 → 2026-05-01 (last close), 498 rows (491 non-recon, 7 reconciliation)
**Method**: read-only review of source + brain artifacts under `organism_brain/`. No live runtime logs available; analysis based on brain manifest + trade history.

---

## Findings

### DD5-1 (HIGH) — Chop-min-hold pyramid_cut gate compares **ticks** to a **bars** constant; gate effectively never fires for short-bars-held cuts

**Source**: `backend/organism/live_engine.py:3026-3042`

```python
_CHOP_MIN_HOLD_BARS = 10
_is_chop = (regime == "chop")
_meta = self._entry_metadata.get(sym, {})
_entry_tick = _meta.get("entry_tick", 0)
_bars_held = self._tick_count - _entry_tick     # ← TICKS, not bars
if _is_chop and _bars_held < _CHOP_MIN_HOLD_BARS:
    ...
    continue
```

`self._tick_count` is incremented **once per `step()` call** (live_engine.py:1781) — i.e. once per market-data tick from the Alpaca streamer, not once per 1-minute bar. The constant `_CHOP_MIN_HOLD_BARS = 10` is named in **bars** and was sized to suppress short-held losers. On 1-min bars there are typically dozens of ticks per bar, so `_tick_count - entry_tick` is order-of-magnitude larger than the bar count and almost always exceeds 10 within the first few seconds. The gate is functionally a no-op.

**Empirical confirmation** from the last 50 non-recon trades (2026-04-29 → 2026-05-01):

| metric | value |
|---|---|
| pyramid_cut closes | 18 |
| pyramid_cuts with `bars_held_at_exit < 10` | 8 |
| of those, `regime_at_entry == "chop"` | 8 / 8 |

Sample short-held chop pyramid_cuts that the gate was supposed to suppress:

```
XLK   bars=4  chop  pyramid_cut_full_at_-3.0R
XLK   bars=7  chop  pyramid_cut_full_at_-1.6R
MSFT  bars=8  chop  pyramid_cut_full_at_-2.6R
MSFT  bars=6  chop  pyramid_cut_full_at_-1.2R
CRM   bars=8  chop  pyramid_cut_full_at_-1.3R
XLE   bars=6  chop  pyramid_cut_full_at_-1.3R
AMZN  bars=9  chop  pyramid_cut_full_at_-1.0R
GOOGL bars=7  chop  pyramid_cut_full_at_-1.7R
```

For comparison, `bars_held` recorded in `trade_history.csv` is sourced from `_exit_lvl.bars_held` (live_engine.py:5561) which is incremented exclusively in the `is_new_bar` branch of `AdaptiveExitEngine.check_exit` (`adaptive_exits.py:419`). That is the correct bar-count.

**Fix**: replace L3030 with bar-derived count (e.g. `self._exit_levels[sym].bars_held` or compare against `entry_metadata["entry_bar_count"]`), or replace the constant with a tick-equivalent of ≈ 10 bars * (ticks-per-bar). V9 DD3-6 reported "3 of 5 short-bars-held cuts not suppressed"; current data shows the true rate is 8 / 8, i.e. the gate is silently inert.

---

### DD5-2 (HIGH) — Wave-60 inverse-ETF helper landed in 3 of 4 consumers; live_engine still carries a private 2-symbol subset

**Source**: `backend/organism/regime.py:41-81` (canonical), `backend/organism/live_engine.py:4020-4045` (private subset)

Wave-60 introduced `effective_regime_for_symbol(regime, symbol)` and the canonical universe `_INVERSE_ETFS = {"SH","PSQ","DOG","RWM"}`, and migrated `kelly_sizer.py:346-347`, `adaptive_exits.py:281-282`, and `alpha_scanner.py:333-359`. **`live_engine.py` was not migrated** and instead retains a hand-rolled

```python
_INVERSE_ETFS_CHOP_SUPPRESSED = frozenset({"PSQ", "SH"})  # missing DOG, RWM
```

at line 4021, used to skip inverse-ETF entries during `regime == "chop"`. Two consequences:

1. **DOG and RWM bypass the chop suppressor.** They are flipped correctly inside Kelly / exits / alpha (per the canonical helper) but not chop-suppressed at the entry-block stage. If alpha promotes DOG/RWM in chop, the order will issue.
2. **Two sources of truth.** The header comment in `regime.py:43-46` explicitly states "Previously each consumer carried its own definition (alpha_scanner.INVERSE_ETFS = {"SH","PSQ","DOG","RWM"}; live_engine._INVERSE_ETFS_CHOP_SUPPRESSED = {"PSQ","SH"}); now unified." But the live_engine constant was not removed during wave-60 — only the alpha_scanner's was. Wave-60 migration is incomplete.

Empirical SH/PSQ trade history (491 non-recon trades, all `direction=1.0`):

```
SH/PSQ:DOG/RWM = 19 trades : 0 trades
chop entries:   15 / 19   (last 2026-04-15)
trending_up:     3 / 19   (Exp2 chop-suppress took effect after 2026-04-15)
```

The 15 chop-entry inverse-ETF trades were all losers — exactly the population Exp2 was designed to block. Note that `effective_regime_for_symbol("chop", "SH")` returns `"chop"` unchanged (only TRENDING_UP↔TRENDING_DOWN flip), so even after wave-60, the chop suppressor remains the only line of defense for the chop case — and it lives only in live_engine.py, only for SH/PSQ.

**Fix**: replace the local frozenset with `is_inverse_etf(sz.symbol)` from `regime.py`, then either (a) accept that DOG/RWM should also be chop-suppressed or (b) move the chop-suppression logic into the canonical helper as a 4th consumer.

---

### DD5-3 (HIGH) — `symbol_trade_counts_runtime` persisted by wave-53 is **identical to the promotion-gated `evolved_params.symbol_trade_counts`** and divergent from actual trade history

**Source**: `backend/organism/live_engine.py:5638-5646` (single-source increment), `:6313-6322` (persist), `:1232-1266` (restore)

Wave-53 was meant to expose a runtime-tracked counter that is independent of evolution-promotion freezes. Both keys are now persisted in `extra_counters.json` and `evolved_params.json` respectively, but they hold **the exact same values**:

| key | sum |
|---|---|
| `extra_counters.symbol_trade_counts_runtime` | 62 |
| `evolved_params.symbol_trade_counts` | 62 |
| non-reconciliation rows in `trade_history.csv` | **491** |

Per-symbol reconciliation (selected):

```
QQQ:    runtime=3   promoted=3   trade_history=61   diff=58
NVDA:   runtime=2   promoted=2   trade_history=46   diff=44
XLE:    runtime=10  promoted=10  trade_history=39   diff=29
AMZN:   runtime=3   promoted=3   trade_history=27   diff=24
SPY:    runtime=5   promoted=5   trade_history=26   diff=21
TSLA:   runtime=3   promoted=3   trade_history=19   diff=16
WMT:    runtime=0   promoted=0   trade_history=15   diff=15
AVGO:   runtime=0   promoted=0   trade_history=24   diff=24
CRM:    runtime=1   promoted=1   trade_history=15   diff=14
COIN:   runtime=0   promoted=0   trade_history=12   diff=12
PLTR:   runtime=0   promoted=0   trade_history=10   diff=10
```

A search for any contiguous tail-window of `trade_history.csv` whose per-symbol counts equal `symbol_trade_counts_runtime` returns **no exact match** (closest tail-of-14 trades has L1-norm diff = 52, first close=2026-05-01). The runtime counter is therefore not "trades since the last cold start" either.

Two structural problems explain this:

1. The wave-53 increment site (`live_engine.py:5644-5645`) writes only to `evolved_params.symbol_trade_counts` — there is no separate `extra_counters["symbol_trade_counts_runtime"]` accumulator. The persistence path (`:6320-6322`) snapshots `evolved_params.symbol_trade_counts` into `extra_counters["symbol_trade_counts_runtime"]` at save time, so by construction the two are always equal at-rest. The "runtime vs promoted" distinction the wave-53 commit message advertises does not exist on the increment side.
2. The fitness gate at `live_engine.py:886` (`params.symbol_trade_counts.get(sym, 0)`) and `:4522` (`evolved_params.symbol_trade_counts.get(c.symbol, 0)`) read the same key. So even if (1) were fixed, the fitness gate is still using the (currently stale-by-x4-x5) counter and gating on it — the V10 DD4-1 stale-62 issue is intact in production.

The 491-trade non-recon population is not the only source of truth (recon adjustments, exploration-flagged trades, and pre-counter-tracking history all warp the picture), but the order-of-magnitude gap (62 vs 491) is far larger than any of these factors can explain.

**Fix**: either (a) accumulate `extra_counters["symbol_trade_counts_runtime"]` independently in the close-path so it reflects the true post-restart trade count, or (b) bootstrap `evolved_params.symbol_trade_counts` from `trade_history.csv` non-recon rows on startup so the fitness gate sees actual counts.

---

### DD5-4 (MEDIUM) — `MomentumPyramider.telemetry()` is exported but never read

**Source**: `backend/organism/pyramider.py:206-218`

Wave-53 DD4-4 added a `telemetry()` method to expose `_pyramid_count` and `_max_layers_reached` so DD3-1/DD4-2 fixes could be verified at runtime. Repo grep:

```
$ grep -rn "pyramider.telemetry\|self.pyramider\.telemetry\|pyramider\.telemetry" backend/
(no matches)
```

The counter is also not snapshotted into `extra_counters.json` (`pyramid_count_total` and `max_layers_reached` keys are absent from the live brain). DD4-4 is therefore implementation-only; the pyramid counters remain write-only at runtime, identical to the pre-wave-53 state.

The trade-history file has no `pyramid_action` or `level` columns either, so there is currently no way to verify that DD4-2's L0-entry-preservation fix produces level-2 adds in production. Fix: include `self.pyramider.telemetry()` in the per-tick `LiveTickResult` or in the brain manifest export at `live_engine.py:6313-6322` so the counters are observable.

---

### DD5-5 (MEDIUM) — Edge concentration on AMD persists; non-top-2 last-60 Sharpe is negative

**Source**: `organism_brain/trade_history.csv` (last 60 non-reconciliation rows, 2026-04-28 → 2026-05-01)

| metric | value |
|---|---|
| total PnL | $29.45 |
| mean PnL/trade | $0.49 |
| top-2 winners | AMD +$51.45, IWM +$11.34 |
| mean PnL/trade excl. top-2 | **−$0.57** |
| std excl. top-2 | $4.01 |
| per-trade Sharpe excl. top-2 | **−0.143** |
| top-3 symbols share of total PnL | **216.7%** (AMD $32.33, IWM $16.92, WMT $14.56 vs aggregate $29.45) |

V9 DD3-6 had reported AMD-concentrated edge; the post-wave-53 window (last 60 trades) shows the situation is worse — without AMD's single +$51.45 max-holding-period winner on 2026-05-01, the rest of the book is negative on the trailing 60 trades. This is not a bug per se, but the gating thesis ("breadth has improved post-fix") is empirically wrong for this window.

---

## Observations (no findings)

- **`_ml_reversal_used` cycle is balanced.** add at `live_engine.py:2659`; discard at `:5518` (no-exit-price cleanup) and `:5734` (normal close); daily clear at `:2205`; persistence list at `:6300`; restore at `:1230`. No leak path identified.

- **No post-deploy trades.** Wave-53 commit timestamp is 2026-05-03T17:19Z, but the last `closed_at` in `trade_history.csv` is 2026-05-01T19:42Z (Friday close). No post-wave-53 production data exists yet — most DD5 verifications hinge on a Monday session that hasn't happened.

- **Calibration counts not yet uniform.** `ml_state.calibration.counts = [[0,0],[53,168],[36,134],[22,52],[0,2]]`. Probability mass is concentrated in bins 1-3 (95% of samples); bin 0 and bin 4 are empty / near-empty. Either the predictor's output range is too narrow or the bin edges are mis-calibrated. V8 wave-33 axis-binning fix did not produce a uniform distribution as DD5 anticipated.

- **`regime_state.json` history is empty.** Cannot evaluate fast-flip-day hysteresis empirically; the persisted history list is `[]` (saved while the engine wasn't actively detecting). DD2-4 hysteresis logic itself is intact at `regime.py:317-334`.

- **Recent `entry_source` distribution looks healthy** (last 50 trades: 31 alpha+breakout, 16 breakout, 2 alpha, 1 blank). Memory note about pre-2026-05-01 source-tag corruption applies to older rows only.

- **`pyramid_positions` in extra_counters is empty (`{}`)**. Either no live position when the brain saved, or restoration cleared it. Cannot verify pyramid layer collapse in production from the manifest alone.

---

## Quality bar
5 findings (3 HIGH, 2 MEDIUM) plus 5 observations. Within the 2-5 finding bar.
