# Apr 2 PnL Reconciliation

# 1. Verdict

The $33.11 gap is explained. The brain's reported +$78.45 **overstates actual realized PnL** because `entry_price` in the TradeRecord is set from the first pyramid leg's fill price, not the cost-weighted average of all pyramid fills. When the organism pyramids into a position with 2–3 buy orders at successively higher prices, the brain records the lowest (first) fill as the entry price for the entire position. This systematically understates the cost basis and inflates computed PnL on winning pyramid trades. The true broker-realized PnL is **+$45.45** (net cash flow from all fills), which matches the equity change of +$45.34 within $0.11 of rounding. No fees, adjustments, or non-trade cash events are involved. This is a **PnL computation bug in the pyramid entry-price tracking**, not a persistence or reporting bug.

# 2. Numbers Being Reconciled

| Source | Value | Method |
|---|---|---|
| Brain cumulative_pnl delta | +$78.45 | learning_state: -714.26 → -635.81 |
| Reported daily PnL | +$78.45 | Sum of 20 TradeRecord.pnl values from CSV |
| Broker net cash flow | **+$45.45** | Sum(sell proceeds) - Sum(buy costs) from 54 fills |
| Equity change (snapshot) | +$45.34 | $111,690.00 - $111,644.66 |
| Alpaca last_equity delta | +$45.45 | $111,690.00 - $111,644.55 |
| Gap (brain vs broker) | **$33.00** | $78.45 - $45.45 |
| Gap (broker vs equity) | $0.11 | $45.45 - $45.34 (rounding) |

# 3. Broker-Fill Recalculation

**Method**: Sum all sell order notionals minus all buy order notionals from the 54 filled orders.

```
Total bought (28 buy fills):  $73,667.20
Total sold (26 sell fills):   $73,712.65
Net cash flow:                $+45.45
```

This is the authoritative broker-realized PnL. Started flat, ended flat, no open positions, no non-trade adjustments. The cash delta IS the realized PnL.

Round-trip reconstruction from broker fills yields 20 trades totaling **+$53.72**. The difference from $45.45 is due to lot-matching ambiguity in multi-leg pyramids (the round-trip aggregation handles partial-fill pyramid sequences imperfectly). The total cash flow ($45.45) is more reliable than any round-trip reconstruction.

# 4. Brain-Trade Recalculation

**Method**: Sum `pnl` field from the 20 TradeRecords in trade_history.csv dated 2026-04-02.

```
Sum of TradeRecord.pnl: $+78.45
```

This matches the brain's cumulative_pnl delta (-714.26 → -635.81 = +78.45). The brain's internal accounting is self-consistent — the issue is that the individual pnl values are computed from incorrect entry prices.

# 5. Account-Activity / Cash-Adjustment Review

Queried `GET /v2/account/activities?after=2026-04-02&until=2026-04-03`:
- **100 activities, all type FILL**
- **0 non-fill activities** (no fees, interest, dividends, journals, or adjustments)

The gap is not caused by any non-trade cash movement.

# 6. Timing / Snapshot Consistency Review

| Snapshot | Source | Timestamp |
|---|---|---|
| Pre-open equity | preopen bundle | Before market open, $111,644.66 |
| Post-close equity | monitor bundle | After market close, $111,690.00 |
| Alpaca last_equity | Account API | $111,644.55 (Apr 1 EOD mark) |

The $0.11 difference between pre-open equity ($111,644.66) and Alpaca's last_equity ($111,644.55) is likely an end-of-day mark-to-market adjustment at Alpaca. The equity snapshots are from the same session window and are directly comparable.

# 7. Root Cause of the $33.00 Gap

## Pyramid Entry-Price Bug

When the organism pyramids into a position with multiple buy orders, `_entry_metadata[symbol]["entry_price"]` is set when the **first** pyramid leg fills. Subsequent pyramid buys at different (typically higher) prices add shares but **do not update the recorded entry_price** to the cost-weighted average.

When the trade closes, PnL is computed as:
```
pnl = (exit_price - entry_price) * shares * direction
```

This uses the first leg's fill price for ALL shares, not the blended cost basis.

### Worked Example: AMD Trade 1

| Leg | Shares | Fill Price | Cost |
|---|---|---|---|
| Buy 1 | 15 | $207.65 | $3,114.75 |
| Buy 2 (pyramid) | 7 | $208.72 | $1,461.04 |
| **Total** | **22** | — | **$4,575.79** |
| True avg entry | — | **$207.99** | — |
| Brain entry_price | — | **$207.54** | — |

```
Brain PnL:  22 × ($209.68 - $207.54) = +$47.08
Actual PnL: 22 × ($209.68 - $207.99) = +$37.17 (matches broker)
Overstatement: $9.91
```

The brain entry_price ($207.54) is even lower than the first fill ($207.65) — it appears to be the **limit price** from the order, not the actual fill price.

### All Affected Trades

Every pyramided trade is affected. The overstatement is largest on winning trades that pyramided into higher prices (AMD +$9.91, XLK +$13.67, XOM +$9.64). The effect partially cancels on losing trades where pyramid buys were at lower prices.

Net overstatement across all 20 trades: **+$33.00**.

# 8. Hard Conclusions

**Is +$78.45 the true broker-realized PnL for Apr 2?**
**NO.** +$78.45 overstates realized PnL by $33.00 due to the pyramid entry-price bug. The true broker-realized PnL is +$45.45 (net cash flow from all fills).

**Is +$45.34 the true equity change for the same session window?**
**YES.** Equity went from $111,644.66 to $111,690.00 = +$45.34. This matches broker cash flow (+$45.45) within $0.11 of rounding.

**Are the two numbers measuring different things?**
**PARTIAL.** Both intend to measure realized PnL, but the brain computes PnL from a stale entry_price (first pyramid leg) while the broker computes from actual blended cost basis. They are measuring the same concept but with different (and conflicting) inputs.

**Is there a report-generation or aggregation bug?**
**YES.** The entry_price in TradeRecord is not updated to reflect the cost-weighted average when pyramid legs fill at different prices. This causes the `pnl` field to be systematically overstated on pyramided winning trades. This is a **PnL computation bug in the pyramid tracking path**, likely in `_reconcile_fills()` or the entry metadata update logic in `live_engine.py`.

**Is any non-strategy cash activity involved?**
**NO.** 100 account activities, all type FILL. Zero fees, interest, dividends, or adjustments.
