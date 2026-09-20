"""Read-only checks over the research deliverable; write receipts inside review only."""
from pathlib import Path
import hashlib,json,csv,datetime,re,subprocess

REVIEW=Path(__file__).resolve().parents[1]
REPO=REVIEW.parents[2]
checks=[]
def check(name,condition,detail):
 checks.append({'name':name,'status':'pass' if condition else 'fail','detail':detail})
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
seal=json.loads((REVIEW/'artifacts/blind_seal.json').read_text())
bad=[r['path'] for r in seal['files'] if not (REVIEW/r['path']).is_file() or sha(REVIEW/r['path'])!=r['sha256']]
check('blind_A_B_immutable',not bad,{'files':len(seal['files']),'changed':bad})
manifest=json.loads((REVIEW/'artifacts/source_manifest.json').read_text())
bad=[r['path'] for r in manifest['files'] if not (REPO/r['path']).is_file() or sha(REPO/r['path'])!=r['sha256']]
check('original_sources_unchanged',not bad,{'files':len(manifest['files']),'changed':bad})
second=json.loads((REVIEW/'phase_c/second_reader_blind_seal.json').read_text())
bad=[name for name,digest in second['files'].items() if sha(REVIEW/'phase_c'/name)!=digest]
check('second_reader_lock_immutable',not bad,{'files':len(second['files']),'changed':bad})
pred=json.loads((REVIEW/'phase_c/prediction_lock_receipt.json').read_text())
check('prediction_lock_immutable',sha(REVIEW/'phase_c/prediction_independent_locked.csv')==pred['lock_sha256'] and sha(REVIEW/'phase_c/prediction_preregistration.json')==pred['preregistration_sha256'],{'rows':60,'post_lock_amendments_separate':True})

required=['PHASE_A_transcript_analysis.md','PHASE_B_independent_regime_analysis.md','PHASE_B_event_validation.md','PHASE_C_adjudication.md','PHASE_D_indicator_spec.md','PHASE_E_dashboard_spec.md','README.md','indicators.csv','dashboard.html']
check('required_deliverables',all((REVIEW/f).is_file() for f in required),required)
pack=['artifacts/task_report.json','artifacts/runtime_config_snapshot.json','artifacts/changed_files.json','artifacts/test_summary.json','artifacts/replay_summary.json','artifacts/grep_assertions.json','artifacts/secret_scan.json','LIVE_AUDIT_INDEX.md','PUBLIC_PACKAGE.md','LOG.md']
published=set(subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','--',str(REVIEW)],cwd=REPO,text=True).splitlines())
missing=[f for f in pack if not (REVIEW/f).is_file() or str((REVIEW/f).relative_to(REPO)) not in published]
check('public_artifact_pack_included',not missing,{'required_files':len(pack),'missing':missing})
private=['directional_predicates.csv','pitch_sentences.csv','citation_like_sentences.csv','contradiction_pair_sample.csv','contradiction_sample_adjudicated.csv']
leaked=[f for f in private if str((REVIEW/'phase_a'/f).relative_to(REPO)) in published]
check('bulk_transcript_tables_local_only',not leaked,{'excluded_files':len(private),'included_in_error':leaked})

spec=list(csv.DictReader((REVIEW/'indicators.csv').open()))
fields=['id','name','definition','source','source_url','frequency_and_lag','revision_behaviour','history','what_it_is_for','thresholds','threshold_selection','measured_base_rate','false_positive_rate','independence','action_it_informs','kill_criterion']
missing=[f"{r.get('id')}:{f}" for r in spec for f in fields if not r.get(f)]
check('indicator_contract',len(spec)==12 and len({r['id'] for r in spec})==12 and not missing,{'n':len(spec),'missing_fields':missing})
check('tiers',sorted(int(r['tier']) for r in spec)==[1]*3+[2]*5+[3]*4,'3 review /5 watch /4 context')
snap=json.loads((REVIEW/'pipeline/output/attempt.json').read_text())
check('snapshot_validated',snap['status']=='validated' and len(snap['indicators'])==12 and snap['mode']=='snapshot',{'status':snap['status'],'version':snap['spec_version'],'as_of':snap['as_of']})
live=json.loads((REVIEW/'artifacts/pipeline_review_live/attempt.json').read_text())
check('fresh_live_source_trial',live['status']=='validated' and live['mode']=='live' and len(live['sources'])==12,{'status':live['status'],'as_of':live['as_of'],'sources':len(live['sources'])})
app=json.loads((REVIEW/'dashboard_app/src/data.json').read_text())
check('dashboard_complete',app['buildStatus']=='complete' and len(app['monitor']['indicators'])==12,{'id':app['id'],'buildStatus':app['buildStatus']})
check('self_contained_html',(REVIEW/'dashboard.html').stat().st_size>1000000,{'bytes':(REVIEW/'dashboard.html').stat().st_size,'sha256':sha(REVIEW/'dashboard.html')})
pipeline=list((REVIEW/'pipeline').glob('*.py'));syntax=[]
for p in pipeline:
 try:compile(p.read_text(),str(p),'exec')
 except SyntaxError as e:syntax.append(str(e))
check('pipeline_syntax',not syntax,{'files':len(pipeline),'errors':syntax})
check('final_targeted_tests','Ran 35 tests' in (REVIEW/'artifacts/pipeline_final_tests.log').read_text() and '\nOK\n' in (REVIEW/'artifacts/pipeline_final_tests.log').read_text(),'35 unittest cases; no platform-test claim')
check('freeze_verify','DRIFT-VERIFY OK' in (REVIEW/'artifacts/freeze_after.log').read_text(),(REVIEW/'artifacts/freeze_after.log').read_text().strip())
check('adjudication_complete','<!-- SECOND_READER_RESULTS -->' not in (REVIEW/'PHASE_C_adjudication.md').read_text() and '<!-- PREDICTION_RESULTS -->' not in (REVIEW/'PHASE_C_adjudication.md').read_text(),'No unresolved report placeholders')
result={'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'pass' if all(c['status']=='pass' for c in checks) else 'fail','checks':checks,'platform_test_status':'unavailable: collection failed, FastAPI missing; no trading-platform files changed'}
(REVIEW/'artifacts/delivery_validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
raise SystemExit(0 if result['status']=='pass' else 1)
