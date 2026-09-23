# September 22 session: pipeline, order recovery and validation repair

## Problem and resulting behavior

The September 22 session produced no orders. All 254 regular-session scanner
passes returned no candidates, and existing streaming-health gates blocked 427
of 1,526 cycles. These counts overlap with strategy filters and are not a count
of lost trades. The reviewed session remains an auditable no-trade session with
no new profitability or strategy-promotion evidence.

A subsequent read-only provider check established a scanner contract mismatch:
most-active rows carry volume but no price, while movers carry price but no
volume. Previously, absent fields became zero and were filtered before the
snapshot step could supply them. Tests fabricated the missing fields and did
not exercise the provider contract.

This candidate qualifies discovery rows only after obtaining valid required
snapshot values. It retains the existing thresholds, IEX/SIP selection, tension
formula, exclusions, ordering, request batching and candidate limit. Malformed,
nonfinite or incomplete values cannot pass by accident. Empty or failed scans
clear stale candidate results, including the caller's retained scanner pool;
they do not remove held positions or the current/base universe.

The streaming repair addresses reproducible bookkeeping/integrity defects:

- Duplicate/same-bar corrections and out-of-order callbacks do not extend bar
  health. Invalid, naive or future timestamps cannot fabricate a fresh stream.
- An advancing but already stale historical bar may support the historical
  buffer, but its recent arrival cannot claim fresh market data.
- Successfully unsubscribed symbols lose obsolete buffers/health and retired
  callbacks cannot resurrect them. Failed unsubscribe requests retain state
  and remain retryable. A new active subscription starts without inherited
  stale or falsely fresh state.
- Aggregate and per-symbol checks determine the final block state before a
  recovery message is emitted. The misleading same-cycle “fresh again” followed
  by a stale block is removed.

The global active-symbol streaming-health rule remains fail-closed at 120
seconds. REST fallback does not override it, and quotes are not substitutes for
bars. The session evidence does not establish why every sparse active symbol
lacked a recent callback; no feed entitlement, routing or strategy threshold is
changed on that assumption.

## Meaningful validation

Scanner tests use actual provider-shaped data and require real qualified
candidates. They cover unavailable/partial snapshots, malformed supplied fields,
thresholds, exclusions, ranking, request batching and success-to-empty/failure
transitions. Diagnostic scan summaries distinguish discovery, enrichment and
qualification losses.

Streaming tests exercise active stale symbols despite fresh aggregate/quotes,
ordered history, delayed delivery, timestamp failures, unsubscribe failures and
retries, retirement/re-subscription, truthful recovery and unchanged REST/global
entry-block behavior.

W100 replay now supplies timezone-aware one-minute frames aligned to its replay
clock. Causal prefixes of real computed features avoid repeatedly recomputing
the same unrelated ML features without exposing future rows. The tests require
actual admitted buys and accounted closes, including a protective loss and an
EOD flatten. Learning-mode partial exits are not fabricated by enabling an
unapproved production mode; existing partial-fill/accounting suites remain
separate required regression evidence.

The scanner-to-engine integration uses the real scanner and realistic provider
responses to demonstrate discovery, injection into the universe and a real
entry through the existing gates. It also checks empty/failing rescans clear
candidate state without deleting the held/base universe.

Both structural guards retain the historical baseline. The reviewed candidate
ceiling is exactly 2,824 lines: the former W100 2,805 plus the prior approved
18-line freshness handling plus one explicit scanner-exception cache clear.
The v12 2,802 baseline uses the equivalent 21+1 documented allowance. There is
no extra growth tolerance and engine decomposition remains parked.

New pipeline tests are included in the focused PR readiness job. Full applicable
nightly core and the seven required replay cases are also required; a green
focused subset alone is not acceptance. External tests needing a separately
provisioned disposable API/broker environment remain explicitly unavailable,
never represented as passing. Test counts from overlapping suites are not added.

## Build-context credential hygiene

The full candidate-image context check also found historical broker-secret
values embedded in an old audit report and an opaque bearer token embedded in
two development tools. These predate this repair and were outside the clean
change-only scan. The historical broker values differ from the current paper
container's configured secret; their past validity and revocation are not
established by that comparison.

The current audit report redacts those values while retaining its findings.
The development tools require a supplied token and fail before making requests
when it is absent. They no longer attempt a demo login or fall back to an
embedded credential. Focused tests verify credential precedence, request
headers, missing-input behavior and non-disclosure in error output. The PR
readiness job includes these tests.

This cleanup does not rotate active credentials or rewrite Git history. Prior
commits can still contain the historical values; their revocation requires
separate confirmation by the credential owner. Image preparation remains
blocked until the new context scan has no unresolved credential findings.
Known public examples, synthetic security fixtures, detector patterns and
non-authentication hashes are classified individually, with raw scan outcomes
retained rather than represented as an unconditional clean scan.

## Ambiguous broker acknowledgement

Review of the full nightly suite's two expected failures identified an active
order-path gap. An empty successful broker response became a generic error;
the outbox could retry submission without knowing whether the first request had
already created an order. This is a source-confirmed boundary defect, not an
observed September 22 incident: that session submitted no orders.

