# V11 State + Monday Handoff (2026-05-03 evening)

## Where the platform stands

**Branch:** `rc-1.5-curated @ eec9a0b`. Container `intra-api-1` rebuilt
3x today; running this branch's code. Brain coherent (gen=168, trades=498,
ml_trained=true). Migration head = `20260503_000003`.

## What V11 caught

49 findings across 12 tracks (4 NEW lenses: AAA, CCC, DDD, III). The
most operationally significant:

**Critical (now closed):**
- **AA5-1 / Wave-67**: V10 wave-47 silently broke ALL JWT auth in prod
  for ~24h. Wave-47's source-grep regression test passed even though
  the code was broken. Fixed by moving leeway into options dict.
- **CCC-2 / Wave-68**: kill-switch + risk-cap values diverged across
  5 places; paper compose wasn't wiring drawdown_kill OR daily-loss
  OR notional caps. Fixed by explicit fallbacks in both compose files.

**High (now closed in code):**
- **AAA-F1 / Wave-68**: `/test/http-*` debug endpoints exposed in paper
  image. Now require explicit opt-in env var.
- **AAA-F2 / Wave-68**: orders.py local require_trader stub ignored
  roles — self-registered users could place orders. Now enforces
  `{trader, admin}` role set.
- **BB5-F4 / Wave-67**: portfolio_history table created via alembic
  upgrade head. ck_orders_status widened.

## What's still open going into Monday

V11 found 49 actionable findings; 5 closed today. **44 still open**, at
descending blast radius:

**High (14, V11 fix waves 69-74):**
- **DDD-1**: ecdsa CVE-2024-23342 (transitive via python-jose).
- **UU3-1/2**: wave-57 lint rule has 2 grandfather typos + 3,542
  violations + CI not actually gating.
- **III-F1/F2**: PII (emails) logged cleartext; structlog scrubber
  unreachable in production.
- **BB5-F1**: outbox unbounded (1,393 rows / 60 days).
- **DD5-1/2/3**: wave-53 strategy fixes were one layer up from root cause:
  - DD5-1: chop-min-hold gate compares ticks to bar-units, inert.
  - DD5-2: live_engine private inverse-ETF set parallel to wave-60.
  - DD5-3: symbol_trade_counts_runtime is identity copy of promotion-gated.
- **HH3-N-1**: `_live_tick_inner` regressing (+196 LOC since V8 baseline).
- **TT3-F1**: ix_orders_attributes_gin index has idx_scan=0; call sites
  use text extraction instead of @> JSON containment.
- **AA5-2**: source-grep test pattern (anti-pattern from wave-47 in
  multiple test files).
- **CCC-1**: production validator demands wrong env var names.

None of these would cause a Monday-morning crisis. They're fix-during-
the-week priorities.

## Monday morning playbook

The remote agent at `trig_01Tukj3vRyLzfBCW1gFQPxLK` fires at 14:30 UTC
(10:30 ET). It will check out rc-1.5-curated, run the V10 wave test
suites, and open a PR with `artifacts/audit/v10_day1_verify.sh` (paste-
runnable on your machine in 30s) plus a report template.

**You should** (in this order):
1. Pull the PR, run the verify script, paste results into the report
   template. ~5 minutes.
2. Confirm `position_lots` / `realized_trades` populated post-fills (BB5-F1
   data verification — proves wave-43 DD3-2 + wave-67 migration are live).
3. Confirm Slack alerts work (drawdown-kill / daily-loss / emergency-
   stop) — wave-52 YY-1 closed silent paging on 4 critical sites.
4. If all green, kick off `git checkout main && git merge --no-ff rc-1.5-curated`
   then push.
5. If issues, file them as V12 inputs. The remote agent's PR is the
   right place to document.

## Honest answer to "do we expect significant improvement?"

Yes — measurably. From the V11 audit data:

| Surface | Pre-V8 reality | Post-V11 reality |
|---|---|---|
| JWT auth | Worked (until wave-47 broke it; never noticed because source-grep test passed) | Behaviorally tested; works |
| Trading-safety nets (DD2-1, DD3-3, DD3-4) | 30s windows where stops silenced | All breach paths evaluate against broker price |
| Operator paging | 6 critical sites silent (V5 S-J3-1 redux) | 4 of 6 now wire dispatch_alert_from_thread (drawdown-kill, emergency-stop, circuit-breaker, SLO burn). YY-3/4 expanded to label dimensions + ML retrain alerting. |
| Brain persistence | Single OOM = lose 161 generations; backups dir didn't exist in prod | Atomic CSV+JSON; backups mint hourly from essential save; corrupt-HEAD captured to forensic dir |
| Auth lifecycle | Logout returned 200 but didn't blacklist; refresh accepted as access | Logout blacklists via Redis; decode_token rejects token_type != "access"; refresh single-use |
| Migration recovery | downgrade base broken (poisoned txn); CHECK rejected `'new'`/`'pending_new'`/`'submitting'` | IF EXISTS; widened CHECK; portfolio_history applied |
| RBAC | orders.py let user-role tokens trade | Enforces {trader, admin} on state-mutating routes |
| Debug surface | /test/http-* exposed in paper | Gated behind explicit opt-in |
| Kill-switch | Diverged 5 ways; paper compose unwired | Explicit fallbacks; safe defaults at every layer |

**Your observation about repeat findings remains structurally true.**
V11 found that 3 V10 fixes were one layer up from the actual cause (DD5
cluster). The cycle keeps drilling deeper. Each round narrows the
blast-radius distribution: V8 had 5 Critical; V9 had 5; V10 had 1; V11
had 2 (one of which we already fixed during the audit).

## What V11 changed about my mental model

The platform was much more broken than I realized in V10. I thought
the wave-50 rebuild was the deploy moment. AA5 caught that wave-47
silently broke auth — the wave-50 rebuild propagated the break until
wave-67 fixed it ~24h later. Without V11, the auth break would have
shown up Monday morning when actual traffic hit `/auth/me`.

## Cycle health metric (V12 target)

V11 yielded 49 — exceeds the 10-30 estimate because the 4 NEW lenses
each found 4-8 first-round findings. **This is healthy expansion**, not
cycle failure. Per V8 OO: each new lens yields 5-10 first-round, then
diminishes. AAA / CCC / DDD / III are still in their first round.

V12 should:
- Retain all 17 lenses.
- Add 1 more new lens (DD-DEPLOY: container vs source-SHA verification —
  would have caught the wave-47 break before it reached prod).
- Yield expectation: 5-15 if waves 69-75 close cleanly.

If V12 finds <5 net-new, the cycle has converged and we drop to
quarterly cadence. We're close. One more round.
