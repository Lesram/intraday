# Artifact reporting contract

The artifact pack is a verification result. A successful generator invocation
must mean that its required checks actually succeeded; an empty or unavailable
result must never be interpreted as a passing test suite.

## Full mode

Run `python scripts/ci/generate_artifacts.py full` with the project Python
environment. It writes the existing task, runtime, changed-file, suite, replay,
invariant and specification artifacts before returning a failing exit status
for a failed required check.

Pytest results retain the process exit code, a diagnostic output tail, a full
output log and JUnit evidence. Success requires a successful process, readable
test evidence, at least one passing test and no failures or errors. Missing
suites, collection errors, zero-test/all-skipped runs, missing executables and
timeouts are failures. A failed process cannot be overruled by a clean-looking
test count. The replay aggregate continues to use `status: fail` so the existing
KPI checker recognizes it.

Each invocation replaces its own evidence. Old replay or semantic results must
not make a new quick invocation claim that those suites ran.

Subprocess wall-clock limits bound regular/semantic suites to 120 seconds,
replay to 300 seconds, snapshot generation to 60 seconds and the specification
check to 30 seconds. The existing per-test pytest timeouts also remain active.
These limits are operational budgets, not trading parameters. A timeout is a
failed check with retained diagnostics, not an exemption.

## Quick mode

Quick mode generates its documented lightweight evidence and explicitly records
that replay, semantic and specification checks were skipped. It must not reuse
their previous full-run results. A successful quick invocation does not certify
the full test suite or the authenticated running application.

## CI failure paths

The generator's nonzero exit remains visible as a failed step. Full-pack
consumers continue to generate the audit index and upload available artifacts
after failure. The postclose workflow also attempts its existing subsequent
evidence and KPI steps. The organism job attempts pack generation even when an
earlier explicit test step fails.

The full-pack steps have a 25-minute limit. Outer job limits leave additional
time for setup, preceding tests and diagnostic upload. They do not suppress or
convert a failed generator result into success.

The dedicated artifact-reporting PR workflow runs the focused generator,
workflow-contract and change-scope regression tests for relevant paths without
a target-branch filter. This provides a check for repairs based on the active
feature branch as well as main. It uses pinned test dependencies, temporary test
roots, no platform conftest and a read-only GitHub token; it uploads its JUnit and
console output after failures.

This behavior does not resolve the separate operational issues recorded in the
September 19 readiness audit: scheduled runs still follow the repository's
default branch; KPI notification coverage and issue-writing permissions require
their own repair; authenticated live status and alert delivery remain separate
from offline test evidence. The parked CI cleanup and frozen trading surface
are unchanged.

## Verification isolation

Local regression runs must use isolated test data and credentials. The paper
checkout and brain directory must not be writable by test processes. A separate
Git worktree isolates source files but does not by itself block broker access
or writes through absolute paths. The September repair verification also denies
network access and reads of the real environment/brain through an OS sandbox.