An invalid successful acknowledgement must trigger an exact lookup using the
original client order ID. If that cannot establish the order, the outbox must
persist an explicit unresolved state and retry lookup only. Once that state is
committed, a worker restart must retain lookup-only behavior. It must not invent
another identity, submit again, or report the
unknown order as accepted, filled or rejected. Retry exhaustion must identify
the need for reconciliation while preserving the local order state.

The repair uses existing outbox storage without a schema migration. Behavioral
tests cover successful recovery, failed or mismatched lookups, durable retry
state, malformed markers and exhaustion. The former source-text probes for
empty responses and null websocket quantities are replaced by executable
behavior checks. Ordinary valid acknowledgements retain their existing path.
The same review found and repaired a redundant local import that broke the
simulated broker path; direct simulation tests now exercise that path.
This does not claim an atomic transaction across the broker and local database:
a process failure before recording the acknowledgement remains a separate
delivery boundary, protected by the original persisted broker client order ID.

## Frozen surface and deployment boundary

This is an isolated candidate PR. No running paper source, environment, broker
orders, model artifacts, history, active freeze or private daily binding is
changed by implementation or tests.

Discovery and preliminary data admission affect which trades reach the final
gate, even when most original frozen functions are unchanged. The freeze now
also covers the scanner module, streaming provider module, live-engine data
module and staleness-admission method. Drift tests demonstrate that helper
changes fail verification without silently rewriting the clock. Snapshot files
expose those hashes as **candidate** source identities, not observed runtime
behavior.

The canonical freeze and readiness reference retain the installed approved
September 22 active artifact byte-for-byte. Candidate generation writes only
`artifacts/phase2/candidate_param_freeze.json`, with `candidate_only=true`,
`deployment_approved=false`, and `VALIDATED_AT`; it contains no `FROZEN_AT`.
Read-only candidate verification requires `--verify --candidate`. Ordinary
generation cannot overwrite the active artifact or strip candidate markers.
Gate, attribution, reconciliation, daily collection/analysis and host binding
readers reject candidate, unapproved or malformed cutoff documents before using
a forward corpus. Legacy active artifacts may omit flags; the separate
activation/binding evidence remains required. Deployment requires explicit approval of the
documented changed surface and new forward measurement boundary, passing
required checks, independent review, secret-scan disposition, a retained runtime
configuration snapshot and fresh closed/flat broker evidence. The actual cutoff
must be established at held-flat deployment, with the prior freeze/binding and
historical evidence retained. Candidate timestamps must not be reused as active
cutoffs, and current daily schedulers must not be repinned before activation.

The 120-second final feature-bar guard, fixed ATR sizing, frozen models/policy,
strategy thresholds, no-live-exploration rule, protective exits and EOD controls
remain unchanged. After deployment, natural paper entries, fills, reconciliation,
protective exits and active EOD flattening still require session evidence.
Passing simulations does not certify profitability or every natural execution
path; zero-trade sessions continue to be reported explicitly.

## Evidence

| Finding | Required evidence for this candidate |
| --- | --- |
| Real screener rows rejected before enrichment | Provider capture, scanner contract tests and scanner-to-engine entry test |
| Old candidates retained after empty/failing scans | Scanner and engine cache-transition tests |
| Duplicate/delayed/retired bars misrepresent health | Provider subscription/timestamp tests and active-symbol admission tests |
| Recovery logged before the final stale decision | Same-cycle recovery logging tests |
| Replay passes without meaningful execution or times out | Actual entries, protective/accounted closes and EOD flatten in W100 and safety replay |
| Helper changes escape freeze verification | Candidate helper hashes and deliberate drift tests; active cutoff untouched |
| Embedded historical credentials enter the image context | Current-file redaction, explicit-token tests and classified full-context scan |
| Ambiguous broker acknowledgement can reach ordinary submission retry | Exact-ID recovery, durable lookup-only retry, persistence-failure and exhaustion tests |
| Natural paper execution and strategy expectancy remain unproven | Subsequent approved paper-session evidence; simulation and after-hours discovery are insufficient |

`artifacts/session_pipeline_repair/plan.json` declares the scope and safety
constraints. Targeted red/green evidence, combined acceptance, candidate surface
diff and independent reviews are stored alongside it. The standard full artifact
pack and `docs/engineering/LIVE_AUDIT_INDEX.md` are regenerated for this PR;
hosted workflow artifacts establish results on the submitted immutable source.

## Review follow-up acceptance

Provider stop/start resets session buffers, symbols, quotes and freshness.
Callbacks are bound to their transport generation, so retired callbacks cannot
repopulate the new session. Serialized transport changes handle queued starts,
stops and cancellations; same-session recovery preserves stale health until
new valid bars arrive. Failed disconnect state remains available for retry.

Scanner outcomes distinguish a genuine successful empty result from transport
or response failures. Only a complete successful scan updates the success time
and clears the failure streak. Individually qualified partial candidates retain
their existing admission rules; degraded scans still count as failures.

The audit index includes every changed path, including evidence, reports and
configuration, and displays the complete inventory beyond category previews.
Earlier candidate commits, image and checks remain historical evidence and are
superseded by the source-bound follow-up acceptance pack.
