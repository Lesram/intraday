# Monday CI and post-close readiness

The active repair preserves trading decisions and the freeze. It repairs CI evidence and prepares scheduled checks to use a reviewed source commit. It does not certify live account health, a profitable strategy, or the historical deep-test baseline.

## Source and integration

PR #11 (`02eaa450a2626bc3683a7cc0141f51d2c57e4d26`) supplies fail-closed artifact generation and reporting headroom. It was merged into `intra-2.0-phase1` as `b2785b66bf39192273a115f002c498f2f159bdcb`. The Monday changes build on that repair. They do not merge the 452-commit PR #9 into `main` or change the default branch.

Scheduled GitHub workflows run on the default branch. Updating only `intra-2.0-phase1` therefore does not repair the schedule. The recommended integration is a separate, small PR against `main` replacing only the two obsolete scheduled workflows with callers of the reviewed active workflows. Pin both the reusable workflow reference and its `source_sha` input to the same accepted 40-character commit. The tested code's SHA is recorded separately from the caller/default-branch SHA. See [GitHub's schedule rules](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) and [reusable workflow configuration](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations).

The active workflows expose `workflow_call` and `workflow_dispatch`; they do not schedule themselves. Each caller supplies a required immutable `source_sha`. Checkout uses that value, disables persisted credentials, verifies the actual commit, clears generated evidence left by old runs, and records provenance before installing dependencies. Full artifact generation and post-close checks use mock/shadow test settings and receive no production secrets. The hosted Phase 8 run is expressly not a live database extraction.

## Evidence and issue delivery

`scripts/ci/check_kpi_thresholds.py` now writes `artifacts/postclose_kpi_report.json` and `.md`, appends an Actions job summary, and exits nonzero for missing, malformed, stale, failed or incomplete evidence. It requires all six ordinary suites, nonzero replay and semantic test counts, invariant assertions, an explicitly disabled exploration field, successful snapshot and drift checks, a matching report SHA, and full-pack success. In hosted post-close runs, a successful Phase 8 report is also required. An upstream failure or skipped/timed-out pack cannot be hidden by old passing JSON files.

This checker validates software evidence. The old workflow's win-rate/payoff environment variables were never consumed by the checker and have been removed rather than represented as implemented trading KPIs. Live operational monitoring and broker reconciliation remain separate work.

A separately permissioned `report-status` job runs after success, failure, cancellation or a worker timeout. It records the worker result, expected/verified source, caller SHA and run URL, then uploads its own status artifact. It never checks out project code. The testing job has `contents: read`; only this reporting job requests `issues: write`.

Issue delivery requires the caller's explicit boolean `notify_issues: true`. The checker itself never invokes `gh` or sends anything. For the approved scheduled bridge, enable this input after validating the real run end to end; AGENTS.md requires automatic failure issues. Manual validation runs can use `false` without creating synthetic issues. Delivery uses the existing `bug` label, not the nonexistent `strategy`, `organism`, `nightly-failure` or `automated` labels. One open issue per workflow is reused, with repeated runs linked and retries deduplicated. A delivery error fails the reporting job and remains recorded in its status artifact. No automatic issue closure is performed.

A canceled workflow or GitHub runner/service outage can still prevent any job from executing. The independent status job covers worker failures/timeouts, not unavailable GitHub infrastructure. A local watchdog and an external alert destination remain necessary for paper-runtime supervision.

The nightly test selection remains the existing full `tests/` corpus excluding `slow`. It runs once, retaining logs, JUnit and coverage instead of rerunning the entire corpus to generate coverage. Legacy baseline failures remain visible; the parked Bandit, frontend audit and Quality Summary work is untouched. Coverage is retained as an artifact; this audit workflow no longer publishes to Pages or needs repository-content write access.

## Hosted environment and time budgets

All readiness/post-close/nightly jobs install the same `requirements.lock`, use test-only JWT/HMAC placeholders and direct all four organism state/telemetry paths into runner scratch space. Nightly uses `postgresql+asyncpg` for async application tests; the configured Alembic migration environment converts that URL to the synchronous driver. Migrations run against the existing `alembic.ini` path rather than a nonexistent legacy directory.

