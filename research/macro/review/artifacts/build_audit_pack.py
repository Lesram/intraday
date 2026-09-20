"""Generate review-scoped audit receipts without touching platform artifacts."""
from pathlib import Path
import datetime, hashlib, json, re, subprocess
R=Path(__file__).resolve().parents[1]; ROOT=R.parents[2]; A=R/'artifacts'
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def write(name,obj): (A/name).write_text(json.dumps(obj,indent=2)+'\n')
def load(rel): return json.loads((R/rel).read_text())
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
sha=git('rev-parse','HEAD'); base=git('rev-parse','origin/main'); branch='codex/macro-review-002'
validation=load('artifacts/delivery_validation.json')
files=sorted(set(git('ls-files','--cached','--others','--exclude-standard','--','research/macro/review/').splitlines()))
files=[x for x in files if (ROOT/x).is_file()]
risks=[
 'Revised macro snapshots and coarse publication lags are pseudo-out-of-sample, not vintage-real-time validation.',
 'Small, dependent event samples and researcher-defined sensitivity experiments do not establish investable skill.',
 'Same-model blind readers are not independent human experts; source retrieval remains incomplete.',
 '35 missing paid videos are all Jikh; 50 additional public catalog videos are absent.',
 'Historical reproduction requires the untouched local companion source package; long transcript extracts remain local only.',
 'Broader platform pytest collection failed because FastAPI is absent; no platform regression or replay pass is claimed.',
 'Existing freeze date 2026-09-19T21:55:01.857005+00:00 differs from the user contract July freeze; no freeze was reset.',
 'Dashboard rebuild requires the Data plugin compiler and Node; the included HTML opens standalone.',
 'No scheduled automation, external website publication or brokerage integration was installed.'
]
commands=[
 {'command':'python -m unittest discover -s research/macro/review/pipeline -p test_*.py -v','result':'35 passed','evidence':'artifacts/pipeline_final_tests.log'},
 {'command':'python scripts/phase2_freeze.py --verify','result':'pass before and after; bundled runtime plus review-local dependencies','evidence':'artifacts/freeze_after.log'},
 {'command':'python research/macro/review/artifacts/validate_delivery.py','result':validation['status'],'evidence':'artifacts/delivery_validation.json'},
 {'command':'pipeline/refresh.py --mode snapshot --as-of 2026-09-18','result':'validated; report and portable dashboard built','evidence':'artifacts/dashboard_build.log'},
 {'command':'pipeline/monitor.py --mode live --output artifacts/pipeline_review_live','result':'12 live sources validated, no fallback','evidence':'artifacts/pipeline_review_live/attempt.json'},
 {'command':'platform safety/regression pytest attempt','result':'collection unavailable: missing fastapi','evidence':'artifacts/platform_regression.log'},
 {'command':'research-local audit generator (this file)','result':'equivalent receipts inside authorized boundary; root generate_artifacts.py full and generate_audit_index.py deliberately not invoked','evidence':'task_plan.json'},
]
write('task_report.json',dict(task_id='macro-adversarial-review-002-2026-09-19',summary='Completed blind A/B, sealed evidence, all 12 adversarial attacks, 72 blind verdict rechecks, 60 prediction audits, 12-indicator specification and working dashboard/refresh/archive.',sha=sha,sha_role='Tested local platform workspace SHA, not self-referential output commit SHA',branch=branch,pr_base_sha=base,delivery_method='Add-only research commit based on origin/main, preserving the detached local checkout and pre-existing dirty files.',files_changed=files,commands=commands,tests_passed=35,tests_failed=0,test_collection_errors=1,runtime_behavior_changed=False,research_monitor_added=True,docs_updated=True,risks=risks,follow_ups=['Accumulate prospective acquired monthly readings before evaluating operational alarm usefulness.','Obtain missing historical publication vintages, consistent index earnings/weights and paid-content records before stronger conclusions.','Run platform CI in its normal provisioned environment if this research PR is promoted beyond draft.'],generated_at_utc=now))
write('changed_files.json',{'scope':'Only research/macro/review additions; existing unrelated dirty files excluded','sha':sha,'files':files,'categories':{'reports':[p for p in files if p.endswith('.md')],'code':[p for p in files if p.endswith(('.py','.js','.jsx','.css'))],'evidence_and_app':[p for p in files if not p.endswith(('.md','.py','.js','.jsx','.css'))]}})
write('test_summary.json',{'generated_at_utc':now,'research_unit_tests':{'passed':35,'failed':0,'log':'pipeline_final_tests.log'},'formula_parity':{'series':8,'status':'pass','receipt':'pipeline_formula_parity.json'},'prediction_audit':{'locked_checks_passed':8,'post_verification_checks_passed':6,'failed':0},'quantitative_checks':load('phase_c/quantitative_validation.json')['validation'],'event_checks':load('phase_b_events/validation_checks.json'),'delivery_integrity_checks':{'passed':sum(c['status']=='pass' for c in validation['checks']),'failed':sum(c['status']=='fail' for c in validation['checks'])},'browser':'desktop, mobile, filters, source inspection and standalone export verified','platform_suites':{'status':'unavailable','passed':None,'failed':None,'collection_errors':1,'reason':'FastAPI missing; no platform files changed'}})
write('replay_summary.json',{'status':'research_historical_checks_pass; platform_replay_unavailable','research_evidence':['phase_b/validation.json','phase_b_events/validation_checks.json','phase_c/quantitative_validation.json','artifacts/pipeline_formula_parity.json'],'platform_replay':{'status':'not_run_due_to_collection_dependency','passed':None,'failed':None,'log':'platform_regression.log'},'scope':'Historical macro study and monitor; not an organism/trading replay; no live trading behavior changed.'})
# Scan only owned executable research code; these names must not occur as executable calls/imports.
owned=list((R/'pipeline').glob('*.py'))
forbidden=re.compile(r'\b(?:submit_order|place_order|create_order)\s*\(|^\s*(?:from|import)\s+backend\.(?:brokers|organism|integrations)',re.M)
hits=[str(p.relative_to(R)) for p in owned if forbidden.search(p.read_text())]
write('grep_assertions.json',{'status':'pass' if not hits else 'fail','scope':'Research executable pipeline only; not a replacement for full platform grep assertions','assertions':{'all_changed_paths_inside_review':all(p.startswith('research/macro/review/') for p in files),'no_order_submission_or_trading_module_import':not hits,'frozen_surface_matches_baseline':'DRIFT-VERIFY OK' in (A/'freeze_after.log').read_text(),'all_344_original_source_files_unchanged':next(c['status']=='pass' for c in validation['checks'] if c['name']=='original_sources_unchanged')},'hits':hits})
index=f'''# Review 002 — audit index

This audit concerns research and monitoring only. All task output is under `research/macro/review/`; the original research and frozen trading platform were not edited.

- Tested workspace SHA: `{sha}`.
- Delivery branch: `{branch}`, add-only parent `{base}`. The delivery commit is separate from the detached, dirty tested checkout.
- Generated: {now}.
- Scope and process: [machine-readable plan](task_plan.json), [task report](artifacts/task_report.json), [changed files](artifacts/changed_files.json).

## Evidence and checks

| Check | Result | Receipt |
|---|---|---|
| Original sources | 344 / 344 hashes unchanged | [Source manifest](artifacts/source_manifest.json) |
| Blind A/B record | 75 / 75 sealed files unchanged | [Seal](artifacts/blind_seal.json) · [Log](LOG.md) |
| Blind second reader | 72 rows; five sealed files unchanged | [Lock](phase_c/second_reader_blind_seal.json) |
| Prediction audit | 60 locked rows; five later amendments separately recorded | [Lock](phase_c/prediction_lock_receipt.json) · [amendments](phase_c/prediction_post_lock_amendments.csv) |
| Monitor tests | 35 passed | [Test summary](artifacts/test_summary.json) · [log](artifacts/pipeline_final_tests.log) |
| Historical formula parity | Eight series match the sealed event study to numerical precision | [Parity](artifacts/pipeline_formula_parity.json) |
| Fresh network trial | All twelve source series validated | [Receipt](artifacts/pipeline_review_live/attempt.json) |
| Dashboard | Complete; desktop, phone, filters, source details and portable export checked | [Browser record](artifacts/browser_validation.json) |
| Frozen surface | Pass; no decision-surface drift | [Verification](artifacts/freeze_after.log) · [runtime snapshot](artifacts/runtime_config_snapshot.json) |
| Platform regression / trading replay | Unavailable: pytest collection requires missing FastAPI | [Log](artifacts/platform_regression.log) · [replay scope](artifacts/replay_summary.json) |
| Final local delivery integrity | {validation['status']} | [Validation](artifacts/delivery_validation.json) |
| Research order-path assertions | {'pass' if not hits else 'fail'} | [Assertions](artifacts/grep_assertions.json) |

## Runtime and publication boundaries

The runtime snapshot captures the actual frozen functions, configuration and allowlisted environment from this checkout. It is **not** a running broker-process snapshot. The pre-existing freeze records `2026-09-19T21:55:01.857005+00:00`, which differs from the July timestamp in the supplied contract. Verification succeeded against the existing baseline; this task neither reset nor reconciled that discrepancy.

The repository's generic artifact generators write outside the task's explicit boundary and invoke platform suites unavailable in this runtime. This review therefore supplies equivalent research-scoped receipts here. It does not claim that the platform's full CI/artifact generator ran successfully.

The full local evidence pack contains the original immutable derivations. Lengthy verbatim transcript extraction tables are excluded from the public PR; their hashes remain in the seal, and reproducing them requires the local companion source corpus. See [public packaging](PUBLIC_PACKAGE.md). No private paid content is included.

## Remaining limits

'''+''.join('- '+x+'\n' for x in risks)
(R/'LIVE_AUDIT_INDEX.md').write_text(index)
print(json.dumps({'files_catalogued':len(files),'unit_tests_passed':35,'delivery_validation':validation['status'],'audit_index':str(R/'LIVE_AUDIT_INDEX.md')},indent=2))
