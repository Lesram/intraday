import json,os,subprocess,sys,tempfile,time
from pathlib import Path
root=Path('/Users/marselkei/.codex/worktrees/intra-streaming-readiness-repair/intra')
out=root/'artifacts/composite_indicator_repair';out.mkdir(exist_ok=True,parents=True)
label=sys.argv[1]
assert label.replace('_','').replace('-','').isalnum()
args=['scripts/ci/generate_artifacts.py','full'] if label.startswith('full') else (['scripts/ci/generate_audit_index.py'] if label.startswith('index') else ['-m','pytest','-q','--timeout=30','--tb=short','--durations=10','--junitxml='+str(out/(label+'.xml')),*sys.argv[2:]])
python='/Users/marselkei/VS/intra/venv/bin/python'
profile='(version 1)(allow default)(deny network*)(deny file-write* (subpath "/Users/marselkei/VS/intra"))(deny file-read* (literal "/Users/marselkei/VS/intra/.env") (subpath "/Users/marselkei/VS/intra/organism_brain") (subpath "/Users/marselkei/Library/Application Support/Intra"))'
with tempfile.TemporaryDirectory(prefix='intra-pipeline-tests-') as temp:
 env={'HOME':str(Path.home()),'USER':os.environ.get('USER','marselkei'),'LOGNAME':os.environ.get('LOGNAME','marselkei'),'LANG':'en_US.UTF-8','PATH':'/Users/marselkei/VS/intra/venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin','PYTHONPATH':str(root),'PYTHONDONTWRITEBYTECODE':'1','PYTHONUNBUFFERED':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTEST_ADDOPTS':'-p pytest_asyncio.plugin -p pytest_timeout -p no:cacheprovider','USE_MOCK_BROKER':'true','USE_MOCK_DATA':'true','TESTING':'true','APP_ENVIRONMENT':'testing','ENVIRONMENT':'testing','TRADING_EXECUTION_MODE':'shadow','DATABASE_URL':'sqlite+aiosqlite:///'+temp+'/test.db','REDIS_URL':'redis://127.0.0.1:1/0','DOCKER_HOST':'unix://'+temp+'/unavailable.sock','ORGANISM_BRAIN_DIR':temp+'/brain','ORGANISM_SHADOW_EXIT_TELEMETRY_PATH':temp+'/shadow.jsonl','ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_PATH':temp+'/filter.jsonl','ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_PATH':temp+'/strategy.jsonl','SECURITY_JWT_SECRET':'test-jwt-secret-not-for-production','PICKLE_HMAC_SECRET':'test-pickle-secret-not-for-production','INTRA_TASK_ID':'composite-indicator-repair-20260925','INTRA_TASK_SUMMARY':'Approved scalar composite correction and paired replay; active deployment unchanged','INTRA_DIFF_BASE':'a69949a216fdcb6a7f210933f885b3cabafd1ae0'}
 command=['/usr/bin/sandbox-exec','-p',profile,python,'-B',*args]
 started=time.monotonic()
 logpath=out/(label+'.log')
 with logpath.open('x') as log:
  p=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=2400)
 result={'label':label,'exit_code':p.returncode,'seconds':round(time.monotonic()-started,2),'command':args,'network_denied':True,'production_writes_denied':True,'installed_credentials_and_brain_reads_denied':True,'candidate_only':True}
 with (out/(label+'.json')).open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps(result));print(logpath.read_text(errors='replace')[-7000:])
 raise SystemExit(p.returncode)
