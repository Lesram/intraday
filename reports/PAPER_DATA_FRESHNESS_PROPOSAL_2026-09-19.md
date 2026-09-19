# Paper market-data freshness correction — undeployed proposal

The installed paper data client returned 500 AAPL bars ending **2026-09-16 16:34 UTC**, although a read-only descending query against the same IEX feed and split adjustment returned **2026-09-18 19:59 UTC**. The active streaming prefill and REST fallback both use this client. The sanitized installed-runtime observation is in `artifacts/data_freshness/actual_runtime_observation.json`; it is separate from isolated test runtime snapshots.

The old request selected the oldest first page of a five-day window, then retained its last 500 rows without following pagination. A date-only end also excluded the current intraday session. Historical prefill labeled those old bars fresh using arrival time. Existing streaming warmup and receipt-time gates still apply; this observation does not establish that a particular bad order occurred or predict a Monday order.

## Proposed correction

Both historical public methods share the same retrieval path: request descending bars through the current timezone-aware UTC time, follow page tokens until the requested unique count or the end of available history, and return the latest bars in chronological UTC order. The configured data feed, split adjustment and existing window-size policy remain unchanged. Requests are bounded to 100 pages and reject repeated/invalid tokens, ambiguous timestamps and timestamps after the request end. A provider error during pagination is an error, not a silently successful partial page.

Prefill validates every historical timestamp before publishing the buffer, orders and deduplicates the bars, and derives historical-only freshness from the newest bar event time. Stale history remains available for inspection but `get_bars` rejects it through the existing 120-second threshold. Concurrent streaming callbacks received while REST is awaited are preserved, including same-minute updates, and global freshness is the maximum across symbols. Existing streaming receipt-time freshness and the frozen alpha gate are unchanged. Future or ambiguous prefill timestamps do not replace existing state.

This is not a continuity guarantee: market closures, IEX no-trade minutes and outages may legitimately produce gaps. The current fixed history window can return fewer bars than requested if fewer are available. Existing streamed callback receipt semantics and handling of later out-of-order WebSocket events are outside this correction; this change does not retune gates or route trades.

## Evidence and acceptance

Deterministic network-free tests reproduce a window larger than the former page, exact latest-500 selection, current-session UTC bounds, multi-page overlap, token/error bounds, malformed/future timestamps, stale historical freshness, chronological ordering, global freshness and concurrent stream preservation. Existing behavioral assertions remain; obsolete ascending/date-only query assertions and stale naive fixtures were updated to the new contract.

Required organism/state/exit/sizing/replay, order/reconciliation and semantic suites, the full artifact pack, audit index and read-only freeze verification are recorded under `artifacts/data_freshness/` and the canonical artifact pack. Test executions deny all network access, deny writes to the live checkout, deny reads of its `.env` and brain, and use an isolated temporary database/brain. The test snapshots are not observations of the installed candidate.

The six hashed functions, feed, routing/config values and historical corpus are unchanged. A freeze-hash PASS does **not** certify equivalent inputs: correcting the data window can change indicators, candidates and future paper trades. This proposal must remain undeployed pending explicit approval of activation and prospective evaluation-cohort treatment. Preserve the existing July freeze and historical records; record an approved activation timestamp and separate forward cohort before evaluating corrected-input results. Coordinate that decision with the separate partial-fill accounting proposal without silently combining samples or resetting either clock.

After approval, acceptance still requires an actual read-only installed-candidate comparison against the provider, a fresh runtime/config snapshot and a controlled paper restart with verified flat/order-free state. A natural-session check must confirm latest-bar timestamps, prefill history and streaming freshness through market open. No profitability or strategy-edge conclusion follows from fixing data integrity.

Provider contract: [Alpaca historical bars, single symbol](https://docs.alpaca.markets/us/reference/stockbarsingle-1) documents descending order, RFC-3339 bounds and pagination tokens (checked 2026-09-19).
