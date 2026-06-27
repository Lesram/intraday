# Intra 2.0 — Phase 1 (Strategy Framework Extraction)

Status ledger + binding decisions for the Phase-1 refactor: every trading
strategy behind a shared `Strategy` contract, params externalized to config,
routed through a `StrategySelector`, with an OOS backtester — all flag-gated and
**behavior-preserving for the live momentum book** (parity is acceptance #1).

## Binding rules (from the plan)
- **Rule A — modularizing ≠ endorsing.** A strategy can be registered and
  measured without influencing capital. `live_routing` in `strategy_config.py`
  gates CAPITAL, not measurement. Today only `momentum` is `live_routing:true`
  (and still unproven); `mean_reversion` (evidence-negative after costs) and
  `orb` (unbuilt) are backtest/shadow benchmarks.
- **Rule B — the backtester is OOS/cost-disciplined by construction.** Net
  expectancy > 0 at t≥2 out-of-sample, costed. See the step-8 guardrail below.

## Step status
| # | Step | State |
|---|------|-------|
| 1 | `Strategy` contract + registry + `Candidate` | ✅ done |
| 2 | Externalize config (verbatim values) | ✅ done |
| 3 | Extract momentum onto the contract | ✅ done — direction parity proven (29k grid) |
| 4 | `StrategySelector` (Rule-A routing + stand-down) | ✅ done |
| 5 | **Thin seam: engine routes entry DIRECTION via framework; prove parity** | ✅ done — engine-level parity proven (below) |
| 6 | Breakout: fold-in vs keep-distinct (documented + parity) | ✅ done — **KEEP DISTINCT**; extracted to contract (below) |
| 7 | Extract mean_reversion (registered, `live_routing:false`) | ✅ done — registered benchmark (below) |
| 8 | `scripts/strategy_backtester.py` — OOS/costed (checkpoint #2) | ✅ done — methodology proven (below) |
| 9 | Build ORB to contract + dynamic in-play universe | ⬜ todo |
| 10 | Park EOD + docs | ⬜ in progress (this doc) |
| **5b** | **Confidence/sizing extraction — REDESIGN, own parity gate** | ⛔ DEFERRED (named, see below) |
| **5c** | **Selector regime-policy reconciliation** | ⛔ DEFERRED (named, see below) |

## Step 5 — the thin seam (done)
**Decision: thin seam, not faithful confidence extraction.** In live mode the
framework supplies only what is provably pure — per-symbol entry **direction** —
applied to `alpha_scanner`'s existing candidate universe. Universe selection,
regime gating, confidence, entry gates, ranking, Kelly sizing, and exits stay
**byte-identical in the engine**. Parity is therefore structural: the scoring/
sizing code is literally unchanged.

Why not faithful extraction now: the live confidence that drives sizing AND the
entry gate AND top_n ranking is a 3-input composite
`0.39·readiness + 0.26·squeeze + 0.35·tension` (`live_engine.py` ~4133,
`alpha_scanner.py:178`), where `tension` isn't even in the strategy feature
contract. Re-deriving all of that byte-identically (plus the ML/no-ML branch and
gate constants) is a large, fragile surface that would fail parity repeatedly and
is **not required** for Phase 1's goal.

Mechanics (`live_engine.py`):
- `FRAMEWORK_ROUTING_ENABLED` (env `ORGANISM_FRAMEWORK_ROUTING`, **default off**).
- `_scan_entry_candidates()` helper (outside the LOC-pinned `_live_tick_inner`):
  flag-off returns `alpha_scanner.scan(...)` unchanged; flag-on re-sources each
  candidate's `.direction` through `StrategySelector` (momentum-only, live mode).
  The seam self-activates only when `DROP_ML_FROM_GATE` is also on (the regime
  the framework models). A `logger.error("FRAMEWORK SEAM MISMATCH …")` tripwire
  fires if framework and scanner ever disagree (impossible by the 29k parity).

### Parity evidence (acceptance #5)
- **Candidate level** (`tests/test_seam_parity.py`): flag-on == flag-off across
  every entry archetype × every regime × both ml-isolation states; tripwire
  silent; a teeth-test proves the override is live and the tripwire fires on a
  forced divergence.
- **Engine level** (`scripts/verify_seam_parity.py`): real engine, flag-off vs
  flag-on over a momentum-trading window (4 round-trips, traverses trending_up).
  **Identical** entered-set + sequence + share counts + entry reasons; identical
  exit reasons + sizes (`horizon_timeout`, `failure_to_follow`); identical
  closed-trade ledger and equity curve. Asserts the window actually traded and
  hit trending_up, so the proof is not vacuous. `PARITY HOLDS ✓`.

## Step 6 — breakout: KEEP DISTINCT (done)
**Decision: keep distinct, do NOT fold into momentum.** The live engine has a
separate *pure-breakout* capital path (`live_engine.py` ~4302-4371): after alpha/
momentum candidates, it takes up to `_MAX_PURE_BREAKOUT=2` `BreakoutScanner`
signals **not already in the alpha set**, with `composite >= 0.55`, forces
`direction=1.0` (long), and routes them. So breakout independently enters symbols
momentum's `_observable_direction` never flags.

Why not fold in (parity-grounded):
- Folding would either **drop** the pure-breakout entries (momentum doesn't
  generate them) — a parity break — or force momentum to **replicate the entire
  6-factor BreakoutScanner composite** (squeeze/volume/contraction/RS/pivot/flow),
  conflating two genuinely different signals. Both are wrong.
- Keep-distinct matches the framework: breakout is its own `Strategy`; the
  selector aggregates momentum + breakout candidates on the shared confidence
  axis.

Extraction (`backend/organism/strategies/breakout.py`, thin-seam discipline):
`BreakoutStrategy` wraps the **unchanged** `BreakoutScanner` (configured verbatim
from `strategy_config.py`, incl. the intraday-scaled lookbacks 80/40/200/80) and
reproduces only the live entry decision — surface scanner signals with
`composite >= entry_composite_threshold (0.55)` as **long** candidates. Config
block `breakout` added with `live_routing:true` (a live capital path today, still
unproven, like momentum). Tests (`tests/test_breakout_strategy.py`): registry +
verbatim config, fail-closed validate, threshold filter, long-only force,
short-emitted when long_only off, and real-data parity (adapter surfaces exactly
the scanner's signals).

**Deferred for breakout (named):** the engine *routing* of pure-breakout — the
dedup-vs-momentum, the per-tick cap of 2, and ranking interplay — are
selector/engine concerns, NOT the strategy's, and are deferred to the routing
step (with 5c regime reconciliation, since breakout has no hard live regime gate).
Confidence-for-sizing is 5b (though live breakout confidence = `min(composite,1)`
is already simple, not the anti-predictive momentum composite).

## Step 7 — mean_reversion: registered benchmark (done)
Extracted `backend/organism/strategies/mean_reversion.py` (`MeanReversionStrategy`
wraps the unchanged `MeanReversionScanner`, verbatim config incl. the live MR_*
env values — top_n=3, cooldown=60, long_only, 9:45-15:30 ET window).
`live_routing:false` (Rule A): MR is **evidence-negative** after costs (gross
bounce ~1.7-2.2bps < ~4bps round-trip; net-negative in every sweep incl. the
residual variant). So it's REGISTERED and MEASURED but never routes capital —
the selector confirms it: built in live mode, eligible in chop only under
backtest mode, gated off in live (`test_rule_a_mean_reversion_measured_not_routed`).

No live-parity obligation (it isn't a capital path). Confidence mirrors the live
MR composite exactly: `min(1, 0.30 + 0.15*abs_distance_atr)` (`live_engine`
~4770). `now` for the entry-window + causal VWAP is read from the feature frames'
latest bar timestamp (contract convention: a FeatureFrame is as-of-now); no
timestamp ⇒ stand down. Flipping it live requires a STRUCTURAL change
(cost/horizon/instrument) that is OOS-positive at t≥2 — not a config toggle.

## Step 8 — OOS cost-disciplined backtester (done, checkpoint #2)
`scripts/strategy_backtester.py` (`run_backtest`, `BacktestConfig`,
`BacktestResult`). The scoreboard that decides routing flips for `live_routing:
false` strategies and re-confirms momentum/breakout.

OOS/costed **by construction** (Rule B):
- Features from the SAME live function (`compute_ml_features`) — online/offline
  parity.
- At bar t the strategy scans only `features[:t+1]` (causal); regime is detected
  causally from SPY, feeding the stateful detector bar-by-bar like live.
- Entry = OPEN of bar `t+entry_lag` (`entry_lag>=1` ⇒ strictly after the signal,
  no same-bar fill ⇒ out-of-sample); exit `horizon` bars later.
- Every trade costed (round-trip bps, `backend.organism.costing`).
- **Acceptance gate (Rule B): net expectancy > 0 AND t_stat >= 2** on costed OOS
  trades (`accepted` per strategy).

**Guardrail decision (the step-8 fork): SIGNAL significance, labeled — NOT live
P&L.** Trades are sized FLAT (fixed notional). Routing through the live
confidence/Kelly composite would measure a known defect (anti-predictive,
corr=-0.112, deferred 5b), so flat sizing answers "does the signal have edge?"
comparably across strategies. The result object self-labels this (`sizing_label`)
and the report prints it. Live-P&L-grade significance waits on 5b.

Methodology proven in `tests/test_strategy_backtester.py`: OOS (entry strictly
after signal, exit within data), costs applied (net<gross), gate semantics,
honest label, regime-eligibility routing, determinism. (Validates the harness,
not that a synthetic strategy is profitable — edge is a data question.)

## DEFERRED — named, with their own gates (do NOT let "Phase 1 done" hide these)

### Step 5b — confidence/sizing ownership (a REDESIGN, not a port)
Today confidence (hence Kelly size, the entry gate, and top_n ranking) still
lives in the engine. Moving it into the `Strategy` contract is deferred to its
own step **with its own parity/quality gate**.

**Critical:** the goal is NOT to faithfully replicate the live composite. The
live code itself records `corr(confidence, correct_direction) = -0.112` — the
composite is **anti-predictive** (it sizes up the trades more likely to be
wrong). Faithfully porting it would enshrine a known defect (the pyramiding
mistake in a new costume). So 5b treats "what should confidence be" as an open
redesign question; **flat sizing is a legitimate baseline candidate** and would
let us measure whether the composite adds anything but noise. Gate: a candidate
confidence model must beat flat sizing on costed OOS expectancy before it routes.

### Step 5c — selector regime-policy reconciliation
`momentum.eligible_regimes = {trending_up, high_vol}` does **not** match the live
engine's actual regime behavior (it also acts in chop/trending_down with
graduated handling: trending_down→exploration-route, chop→defensive conf
threshold, high_vol/stress→raised composite threshold). The step-5 seam therefore
re-sources DIRECTION only and leaves regime authority in the engine. Making the
selector's regime policy authoritative requires first reconciling
`eligible_regimes` with the engine's real behavior, then a fresh parity proof.

## Step 8 guardrail — backtester sizing honesty (decide on purpose)
If live sizing stays in the engine (per 5b deferral) but the backtester sizes
momentum by the raw-readiness `Candidate.confidence` proxy, then backtest
sizing ≠ live sizing. That's fine for comparing strategies **against each other**
(consistent within the backtester), but the absolute t≥2 OOS edge t-stat it
produces is **not** the t-stat live would achieve. We've already been burned once
by a backtest surface that ran rosier than live. So step 8 must EITHER route the
backtester through the real Kelly/confidence path, OR label its output explicitly
as "signal significance, not live-P&L significance." Pick one deliberately;
never let it happen silently.
