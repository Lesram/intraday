# Final paper-entry freshness release — September 22, 2026

Marsel approved the final feature-bar freshness gate and full paper deployment,
including a new forward evaluation cutoff at deployment. This release also
includes the session-log, daily-evidence, watchdog and nightly repairs in PR #25.

Immediately before OrderService admission, every entry requires its same-tick,
same-symbol/direction passed-gate feature receipt, the approved 1Min timeframe,
complete timezone-aware strictly ordered timestamps, and an actual last-bar age
in the inclusive 0–120 second range. The provider timestamp means bar start; no
one-minute grace is added. Fresh callback/REST arrival cannot make an old bar
eligible. Invalid, future-at-capture and stale data produce fixed-reason skips,
without orders, pending-entry state or tick errors. Protective exits retain their
existing path. Actual admission time and age are stored in coroutine-local
receipts, including delayed quote lookup and overlapping submissions.

Strategy thresholds, models, feed, risk sizing, evolution/promotion locks and
historical records are unchanged. Missing or mismatched passed-gate feature
context blocks admission. Missing feed/source/image/configuration identity, or
a changed runtime identity, marks the receipt UNVERIFIED and blocks daily
evidence qualification; these identity fields are not an additional admission
veto. Other timeframes require separately reviewed eligibility; this release
certifies the existing 1Min paper configuration.

The committed freeze/reference is candidate-only evidence. Its timestamp is
never the installed measurement boundary. Deployment archives the old host
freeze, activation and private binding, obtains a fresh paper-broker flat/no-open-
orders proof, and explicitly stamps a new host cutoff under a maintenance hold.
The new binding pins exact active freeze/activation, source/image/configuration
and the original historical baseline. Historical learner counters are preserved.
Monday's blocked evidence is not reclassified or silently filtered into the new
cohort. These checks do not establish strategy profitability.

Validation at application commit `99ce963` includes 129 focused cases (49 new),
70 freeze/snapshot/configuration cases, the complete required safety/replay pack,
and independent review under artifacts/final_entry_freshness/. The old replay
fixture failure is retained with its repaired single-case result; its original
minimum-orders assertion remains. The final pack reruns that repair successfully.
The machine reports give exact counts, overlaps, commands and file hashes.

Final review also requires nonzero entries and actual throttle activity in the
low-limit replay, actual entries and accounted closes in the intraday replay,
and explicit no-entry expectations for unsupported daily replay. Snapshots
expose the required 1Min timeframe. The historical 2,802-line engine baseline is
preserved; the approved normal-skip handlers bring the function to 2,823 lines,
which is the explicit ceiling. Engine decomposition remains parked.

Release gates remain the final-head hosted operational check, checksum-verified
immutable image, fresh backup and isolated restore, actual startup/policy/model/
operator/accounting checks, canonical UTC startup logs, private binding and host
recovery/schedule verification. Installation is proven by the separate active
receipt, not by this candidate document or an offline runtime-default snapshot.
Natural entries, fills, exits and full-session coverage must still be observed.
