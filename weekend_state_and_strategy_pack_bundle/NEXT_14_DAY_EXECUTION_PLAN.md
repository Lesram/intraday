# NEXT 14-DAY EXECUTION PLAN
**Window:** 2026-04-25 (Sat) → 2026-05-08 (Fri)
**Live commit:** `ce06d41`
**HEAD:** `eb90fa3`
**Strategy:** ship `eb90fa3` Mon pre-open → 5–10 session observation → Exp 3 design → Stage-1 readiness gate

---

## Principles for the window

1. **One deploy.** Land `eb90fa3` cleanly Mon pre-open. Do not stack a second deploy on top until 5+ post-deploy sessions are observed.
2. **No experiment design changes during observation.** Exp 1A and Exp 2 stay live untouched. Exp 3 logging stays untouched.
3. **No structural persistence edits.** F1–F4 + F-lite remain frozen / observation-only.
4. **No real capital this window.** The earliest plausible Stage-1 cutover is ~2026-05-12 (3 days after this window ends), and only if all 8 proofs from `REAL_MONEY_STATUS_REFRESH.md` come back green.
5. **Daily post-close audit, weekly cumulative review.** One `POSTCLOSE_*.md` per session. One `WEEK_<n>_REVIEW.md` next Friday.

---

## Calendar

| Date | Day | Plan |
|---|---|---|
| Sat 2026-04-25 | Sat | Weekend pack circulated. Replay regression on `eb90fa3` run + captured to `artifacts/replay_summary.json`. Brain backup snapshot taken. PR review bundle composed under `docs/engineering/reviews/pr-XXX-eb90fa3/`. **No deploy.** |
| Sun 2026-04-26 | Sun | Quiet day. Optional: tidy untracked `.md` audit reports into `docs/engineering/audits/`. Optional: run a fresh full test suite on a clean checkout. **No deploy.** |
| Mon 2026-04-27 | Open | **DEPLOY `eb90fa3` pre-open (8:30–9:00 ET).** Run preflight checklist from `RC_DEPLOY_READINESS_RECHECK.md`. Babysit first 30 minutes. Verify alert wiring, notional cap, daily max-loss, drawdown-kill validator log lines. |
| Mon 2026-04-27 | Close | Post-close audit: `POSTCLOSE_FULL_PICTURE_2026-04-27.md`. Verify manifest+learning_state still in sync, no halt events. |
| Tue 2026-04-28 | — | Live run + post-close. |
| Wed 2026-04-29 | — | Live run + post-close. |
| Thu 2026-04-30 | — | Live run + post-close. |
| Fri 2026-05-01 | Week 1 close | Week-1-on-`eb90fa3` review: did pyramid_cut share drop ≥30%? Did trailing_stop giveback shrink? Did notional cap or daily max-loss fire (any false positives?)? |
| Sat 2026-05-02 | Sat | Mid-window assessment. Decide: (a) continue observation; (b) tighten any param; (c) design Exp 3 execution variant. |
| Sun 2026-05-03 | Sun | Exp 3 execution design draft (offline). 30-day replay backtest scaffold. **Do not commit anywhere near `live_engine` execution paths.** |
| Mon 2026-05-04 | — | Live run + post-close. |
| Tue 2026-05-05 | — | Live run + post-close. |
| Wed 2026-05-06 | — | Live run + post-close. |
| Thu 2026-05-07 | — | Live run + post-close. Exp 3 execution backtest results in. |
| Fri 2026-05-08 | Window close | **Stage-1 readiness gate.** Are all 8 proofs from `REAL_MONEY_STATUS_REFRESH.md` green? If yes, schedule Stage-1 cutover for 2026-05-12. If no, list specific outstanding proofs, extend window. |

---

## What stays unchanged (do NOT touch)

- Universe: 22 symbols. Do not add or remove during observation.
- ML weights, retrain cadence, freeze gate at 300 trades, evolution gen+param-apply.
- Confidence weights (production: ml=0.5, breakout=0.3, tension=0.2; learning unused — we are post-300).
- Stop ATR table: trending_up=3.5, trending_down=2.5, chop=2.5, high_vol=4.0, low_vol=3.0, stress=2.5.
- Risk budget: learning=0.10%, production=0.25%.
- ALPHA_TOP_N=5. MAX_OPEN_POSITIONS=8. Tick interval=10s. Bar boundary=true. Horizon timeout=18 bars.
- Exp 1A min-hold gate. Exp 2 inverse-ETF chop suppression. Exp 3 prep logging.
- F1–F4 + F-lite brain guards. AGENTS.md. Hooks. CI.

---

## What to observe — week 1 (post-deploy)

| Metric | Pre-deploy baseline (`ce06d41`, 12 sessions) | Week-1 target post-deploy |
|---|---|---|
| Trades / session | 15.2 | 12–18 (no shock) |
| Pyramid_cut share | 31.3% of exits | **≤ 22%** (G1/G2/G3 should reduce; baseline is too high) |
| Stop_loss share | 19.2% | **≤ 18%** (no expected change from G-series; flag if increases) |
| Trailing_stop giveback (MFE−realized per share) | $77/$−10 | **trailing_stop avg PnL ≥ $0** (Exp 4 widens chop trail) |
| Win rate | 31.3% | **≥ 35%** would be a real signal |
| Expectancy | −$0.59 | **≥ −$0.30** would be progress; ≥ 0 would be a milestone |
| Halt / freeze events | 0 | 0 (any halt is a P0 to investigate) |
| Manifest+learning_state sync at session close | 100% | 100% |
| Alert wiring deliveries on synthetic events | n/a (not deployed) | 100% (all test events received in Slack/webhook) |

