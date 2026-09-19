# Track PP v9 — Chaos / Fault-Injection (NEW LENS)

V8 OO meta-audit ranked CHAOS-GAP as Critical: 0 of 278 historical findings came from fault injection. The cycle's three most severe historical bugs (reconciliation pollution, alert silent-drop, PnL drift) were chaos-shaped — caught only post-mortem. **Track PP ships the missing lens for V9.**

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `db1a3fc`. Use a SCRATCH container or local sandbox; NEVER touch production.

## Method

This is read-mostly with controlled small mutations on a SCRATCH copy. If a scratch DB / container isn't easily available, use code-review + targeted unit tests instead of live chaos.

### Strategy

For each high-blast-radius surface, ask: "What if X fails right now?"
For each `try / except`, ask: "What state is left dirty if this except fires?"
For each external dependency, ask: "What if the call hangs? Is there a timeout? What does timeout-recovery look like?"

### 1. Database failure modes

| Scenario | Code site | Question |
|---|---|---|
| Postgres down at startup | `lifespan.py` startup | Does the API start with degraded mode, or fail-fast? |
| Postgres connection drops mid-tick | `_live_tick_inner` step 4 (audit_log) | Is the tick aborted or partial? Does brain save still work? |
| Postgres slow (5s query) on `audit_logs` write | `fire_audit_log_threadsafe` | Does the tick miss its 10s deadline? |
| Hash chain breaks (one row corrupted) | ComplianceAuditService | Does verify_chain_integrity surface it; does the next write proceed or halt? |

For each, identify the actual code path and assess whether failure mode is acceptable.

### 2. Broker / Alpaca failure modes

| Scenario | Code site | Question |
|---|---|---|
| Alpaca returns 5xx on submit_order | `_submit_entry_order` / `_submit_exit_order` | Retry? Backoff? Position state correctness? |
| Alpaca returns 429 rate limit | (same) | Backoff schedule? Does it mask a too-aggressive trade rate? |
| Alpaca WS drops mid-stream | `alpaca_stream.py` reconnect | Are pending fills recovered on reconnect, or lost? |
| Broker fills order but WS message lost | reconciliation | Does the next tick reconcile? What's the lag? |
| Alpaca clock drift (broker timestamp 2 min off) | `_now_fn`-fed comparisons | Does any logic assume broker_time ≈ now()? |

### 3. Brain-save failure modes

| Scenario | Code site | Question |
|---|---|---|
| Disk full mid-`organism_brain/manifest.json` write | brain save path | Atomic rename? Or partial-write corruption? |
| Brain backup directory permission denied | brain backup path | Silent skip or alert? |
| Process killed (SIGTERM / SIGKILL) mid-save | shutdown handler | Was a save in flight? Does it leave a `.tmp` file? |
| Brain file truncated to 0 bytes | startup load path | Does load fail clean? Recover from latest backup? |

### 4. Alert dispatch failure modes

V5/V6/V7 had 4 rounds of fix-didn't-fix on the alert dispatcher. Verify:
- Slack webhook returns 5xx → does the call retry? Block the tick?
- Slack URL not configured → log warning, continue (verified historically).
- Main event loop dropped → set_main_event_loop fallback?
- 1000 alerts queued in 1s → bounded queue or unbounded growth?

### 5. State persistence under restart

| Scenario | Question |
|---|---|
| Restart 5x in 1 hour | Brain coherence preserved at every cycle? `_pending_exit` / `_exit_cooldown` re-hydrated correctly? |
| Restart mid-tick (signal during _live_tick_inner) | Was `_tick_count` incremented? Does the next start re-process? |
| Restart with 5 open positions | Are positions reconstructed from broker, or read stale from manifest? |

### 6. Universe scanner failure modes

| Scenario | Question |
|---|---|
| Alpaca movers API returns 0 symbols | Does the universe degrade to a default set, or block trading? |
| Scanner tick fails 5 times in a row | Backoff / circuit breaker? |

### 7. Time-of-day boundary chaos

| Scenario | Question |
|---|---|
| 16:00:01 ET — first second past close | Pending fills arrive: handled? |
| DST transition (Mar 9 / Nov 2) | _now_fn() jumps an hour: does anything double-count? |
| Leap second | (Probably not a real concern but) |

### 8. Code review for `except Exception: pass` silenced errors

This overlaps Track UU but specifically chaos-relevant:

```
grep -rn "except Exception:" backend/ --include='*.py' | wc -l
grep -rn "except Exception:" backend/ --include='*.py' | grep -c "pass"
```

Identify the top 5 most-dangerous swallowed exceptions (those in tick path, broker path, brain save path).

## Output

`artifacts/audit/v9_reports/track_pp_chaos_fault_injection.md` with:
- Failure-mode table per category (above)
- Severity tags (Critical: data loss / fund loss; High: alert silenced; Medium: reconnect lag; Low: cosmetic)
- Top 5 swallowed-exception sites
- Recommended chaos drills for V10

Quality bar: 3-7 findings. End with one-paragraph TL;DR. **This track has the highest "we never knew this was broken" potential.**
