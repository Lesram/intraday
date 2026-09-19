# MASTER ISSUE LEDGER — WEEKEND REFRESH
**Audit time:** 2026-04-25T00:50Z
**Live commit:** `ce06d41`
**HEAD:** `eb90fa3`

Severity legend: **P0** blocks real-money / breaks platform; **P1** material drag or risk; **P2** quality / observability; **P3** cleanup.

Status legend: **LIVE** active in container; **OFFLINE READY** in repo at HEAD, not deployed; **FROZEN** observation-only; **BACKLOG** not yet implemented; **RESOLVED** closed in this audit window.

---

## A. Real-money blockers

| ID | Sev | Cat | Status | Title | Code surface | Next action | Timing |
|---|---|---|---|---|---|---|---|
| RM-1 | P0 | risk | OFFLINE READY | Per-trade notional cap missing in live container | `bb5cbb5` `kelly_sizer.py` (+18) + `test_real_money_risk_limits.py` | Deploy `eb90fa3` | Mon pre-open |
| RM-2 | P0 | risk | OFFLINE READY | Daily max-loss circuit breaker not in live | `bb5cbb5` `live_engine.py` + `governance.py` | Deploy `eb90fa3` | Mon pre-open |
| RM-3 | P0 | risk | OFFLINE READY | H1 production risk-budget cap not enforced live | `679ffd2` `kelly_sizer.py` | Deploy `eb90fa3` | Mon pre-open |
| RM-4 | P0 | algorithm | OFFLINE READY | H2 feature drift guard not active live | `679ffd2` `ml_signal.py` | Deploy `eb90fa3` | Mon pre-open |
| RM-5 | P0 | governance | OFFLINE READY | Drawdown-kill resolution path not canonical (no startup validator live) | `0ac6e2d` `governance.py` (+62) | Deploy `eb90fa3` | Mon pre-open |
| RM-6 | P1 | governance | OFFLINE READY | Compose ORGANISM_DRAWDOWN_KILL_PCT default mismatch with code | `eb90fa3` `docker-compose.yml` (+5) | Deploy `eb90fa3` | Mon pre-open |
| RM-7 | P0 | ops | OFFLINE READY | No alert wiring on critical events (halt, freeze, drawdown trip, alpaca down) | `33d6138` `live_engine.py` + `governance.py` | Deploy `eb90fa3` + provision Slack URL | Mon pre-open |
| RM-8 | P1 | governance | OFFLINE READY | Settings API does not enforce frozen/halted state on writes | `c306074` `routes/settings.py` (+14) | Deploy `eb90fa3` | Mon pre-open |
| RM-9 | P1 | risk | LIVE | Drawdown-kill threshold = 20% (very wide for tiny capital) | `governance.py` env `ORGANISM_DRAWDOWN_KILL_PCT` | After Stage-1 capital lands, tighten to e.g. 5% for tiny-capital phase | Stage-1 prep |

---

## B. Strategy / algorithmic issues

| ID | Sev | Cat | Status | Title | Evidence | Next action | Timing |
|---|---|---|---|---|---|---|---|
| ALG-1 | P1 | algorithm | LIVE | Pyramid_cut is 31% of all exits, −$165 over 12 sessions (dominant drag) | live_window.csv | G1/G2/G3 + Exp 4 deploy reduces; deeper rethink (no-pyramid in chop?) is Phase C | Deploy + 5 sessions, then assess |
| ALG-2 | P1 | algorithm | LIVE | Stop_loss avg −$1.94/trade, 35 events, 19% of exits, −$68 over 12 sessions | live_window.csv | Re-tune chop stop ATR (currently 2.5×) using replay; currently OFFLINE evaluation only | After deploy, in observation phase |
| ALG-3 | P2 | algorithm | LIVE (logging) | Confidence-inversion observation: 0.5–0.6 = +$0.27 expectancy; ≥0.7 = −$0.72 | Exp 3 prep logs | Exp 3 execution variant requires offline backtest + 60+ samples per bucket | 14-day window → design |
| ALG-4 | P2 | algorithm | LIVE | Avg directional accuracy = 31% (well below the 50% reference) | live_window.csv | This is *direction* not just *outcome*; the 31% says we're often wrong on direction even when stops/timeouts mask it. Investigate alpha+breakout direction logic in chop | After deploy |
| ALG-5 | P2 | algorithm | LIVE | Trailing_stop captures only a fraction of MFE in chop ($77/share aggregate vs −$10 realized) | live_window.csv | Exp 4 deploys with `eb90fa3` and addresses this | Mon pre-open |

---

## C. Mechanical / structural issues

| ID | Sev | Cat | Status | Title | Code surface | Next action | Timing |
|---|---|---|---|---|---|---|---|
| MECH-1 | P1 | mechanical | OFFLINE READY | G1 — exit-level restore warning missing (silent loss of stop/trail levels on restart) | `15cc0a4` `live_engine.py` | Deploy `eb90fa3` | Mon pre-open |
| MECH-2 | P1 | mechanical | OFFLINE READY | G2 — cooldowns triggered on losing trades (consume budget without an outcome to learn from) | `15cc0a4` `live_engine.py` | Deploy `eb90fa3` | Mon pre-open |
| MECH-3 | P1 | mechanical | OFFLINE READY | G3 — pyramider can NaN if avg_price is 0 / not initialized | `15cc0a4` `pyramider.py` (+8) | Deploy `eb90fa3` | Mon pre-open |
| MECH-4 | P3 | mechanical | LIVE | `reconciliation_adjustment` exits inflate / deflate per-day P&L (today: ±$20) | trade_history.csv | Tag and exclude from strategy P&L in reports; pure cosmetic | Backlog |

