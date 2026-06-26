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
| 6 | Breakout: fold-in vs keep-distinct (documented + parity) | ⬜ todo |
| 7 | Extract mean_reversion (registered, `live_routing:false`) | ⬜ todo |
| 8 | `scripts/strategy_backtester.py` — OOS/costed (checkpoint #2) | ⬜ todo |
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
