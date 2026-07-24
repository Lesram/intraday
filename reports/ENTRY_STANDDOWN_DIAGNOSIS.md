# Entry-path stand-down — diagnosis

**Work order 2026-07-23, Task 5 (REPORT ONLY — quantify, don't fix).** No code or
config changed. Drift-verify green. FROZEN_AT unchanged.

> **Scope note + EOD correction.** The work order asks for "the next 2–3 live
> sessions." Session 1 (2026-07-23) is below; Sessions 2–3 are stubs. **These numbers
> were re-measured at session close (23:39Z) after a Cowork red-team caught that the
> first draft used a ~17:48Z MID-SESSION snapshot.** Two kill-counts that read "0" at
> 17:48 (`direction_zero`, the liquidity floor) both fired later (18:55–19:35Z), so
> the original "both 0 — not the binding constraint" framing was false for the full
> session. The IEX-starvation conclusion is unchanged (and stronger). **Discipline
> fix: Session tables are measured at session close, never midday.**

## 1. Per-session table (measured at session close)

| Session (ET date) | regime mix (evidence events) | scanner empty | stale-bar rejects | live candidates | orders | fills |
|---|---|---:|---:|---:|---:|---:|
| **2026-07-23** | trending_down 853 (74%) / chop 257 (22%) / high_vol 26 / trending_up 17 (n=1,153) | 164 | 1,582 | 17 | 0 | 0 |
| 2026-07-2_ (TBD) | — | — | — | — | — | — |
| 2026-07-2_ (TBD) | — | — | — | — | — | — |

## 2. Session 1 (2026-07-23) — measured at session close (23:39Z)

**Regime (from `strategy_evidence_events.jsonl`, 1,153 events):** trending_down
**74%** (853), chop **22%** (257), high_vol 26, trending_up 17. A trending-dominant
session — but chop is a real 22% minority, not the ~2% the mid-session draft implied.

**Where the candidates die — EOD kill counts:**
- Order submissions: **0**. Fills: **0** (zero orders all day).
- **In-play scanner empty — 164×** (`market_scanner.py:410`): the Alpaca
  most-actives/movers screener returns empty on IEX → falls back to cached candidates.
- **Streaming bars stale — 1,582×** (`streaming_data_provider`, >120s → REST), on the
  thin-on-IEX names — SH+PSQ (the inverse ETFs) alone are 75%:

  | symbol | stale rejects | note |
  |---|---:|---|
  | PSQ | 599 | inverse ETF (short hedge) |
  | SH | 585 | inverse ETF (short hedge) |
  | LLY | 214 | |
  | COST | 96 | high-priced, quiet on IEX |
  | CAT | 53 | |
  | XLK | 19 | |
  | CRM | 12 | |
  | XOM | 4 | |

- The `direction_zero` filter fired **25×** — 3 at the 15:46Z boot + the rest in a
  19:18–19:35Z cluster. NOT zero (the earlier "0" predated the 19:xx cluster).
  Second-order: ~2% of events.¹
- Liquidity floor (`$50k`, `live_engine.py:1457`): **7** blocks, **all SH**,
  18:55–19:22Z — the first liquidity blocks in the retained log, landing on an inverse
  ETF (short-side, thinnest on IEX). NOT "0 ever" as the first draft claimed.

¹ *Two predicates, adjudicated in red-team round 2: **25** = evidence rows with
`defensive_filter_reason == "direction_zero"` (the filter actually firing); **30** =
all rows with `direction == 0`, of which the other 5 were killed by
`alpha_breakout_chop_blocked_by_evidence` instead. Both counts are stable across
cutoffs (last event 20:00:07Z) — the earlier 25-vs-30 discrepancy was a predicate
difference, not timing.*

**Net:** starvation (1,582 stale + 164 empty = 1,746) outweighs the second-order gate
kills (25 direction_zero + 7 liquidity = 32) by ~55×. **17 `live_pipeline_candidate`
events** produced **0 order submissions.** (Note: the raw `entry_source` alpha/
alpha+breakout tags total 60, but only 17 carry `live_pipeline_candidate=True` — the
first draft conflated the two into "13 candidates / alpha 16 + breakout 5"; the
authoritative live-candidate count is 17.) Isolating the exact gate on those 17 needs
per-candidate tracing (follow-up; Task 5 is quantify-not-fix).

### Task-0(b) validation — CLOSED
The deferred question from `docs/architecture/phase3_task0_data_decision.md` — *does
IEX starve the in-play universe?* — is answered **YES, decisively.** The most-actives/
movers screener is dry (164× empty) and the streaming feed cannot keep the universe
fresh (1,582 stale-bar fall-throughs; SH+PSQ = 75%). The `$50k` floor is reached only
7× (all SH); starvation is ~55× larger than all gate kills combined. On IEX the
universe is starved before any strategy logic meaningfully runs.

## 3. Does the live path fire on a trending/high-vol session?

**Session 1 answer: no — and starvation, not regime, is why.** 2026-07-23 was 74%
trending_down (momentum/breakout-eligible per REGIME_POLICY), the live path generated
17 candidates, and still **zero filled.** The `direction_zero` (25) and liquidity (7)
kills DID fire late in the session, but they are second-order — 32 events against 1,746
starvation events. The primary binding constraint is **IEX data starvation** (empty
screener + stale bars), not the chop/`direction_zero` mechanism the plan assumed. The
plan's hypothesis ("chop → `direction_zero` → no fills") is not the dominant story;
IEX starvation is. **Sessions 2–3 are still needed** to confirm this holds across more
tape (and to catch any session where the screener/feed do deliver a tradeable universe).

## 4. DECISION ITEMs (Marsel) — clock-sensitive levers, none touched

Each would change the frozen decision surface and/or reset the forward clock:

| Lever | Expected effect | Cost | Clock consequence |
|---|---|---|---|
| **SIP re-subscription** (drop `ALPACA_DATA_FEED=iex`) | Fixes the root cause: working screener + fresh bars → the universe stops starving. Highest-leverage. | Paid Alpaca feed ($/mo) | **Resets the clock.** `ALPACA_DATA_FEED` is a first-class frozen fact in `param_freeze.json` (`routing_data_env`). Changing it re-stamps FROZEN_AT. |
| **Universe expansion** to names that survive IEX | More symbols that stay fresh on the free feed → candidates that reach the gates. | Calibration sweep | Decision-surface (`strategy_config`/scanner universe) → likely reset. |
| **Gate loosening** (lower `$50k` floor / relax staleness) | Little to none — the floor already rejects 0; the bind is empty screener + stale bars, which loosening the floor does not fix. | Low | `routing_data_env`/exit env are frozen → reset for ~no benefit. Not recommended. |
| **Symmetric-short paths** (`2454ceb`, flag-gated) | Enables short-side entries. But SH/PSQ (the short instruments) are the **most** data-starved on IEX (515 of 688 stale rejects) — shorts won't fire until the feed is fixed. | Testing | Entry-direction logic is frozen → reset. Sequence AFTER a data fix, not before. |

**Recommendation (not a decision):** the binding constraint is the **IEX data feed**,
so the short-list starts and ends with the data feed (SIP) — the other levers give
little until the universe stops starving. This is Marsel's call; it resets the clock.

## 5. Follow-ups (mechanical, non-clock)
- Per-candidate trace of the 13 live candidates → exact no-submit gate (needs a debug
  counter, not a surface change).
- Recalibrate the in-play scanner thresholds for IEX (noted open in the 07-06 restart
  memo) — only meaningful if IEX is kept.
