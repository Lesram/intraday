# FRIDAY POST-CLOSE REVIEW
**Session:** Friday 2026-04-24
**Live commit:** `ce06d41` (Exp 1A + Exp 2 + Exp 3 prep)
**Audit type:** READ-ONLY (no broker mutations, no restarts)

---

## Headline metrics

| Metric | Value |
|---|---|
| Trades closed | **26** |
| Net PnL | **−$2.17** (≈ flat) |
| Wins / Losses | 11 / 15 |
| Win rate | 42.31% |
| Gross wins | $48.76 |
| Gross losses | −$50.93 |
| Avg win | $4.43 |
| Avg loss | −$3.40 |
| Win/loss ratio | 1.30× |
| Expectancy | −$0.083 / trade |
| Avg hold time | 918 s (~15.3 min) |
| Directional accuracy | 42.31% |
| Total per-share MFE | $70.19 |
| Total per-share MAE | $87.47 |

Session ran cleanly through the close. Brain saved at 20:00:24Z (= 16:00 ET = market close), governance restored at next-day container restart.

---

## Best / worst trades

| Rank | Symbol | PnL | Exit reason | Note |
|---|---|---|---|---|
| Best | NVDA | +$19.46 | `reconciliation_adjustment` | Broker-fill reconciliation gap; not a strategy win — informational |
| 2nd | NVDA | +$11.64 | `take_profit` | Real strategy win, alpha+breakout, chop, conf 0.605 |
| 3rd | TSLA | +$4.48 | `max_holding_period` | Held to 30-bar timeout, +0.13% |
| Worst | AMZN | −$21.55 | `reconciliation_adjustment` | Broker-fill reconciliation; offsetting NVDA reconciliation above |
| 2nd worst | AVGO | −$4.92 | `stop_loss` | Hit stop in 4 bars; 0.71 confidence — this is concerning |
| 3rd worst | LLY | −$4.45 | `stop_loss` | 9-bar hold, 0.45 confidence |

Note: the two `reconciliation_adjustment` trades (+$19.46 NVDA, −$21.55 AMZN) net to −$2.09 and represent **broker-side reconciliation, not strategy P&L**. Excluding them: 24 strategy trades, net **−$0.08**, win rate 41.7%.

---

## Exit reason breakdown

| Exit reason | n | PnL | Win rate | Avg / trade |
|---|---|---|---|---|
| `max_holding_period` | 6 | **+$14.09** | 100.0% | +$2.348 |
| `take_profit` | 1 | +$11.64 | 100.0% | +$11.640 |
| `ml_reversal` | 1 | +$2.34 | 100.0% | +$2.340 |
| `trailing_stop` | 4 | +$0.03 | 50.0% | +$0.008 |
| `failure_to_follow` | 3 | −$1.96 | 0.0% | −$0.653 |
| `pyramid_cut_full` (≤−2.0R) | 1 | −$1.47 | 0.0% | −$1.470 |
| `pyramid_cut_full` (≤−1.5R) | 0 | — | — | — |
| `pyramid_cut_full` (~−1.2R) | 2 | −$3.33 | 0.0% | −$1.665 |
| `reconciliation_adjustment` | 2 | −$2.09 | 50.0% | −$1.045 |
| `stop_loss` | 6 | **−$21.42** | 0.0% | −$3.570 |

**Stop_loss is the single biggest drag today** (−$21.42 from 6 trades). Average loss per stop = −$3.57; that lines up with the 2.5× ATR chop stop size.

**Max_holding_period was 100% positive** (6 winners, +$14.09). Confirms the timeout policy is harvesting drift well in chop.

**Trailing_stop is essentially flat** (+$0.03 from 4 trades) — but the per-share MFE was positive so giveback exists; Exp 4 (offline-ready) is targeted at this.

**Pyramid_cut absorbed only 3 trades today** (−$4.80 total). Down from the live-window average of ~31% — Exp 1A is functioning.

---

## Confidence-bucket analysis

| Bucket | n | PnL | Win rate | Expectancy |
|---|---|---|---|---|
| ≥ 0.7 | 3 | −$2.49 | 33.3% | −$0.830 |
| 0.6 – 0.7 | 8 | −$9.07 | 50.0% | −$1.134 |
| **0.5 – 0.6** | **11** | **+$15.80** | **54.5%** | **+$1.436** |
| < 0.5 | 4 | −$6.41 | 0.0% | −$1.603 |

