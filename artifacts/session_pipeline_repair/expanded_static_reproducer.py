import sys
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime, timezone

ROOT = Path('/Users/marselkei/.codex/worktrees/intra-session-pipeline-repair/intra')
OUT = ROOT / 'artifacts/session_pipeline_repair/expanded_static'
OUT.mkdir(parents=True, exist_ok=True)
BASE = 'f8bc52de1687f664278e8a8c032cb3aca4b39876'
HEAD = sys.argv[1]
assert re.fullmatch(r'[0-9a-f]{40}', HEAD)
PYTHON = '/Users/marselkei/VS/intra/venv/bin/python'
GITLEAKS = Path('/tmp/intra-gitleaks/gitleaks')
GITLEAKS_SHA = 'ba52fb1bfabbcde42f032afad3d6e0b19dff8ed105229a16e7caa338bbc0e84f'
SANDBOX = ['/usr/bin/sandbox-exec', '-p', '(version 1) (allow default) (deny network*)']
ENV = {key: os.environ[key] for key in ('PATH', 'HOME', 'USER', 'LANG') if key in os.environ}
for key in ('GITLEAKS_CONFIG', 'GITLEAKS_CONFIG_TOML'):
    ENV.pop(key, None)
ENV['PYTHONDONTWRITEBYTECODE'] = '1'

