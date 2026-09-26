"""Research-scoped audit receipts; never invokes a root artifact writer or resets the freeze."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys

A = Path(__file__).resolve().parent
F = A.parent
R = F.parent
ROOT = R.parents[2]
sys.path.insert(0, str(ROOT))
from scripts.phase2_freeze import compute_surface

def write(name, data):
    (A/name).write_text(json.dumps(data, indent=2) + '\n')

def load(path):
    return json.loads(path.read_text())

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()

now = dt.datetime.now(dt.timezone.utc).isoformat()
workspace_sha = git('rev-parse', 'HEAD')
branch_parent = git('rev-parse', 'codex/macro-review-002')
freeze = subprocess.run([sys.executable, 'scripts/phase2_freeze.py', '--verify'], cwd=ROOT, capture_output=True, text=True)
(A/'freeze_after.log').write_text(freeze.stdout + freeze.stderr)
if freeze.returncode:
    raise SystemExit('Frozen surface verification failed; no final delivery.')
baseline = load(ROOT/'artifacts/phase2/param_freeze.json')
surface = compute_surface()
write('runtime_config_snapshot.json', {
    'generated_at_utc': now, 'workspace_sha': workspace_sha,
    'scope': 'Read-only imported frozen functions/configuration and allowlisted environment; not a running broker process snapshot.',
    'FROZEN_AT': baseline.get('FROZEN_AT'), 'matches_existing_freeze': True,
    'original_decision_surface_frozen_at': baseline.get('original_decision_surface_frozen_at'),
    'freeze_was_reset': False, 'surface': surface,
    'preexisting_contract_discrepancy': 'Existing September19 freeze differs from July7 timestamp in user contract; unchanged by this task.'
})

paths = sorted(p for p in F.rglob('*') if p.is_file() and not any(x in p.parts for x in ['__pycache__', '.pytest_cache']) and not p.name.startswith('delivery.gitindex') and p.name != 'pr_body.md')
files = [str(p.relative_to(ROOT)) for p in paths]
validation = load(A/'final_validation.json') if (A/'final_validation.json').exists() else {'status': 'pending', 'checks': []}
qv = load(F/'evidence/quantitative_validation.json')
cv = load(F/'evidence/contract_validation.json')
write('changed_files.json', {'scope': 'New final research package only; prior sources and platform untouched.', 'workspace_sha': workspace_sha, 'files': files})
write('test_summary.json', {
    'generated_at_utc': now,
    'final_research_validation': {'status': validation['status'], 'checks_passed': sum(x['status']=='pass' for x in validation['checks']), 'checks_failed': sum(x['status']=='fail' for x in validation['checks'])},
    'quantitative_reproduction': qv,
    'contract_validation': cv,
    'prior_prototype_unit_tests': {'passed': 35, 'failed': 0, 'rerun_for_this_finalization': False, 'reason': 'Prototype code is unchanged; prior test receipt is historical evidence, not a validation of future software.', 'receipt': '../../artifacts/pipeline_final_tests.log'},
    'platform_safety_regression_replay': {'status': 'not_run', 'reason': 'No platform changes; prior collection unavailable due to missing FastAPI. No new platform-pass claim.'},
    'freeze_verification': 'pass',
    'hosted_ci': 'See delivery_status.json when present; earlier checks blocked by existing workflow configuration.'
})
write('replay_summary.json', {'status': 'research_reproduction_pass', 'research': ['../evidence/quantitative_validation.json', '../evidence/contract_validation.json'], 'platform_replay': {'status': 'not_run', 'passed': None, 'failed': None}, 'scope': 'Historical macro comparisons, not a trading-system replay or demonstration of investment performance.'})
forbidden = re.compile(r'\b(?:submit_order|place_order|create_order)\s*\(|^\s*(?:from|import)\s+backend\.(?:brokers|organism|integrations)', re.M)
code = list(F.rglob('*.py'))
hits = [str(p.relative_to(F)) for p in code if forbidden.search(p.read_text())]
write('grep_assertions.json', {'status': 'pass' if not hits else 'fail', 'scope': 'New research scripts only; read-only frozen-surface import is intentional and not an execution path.', 'files': len(code), 'hits': hits, 'frozen_surface_matches': True, 'runtime_behavior_changed': False})
secret_patterns = [r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', r'\bgh[pousr]_[A-Za-z0-9]{30,}\b', r'\bAKIA[0-9A-Z]{16}\b', r'\bsk-(?:proj-)?[A-Za-z0-9_-]{35,}\b']
secret_hits = []
for p in paths:
    if p.name == 'build_final_audit.py':
        continue
    content = p.read_text(errors='replace')
    if any(re.search(pattern, content) for pattern in secret_patterns):
        secret_hits.append(str(p.relative_to(F)))
write('secret_scan.json', {'status': 'pass' if not secret_hits else 'fail', 'scope': 'Local recognizable credential-format scan of final files; not an exhaustive guarantee.', 'matches': secret_hits})
risks = [
    'No validated forecasting or investment-performance edge; revised histories and dependent small samples.',
    'AI cross-agent review is not independent human peer review; some reviewers authored component evidence.',
    'Original/paid corpus and vintage/portfolio records are incomplete; companion inputs are not all publicly packaged.',
    'Final contract supersedes prior prose but is not implemented in the existing prototype.',
    'Platform regression/replay and full root artifact generators were not run; no platform behavior changed.',
    'Hosted CI blockers are pre-existing and remain outside this research-only/frozen-surface task.'
]
write('task_report.json', {
    'task_id': 'MACRO_FINAL_004_2026-09-20',
    'summary': 'Finalize research with 41 consolidation dispositions, additional corrections, 74 reconciled disputes, controlled quantitative comparisons, canonical future contract and cross-agent peer review.',
    'sha': workspace_sha, 'sha_role': 'Read-only checked workspace SHA; delivery commit is recorded separately and cannot contain its own hash.',
    'branch': 'codex/macro-review-002', 'branch_parent_at_receipt_generation': branch_parent,
    'files_changed': files,
    'commands': [
        {'command': 'PYTHONDONTWRITEBYTECODE=1 python3 research/macro/review/final/evidence/quantitative_completion.py', 'result': qv['status']},
        {'command': 'PYTHONDONTWRITEBYTECODE=1 python3 research/macro/review/final/evidence/contract_finalize.py', 'result': '24 count joins and 5 calendar examples pass'},
        {'command': 'PYTHONDONTWRITEBYTECODE=1 python3 research/macro/review/final/artifacts/validate_final.py', 'result': validation['status']},
        {'command': 'PYTHONDONTWRITEBYTECODE=1 python3 scripts/phase2_freeze.py --verify', 'result': 'pass'},
        {'command': 'Research-scoped build_final_audit.py', 'result': 'Root artifact generators not invoked; explicit prior review-only boundary preserved.'}
    ],
    'tests_passed': sum(x['status']=='pass' for x in validation['checks']), 'tests_failed': sum(x['status']=='fail' for x in validation['checks']),
    'test_count_meaning': 'Final research validation groups, not unit-test cases or financial out-of-sample observations.',
    'runtime_behavior_changed': False, 'monitor_implementation_changed': False, 'docs_updated': True,
    'risks': risks,
    'follow_ups': ['User review before a monitoring-tool implementation decision.', 'Any future build must conform to the final contract and establish a separate acquired prospective record.'],
    'generated_at_utc': now
})
(A/'AUDIT_INDEX.md').write_text(f'''# Final research audit index

Generated {now}. Checked workspace: `{workspace_sha}`. Delivery branch: `codex/macro-review-002`; existing draft [PR #21](https://github.com/Lesram/intraday/pull/21). The branch is separate from the detached, dirty platform checkout; final delivery adds only this research directory through an isolated index.

| Check | Status and receipt |
|---|---|
| Final evidence, denominator and integrity checks | **{validation['status']}** — [final_validation.json](final_validation.json) |
| Controlled quantitative completion | **{qv['status']}** — [quantitative validation](../evidence/quantitative_validation.json) |
| Canonical contract | 21 rows, 42 fields; 24 exact count joins; five calendar-dependency examples — [contract validation](../evidence/contract_validation.json) |
| Cross-agent peer review | [Findings and closure](../PEER_REVIEW.md); AI analytical review, not external human certification |
| Original and consolidation files | [Pre-finalization hashes](source_integrity_before.json), [after-check](source_integrity_after.json); 1,200 research files and 14 pre-existing modified tracked files |
| Frozen decision surface | **pass** — [verification](freeze_after.log), [read-only runtime snapshot](runtime_config_snapshot.json) |
| New order paths / local credential patterns | [Research assertions](grep_assertions.json), [credential scan](secret_scan.json) |
| Prior prototype tests | Historical 35/35 pass; unchanged code, not rerun or presented as proof of future tool validity |
| Platform regression / replay | Not run; prior collection lacked FastAPI; no platform changes or new passing claim |
| Hosted checks | Existing blockers documented in [prior CI receipt](../../artifacts/ci_status.json); final-head status, when available, in [delivery status](delivery_status.json) |

## Scope and reproduction

[Task plan](task_plan.json), [task report](task_report.json), [changed files](changed_files.json), [test summary](test_summary.json) and [replay scope](replay_summary.json) form the research artifact pack. Exact research reproduction requirements are in [the quantitative supplement](../evidence/quantitative_completion.md). Local companion inputs remain necessary; no claim is made that all raw inputs are in the public PR.

The task writes inside `research/macro/review/final/`. Root `generate_artifacts.py full` and `generate_audit_index.py` would mutate outside the explicit review boundary and invoke platform suites; they were not run. These scoped receipts are not represented as the platform's full artifact pack. No runtime, dashboard, automatic schedule, order submission, protected parameter or source historical judgment was changed.

The existing freeze timestamp is `{baseline.get('FROZEN_AT')}`, which differs from July7 in the supplied operating instructions. Verification passes against the existing baseline. This finalization did not create, reset or reconcile that earlier discrepancy. The snapshot is imported configuration and source hashes, not observation of a running broker process.

## Remaining limits

''' + ''.join('- ' + risk + '\n' for risk in risks))
print(json.dumps({'freeze': 'pass', 'validation': validation['status'], 'new_research_files': len(files), 'credential_scan': 'pass' if not secret_hits else 'fail'}))
