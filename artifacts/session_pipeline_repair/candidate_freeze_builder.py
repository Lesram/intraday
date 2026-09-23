import hashlib,json,os,subprocess,sys
from pathlib import Path

root=Path('/Users/marselkei/.codex/worktrees/intra-session-pipeline-repair/intra')
installed=Path('/Users/marselkei/VS/intra/artifacts/phase2/param_freeze.json')
assert Path.cwd()==root
sys.path.insert(0,str(root))
from scripts import phase2_freeze as f
for name in f.EXIT_ENV_VARS+f.ROUTING_DATA_ENV_VARS:
    os.environ.pop(name,None)
os.environ.update(json.loads((root/'artifacts/monday_readiness/freeze_environment.json').read_text()))
active_before=installed.read_bytes()
active=json.loads(active_before)
prior=json.loads(f.FREEZE_PATH.read_text())
candidate=f.build_freeze()
candidate.update({
    'candidate_only':True,
    'deployment_approved':False,
    'active_forward_cutoff':active['FROZEN_AT'],
    '_note_status':'Undeployed scanner/data pipeline candidate; timestamp is a validation boundary only. Explicit deployment/new forward-cutoff approval remains pending.',
    'activation_requirements':'Retain prior evidence; independently reviewed green PR; explicit approval of changed surface and new forward boundary; fresh closed/flat broker evidence; establish actual cutoff at held-flat activation. Do not copy candidate timestamp into active binding.',
})
changed_groups=sorted(k for k in set(active['surface'])|set(candidate['surface']) if active['surface'].get(k)!=candidate['surface'].get(k))
assert changed_groups==['data_pipeline_sources','source_hashes'],changed_groups
changed_original=sorted(k for k in active['surface']['source_hashes'] if active['surface']['source_hashes'][k]!=candidate['surface']['source_hashes'][k])
assert changed_original==['entry_gates_dispatch'],changed_original
body=json.dumps(candidate,indent=2,sort_keys=True)+'\n'
f.FREEZE_PATH.write_text(body)
(root/'artifacts/monday_readiness/frozen_surface_reference.json').write_text(body)
rc=f.verify()
assert rc==0
assert installed.read_bytes()==active_before
assert hashlib.sha256(active_before).hexdigest()=='cbff5d2c405031346426c7fa4cc496ffb21b8a6d9274fc7a329239ae9eb128cb'
receipt={
 'candidate_only':True,'deployment_approved':False,'candidate_code_sha':candidate['git_sha'],
 'candidate_validation_timestamp':candidate['FROZEN_AT'],'active_forward_cutoff_unchanged':active['FROZEN_AT'],
 'active_freeze_sha256_unchanged':hashlib.sha256(active_before).hexdigest(),
 'candidate_freeze_sha256':hashlib.sha256(body.encode()).hexdigest(),
 'candidate_verify_exit_code':rc,'changed_surface_groups':changed_groups,
 'changed_original_function_hashes':changed_original,
 'new_data_pipeline_sources':candidate['surface']['data_pipeline_sources'],
 'active_surface_diff':f._diff_surface(active['surface'],candidate['surface']),
 'previous_candidate_surface_diff':f._diff_surface(prior['surface'],candidate['surface']),
 'unchanged_groups':sorted(k for k in active['surface'] if active['surface'][k]==candidate['surface'].get(k)),
 'environment_profile':'artifacts/monday_readiness/freeze_environment.json',
}
(root/'artifacts/session_pipeline_repair/candidate_freeze_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