---

## D. Brain / persistence (F-track — already shipped)

| ID | Sev | Cat | Status | Title | Notes |
|---|---|---|---|---|---|
| F-1 | P0 | structural | RESOLVED (`eaa4b2f`/`3a694ee`) | All save() paths route through `_write_manifest_guarded` | LIVE |
| F-2 | P0 | structural | RESOLVED (`9e7c9a9`) | Break-glass reset + suspicious-write instrumentation + read-back invariant | LIVE |
| F-3 | P0 | structural | RESOLVED (`7d36b61`) | LiveEngine forensic guard + bypass audit | LIVE |
| F-4 | P0 | structural | FROZEN | Structural persistence path observation-only | No further structural edits in flight |

---

## E. Experiments

| ID | Sev | Cat | Status | Title | Evidence | Next action | Timing |
|---|---|---|---|---|---|---|---|
| EXP-1A | P2 | algorithm | LIVE | Chop-regime min-hold gate for pyramid_cut | Avg chop pyramid_cut bars=7.8 | KEEP — working as designed | n/a |
| EXP-2 | P2 | algorithm | LIVE | Chop inverse-ETF entry suppression | 3 PSQ/SH trades only, all early window | KEEP — eliminated drag | n/a |
| EXP-3-PREP | P2 | algorithm | LIVE | Confidence inversion side-by-side logging | Bucket inversion confirmed | KEEP logging; design Exp 3 execution after 60+ samples per bucket | After deploy |
| EXP-3-EXEC | P2 | algorithm | BACKLOG | Confidence inversion execution variant (gate / invert above threshold) | n/a | Offline backtest + 30-day window before deploy | 14-day window → backtest |
| EXP-4 | P2 | algorithm | OFFLINE READY | Chop trailing-stop giveback control (5.0× ATR widen, or disable) | `b97f903`, 7 tests pass | Bundle into next deploy | Mon pre-open |
| EXP-5 | — | — | BACKLOG | (Open slot) Stop-loss ATR re-tune in chop, post-Exp 4 | Drag analysis | Design after observing Exp 4 effect | 14-day window |

---

## F. Observability / ops / testing

| ID | Sev | Cat | Status | Title | Next action |
|---|---|---|---|---|---|
| OPS-1 | P1 | ops | OFFLINE READY | Slack/webhook URLs not yet provisioned in `.env` | Provision before/at deploy |
| OPS-2 | P2 | ops | LIVE | Alpaca SSL `UNEXPECTED_EOF` events seen Apr 23 18:47 (3 calls / 1 min) | Add backoff + retry telemetry; non-blocking, log-only fix |
| OPS-3 | P2 | ops | LIVE | Scanner request retry failures (Apr 23, Apr 24) — 1 each, no positions impact | Increase scanner retry budget; non-blocking |
| OPS-4 | P2 | ops | LIVE | `paper-postclose-audit` GitHub workflow runs daily — has it published reports recently? | Verify workflow output for last 5 sessions |
| TEST-1 | P2 | testing | LIVE | 4 flaky async tests pass individually, fail in full suite | Known timing issue; document in CONTROL_PLANE.md; defer fix |
| TEST-2 | P1 | testing | LIVE | No replay regression in CI on PR-merge | Add replay test gate to `pr-verify.yml` workflow |

---

## G. Coherence / dead code / stale subsystems

| ID | Sev | Cat | Status | Title | Notes |
|---|---|---|---|---|---|
| COH-1 | P3 | architecture | LIVE | `is_exploration` column always False in trade_history (exploration removed in H1) | Cosmetic; CSV column kept for backwards compat. |
| COH-2 | P3 | architecture | LIVE | `entry_source` is empty string for ml_reversal/trailing_stop entries | Annotate from upstream caller; observability gap |
| COH-3 | P3 | architecture | BACKLOG | `ranking_score / direction / expected_return / size` are conflated in alpha scanner output | Phase C-1 design |
| COH-4 | P3 | architecture | BACKLOG | True microstructure alpha (order-flow imbalance, depth) not implemented | Phase C-2 |
| COH-5 | P3 | architecture | BACKLOG | Staged learning→production transition (4 stages: 0→1→2→3) | Phase C-3 |
| COH-6 | P3 | architecture | LIVE | `governance.policy_version` and `config_hash` are empty strings | Set on deploy/startup; non-blocking |

---

## Summary by category and severity

| | P0 | P1 | P2 | P3 |
|---|---|---|---|---|
| Real-money blockers | 5 | 4 | 0 | 0 |
| Strategy / algorithm | 0 | 2 | 4 | 0 |
| Mechanical / structural | 0 | 3 | 0 | 1 |
| Brain / persistence | 4 | 0 | 0 | 0 |
| Experiments | 0 | 0 | 6 | 0 |
| Observability / ops | 0 | 1 | 4 | 0 |
| Coherence | 0 | 0 | 0 | 6 |
| **Total** | **9** | **10** | **14** | **7** |

Of the **9 P0 items, 4 are RESOLVED (F-1..F-4) and 5 are OFFLINE READY (RM-1..RM-5, RM-7).** Zero P0 issues are open with no fix in flight. The next deploy resolves the 5 OFFLINE READY P0s in a single shot.
