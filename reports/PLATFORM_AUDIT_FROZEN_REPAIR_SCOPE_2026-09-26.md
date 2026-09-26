# Proposed frozen-surface repairs — 26 September 2026

Status: proposed, awaiting Marsel's explicit approval. No frozen implementation or new forward boundary has been applied.

The running paper process is healthy while the market is closed. That observation does not disprove the following failures, reproduced with synthetic inputs and denied network access against the deployed source tree.

| Defect | Reproduction / consequence | Proposed bounded repair and acceptance |
|---|---|---|
| Market-data subscriptions are assumed successful when a request is sent | Provider rejection or a partial acknowledgement leaves a new symbol locally subscribed. The next sync sends nothing; a fresh SPY stream prevents aggregate recovery while the missing symbol blocks admission. | Track desired, pending and server-confirmed subscriptions separately; bounded retries, explicit degraded status, no entry on unconfirmed data. Test rejection, partial acknowledgement, unsubscribe, reconnect and old-session acknowledgements. |
| Market-data lifecycle can stop recovering | A normal socket close leaves connected/authenticated flags true. Failed provider startup can return normally and leave the scheduler holding a stopped provider which cannot recover. | Make failed start/disconnect explicit and ensure bounded recovery through the existing streaming path. Test failed connect, failed subscribe, clean close and successful recovery without fallback data or relaxed safety gates. |
| SPY cross-asset features align row numbers instead of timestamps | Stock 80/SPY 120 bars ending at the same instant selects SPY 40 minutes earlier. Synthetic correlation changes from the timestamp oracle 0.869768 to −0.129156. Current learning-mode ML isolation limits immediate execution impact, but research inputs are wrong. | Align by aware timestamps using only current/past observations, preserve stock output order; test unequal lengths, gaps and causal prefixes. |
| End-of-day pending-order cancellation calls a missing method | The exact EOD source block calls AlpacaStreamClient.cancel_order, which does not exist; its exception is caught and the cancellation service receives no call. Existing legacy cancellation/expiry helpers can also discard local pending IDs without broker terminal proof. | Use supported cancellation with explicit broker terminal confirmation; retain unresolved entry attribution and EOD entry block/flatten. Do not substitute the unsafe legacy helper. Verify pending, already-terminal, failed and timed-out cancellations with replay/restart tests. |
| Freeze coverage omits the underlying streaming transport | The transport controls whether data admission is considered successful but is not directly hashed in the data-pipeline source inventory. | Include the transport in the frozen source inventory and runtime evidence; prove a transport edit invalidates verification. |

These are correctness repairs. This scope does not change the market-data feed, strategy parameters, thresholds, position sizing or trading mode. It does not authorize real-money trading, historical data deletion, or performance claims.

Approval authorizes implementation and paper validation of this scope, with tests, replay, runtime snapshot, independent review and PR gates. Activation must establish a new explicitly recorded forward-evidence boundary; existing history and the prior boundary remain preserved. A new boundary means fresh forward observations are needed before judging the repaired system's strategy performance.

Non-frozen accounting, display/authentication and nightly-verification repairs proceed separately under the current request.
