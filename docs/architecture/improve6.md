# Mid‑Session Audit and Fast Remediation Plan for Intra

## What today’s half‑day report actually proves

Your half‑day report is **not** “the strategy is bad.” It’s “the strategy is being capped by one exit rule and a data-timing defect.”

Two facts dominate:

- **`failure_to_follow` (FTF) is your primary performance drag**: 17 exits (65%) and **net −$50.07**, while the only meaningful winners come from trades that survive to the **time‑based exit** (`max_holding_period`, net +$314.71 across just 2 closes). That is the textbook signature of **“you’re cutting winners early.”**
- Your system appears to be operating off **delayed / lagging 1‑minute bars**: you observed a position held for ~23 minutes but `bars_held=9`. That means your new‑bar detection is not seeing a new bar every minute, so *many bar‑based checks are running at the wrong cadence*.

Those two issues together produce exactly what you’re seeing:
- FTF closes trades “for not moving fast enough” **in a regime that is slow to trend (chop/high_vol)**, and
- bar lag means “fast enough” and “how long you waited” are **mis-measured**.

## Immediate changes to capture a positive redirection while the market is open

There are only two interventions worth doing *during* the session because they directly target the failure mode causing today’s drag.

### Disable or de-fang FTF in chop/high_vol now

Right now, FTF is **net negative** and is intercepting trades before they can become the kind of winners that are paying your day.

In your current code, the FTF thresholds are explicitly:

- `chop`: **0.25R**
- `high_vol`: **0.25R**
- `stress`: 0.15R
- `trending_down`/`unknown`: 0.35R

and FTF is only disabled for `trending_up` and `low_vol`. (You already noticed this.) This is exactly why you’re bleeding in chop/high_vol: it is still “on” and still strict.

**The fast, safe fix for the rest of today** is one of the following (listed from safest to most aggressive):

- **Option A (safest): “FTF only exits losers.”**  
  Keep FTF as a “stagnant loser killer,” not a “winner killer.”  
  Change FTF from:
  - “exit if `r_achieved < 0.25`”
  to:
  - “exit only if `r_achieved < 0`” in `chop` and `high_vol`.

- **Option B (very effective): “FTF becomes tighten‑stop, not exit.”**  
  If FTF triggers in `chop/high_vol`, do **not** close the position. Instead:
  - raise stop to **break-even** (or entry − 0.25R),
  - keep the position alive to reach trailing/time exits.

- **Option C (most blunt): disable FTF for `high_vol` (and maybe `chop`) for the remainder of the session.**  
  You already have stop_loss and max_loss safety net. If FTF is net-negative intraday, disabling it can immediately increase expectancy—but it can also increase stop_loss hits, so you need a rollback rule (below).

**Why this is rational mid‑day:** your empirical evidence today says “the only winners are the longer-held positions.” So the only lever that can plausibly recover profits today is removing the rule that prevents longer holds.

### Fix bar freshness before you calibrate any bar-based exit thresholds

Your bar cadence issue is serious because it corrupts all “bar-based” logic (FTF timing, max-hold, time decay). The quickest operational fix is:

- **Turn on streaming minute bars and drive `is_new_bar` from streamed `bars` / `updatedBars` instead of REST polling.**

entity["company","Alpaca Markets","broker api provider"] explicitly recommends using the WebSocket stream for up‑to‑date pricing rather than polling historical endpoints, and notes that **minute bars are emitted right after each minute mark** (with `updatedBars` after half‑minute marks for late trades). citeturn0search1  
Alpaca also documents that “historical” classification has a **15‑minute delay**, which is exactly why using historical endpoints for near-real-time bar cadence can create lag or unexpected behavior depending on plan/feed selection. citeturn0search0  

If you’re not already running the streaming provider for bars, enabling it mid‑day is the single best way to eliminate the “bars_held is wrong” defect.

## Why FTF is destroying value today

Given your half‑day stats:

- win rate 38.5%,
- avg win $35.54,
- avg loss $16.13,

you have an intrinsically positive payoff geometry **if winners are allowed to express**. But your exit breakdown says:

- FTF is closing 65% of trades and is net negative,
- the only real profit comes from two trades held until the time exit.

That means FTF is frequently doing this:

1. You enter into a legitimate move.
2. The move does not reach “fast enough R” quickly (common in chop/high_vol).
3. FTF exits at small loss or small gain.
4. Later, the trade would have become one of your “max holding” winners.

In short: your system’s edge appears to be **“eventual drift after setup”**, but FTF is a **latency-requirement** rule. That mismatch is what’s killing the PnL distribution.

Also, note that your FTF check is **disabled when trailing is active**, which implies: *if you can get more trades to activate trailing sooner, FTF triggers less.* But trailing activation is ATR-based and often requires a meaningful move; in chop/high_vol, many good trades won’t hit that early. So FTF becomes the default exit.

## The bar detection lag is a first-order defect, not just a nuisance

Your observed mismatch (“23 minutes held, bars_held=9”) is consistent with this implementation in the live engine:

