import json,os,subprocess,sys,tempfile,time
from pathlib import Path
root=Path('/Users/marselkei/.codex/worktrees/intra-paper-data-freshness/intra')
out=root/'artifacts/data_freshness'; out.mkdir(exist_ok=True,parents=True)
label=sys.argv[1]
args=['scripts/ci/generate_artifacts.py','full'] if label=='full' else ['-m','pytest','-q','-p','no:cacheprovider','--timeout=30','--tb=short','--junitxml='+str(out/(label+'.xml')),*sys.argv[2:]]
with tempfile.TemporaryDirectory(prefix='intra-monday-test-') as temp:
 env=dict(os.environ)
 for k in list(env):
  if k.startswith(('ALPACA_','ORGANISM_','INTRA_API_','GH_TOKEN','GITHUB_TOKEN')): env.pop(k,None)
 env.update({'PYTHONPATH':str(root),'PYTHONDONTWRITEBYTECODE':'1','PYTHONUNBUFFERED':'1','USE_MOCK_BROKER':'true','USE_MOCK_DATA':'true','APP_ENVIRONMENT':'testing','ENVIRONMENT':'testing','DATABASE_URL':'sqlite+aiosqlite:///'+temp+'/test.db','ORGANISM_BRAIN_DIR':temp+'/brain','ORGANISM_SHADOW_EXIT_TELEMETRY_PATH':temp+'/shadow.jsonl','ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_PATH':temp+'/filter.jsonl','ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_PATH':temp+'/strategy.jsonl','SECURITY_JWT_SECRET':'test-jwt-secret-not-for-production','PICKLE_HMAC_SECRET':'test-pickle-secret-not-for-production','INTRA_TASK_ID':'paper-data-freshness-2026-09-19','INTRA_TASK_SUMMARY':'Undeployed latest market-data and historical prefill correction proposal','INTRA_DIFF_BASE':'d7c3c6c047d97a4f925c7b66c7f121e3ee10cd4d'})
 command=['/usr/bin/sandbox-exec','-f','/private/var/folders/52/1b3lnm3n5252r2cynmqgzhlc0000gn/T/intra-readiness-20260919-v0s9vanl/readiness_results/sandbox.sb','/Users/marselkei/VS/intra/venv/bin/python','-B',*args]
 start=time.monotonic()
 with (out/(label+'.log')).open('w') as log:
  r=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1500)
 result={'label':label,'exit_code':r.returncode,'seconds':round(time.monotonic()-start,2),'command':command,'network_denied':True,'real_checkout_writes_denied':True,'real_env_and_brain_reads_denied':True}
 (out/(label+'.json')).write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result)); print((out/(label+'.log')).read_text(errors='replace')[-6500:])
 raise SystemExit(r.returncode)
