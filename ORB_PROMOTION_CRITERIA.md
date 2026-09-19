# ORB Stocks-in-Play — Validation Framework & Promotion Criteria

**Status:** SHADOW telemetry live (commit `500a868`). Promotion to live entry path requires evidence below.
**Author:** weekend sprint v3, R4
**Builds on:** RESEARCH_DEEP_DIVE_REPORT.md (research basis), tests/test_orb_scanner.py (unit), tests/test_orb_shadow_wiring.py (integration)

---

## What's already in place

✅ **`backend/organism/orb_scanner.py`** — ORBScanner class, 14 unit tests pass
✅ **`backend/organism/live_engine.py`** — instantiated, scan called each tick after regime detection
✅ **Shadow logging** — `ORB shadow BREAKOUT:` log lines, periodic summaries
✅ **Wiring guarantees** — no mark_fired calls, no cand_dicts append, exceptions caught
✅ **Daily reset** — scanner state clears at session boundary
✅ **Time gating** — 9:30-9:35 ET ORB window + 9:35-15:55 ET decision window

## What's NOT yet in place

❌ Live entry path for ORB candidates
❌ Position sizing pathway specific to ORB (currently would route through Kelly with ORB-anchored stop)
❌ Shadow simulation of ORB outcomes (what would have happened if we'd entered)
❌ Backtest runner that compares baseline vs ORB-augmented paths
❌ Operator dashboard for shadow disagreements

---

## Validation phases

### Phase A — Replay backtest (this session, post-Monday-deploy)

Goal: validate the ORB scanner runs correctly against real bars and produces sensible candidate counts.

Setup: same 14-day Alpaca bar cache used for the RC-1.5 baseline backtest. Run replay with the rc-1.5-curated branch.

Measurements per session:
- Total ORB candidates ranked (top-N=10 → expected: ~10/session)
- Total breakouts triggered (subset that crossed ORB high/low)
- Symbol overlap with alpha+breakout actual entries
- Time-of-day distribution of breakouts
- rv_ratio distribution of triggered breakouts

Pass criteria:
- ≥ 3 ORB breakout events per session on average (otherwise signal too sparse)
- ≤ 12 breakouts per session (otherwise signal too noisy / over-firing)
- Breakouts spread across multiple symbols (not concentrated in 1-2)
- rv_ratio distribution shows real high-RV outliers (median ≥ 2.0)

Fail action: revisit min_rv_ratio threshold and top_n. The paper used top-20 from 1000 universe; we have top-N from 22. Some recalibration likely needed.

### Phase B — 5 live shadow sessions (post-Monday RC-1.5 + first week)

Goal: confirm shadow telemetry is generating data in production conditions.

Measurements per session (post-close):
- `grep "ORB shadow BREAKOUT" logs/application.log | wc -l`
- Distinct symbols breaking out today
- Compare with alpha+breakout actual fires today (which symbols overlap?)

Pass criteria (cumulative across 5 sessions):
- 15+ total ORB breakout events logged
- Reasonable symbol distribution (not all NVDA every day)
- Logs show no exceptions / errors from the ORB scanner
- No live behavior change vs RC-1.5 baseline (verified by tick count, exit reason mix)

### Phase C — Hypothetical-outcome simulation (week 2 post-deploy)

Goal: project what ORB picks would have produced if entered.

Build a small post-hoc simulator: for each logged ORB breakout, look at the next bar after the trigger. Simulate:
- Entry at next bar's open + 5bps slippage
- Stop at the suggested stop price
- Hold to EOD or stop hit
- Compute realized PnL

Aggregate over the 5-10 sessions of shadow data:
- Total simulated trades
- Win rate
- Average PnL per simulated trade
- Sharpe (annualized, assuming 1 trade/day average)
- Max drawdown of the simulated equity curve

Pass criteria:
- Simulated win rate ≥ 25% (paper showed 17%; convex payoff)
- Simulated expectancy ≥ +$1.00 / trade (need positive net of slippage)
- Simulated Sharpe ≥ 0.5 (modest but positive — half of paper's haircut estimate)

Fail action: adjust entry timing (e.g., wait for confirmation bar), tighten min_rv_ratio, or shelve and revisit with paper-exact parameters.

### Phase D — Live promotion (week 3+ post-deploy, conditional)

If Phase A, B, C all pass:

1. Add a feature flag: `ORGANISM_ORB_LIVE_ENABLED=false` (default off).
2. When flag is on, ORB candidates flow into the entry pipeline alongside alpha+breakout, with `entry_source="orb_sip"` for telemetry.
3. ORB candidates pass through:
   - Same composite confidence formula (no special treatment)
   - Same RC-1.5 gate (composite ≥ 0.45 in chop, etc.)
   - Same Kelly sizer + risk-budget cap
   - Same per-trade notional cap
   - Same drawdown / daily max-loss kills
4. ORB-specific stop: use ORB-anchored stop (info["orb_low"] - ATR × stop_atr_mult for longs) instead of regime-default ATR stop.

Initial deployment: a single ORB candidate per session, treated as 1 of the 2 max positions in Stage-1.

Pass criteria after 4 weeks of live ORB:
- Total ORB live trades ≥ 20
- ORB-specific expectancy ≥ +$0 (acceptable; we're testing edge, not demanding large profit yet)
- ORB-specific drawdown ≤ 5% of capital (Stage-1 budget protection)
- No risk-control failures attributable to ORB
- ORB-vs-alpha+breakout: no severe degradation of either (e.g., ORB doesn't "steal" all the good entries from alpha+breakout)

### Phase E — A/B comparison (week 8+ post-promotion)

After 4+ weeks of ORB live, run a comparison:
- Sessions where ORB fired vs sessions where it didn't
- Alpha+breakout-only baseline expectancy vs ORB-augmented
- Per-symbol contribution analysis

Decision tree:
- ORB clearly positive: scale up (raise top_n from 10 to 20, lower min_rv_ratio to 1.3)
- ORB neutral: keep as-is, monitor longer
- ORB clearly negative: feature-flag off, write post-mortem

---

## Metrics to track in shadow

Add to `decision_telemetry` (currently logs ticks/regime/signals; extend with ORB):

```python
# Per-tick (when scanner runs):
{
    "orb_candidates_ranked": int,    # how many made it through min_rv_ratio + top_n filter
    "orb_breakouts_triggered": int,  # subset where current_price crossed ORB level
    "orb_session_breakouts": int,    # cumulative for the session
    "orb_cache_size": int,           # how many symbols have a cached ORB
}
```

This gives us per-tick telemetry. Aggregated daily into the post-close audit.

---

## Failure modes specific to ORB

| Failure | Detection | Response |
|---|---|---|
| Scanner raises exception | logs `ORB shadow scan err:` repeatedly | Investigate; shadow exception handler protects live tick |
| No breakouts ever | shadow_breakout_count stays 0 across 5 sessions | min_rv_ratio too high, or universe too small for stocks-in-play strategy. Lower threshold or expand universe |
| Too many breakouts | >20 per session, scanner spamming logs | top_n too high or min_rv_ratio too low; tune down |
| All breakouts in one symbol | Concentration risk | Add per-symbol cooldown or hard cap |
| ORB direction wrong systematically | win rate < 10% in simulation | Fundamental thesis problem on this universe — shelve and revisit |
| Phantom breakouts from data gaps | logs show triggers on stale data | Add staleness check on `current_price` (fresh within last 60s) |

---

## What "success" looks like at each phase

| Phase | Window | Success | Failure |
|---|---|---|---|
| A. Replay | This session | 3-12 breakouts/session, sensible symbol/time distribution | <3 or >20 — recalibrate thresholds |
| B. Live shadow | Week 1 post-deploy | 15+ logged events, no exceptions | Zero events or errors → scanner bug |
| C. Hypothetical sim | Week 2 | Sim Sharpe ≥ 0.5, expectancy ≥ +$1 | Sub-zero sim Sharpe → strategy doesn't work on our data |
| D. Live ORB | Weeks 3-7 | Real expectancy ≥ $0, drawdown ≤ 5% | Loses money or causes risk-control failures → flag off |
| E. A/B | Weeks 8+ | Clear positive contribution → scale up | Marginal/negative → shelve |

---

## Why we DON'T promote ORB to live in RC-1.5

1. **No shadow data yet.** Scanner just shipped tonight; the baseline RC-1.5 deploy hasn't even happened. We don't know what ORB looks like in our specific live conditions.
2. **Stage-1 readiness gate G3 not met** (RC-2 hasn't shipped either). Adding a third entry source while RC-2 isn't validated is layered risk.
3. **Shadow-mode discipline.** Every behavioral change in this sprint has gone through shadow first (RC-2 regime + ML weight, now ORB). Discipline.
4. **Bandwidth.** Operator can monitor RC-1.5 changes effectively in week 1; layering ORB on top is too much to track at once.

ORB earns live promotion through evidence over time, not through belief.

---

## Honest framing

The ORB strategy is the most promising research direction we identified — paper Sharpe 2.81, peer-reviewed, OOS-validated, infra-compatible. **Even with a 70% real-world haircut, it's a Sharpe ~0.85 step from our current ~0.**

But it's still a hypothesis until WE see it work on OUR data with OUR execution. The shadow → simulation → live → A/B path is how we find out without risking capital on speculation.

If ORB fails on our data: that's a learning, not a defeat. Even a failed validation tells us something concrete about which directions actually work for this platform.

If ORB succeeds: we have the first genuinely-evidenced edge component on this platform. That changes Stage-1 economics from "operational validation only" to "operational validation + small expected return."

Either outcome is information. Building the shadow + validation framework is the right move regardless.