- For each symbol, `_is_new_bar` is computed by comparing the **latest bar timestamp** to the previous saved timestamp.
- If the bar timestamp doesn’t advance (because the latest 1‑minute bar hasn’t arrived), `_is_new_bar=False`.
- When `_is_new_bar=False`, the exit engine runs only risk checks (stop/max_loss) and **does not advance bars_held**.

This is logically correct **if** bar timestamps arrive on time.

But if you’re polling bars via REST and those bars arrive 2–3 minutes late (which is a known pattern people observe in practice depending on feed/subscription/config), your system will:
- treat time as “not advancing,”
- run bar-based exits late,
- calibrate thresholds incorrectly (because “bar” no longer means “minute”).

Alpaca’s own documentation makes two relevant points:

- streaming provides “most up to date market information” and is preferable to polling historical endpoints for accurate and timely behavior, citeturn0search1  
- historical classification has a 15-minute delay, which is ~exactly the kind of semantic mismatch that can happen when a system mistakenly depends on historical delivery for live cadence. citeturn0search0  

This is why your report’s suspicion (“historical bar API lag”) is credible: it’s a classic failure mode.

## Safe live-change menu while the market is open

You asked what you can change “now” to redirect performance. Here is the blunt truth:

### Changes you can make without a code deploy (via runtime config)

If you are using the scheduler settings API, you can hot-update:

- `tick_interval_seconds` (scheduler cadence)
- Kelly sizer knobs: `max_position_pct`, `vol_target`, `min_position_usd`
- a limited set of exit engine knobs: `atr_multiplier`, `profit_r_multiple`, `trailing_distance_atr`, `max_bars_held`, `partial_tp_pct`

However: **none of those hot-reload knobs change FTF behavior** because FTF thresholds and regime exclusions are hard-coded in the exit engine logic.

So if FTF is the day’s primary drag, runtime config alone does not give you the lever you actually need.

### Changes that matter most today (require a quick code patch + restart)

To address today’s root cause, you need exactly two small code changes:

- **FTF rule adjustment** (as described above)
- **Bar freshness fix** by enabling streaming bars (if not already running)

The good news: your engine already persists exit levels and reconstructs state on restart, and the scheduler supports starting a streaming provider when configured. That means you can patch + restart without “losing the brain,” as long as your brain directory is stable.

## Recommended parameter changes for today’s session

Below is a concrete change set that is deliberately conservative and intended to **improve returns today** without blowing up risk.

### Critical change set (do this first)

| Parameter / logic | Current (today) | Recommended for the rest of today | Rationale | Risk | Complexity |
|---|---:|---:|---|---|---|
| FTF in `chop` / `high_vol` | exit if `R < 0.25` | **exit only if `R < 0.0`** (losers only) | Stops FTF from cutting small winners that later become max-hold winners | Medium | Small |
| Alternative FTF behavior | full exit | **tighten stop to breakeven** instead of exit when `0 ≤ R < threshold` | Converts a value-destroying hard exit into a risk-reducing soft action | Medium | Small–Medium |
| Streaming minute bars | possibly off or unreliable | **enable streamed `bars` / `updatedBars`** | Restores 1-min cadence; makes bars_held and time exits meaningful | Low–Medium | Medium (ops) |

### Optional “today-only” tuning if you cannot patch code

If you truly cannot patch code mid-session, the only meaningful mitigation is to reduce the probability that FTF triggers by making trades reach trailing sooner and express more R sooner. But your hot-reload config does **not** include trailing activation (`trailing_start_atr`), which is the real lever. So you are largely boxed in.

If you need *some* lever anyway:
- increase `max_position_pct` slightly (e.g., 0.08 → 0.10) to capitalize on the winners you do get,
- but only if you also enforce a strict daily loss stop and are comfortable with larger variance.

This does not fix the strategy flaw; it just scales what you already have.

## Rollback criteria so you don’t “change knobs blindly”

If you implement the FTF change mid-session, you need an objective rollback rule within 45–60 minutes:

- If the number of **stop_loss** exits rises sharply AND net P&L from those additional stop losses exceeds the avoided FTF losses, revert.
- If average loss increases materially (FTF sometimes prevents full stop losses), revert to “tighten-stop instead of exit” (Option B), which preserves the protective aspect without killing winners.

Given your current distribution, the best “middle path” is almost always Option B: **FTF tightens risk, it does not close.**

## Bottom line

Your report shows a system that is finally producing real diagnostic truth:

- You have a payoff profile that can be profitable.
- Your system’s own evidence says “longer holds pay.”
- Your code says “FTF aggressively penalizes slow development in chop/high_vol.”

So the immediate mid-session fix is not “more ML” or “more indicators.” It is:

- **remove FTF’s ability to kill winners in chop/high_vol** (losers-only or tighten-stop),
- **restore true 1-minute bar cadence** via streaming minute bars so time-based logic is calibrated to real time. citeturn0search1turn0search0