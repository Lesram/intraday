# September 24 paper-session review

The platform completed a full session without a restart or logged tick errors, but made no trades. Broker orders, fills and authoritative ledger closes were all zero; equity remained $100,067.85, with $0 session change and no open positions. The running release was still PR28 source `3acb796`; the new improvement plan had not been deployed during this session.

| Measure | September 24 regular session |
| --- | ---: |
| Completed successful decision cycles | 845 |
| Cycles blocked by global stale-data gate | 250 / 845 (29.6%) |
| Median processing time | 17.1 seconds |
| Maximum processing time | 22 seconds |
| Longest completion-summary gap | 32.0 seconds |
| Positive scanner runs | 134 / 141 |
| Median candidates per scan | 38 |
| Orders / fills / closed trades | 0 / 0 / 0 |
| Local database/Redis readiness failures | 20 / 77 checks |
| Truncated watchdog alert-log windows | 41 / 77 checks |

The seven empty early scans were properly completed scans whose candidates failed qualification, not missing/invalid provider responses. All 141 qualification records had zero missing or invalid snapshots. Repeated scanner pools are not unique eligible trading opportunities.

Freshness-blocked cycles fell from 45.2% in September 23's post-deployment window to 29.6% today. Median cycle processing nevertheless increased from 13.4 to 17.1 seconds. Different market conditions, session windows and workloads prevent attributing this comparison to a code effect; no new deployment occurred today. The feature universe grew from 57 to 69 symbols during the regular session, with no corresponding streaming-subscription updates logged. The source-confirmed scanner-to-subscription gap persists.

There were 595 cycles without the early global stale block, but no resulting main-book signals. Logs contain 836 combined main-book routing rejections, 477 defensive-regime exclusions and 288 liquidity exclusions. These repeat across cycles and cannot form an additive unique-opportunity funnel. Of the routing messages, 271 logged confidence at least 0.45 and heuristic=False; the combined message still does not reveal which exact condition failed. This supports repairing diagnostics, not relaxing confidence thresholds or declaring that the strategy has no edge.

The 13:10 Pacific daily pack is READY_FOR_REVIEW with no collection issues; all 21 input hashes/sizes, report identity and pack identity verified. It passes observed session-coverage requirements. All four strategy gates remain INSUFFICIENT with zero forward trades; fill reconciliation is INCOMPLETE/no_forward_evidence. This is good evidence collection, not profitable-strategy certification. Calendar-day summaries total 853; this report consistently uses the 845 regular-session summaries.

The 20 failed readiness checks refer to local PostgreSQL and Redis, not Alpaca: 5 Redis-only, 6 database-only and 9 both. Lossy legacy classification cannot distinguish actual dependency latency, connection/pool setup, loop scheduling delays and exceptions from these records. All 77 sampled checks found the API running with Docker health and research policy intact; no recovery action or maintenance pause occurred. Current GET-only observation at 21:26 Pacific confirms the same September 23 container/start identity, zero restarts, no pending close accounting and no operator halt. Closed-market freshness is not proof of next-session freshness.

Forty-one truncated alert-log windows limit claims that every critical message was reviewed. No new critical alert is not complete absence-of-error proof when input was truncated. The nightly brain and PostgreSQL backups passed file/hash integrity checks; the database dump receipt does not attest a restore test. Historical ledger quality limitations remain separate from today's zero new trades.

Next repair scope: synchronize discovered/base/benchmark/held symbols with live subscriptions; preserve strict data admission while waiting for genuine bars and recovering failures; provide distinct candidate rejection reasons and measured processing segments; fix typed readiness outcomes and actual scheduler observation. Offline tests must exercise real provider lifecycle plus gated simulated orders and protective exits. Expanding subscriptions can increase global blocks under the existing any-stale-symbol policy; this consequence must be measured, not silently suppressed. Strategy/feed/risk tuning is excluded.

The active runtime configuration and frozen surface were verified unchanged. Raw private observations, immutable log captures and reproducible analysis are archived in the September 24 readiness evidence directory; metrics.json records source hashes. No orders, strategy settings or active measurement boundaries were changed by this review.

The subsequent offline performance investigation exposed a separate existing
feature-computation defect. Three composite formulas pass the scalar `100` to
`_safe_div`, which unconditionally calls `.abs()` on that numerator. The first
such call raises `AttributeError`; `compute_ml_features` catches it and replaces
all seven composite columns with zeros. Alpha and momentum paths consume these
columns. Existing division coverage uses only Series inputs, while broader
feature tests accept present, non-null columns, allowing the fallback to pass.
This establishes a code defect, not the number of September 24 missed trades or
the cause of the zero-order result. Correcting these decision inputs requires
explicit additional scope approval and counterfactual replay. The proposed ML
cache is not accepted while it could retain fallback results and suppress retry.
