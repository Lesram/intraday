# Pyramid_cut deep-dive (S4)

**Run:** 2026-04-25 weekend sprint
**Branch:** `rc-1.5-curated`
**Window:** since `ce06d41` deploy (2026-04-13), 12 sessions, 182 trades
**Audit type:** code review + data analysis

**TL;DR — partial-correction to Track 1's interpretation, then a small actionable finding:**

1. **Track 1 was right that pyramid_cut accounts for −$165 (31% of exits, biggest dollar drag).** That part stands.
2. **Track 1's framing — that "pyramid sizing compounded the loss" — is incorrect.** The pyramider only adds layers at +1.5R and +3.0R. A trade that never went above 0R cannot have pyramided up. So 41 of 57 "pyramid_cut" trades (72%) are *initial-position* cuts at -1.0 to -1.9R, NOT pyramid-amplified losses.
3. **The real pyramid_cut problem is upstream entry quality**, which the composite-gate fix in RC-1.5 directly addresses. No pyramider code changes needed for RC-1.5/RC-2.
4. **One small actionable finding worth scheduling: deep cuts (≥3R, 9% of pyramid_cuts) are slippage/gap losses, and they could be reduced.** Likely a future Exp 6 candidate.

---

## What `pyramid_cut` actually means in code

From `backend/organism/pyramider.py:188-202`:

```
# Anti-pyramid: cut losers
if r_current <= self.CUT_FULL:        # CUT_FULL = -1.0
    return PyramidAction(action="close_partial",
                         shares_to_add=-position.total_shares,
                         reason=f"cut_full_at_{r_current:.1f}R")

if r_current <= self.CUT_PARTIAL and position.layer_count == 1:  # CUT_PARTIAL = -0.7
    cut_shares = max(1, position.total_shares // 2)
    return PyramidAction(action="close_partial",
                         shares_to_add=-cut_shares,
                         reason=f"cut_partial_at_{r_current:.1f}R")
```

**`pyramid_cut` is the platform's loss-cap rule, not a pyramid-specific failure mode.** It fires whenever any position (layer_count = 1, 2, or 3) reaches -1.0R adverse. The "_full" suffix means "close all shares"; "_partial" means "close half" (only fires when no pyramid layer has been added yet).

## Live-window distribution (n=57)

| R-multiple bucket | n | % | Mechanism |
|---|---|---|---|
| Partial cut, < -1R | 5 | 9% | Partial-cut logic, single layer, fired at -0.7R |
| **Shallow full cut, -1.0 to -1.9R** | **41** | **72%** | **Standard CUT_FULL fired near design point** |
| Mid full cut, -2.0 to -2.9R | 6 | 11% | Slippage / cross-bar move → cut overshot the -1.0R trigger |
| Deep full cut, ≥-3R | 5 | 9% | Significant slippage / gap → cut materially overshot |

Aggregate: avg MFE = $0.47/share, avg MAE = $2.92/share.

## MFE comparison vs other exit categories

| Category | n | avg MFE | avg MAE | avg pnl |
|---|---|---|---|---|
| Pyramid_cut | 57 | **$0.47** | $2.92 | −$2.89 |
| Winners | 57 | **$4.83** | $3.37 | +$2.95 |
| Non-cut losers | 68 | $1.99 | $2.70 | −$1.05 |

The pyramid_cut bucket has 10× lower MFE than winners — these trades **never had a meaningful favorable excursion**. They were going adverse from near-entry.

## What this confirms

37% of pyramid_cut trades had MFE ≤ 0 — they were immediately underwater and never recovered. Another 33% had MFE between $0 and $0.50 — barely favorable before reversing. Only 30% reached MFE > $0.50/share. None of these trades pyramided up before being cut, because pyramider adds only at +1.5R+. So the "compounding" framing in Track 1 is wrong; these are vanilla initial positions hitting the loss cap.

## Confidence at entry

| Subset | n | avg composite confidence at entry |
|---|---|---|
| Pyramid_cut trades | 57 | 0.401 |
| All other exits | 125 | 0.428 |

The pyramid_cut bucket has marginally lower confidence — consistent with the composite-gate fix removing them.

## Deep cuts (≥3R) — the one actionable finding

5 of 57 cuts (9%) overshot the -1.0R trigger by 2× or more, ending at -3.0R to -3.6R. PnL impact: −$26.79 across just these 5 trades, average −$5.36/trade — they're $2.47/trade more costly than the median pyramid_cut.

Mechanism: the engine ticks at 10s intervals. If price moves fast between bars (news, large order, gap), the price can be at -3R by the time the next tick fires. The CUT_FULL action submits a market order, which fills at next bar's open or partway through, often further from the -1.0R trigger.

**Potential mitigations (Exp 6 candidate, not for RC-1.5):**
- Tighter tick interval during open positions
- Bar-boundary-aware deep-cut detection: if the bar's HIGH/LOW shows the cut threshold was crossed mid-bar, log and consider a tighter exit policy
- Pre-position broker stop order (Alpaca supports stop orders) — submit at entry time, broker handles fast moves

Queue as **Exp 6** for after RC-1.5 + RC-2 ship and stabilize.

## Pyramid_cut interaction with the composite-gate fix (RC-1.5)

Counterfactual: of the 57 pyramid_cuts, how many had composite < 0.45 at entry?

| Subset | n | % |
|---|---|---|
| Pyramid_cut, composite < 0.45 (would be filtered by RC-1.5 gate) | **46** | **81%** |
| Pyramid_cut, composite ≥ 0.45 (would still fire) | 11 | 19% |

**81% of pyramid_cut events trace back to entries the RC-1.5 gate would have filtered.** This cleanly confirms the upstream-cause hypothesis: the gate fix attacks the right thing without needing pyramider changes.

Expected post-deploy: pyramid_cut share drops from 31% of exits to roughly **6% of exits** (= 31% × 19%). Track this in the 5-session observation window.

## Recommendations

| Item | Priority | Where |
|---|---|---|
| **No pyramider code change for RC-1.5/RC-2** | — | Upstream gate fix addresses entry quality |
| **Verify post-RC-1.5 that pyramid_cut share drops materially** | P1 | Track in 5-session post-deploy observation |
| **Exp 6: deep-cut overshoot mitigation** | P2 | After RC-2, after we've measured remaining cuts |
| **Track 1 correction in memory** | P3 | Done in this report — pyramider doesn't compound losses on these trades |
