# Post-Close Full Picture — 2026-04-16 (Thursday)

## 1. Executive verdict

**Experiment verdict: NO SESSION YET**
**Mechanical verdict: CLEAN**

The Exp2 + Exp3 prep deployment completed at 02:42 UTC today. The market has not yet opened (next open: Thu Apr 16 13:30 UTC, ~10.5h from now). Zero trades, zero ticks, zero errors. The container booted cleanly with the correct experiment stack. This report serves as the pre-session verification that the deployment is healthy and ready.

## 2. Session identification

- Date reviewed: 2026-04-16
- Market: NOT YET OPEN (next open 13:30 UTC)
- Container: `ce06d41` (Exp1A + Exp2 + Exp3 prep) — deployed 02:42:22 UTC today
- Exp1A: PRESENT (1 match)
- Exp2: PRESENT (2 matches)
- Exp3 prep: PRESENT (1 match)
- Exp4: ABSENT (0 matches)

## 3. Live state verification

| Check | Result |
|---|---|
| Container | running, restarts=0, healthy, started 2026-04-16T02:42:22Z |
| API | ok |
| Account | ACTIVE, equity=$111,535.90 |
| Positions | flat |
| Manifest sync | ALL ✅ (gen=70, trades=258, pnl=-562.88, best_sharpe=3.4363) |

## 4. Mechanical integrity

- Guard fires: ALL ZERO ✅
- Errors today: 0 ✅
- Ticks today: 0 (market not yet open)
- Orders today: 0
- Container healthy, fresh boot from Exp2 deploy

**Session trustworthy**: N/A — no session occurred yet. The container is ready.

## 5-11. Trade activity

No trades, no fills, no ticks. The first Exp2 observation session begins at market open (13:30 UTC).

## 12. Experiment tracking

**Status entering first Exp2 session:**

| Experiment | Status | What to watch |
|---|---|---|
| Exp1A (min-hold) | LIVE, verified KEEP after 3 sessions | Continue tracking pyramid_cut % |
| Exp2 (inverse ETF gate) | **LIVE, first session pending** | PSQ/SH trades = 0 in chop? Suppression logs? |
| Exp3 prep (confidence logging) | **LIVE (read-only)** | confidence_bt_only fields populated? |
| Exp4 (trailing-stop) | OFFLINE | Not deployed |

**Cumulative from Exp1A window (Sessions 1-3):**

| Metric | Baseline | Exp1A cumulative (44 trades) |
|---|---:|---:|
| Pyramid_cut % | 75% | 43% |
| Timeout/max_hold % | 16% | 23% |
| Win rate | 18.8% | 25.0% |
| Expectancy | -$1.92 | -$1.11 |
| Avg hold | 550s | 803s |

## 15. Decisions

1. **Continue current live stack unchanged?** YES — Exp2 hasn't had its first session yet.
2. **Session trustworthy?** N/A (no session).
3. **Is Exp2 helping?** TOO EARLY — first session is today.
4. **Exp3 evidence?** INCONCLUSIVE — needs trade data with side-by-side fields.
5. **Exp4 leapfrog?** NO.
6. **Blocker?** NO.

**Next action**: Run the full post-close report AFTER today's market close (~20:00 UTC). That will be the first Exp2 observation session.

**Live branch must remain unchanged**: `ce06d41` (Exp1A + Exp2 + Exp3 prep).
