# Audit Branch Hygiene Convention

**Date:** 2026-05-03
**Author:** V12 W84 (post-external-audit cleanup)
**Source:** V11 + V12 external auditor finding ("audit corpus committed in release branch").

## Decision

Going forward (V13+):

1. **Audit deliverables (synthesis docs, ledgers, plans, per-track reports) live on `audit-evidence/v<N>` branches**, not on the release branch.
2. **The release branch (`rc-1.5-curated` and eventually `main`) carries product code, tests, CI workflows, and the operationally-required scripts** (`scripts/ci/*.py`, `scripts/deploy/*.sh`).  Tests for those scripts also live on the release branch.
3. **`artifacts/audit/v12/v12_state.json` and `artifacts/audit/findings_ledger.json` live on BOTH branches** because CI scripts depend on them (audit_gate, ledger verifier).
4. **What gets retired from the release branch** at the V13 cutover: the V8-V11 synthesis prose docs, per-track V11 reports, and any prompt files.  These move to `audit-evidence/v12` and are removed from `rc-1.5-curated`.

## Why not retroactively rewrite history

The V11 + V12 auditors both flagged the audit corpus living in the release diff.  The non-destructive answer is to:

- Snapshot the current state to `audit-evidence/v12` (done — see `git branch audit-evidence/v12`).
- Stop committing NEW audit prose into the release branch starting V13.
- Selectively remove non-CI-dependent audit prose at the V13 cutover via normal commits (not history rewrites).

History rewrites are destructive on shared branches and break references to commits in commit bodies, GitHub issues, and external auditor reports.  The user's "do not break, but only resolve" constraint forbids that path.

## What's snapshotted on `audit-evidence/v12`

As of V12 W84, the branch carries everything in `artifacts/audit/` at HEAD.  It is the immutable record of V1-V12 audit work.

To inspect:

```bash
git log audit-evidence/v12 -- artifacts/audit/
git show audit-evidence/v12:artifacts/audit/MASTER_AUDIT_SYNTHESIS_v12.md
```

## V13 cutover plan

When V13 begins:

1. Create `audit-evidence/v13` from `rc-1.5-curated` HEAD.
2. On the release branch, `git rm` everything in `artifacts/audit/` EXCEPT:
   - `artifacts/audit/v12/v12_state.json` (CI dependency)
   - `artifacts/audit/findings_ledger.json` (CI dependency)
   - `artifacts/audit/findings_ledger_v12.md` (operator reference)
   - `artifacts/audit/v12/lint_baseline.json` (lint ratchet dependency)
   - The `V13_FRAMEWORK.md` document (forward-facing).
3. Update CI workflow paths if needed.
4. V13 wave commits add new artifacts to `audit-evidence/v13` only; the release branch sees only product/test/CI changes.

This shrinks the release diff against `main` from ~140+ audit files to whatever V13 actually changes in product surface area.

## Reasoning for keeping the 4 CI-dependent files on release branch

The audit gates fail if these files are missing.  Moving them off-branch would break:

- `scripts/ci/forbid_marker_only_critical_high.py` (reads `v12_state.json`)
- `scripts/ci/lint_ratchet.py` (reads `lint_baseline.json`)
- `scripts/ci/verify_findings_ledger.py` (reads `findings_ledger.json`)

A future V13+ wave could move these to a `config/audit/` directory if the audit/release split is so important that even the CI-dependency files must live separately.  Today the answer is: keep them where the CI scripts can find them.