**The mid-confidence bucket (0.5–0.6) is the only positive bucket today**, mirroring the live-window pattern (since `ce06d41`). High confidence (≥ 0.7) is small-n but unprofitable. **This is the Exp 3 hypothesis signal in plain sight** — there's a non-monotonic confidence→outcome mapping. Exp 3 prep logging is the right groundwork; an Exp 3 execution variant deserves a serious offline backtest before we commit.

---

## Regime / symbol / time-of-day

**Regime:** essentially 100% chop. 25 chop→chop, 1 unknown→chop. No trending or high_vol entries. The market spent the whole day in chop and the organism stayed inside its chop policy throughout — appropriate.

**Symbols (Friday only):**

| Symbol | n | PnL |
|---|---|---|
| NVDA | 5 | **+$32.53** |
| TSLA | 2 | +$4.35 |
| QQQ | 1 | +$1.98 |
| XLK | 2 | +$0.15 |
| IWM | 1 | +$0.06 |
| XOM | 1 | −$0.07 |
| META | 1 | −$1.47 |
| WMT | 1 | −$1.26 |
| AVGO | 3 | −$2.56 |
| GOOGL | 1 | −$2.20 |
| SPY | 1 | −$0.55 |
| LLY | 2 | −$6.52 |
| AAPL | 1 | −$3.80 |
| XLE | 1 | −$4.00 |
| AMZN | 3 | −$18.81 (incl. −$21.55 reconciliation) |

NVDA carried the day (5 trades, +$32.53). AMZN was the worst symbol, but that's mostly the reconciliation hit; the two non-reconciliation AMZN trades were +$0.78 net.

**Time-of-day (UTC):**

| Hour (UTC) | n | PnL |
|---|---|---|
| 13:00 (open–10:00 ET) | 4 | +$1.26 |
| 14:00 (10:00–11:00 ET) | 5 | +$7.56 |
| 15:00 (11:00–12:00 ET) | 3 | −$2.43 |
| 16:00 (12:00–13:00 ET) | 5 | −$1.70 |
| 17:00 (13:00–14:00 ET) | 5 | −$6.51 |
| 18:00 (14:00–15:00 ET) | 2 | −$1.07 |
| 19:00 (15:00–close) | 2 | +$0.72 |

Early session (open + first hour) was the strongest. Mid-day (1 PM ET) was the weakest. Same chop-style pattern we've been seeing.

---

## Giveback analysis (per-share)

- Total per-share MFE = $70.19 across 26 trades → avg $2.70/share unfilled MFE
- Total per-share MAE = $87.47 → avg $3.36/share adverse excursion (this is structurally larger than realized P&L because most trades cycle through MAE before resolving)
- Trailing-stop trades: 4 trades, MFE/share sum = $11.92, captured P&L sum = $0.03 → trailing strategy gave back the majority of its MFE today (small absolute dollars but the pattern is consistent with the broader Exp 4 motivation)

---

## Trustworthiness of session

| Check | Status |
|---|---|
| Container healthy through session | YES |
| No halt / freeze events | YES |
| Manifest + learning_state in sync at close | YES |
| Brain saved at close (20:00:24Z) | YES |
| Regime classification stable (chop-dominant) | YES |
| Universe complete (22 symbols) | YES |
| Reconciliation events present and accounted for | YES (2 trades, ±$20 cancel) |
| Connectivity errors | 1 minor scanner retry, no positions impact |
| Drawdown vs peak | −0.227% (well within 20% kill) |
| Strategy-pure PnL (excl. reconciliation) | −$0.08 |

**Verdict: SESSION IS TRUSTWORTHY.**

The session is small-n (26 trades), reconciliation-noisy, and basically flat. **It is one data point, not an inflection.** It does NOT change the prior week conclusion that the live stack is mildly negative-expectancy in chop and pyramid_cut is the dominant drag.

---

## What this session tells us

1. **Stop_loss is still the largest single drag in chop.** The 2.5× ATR chop stop sized −$3.57/trade (6 trades = −$21.42).
2. **Max_holding_period is the most reliable winner.** All 6 timeouts profitable today; expectancy +$2.35.
3. **The mid-confidence bucket is the profitable one** (+$1.44 expectancy). Exp 3 hypothesis remains alive.
4. **NVDA is doing the heavy lifting** (5 trades, +$32.53). Concentration risk to flag.
5. **Trailing_stop is barely covering its giveback** — supports Exp 4 thesis (offline-ready).
6. **Reconciliation events are a known broker-side adjustment** and should not be conflated with strategy P&L.