If after 5 sessions the pyramid_cut-share metric **does not drop to ≤22%**, that's a tell that G2 (cooldown-on-success-only) isn't doing what we expected and we need to dig in.

---

## What to ship next (after observation phase)

Priority order, conditional on observation results:

| Item | Trigger | Type |
|---|---|---|
| **Exp 3 execution variant** | After 60+ samples per confidence bucket post-deploy AND offline 30-day backtest shows positive lift | strategy experiment, offline-first |
| **Stop-loss ATR re-tune in chop** (Exp 5) | If post-deploy stop_loss expectancy still < −$1.50/trade after 10 sessions | strategy experiment, offline-first |
| **Brain backup rotation** | Always — small ops task | ops |
| **Replay regression in `pr-verify.yml`** | Always — small CI task | testing |
| **Stage-1 risk parameter set** | After 10 clean post-deploy sessions and all 8 proofs green | risk |
| **Universe trim for Stage 1** (top 8 by liquidity) | At Stage-1 cutover only | risk |

---

## What to prepare offline (parallel, no live impact)

These can be drafted / scaffolded during the observation window without touching live:

1. **Exp 3 execution variant:**
   - Two variants: (a) gate entries above 0.7 confidence; (b) invert direction above 0.7 confidence; (c) reweight ml_signal contribution as a function of confidence.
   - Backtest scaffold: 30 days of bar data, paper-config replay, fold-validate (3 folds).
   - **Do not edit `live_engine.py` until backtest results are in and reviewed.**

2. **Brain backup rotation:**
   - One-line cron in `paper-postclose-audit.yml` that copies `organism_brain/` → `organism_brain_archive/<date>/`.

3. **Stage-1 capital plan:**
   - $500–$1000 starting capital.
   - Notional cap: $200 absolute or 20%, whichever lower.
   - Daily max-loss: $50 or 5%, whichever lower.
   - MAX_OPEN_POSITIONS: 2.
   - Universe: top 8 by liquidity.
   - Document in `STAGE_1_CAPITAL_PLAN.md` (not yet committed).

4. **Replay-test CI gate:**
   - Add `pytest tests/test_replay_simulator.py --timeout=60` step to `pr-verify.yml` for changes touching `backend/organism/**`.

5. **Coherence cleanup (Phase C-1):**
   - Design doc only: clean separation of `ranking_score / direction / expected_return / size`. **No code changes during this window.**

---

## What explicitly should NOT change

- **No new strategy experiments deployed during observation.** Exp 5 design is OK; deploy is not.
- **No tuning of confidence thresholds, stop ATR, or risk budgets** during observation.
- **No universe changes** during observation.
- **No structural edits to `brain_persistence.py`, `live_engine.py` save paths, or governance restoration.** F-track is frozen.
- **No real capital movements.**
- **No CI workflow changes that could break post-close audit.**

---

## What must happen before any real-money step

(restated from `REAL_MONEY_STATUS_REFRESH.md`, hard-coded as gate)

```
[ ] eb90fa3 deployed clean
[ ] 5+ clean post-deploy paper sessions (no halt, no manifest corruption)
[ ] Notional cap reject path verified live
[ ] Daily max-loss kill verified live
[ ] Alert wiring verified live (Slack/webhook delivery confirmed)
[ ] Canonical drawdown-kill startup validator logs the correct value
[ ] No regression in execution latency, brain save cadence, ML retrain
[ ] Expectancy ≥ neutral over 5 post-deploy sessions
[ ] G1/G2/G3 reduces pyramid_cut share to ≤22% (≥30% relative reduction)
[ ] Exp 4 trailing-stop giveback measurably reduced
[ ] Brain backup rotation in place
[ ] Stage-1 risk parameter set documented and reviewed
[ ] Real-money capital allocation discussion with operator (not engineering)
```

All twelve must be green.

---

## Decision points

| When | Decision |
|---|---|
| Mon 2026-04-27 09:00 ET | Did `eb90fa3` deploy cleanly? If no → revert, regroup, postpone to Tue. |
| Fri 2026-05-01 close | Week-1 metrics on track? If no → diagnose, do not deploy further. |
| Fri 2026-05-08 close | All 8 proofs green? If yes → schedule Stage-1 cutover for 2026-05-12. If no → extend window, list outstanding gates. |

---

## Immediate next action (next 24 hours)

1. **Saturday morning:** run replay regression on `eb90fa3`; capture to `artifacts/replay_summary.json`. Take brain backup snapshot.
2. **Saturday afternoon:** compose PR-review bundle under `docs/engineering/reviews/pr-XXX-eb90fa3/` per AGENTS.md two-step convention. Open the PR (do not merge).
3. **Sunday afternoon:** run the full preflight checklist from `RC_DEPLOY_READINESS_RECHECK.md` end-to-end as a dry-run (without the actual `docker-compose up --build` step).
4. **Monday 8:30 ET:** execute deploy.

---

## Single most important next move

**Deploy `eb90fa3` Monday pre-open, with a human at the keyboard for the first 30 minutes.** Everything else in this plan is downstream of that one move.
