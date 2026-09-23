import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
root=Path('/Users/marselkei/.codex/worktrees/intra-session-pipeline-repair/intra')
installed=Path('/Users/marselkei/VS/intra')
label=sys.argv[1]
assert label.replace('_','').isalnum()
sha=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
active=installed/'artifacts/phase2/param_freeze.json'
before={'sha256':sha(active),'mtime_ns':active.stat().st_mtime_ns}
assert before['sha256']=='cbff5d2c405031346426c7fa4cc496ffb21b8a6d9274fc7a329239ae9eb128cb'
candidate=root/'artifacts/phase2/param_freeze.json'
reference=root/'artifacts/monday_readiness/frozen_surface_reference.json'
assert sha(candidate)==sha(reference)=='d93ef5a9c24d4fdff65bac4cfeb072d5c2765fafdc80910070d37fe513aa873d'
profile=json.loads((root/'artifacts/monday_readiness/freeze_environment.json').read_text())
with tempfile.TemporaryDirectory(prefix='intra-freeze-verify-') as tmp:
 env={'PATH':'/Users/marselkei/VS/intra/venv/bin:/opt/homebrew/bin:/usr/bin:/bin','HOME':tmp,'PYTHONPATH':str(root),'PYTHONDONTWRITEBYTECODE':'1','APP_ENVIRONMENT':'testing','ENVIRONMENT':'testing','TESTING':'true','USE_MOCK_BROKER':'true','USE_MOCK_DATA':'true','TRADING_EXECUTION_MODE':'shadow','ORGANISM_BRAIN_DIR':tmp+'/brain','DATABASE_URL':'sqlite+aiosqlite:///:memory:',**profile}
 cmd=['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)(deny file-write* (subpath "/Users/marselkei/VS/intra"))(deny file-read* (literal "/Users/marselkei/VS/intra/.env") (subpath "/Users/marselkei/VS/intra/organism_brain") (subpath "/Users/marselkei/Library/Application Support/Intra"))','/Users/marselkei/VS/intra/venv/bin/python','-B','scripts/phase2_freeze.py','--verify']
 p=subprocess.run(cmd,cwd=root,env=env,text=True,capture_output=True,timeout=60)
 after={'sha256':sha(active),'mtime_ns':active.stat().st_mtime_ns}
 assert before==after and sha(candidate)==sha(reference)=='d93ef5a9c24d4fdff65bac4cfeb072d5c2765fafdc80910070d37fe513aa873d'
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
 result={'source_sha':head,'exit_code':p.returncode,'candidate_freeze_sha256':sha(candidate),'active_freeze_before':before,'active_freeze_after':after,'cutoff_changed':False,'runtime_deployed':False,'command':['python','scripts/phase2_freeze.py','--verify'],'scope':'candidate verify under nonsecret deployment profile; installed freeze read only; no runtime or broker API call'}
 out=root/'artifacts/session_pipeline_repair';(out/(label+'.log')).write_text(p.stdout+p.stderr);(out/(label+'.json')).write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result));print(p.stdout+p.stderr)
 raise SystemExit(p.returncode)