At source `dead82a4d3d110afe811ed91b59959e76bfd9ce6`, [operational safety passed](https://github.com/Lesram/intraday/actions/runs/35463347099) with scenarios at 74.37 seconds and replay at 283.47 seconds. The same source's [post-close run](https://github.com/Lesram/intraday/actions/runs/35463360197) hit the former 120/300-second suite ceilings. The post-close dependency artifact matched every repository lock pin; environment differences and runner variability remain hypotheses, not a proven dependency defect. Both failed runs and their artifacts remain visible.

Ordinary/semantic suite subprocess caps are 180 seconds. The replay outer process ceiling is 1200 seconds after the 600-second ceiling cut off 22 of 28 completed case markers in both final 0d1 hosted checks, without an individual assertion failure. The 120-second replay CLI default and its existing 180-second test markers remain unchanged, as do all other test deadlines. Replay now retains verbose case names and all durations so another incomplete run identifies its active case. Errors and timeouts still fail the pack and terminate the entire process group. A local offline CPU profile identified synchronous pandas/NumPy feature work; a Linux arm64 two-CPU comparison was 12.37s versus 11.95s with numerical pools capped to one thread, so no thread-cap fix is claimed or applied. The larger cumulative ceiling still requires direct hosted amd64 validation. The full-pack step has 50 minutes: suite/snapshot/drift ceilings total 42.5 minutes, plus invariant checks and report generation. Readiness and post-close jobs have 80 minutes; the separate PR organism job retains its existing explicit suites with 110 minutes overall. Budget contracts check every full-pack consumer and reserve artifact/reporting headroom. These changes do not alter trading code or certify the entire legacy nightly corpus.

## Minimal default-branch bridge

After the active repair has passed review and checks, substitute its accepted full SHA for `REVIEWED_SHA` below. This substitution is mandatory in both locations; do not use an unreviewed branch tip. The following is the complete replacement for `main`'s `.github/workflows/paper-postclose-audit.yml`:

```yaml
name: paper-postclose-audit
on:
  schedule:
    - cron: '15 22 * * 1-5'
  workflow_dispatch:
permissions:
  contents: read
  issues: write
jobs:
  reviewed-audit:
    uses: Lesram/intraday/.github/workflows/paper-postclose-audit.yml@REVIEWED_SHA
    with:
      source_sha: REVIEWED_SHA
      notify_issues: true
```

The complete replacement for `main`'s `.github/workflows/nightly.yml` is:

```yaml
name: Nightly Deep Tests
on:
  schedule:
    - cron: '0 2 * * *'
  workflow_dispatch:
permissions:
  contents: read
  issues: write
jobs:
  reviewed-audit:
    uses: Lesram/intraday/.github/workflows/nightly.yml@REVIEWED_SHA
    with:
      source_sha: REVIEWED_SHA
      notify_issues: true
```

Do not inherit secrets or add dispatch/contents write permissions. On each later accepted operational update, change both pin locations together through review. A default-branch change is unnecessary. Existing unrelated default-branch CI/deployment behavior is outside this bridge.

## Validation and activation checklist

1. Run the focused reporting/workflow tests. They execute the actual provenance script and notification JavaScript against local mocks, including cancellation, disabled delivery, missing evidence and issue API failure; they send no real notification.
2. Run the required safety/regression artifact pack and freeze verification, preserving the runtime snapshot separately from the test environment.
3. Open/review the active repair PR. Dispatch its actual post-close workflow with the accepted source SHA and `notify_issues: false`. Confirm the audited SHA, full pack, KPI report and independent status artifact. A workflow badge alone is insufficient.
4. Review/merge the small `main` bridge PR with the same pinned source SHA. Enable its `notify_issues: true` input under the existing automatic-KPI-issue requirement. Do not merge PR #9 to activate scheduling.
5. Verify the next real scheduled run's audited source and evidence. If a real failure occurs, verify its failure issue; do not manufacture an issue merely to test delivery.

Focused command:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --noconftest -o addopts= \
  -p pytest_timeout --timeout=30 -q \
  tests/test_generate_artifacts.py tests/test_artifact_workflow_contract.py \
  tests/test_artifact_change_scope.py tests/test_postclose_kpi_reporting.py \
  tests/test_monday_ci_workflows.py
```

Use the project Python environment. The workflow behavior tests also require Node; the focused GitHub workflow installs Node 22 explicitly.

## Historical secret alert

GitHub alert #1 was resolved on September 19 as `used_in_tests` after verifying its three historical fixture/JUnit locations and synthetic placeholder pattern. No provider request or credential-use attempt was made. Repository vulnerability alerts are now enabled; automatic dependency changes were not enabled. The sanitized disposition is recorded in `artifacts/monday_readiness/secret_alert_triage.json`.
