# Next Deploy Decision

**Date**: Apr 23, 2026
**Based on**: 5-session observation window (Apr 16-22), 90 trades, 348 all-time

---

## Decision 1: KEEP current stack?

### **YES — KEEP**

The current stack (Exp1A + Exp2 + Exp3 prep on `ce06d41`) is working as intended:
- Pyramid cut share dropped from 56% to 33%
- PSQ/SH chop trades eliminated completely
- Expectancy improving (-$1.75 all-time -> -$0.41 last 100)
- Infrastructure is stable (0 restarts, no brain incidents)
- Evolution activated cleanly at trade 300

No algorithm rollback is warranted. The experiments are having the designed effect.

---

## Decision 2: Is hardening deploy cleared for Thu Apr 23 post-close?

### **YES — CLEARED**

Rationale:
1. **Mechanical stability proven**: 5 sessions, 0 restarts, 0 incidents, 0 brain save failures
2. **Algorithm stable**: No regressions from evolution activation at trade 300
3. **Hardening is additive**: G1/G2/G3 fix edge cases, H1/H2 add safety caps, H5 adds governance, alerts add observability — none change the trading algorithm
4. **CAP/HALT disabled by default**: Per-trade notional cap and daily max-loss halt are controlled by env vars (`ORGANISM_MAX_NOTIONAL=0`, `ORGANISM_MAX_DAILY_LOSS=0`), so they ship inert
5. **No outstanding P0/P1 blockers**

### Pre-deploy checklist
- [x] Market closed
- [x] Positions flat (confirmed: `[]`)
- [x] Container healthy (running, 0 restarts)
- [x] Brain synced (manifest total_trades=348, learning_state total_trades=348)
- [x] 5-session observation complete
- [ ] `git rev-parse HEAD` = target commit (to be verified at deploy time)

---

## Decision 3: Hardening-only (without Exp4) or full HEAD `33d6138` including Exp4?

### **FULL HEAD `33d6138` — INCLUDE EXP4**

Rationale:

1. **Exp4 addresses the #1 remaining problem.** Trailing-stop giveback is the biggest value-destruction mechanism:
   - 61% of trades went green then closed red
   - $195.21 of MFE given back in 5 sessions
   - 8 trailing-stop exits gave back $31.38
   - Trailing stop widening from 3.0x to 5.0x ATR in chop directly targets this leak

2. **Cherry-picking around Exp4 is risky.** Exp4 (`b97f903`) sits between G1/G2/G3 and H1/H2 in the commit chain. Cherry-picking introduces merge conflict risk for marginal value.

3. **Exp4 scope is narrow.** It only affects `trailing_stop` in chop regime — one constant change in `adaptive_exits.py`. It does not touch entries, sizing, confidence, or persistence.

4. **Evolution partially offsets Exp4.** The evolved `trailing_distance_scale=0.8916` tightens the trailing stop by ~11%. With Exp4's 5.0x base, the effective trailing in chop becomes 5.0 × 0.89 ≈ 4.45x ATR — still wider than the current 3.0x but more moderate than a raw 5.0x.

5. **The data supports it.** The trailing stop was the worst exit type in the window: -$4.72 net PnL, 25% WR, average $3.92 MFE giveback per trade. Widening the trailing distance is the natural next experiment.

6. **Tests pass.** Exp4 has 7 passing tests with zero regression impact.

---

## Decision 4: Why?

### The reasoning chain

1. **The system is mechanically stable.** Five sessions, zero incidents. This is the prerequisite for any deploy and it is met.

2. **The hardening bundle reduces real-money risk without changing trading logic.** G1 (exit-level restore), G2 (cooldown fix), G3 (pyramider NaN guard), H1 (risk-budget cap), H2 (feature drift guard), H5 (settings governance), alerts — all are defensive. They make the system safer without altering when or how it trades.

3. **Exp4 targets the largest remaining leak.** The 5-session data clearly shows trailing-stop giveback as the dominant problem. $195.21 of favorable excursion was destroyed by exits that triggered too early. Exp4's trailing-stop widening in chop is the minimal intervention that directly addresses this.

4. **The evolution activation did not break anything.** Trade 300 crossed on Apr 20 (Session 3). Post-300 performance is statistically indistinguishable from pre-300 within the window. The evolved parameters are safe.

5. **CAP/HALT ship disabled.** The risk controls (notional cap, daily max-loss) deploy with env vars at 0, meaning they don't change live behavior until explicitly activated. This lets us validate the code path without risk.

6. **The expectancy trend is improving.** From -$1.75 all-time to -$0.41 over the last 100 trades. The system is converging toward breakeven. Adding Exp4 (trailing giveback control) is the logical next step to push expectancy positive.

---

## Deploy summary

| What | Decision |
|------|----------|
| Current stack | **KEEP** (no rollback) |
| Hardening deploy | **CLEARED** for Apr 23 post-close |
| Deploy scope | **Full HEAD `33d6138`** (hardening + Exp4) |
| CAP/HALT | Ships disabled (`=0`), activate later |
| Alerts | Ships silent (no `SLACK_WEBHOOK_URL`), wire later |
| Rollback target | `ce06d41` if regression detected |

### Post-deploy monitoring plan
After deploying `33d6138`, monitor the first 2 sessions (Apr 24-25) for:
1. **Trailing-stop behavior in chop**: Should see wider trailing, fewer premature trailing exits
2. **MFE giveback reduction**: The 61% giveback rate should improve
3. **G1/G2/G3 log signatures**: Confirm hardening code paths are present
4. **H1/H2 activation**: Risk-budget cap and drift guard should log on boot
5. **Evolution interaction**: Evolved trailing_distance_scale (0.89) × Exp4 base (5.0x) = ~4.45x effective — verify this is the actual behavior
6. **No increase in stop_loss exits**: Widening trailing should not cause more stop-loss hits

---

## Next decision points after deploy

1. **After 2 sessions (Apr 25)**: Quick sanity check — is Exp4 reducing trailing giveback?
2. **After 5 sessions (Apr 29-30)**: Full Exp4 observation verdict — is expectancy improving?
3. **When expectancy crosses zero**: Consider activating CAP/HALT with conservative values ($2500 notional, $250 daily max-loss)
4. **When Exp3 data is conclusive**: Decide on ML-confidence formula change (Exp3B)
5. **Stage 1 tiny live capital**: Only after all of the above gates pass
