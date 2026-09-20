"""Verify final research against preserved inputs; write only this final artifact directory."""
from pathlib import Path
from collections import Counter, defaultdict
import csv
import datetime as dt
import hashlib
import io
import json
import math
import re
import statistics
import subprocess
import sys
from urllib.parse import unquote

A = Path(__file__).resolve().parent
F = A.parent
R = F.parent
M = R.parent
ROOT = M.parents[1]
checks = []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def rows(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def check(name, ok, details):
    checks.append(dict(name=name, status='pass' if ok else 'fail', details=details))


before = load(A / 'source_integrity_before.json')
integrity = {}
for group, records in before.items():
    changed = [r['path'] for r in records if not (ROOT / r['path']).is_file() or sha(ROOT / r['path']) != r['sha256']]
    integrity[group] = dict(checked=len(records), changed=changed)
    check(group + '_unchanged', not changed, integrity[group])
(A / 'source_integrity_after.json').write_text(json.dumps(integrity, indent=2) + '\n')

seal = load(R / 'artifacts/blind_seal.json')['files']
check('75_file_blind_seal', all(sha(R / x['path']) == x['sha256'] for x in seal), {'files': len(seal)})
seal = load(R / 'phase_c/second_reader_blind_seal.json')['files']
check('five_file_second_reader_seal', all(sha(R / 'phase_c' / p) == h for p, h in seal.items()), {'files': len(seal)})
seal = load(R / 'consolidation/artifacts/consolidation_seal_final.json')
combined = {**seal['deliverables'], **seal['evidence']}
bad = []
for name, item in combined.items():
    p = R / 'consolidation' / name
    if not p.exists():
        p = R / 'consolidation/evidence' / name
    if not p.is_file() or sha(p) != item['sha256']:
        bad.append(name)
check('17_file_consolidation_seal', not bad, {'files': len(combined), 'mismatches': bad})
lock = load(R / 'phase_c/prediction_lock_receipt.json')
check('prediction_lock_and_design', sha(R / 'phase_c/prediction_independent_locked.csv') == lock['lock_sha256'] and sha(R / 'phase_c/prediction_preregistration.json') == lock['preregistration_sha256'], 'Locked judgments preserved; amendments remain separate.')
if (A / 'final_seal.json').exists():
    final_seal = load(A / 'final_seal.json')['files']
    check('final_authored_evidence_seal', all(sha(F / r['path']) == r['sha256'] for r in final_seal), {'files': len(final_seal)})

required = ['README.md', 'FINAL_RESEARCH.md', 'MONITORING_AND_DECISION_SPEC.md', 'PEER_REVIEW.md', 'INDICATOR_CONTRACT.csv', 'CHANGE_DISPOSITION.csv', 'RESOLUTION_LEDGER.csv', 'evidence/quantitative_completion.md', 'evidence/peer_quantitative.md', 'evidence/peer_indicators.md', 'evidence/peer_narrative.md', 'evidence/SOURCE_REGISTER.md', 'artifacts/AUDIT_INDEX.md']
check('required_documents', all((F / p).is_file() for p in required), {'missing': [p for p in required if not (F / p).is_file()]})

contract = rows(F / 'INDICATOR_CONTRACT.csv')
inventory = Counter(x['tier'] for x in contract)
check('canonical_inventory', inventory == {'review_flag': 2, 'watch': 5, 'context': 6, 'retired': 5, 'candidate': 2, 'engineering_control': 1}, dict(inventory))
cv = load(F / 'evidence/contract_validation.json')
check('contract_receipt_matches_bytes', sha(F / 'INDICATOR_CONTRACT.csv') == cv['final_contract_sha256'], {'joins': cv['empirical_join_checks'], 'join_failures': cv['empirical_join_failures']})
check('contract_empirical_joins', cv['empirical_join_checks'] == 24 and cv['empirical_join_failures'] == 0 and cv['financial_thresholds_and_empirical_fields_unchanged'], '24 mappings against sealed historical metrics; no thresholds optimized.')

metrics = rows(R / 'phase_b_events/indicator_event_metrics.csv')
bad = []
for r in metrics:
    n, hits, false = (int(r[x]) for x in ['n_alarm_episodes', 'episode_hits', 'episode_false_alarms'])
    if hits + false != n or (n and not math.isclose(float(r['episode_false_alarm_fraction']), false / n, abs_tol=1e-10)):
        bad.append((r['indicator'], r['event'], r['split']))
check('all_historical_alarm_denominators', len(metrics) == 162 and not bad, {'rows': len(metrics), 'failures': bad})

# Independent direct parsing of the raw CSV payloads; no factbase/monitor helper.
raw = {}
for name in ['fred_bundle_2026-09-19.json', 'fred_bundle2_2026-09-19.json']:
    raw.update(load(M / 'data/raw' / name)['series'])
def series(name):
    result = {}
    for row in csv.DictReader(io.StringIO(raw[name])):
        try:
            value = float(row[name])
        except (ValueError, TypeError):
            continue
        if math.isfinite(value):
            result[row['observation_date']] = value
    return result

computed = {}
for name, expected in [('CPIAUCSL', 3.3530163228), ('CPILFESL', 2.44616317865)]:
    s = series(name)
    value = 100 * (s['2026-08-01'] / s['2025-08-01'] - 1)
    computed[name] = value
    check('raw_calendar_' + name, math.isclose(value, expected, abs_tol=1e-8) and '2025-10-01' not in s, {'calendar_yoy': value, 'missing_october_preserved': True})
claims = sorted((dt.date.fromisoformat(k), v) for k, v in series('ICSA').items() if k <= '2026-09-18')
last55 = claims[-55:]
weekly = all((b[0] - a[0]).days == 7 for a, b in zip(last55, last55[1:]))
means = [statistics.mean(v for _, v in last55[i:i+4]) for i in range(52)]
rise = 100 * (means[-1] / min(means) - 1)
check('raw_claims_current_reading', weekly and means[-1] == 203250 and math.isclose(rise, 2.135678, abs_tol=1e-5), {'four_week_mean': means[-1], 'rise_pct': rise, 'last_date': str(last55[-1][0])})

pred = rows(R / 'phase_c/prediction_rescore.csv')
counts = Counter(r['final_label'] for r in pred)
check('prediction_final_counts', counts == {'HIT': 4, 'MISS': 3, 'PENDING': 11, 'CANNOT_VERIFY': 7, 'UNSCORABLE': 35}, dict(counts))

# Independently re-aggregate every asset/horizon/basis summary from the new row outputs.
summary_count = 0
bad = []
for prefix, extra in [('common_screen', []), ('rich_calm', ['window', 'sample'])]:
    groups = defaultdict(list)
    observations = defaultdict(dict)
    for r in rows(F / 'evidence' / (prefix + '_returns.csv')):
        origin_key = tuple([r['specification'], r['horizon_years']] + [r[x] for x in extra] + [r['month']])
        observations[origin_key][r['asset']] = r
        for basis in ['nominal', 'real']:
            key = tuple([r['specification'], r['horizon_years'], basis, r['asset']] + [r[x] for x in extra])
            groups[key].append(float(r[basis + '_cumulative_pct']))
    for origin_key, assets in observations.items():
        for asset, r in assets.items():
            if asset in ['MKT', 'CASH']:
                continue
            for basis in ['nominal', 'real']:
                key = tuple([r['specification'], r['horizon_years'], basis, asset + ' minus MKT'] + [r[x] for x in extra])
                groups[key].append(float(r[basis + '_cumulative_pct']) - float(assets['MKT'][basis + '_cumulative_pct']))
    for r in rows(F / 'evidence' / (prefix + '_summary.csv')):
        key = tuple([r['specification'], r['horizon_years'], r['return_basis'], r['asset']] + [r[x] for x in extra])
        values = groups[key]
        summary_count += 1
        if int(r['n']) != len(values) or not math.isclose(float(r['median']), statistics.median(values), abs_tol=1e-7) or not math.isclose(float(r['mean']), statistics.mean(values), abs_tol=1e-7) or not math.isclose(float(r['negative_pct']), 100 * sum(x < 0 for x in values) / len(values), abs_tol=1e-6):
            bad.append(key)
check('independent_return_summary_aggregation', not bad, {'asset_horizon_summaries': summary_count, 'failures': bad})
selected = rows(F / 'evidence/common_screen_selections.csv')
groups = defaultdict(list)
for r in selected:
    y, m = map(int, r['month'].split('-'))
    groups[r['specification']].append(y * 12 + m)
check('common_screen_episode_spacing', all(len(v) == 8 and all(b-a >= 60 for a, b in zip(sorted(v), sorted(v)[1:])) for v in groups.values()), {k: len(v) for k, v in groups.items()})
qv = load(F / 'evidence/quantitative_validation.json')
check('quantitative_reproduction_receipt', qv['status'] == 'PASS' and qv['common_eligible_months'] == 684 and qv['cape_rewritten_history_months'] == 38, qv)

if (F / 'CHANGE_DISPOSITION.csv').exists():
    changes = rows(F / 'CHANGE_DISPOSITION.csv')
    ids = [r['correction_id'] for r in changes]
    expected = set(re.findall(r'^### ((?:DELTA|WD|RV)-\d+)\b', (R / 'consolidation/IMPLEMENTATION_DELTA.md').read_text(), re.M))
    # Some DELTA definitions are table entries, so use the explicit bounded ID ranges.
    expected = {f'DELTA-{i:02d}' for i in range(1, 18)} | {f'WD-{i:02d}' for i in range(1, 18)} | {f'RV-{i:02d}' for i in range(1, 8)}
    check('all_41_change_dispositions', expected <= set(ids) and len(ids) == len(set(ids)), {'expected': 41, 'rows_including_new_corrections': len(ids), 'missing': sorted(expected-set(ids))})
if (F / 'RESOLUTION_LEDGER.csv').exists():
    old = rows(R / 'consolidation/RESOLUTION_LEDGER.csv')
    new = rows(F / 'RESOLUTION_LEDGER.csv')
    check('all_74_disputes_retained', {r['id'] for r in old} == {r['source_id'] for r in new} and len(new) == 74, {'rows': len(new)})

links = []
for p in F.rglob('*.md'):
    for target in re.findall(r'\]\(([^)]+)\)', p.read_text()):
        if target.startswith(('https:', 'http:', '#', 'mailto:')):
            continue
        target = unquote(target.split('#')[0].strip('<>'))
        if target and not (p.parent / target).exists():
            links.append({'file': str(p.relative_to(F)), 'target': target})
check('local_markdown_links', not links, {'missing': links, 'scope': 'Local workspace; companion packages are deliberately not all published.'})
syntax = []
for p in F.rglob('*.py'):
    try:
        compile(p.read_text(), str(p), 'exec')
    except SyntaxError as err:
        syntax.append(str(err))
check('new_research_script_syntax', not syntax, syntax)

result = dict(checked_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(), status='pass' if all(c['status'] == 'pass' for c in checks) else 'fail', checks=checks, note='Research integrity and arithmetic validation, not a financial-performance test or platform regression suite.')
(A / 'final_validation.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'status': result['status'], 'passed': sum(x['status']=='pass' for x in checks), 'failed': [{'name':x['name'],'details_preview':str(x['details'])[:900]} for x in checks if x['status']=='fail']}, indent=2))
sys.exit(0 if result['status'] == 'pass' else 1)