def run(args, *, source=None, cwd=ROOT):
    return subprocess.run(SANDBOX + args, cwd=cwd, env=ENV, input=source,
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def git(*args):
    result = subprocess.run(['git', *args], cwd=ROOT, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError('git operation failed: ' + args[0])
    return result.stdout

def sha_bytes(content):
    return hashlib.sha256(content).hexdigest()

def write(name, obj):
    path=OUT/name
    path.write_text(json.dumps(obj, indent=2, sort_keys=True)+'\n')
    return {'path':str(path.relative_to(ROOT)), 'sha256':sha_bytes(path.read_bytes())}

def context(text, start, end=None):
    return sha_bytes('\n'.join(line.strip() for line in text.splitlines()[start-1:(end or start)]).encode())

assert git('rev-parse', 'HEAD').strip() == HEAD
assert not git('diff', '--name-only', 'HEAD', '--', '*.py').strip()
assert GITLEAKS.is_file() and sha_bytes(GITLEAKS.read_bytes()) == GITLEAKS_SHA
files=git('diff', '--name-only', BASE, HEAD, '--', '*.py').splitlines()
base_paths=set(git('ls-tree', '-r', '--name-only', BASE).splitlines())
source={'base':{},'head':{}}
for path in files:
    source['head'][path]=git('show', HEAD+':'+path)
    if path in base_paths:
        source['base'][path]=git('show', BASE+':'+path)
    assert (ROOT/path).read_text()==source['head'][path]
config_names=['pyproject.toml','.bandit']
config={p:sha_bytes((ROOT/p).read_bytes()) for p in config_names}
assert not git('diff','--name-only',BASE,HEAD,'--',*config_names).strip()
ruff_version=run([PYTHON,'-m','ruff','--version']).stdout.strip()
assert ruff_version=='ruff 0.15.12'
ruff_runs={};ruff_normalized={}
for version,texts in source.items():
    results=[]; exits={}
    for path,text in texts.items():
        res=run([PYTHON,'-m','ruff','check','--no-fix','--output-format=json','--stdin-filename',path,'-'],source=text)
        assert res.returncode in (0,1), 'ruff execution error'
        exits[path]=res.returncode
        for issue in json.loads(res.stdout):
            results.append({'path':path,'code':issue['code'],'message':issue['message'],
                            'source_context_sha256':context(text,issue['location']['row'],issue['end_location']['row'])})
    ruff_normalized[version]=results
    ruff_runs[version]={'file_exit_codes':exits,'findings':results,'findings_count':len(results)}

def key(obj):return json.dumps(obj,sort_keys=True)
old=collections.Counter(map(key,ruff_normalized['base']));new=collections.Counter(map(key,ruff_normalized['head']))
added=[json.loads(k) for k,n in (new-old).items() for _ in range(n)]
removed=[json.loads(k) for k,n in (old-new).items() for _ in range(n)]
ruff_receipt=write('security_ruff_delta.json',{'version':ruff_version,'base':BASE,'head':HEAD,'normalization':'path + diagnostic code + message + SHA256 of stripped diagnostic source span; counters preserve duplicate multiplicity, line numbers ignored','runs':ruff_runs,'new_findings':added,'removed_findings':removed})

bandit_runs={};bandit_norm={}
with tempfile.TemporaryDirectory(prefix='intra-static-snapshots-') as tmp:
    private=Path(tmp);private.chmod(0o700)
    for version,texts in source.items():
        snapshot=private/version;snapshot.mkdir(mode=0o700)
        for path,text in texts.items():
            p=snapshot/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
        # The hosted high-severity lane uses Bandit's default rules, without
        # passing repository pyproject/.bandit config. Match that here.
        res=run([PYTHON,'-m','bandit','-lll','-f','json',*texts],cwd=snapshot)
        assert res.returncode in (0,1), 'bandit execution error'
        payload=json.loads(res.stdout)
        assert not payload.get('errors'), 'bandit file parsing errors'
        normalized=[]
        for issue in payload.get('results',[]):
            p=Path(issue['filename']);path=str(p.relative_to(snapshot)) if p.is_absolute() else str(p)
            path=path.removeprefix('./')
            normalized.append({'path':path,'code':issue['test_id'],'message':issue['issue_text'],
                               'severity':issue['issue_severity'],'confidence':issue['issue_confidence'],
                               'source_context_sha256':context(texts[path],issue['line_number'])})
        bandit_norm[version]=normalized
        bandit_runs[version]={'exit_code':res.returncode,'findings':normalized,'findings_count':len(normalized),'parse_errors':[],'metrics_totals':payload.get('metrics',{}).get('_totals',{})}
        (OUT/f'security_bandit_{version}.log').write_text(res.stderr)
    old=collections.Counter(map(key,bandit_norm['base']));new=collections.Counter(map(key,bandit_norm['head']))
    bandit_added=[json.loads(k) for k,n in (new-old).items() for _ in range(n)]
    bandit_removed=[json.loads(k) for k,n in (old-new).items() for _ in range(n)]
    bandit_version=run([PYTHON,'-m','bandit','--version']).stdout.strip()
    bandit_receipt=write('security_bandit_delta.json',{'version':bandit_version,'base':BASE,'head':HEAD,'scope':'changed Python files, high severity, default rules matching hosted CI, no application import','normalization':'path + rule + message + severity/confidence + SHA256 of stripped finding source line; line numbers ignored','runs':bandit_runs,'new_findings':bandit_added,'removed_findings':bandit_removed})
    raw_report=private/'gitleaks-redacted.json'
    args=[str(GITLEAKS),'git','--redact','--no-banner','--no-color','--log-opts='+BASE+'..'+HEAD,'--report-format=json','--report-path='+str(raw_report)]
    res=run(args)
    assert res.returncode in (0,1), 'gitleaks execution error'
    raw=json.loads(raw_report.read_text()) if raw_report.exists() else []
    # Reports contain metadata only, even with the tool's redaction enabled.
    safe=[{k:item.get(k) for k in ('RuleID','Description','File','StartLine','EndLine','Commit','Fingerprint')} for item in raw]
    gitleaks_receipt=write('security_gitleaks_redacted.json',safe)
    (OUT/'security_gitleaks_redacted.log').write_text(res.stdout+res.stderr)
    security={'base_sha':BASE,'head_sha':HEAD,'binary_sha256':GITLEAKS_SHA,'binary_checksum_verified':True,
              'version':run([str(GITLEAKS),'version']).stdout.strip(),'redaction_enabled':True,
              'output_policy':'finding metadata only; no Match/Secret fields retained',
              'command':[str(GITLEAKS),'git','--redact','--no-banner','--no-color','--log-opts='+BASE+'..'+HEAD,'--report-format=json','--report-path=<private-temporary-redacted-report>'],
              'exit_code':res.returncode,'findings_count':len(safe),'report':gitleaks_receipt,
              'log':{'path':str((OUT/'security_gitleaks_redacted.log').relative_to(ROOT)),'sha256':sha_bytes((OUT/'security_gitleaks_redacted.log').read_bytes())}}
    security_receipt=write('security_scan_receipt.json',security)
report={'task_id':'sept22_pipeline_final_static_security_delta','recorded_at_utc':datetime.now(timezone.utc).isoformat(),
        'status':'PASS_NO_NEW_FINDINGS' if not added and not bandit_added and not raw else 'REQUIRES_REVIEW',
        'base_sha':BASE,'head_sha':HEAD,'working_head_unchanged_at_completion':git('rev-parse','HEAD').strip()==HEAD,
        'changed_python_files':files,'head_python_sha256':{p:sha_bytes(t.encode()) for p,t in source['head'].items()},
        'unchanged_lint_configuration':config,'source_edits':False,'runtime_calls':False,'application_imports':False,'network_denied':True,
        'ruff':{'version':ruff_version,'baseline_findings':len(ruff_normalized['base']),'candidate_findings':len(ruff_normalized['head']),'new_findings':len(added),'removed_findings':len(removed),'receipt':ruff_receipt},
        'bandit_high':{'version':bandit_version,'baseline_findings':len(bandit_norm['base']),'candidate_findings':len(bandit_norm['head']),'new_findings':len(bandit_added),'removed_findings':len(bandit_removed),'receipt':bandit_receipt},
        'secrets':{'findings':len(safe),'receipt':security_receipt},
        'reproducer':{'path':__file__,'sha256':sha_bytes(Path(__file__).read_bytes())},
        'limitations':['This is a changed-Python/static delta review, not repository-wide lint cleanup or complete security assurance.','Gitleaks scans the exact committed revision range; root must rescan after final artifact-only commit.','Existing parked baseline findings remain unchanged unless naturally removed by this scoped work.']}
receipt=write('static_review.json',report)
print(json.dumps({'receipt':receipt,'status':report['status'],'ruff':report['ruff'],'bandit_high':report['bandit_high'],'secret_findings':len(safe)},indent=2))
