import os,pathlib,subprocess,sys,tempfile
root=pathlib.Path('/Users/marselkei/.codex/worktrees/intra-session-pipeline-repair/intra')
assert not (root/'.env').exists(), 'Refuse worktree dotenv'
scratch=pathlib.Path(tempfile.mkdtemp(prefix='intra-scanner-tests-'))
env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','PYTHONPATH':str(root),'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','APP_ENVIRONMENT':'testing','ENVIRONMENT':'testing','TESTING':'true','USE_MOCK_BROKER':'true','USE_MOCK_DATA':'true','TRADING_EXECUTION_MODE':'shadow','DATABASE_URL':'sqlite+aiosqlite:///:memory:','SECURITY_JWT_SECRET':'test-jwt-secret-not-for-production','PICKLE_HMAC_SECRET':'test-pickle-secret-not-for-production','ORGANISM_BRAIN_DIR':str(scratch/'brain'),'ORGANISM_SHADOW_EXIT_TELEMETRY_PATH':str(scratch/'shadow.jsonl'),'ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_PATH':str(scratch/'filter.jsonl'),'ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_PATH':str(scratch/'strategy.jsonl')}
args=['/usr/bin/sandbox-exec','-p','(version 1) (allow default) (deny network*)','/Users/marselkei/VS/intra/venv/bin/python','-B','-m','pytest','-p','pytest_asyncio.plugin','-p','pytest_timeout','-p','no:cacheprovider','--timeout=30','--tb=short','-q',*sys.argv[1:]]
raise SystemExit(subprocess.run(args,cwd=root,env=env).returncode)
