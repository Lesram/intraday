"""Finish post-seal audit receipts, checks, and readable reports; review writes only."""
from pathlib import Path
import hashlib,json,re,sys
import numpy as np
import pandas as pd
O=Path(__file__).resolve().parent;R=O.parents[1]
sys.path.insert(0,str(R/'scripts'))
import factbase as f

# The semantic reading was performed in full; receipt also distinguishes machine
# inspection of every CSV from reading prose and code.
receipt=[]
for p in sorted((R/'analogs').iterdir()):
    if not p.is_file():continue
    d=dict(path=str(p.relative_to(R)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
    if p.suffix=='.csv':
        x=pd.read_csv(p);d.update(mode='Full machine load, schema/coverage inspection, and numerical use or reconciliation',rows=len(x),columns=list(x.columns),null_cells=int(x.isna().sum().sum()))
    else:d.update(mode='Full semantic source-code/prose/output reading after blind seal',lines=len(p.read_text().splitlines()))
    receipt.append(d)
for pack in ['V2','V7']:
    for name in ['facts.md','SUMMARY.md','verdicts.csv']:
        p=R/'verify/out'/pack/name
        d=dict(path=str(p.relative_to(R)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size,read_after_blind_seal=True)
        if name.endswith('.csv'):
            x=pd.read_csv(p);d.update(mode='Full machine load, schema and fact-key coverage check; prose read separately',rows=len(x),columns=list(x.columns),unique_fact_keys=x.fact_key.nunique())
        else:d.update(mode='Full semantic reading',lines=len(p.read_text().splitlines()))
        receipt.append(d)
(O/'quantitative_input_reading_receipts.json').write_text(json.dumps(receipt,indent=2))

v=json.loads((O/'quantitative_validation.json').read_text())
checks={
 'original_scores_reproduce_within_csv_rounding':v['screen']['prior_score_max_abs_difference']<0.000051,
 'cape_source_function_reproduces_cached_values':v['cape']['model_vs_cached_max_error']<1e-10,
 'original_set_is_twelve_screen_plus_one_manual':v['overlap']['screen_n_automatically_selected']==12 and v['overlap']['original_n_episodes']==13,
 'all_fifteen_original_analog_files_in_reading_receipt':sum(d['path'].startswith('analogs/') for d in receipt)==15,
}
sample=pd.read_csv(O/'quantitative_original_sample_sensitivity.csv')
gold=sample.query("sample=='complete_horizons_only' and asset=='GOLD' and horizon==5").iloc[0]
checks['mature_gold_nine_and_median_25_17']=gold['n']==9 and abs(gold['median']-25.173)<.002
for name in ['screen_returns','tightening_all_episodes','profit_mean_reversion','industry_concentration_history','cape_base_rate_freshness','energy_tilt_sensitivity']:
    x=pd.read_csv(O/f'quantitative_{name}.csv');checks[f'{name}_nonempty']=len(x)>0
checks={k:bool(value) for k,value in checks.items()}
v['validation']={'status':'PASS with methodological limitations','checks':checks,'all_checks_pass':bool(all(checks.values()))}
v['risks']=[
 'All macro histories are revised captures. Expanding ranks and frozen coefficients are pseudo-out-of-sample, not real-time vintage validation.',
 'Historical 1/3/5-year rows overlap unless explicitly spaced; spaced starts need not be economically independent.',
 'French total market and industries differ from S&P 500/GICS. Hybrid CAPE return extension is explicitly a universe substitution.',
 'Gold is spot-price return; Treasury return is the original yield-based model, without an observed total-return index validation.',
 'CAPE after June 2023 uses a NIPA aggregate-profit EPS proxy; buyback/forward-EPS alternatives cannot be reconstructed from supplied inputs.',
 'Sensitivity choices are disclosed diagnostics rather than independent prospective tests. No operational portfolio recommendation is validated.'
]
v['input_receipt_file']='quantitative_input_reading_receipts.json'
(O/'quantitative_validation.json').write_text(json.dumps(v,indent=2))
assert all(checks.values()),checks

p=O/'quantitative_adjudication.md';s=p.read_text().split('\n## Source-code anchors and evidentiary limits')[0]
s=s.replace('2026-09-20 T 04:51:13 Z','2026-09-20T04:51:13Z')
for a,b in {'November2021':'November 2021','June2023':'June 2023','Original7/7':'Original 7/7','the2000':'the 2000','old6%':'old 6%','after2000':'after 2000','A100-year':'A 100-year','Gold45pp':'Gold 45 pp','CAPE41.3 versus42.0':'CAPE 41.3 versus 42.0','to+25.2%':'to +25.2%','and+36.0%':'and +36.0%'}.items():s=s.replace(a,b)
s+='''
## Source-code anchors and evidentiary limits

All dated forward comparisons here use the supplied revised history. Expanding percentiles remove future observations from the ranking window; they **do not restore the original data vintage, original release calendar, historical accounting definitions, or an untouched test set**. The frozen profit-share model is a chronological pseudo-out-of-sample test. Its error comparison is evidence about this dataset, not a simulated implementable vintage strategy. The independent Phase B report uses approximate availability lags but is likewise not an ALFRED vintage reconstruction.

| Issue | Original source anchor | Executed review evidence |
|---|---|---|
| Mixed target timestamp | [regime_screen.py:44](/Users/marselkei/VS/intra/research/macro/analogs/regime_screen.py:44) | quantitative_cape_inputs.csv; quantitative_screen_selections.csv |
| Full-history ranks and candidate scoring | [regime_screen.py:171](/Users/marselkei/VS/intra/research/macro/analogs/regime_screen.py:171) | quantitative_screen_selections.csv; quantitative_alternative_expanding_normalization.csv |
| Manual 2000 anchor | [report_tables.py:23](/Users/marselkei/VS/intra/research/macro/analogs/report_tables.py:23) | quantitative_original_episode_maturity.csv |
| Aggregation omits the maturity filter | [report_tables.py:78](/Users/marselkei/VS/intra/research/macro/analogs/report_tables.py:78) | quantitative_original_sample_sensitivity.csv; quantitative_overlap_pairs.csv |
| Incomplete horizons are returned | [analog_scripts.py:110](/Users/marselkei/VS/intra/research/macro/analogs/analog_scripts.py:110) | quantitative_original_episode_maturity.csv |
| CAPE aggregate-profit splice | [regime_model.py:47](/Users/marselkei/VS/intra/research/macro/scripts/regime_model.py:47) | quantitative_cape_sensitivity.csv; quantitative_validation.json |
| Missing promised return extension | [step5_credit.py:28](/Users/marselkei/VS/intra/research/macro/analogs/step5_credit.py:28) | quantitative_cape_base_rate_freshness.csv; quantitative_cape_base_rate_starts.csv |
| Repeated tightening levels rather than first crossings | [analog_scripts.py:218](/Users/marselkei/VS/intra/research/macro/analogs/analog_scripts.py:218) | quantitative_tightening_all_episodes.csv; quantitative_tightening_sensitivity.csv |
| Separate energy/market medians | [step5_credit.py:184](/Users/marselkei/VS/intra/research/macro/analogs/step5_credit.py:184) | quantitative_energy_tilt_sensitivity.csv |
| Energy-edge inference | [regime_model.py:129](/Users/marselkei/VS/intra/research/macro/scripts/regime_model.py:129) | quantitative_energy_tilt_sensitivity.csv |
| Stale context series and hardcoded reading | [regime_model.py:144](/Users/marselkei/VS/intra/research/macro/scripts/regime_model.py:144) | Source inspection; separate TIPS and backward-inflation definitions required |
| Implemented stress criteria | [regime_model.py:164](/Users/marselkei/VS/intra/research/macro/scripts/regime_model.py:164) | Source inspection; Phase B event metrics provide individual-trigger diagnostics |
| Reversed lead/lag kill criterion | [regime_model.py:189](/Users/marselkei/VS/intra/research/macro/scripts/regime_model.py:189) | Source inspection |

The complete source-reading receipt covers all 15 original analog files (7 CSVs, 4 Python files, 3 text outputs and ANALOGS.md), plus V2 and V7. CSVs were loaded in full and inspected numerically; receipt language does not imply that every cell of a large CSV was visually read. V2's 124 rows map to 89 fact keys. V7 has 150 rows/141 fact keys but 142 fact headings because the unassigned debt-to-GDP section has no claim ID. The separate V7 adjudication records semantic findings from all 1,142 facts-log lines and all 163 SUMMARY lines.

To settle the remaining issues: retain a true index-EPS/share-count history; obtain the original vintages and release timestamps; use completed, prospectively specified events; validate bonds against an observed total-return index; acquire firm-level capitalization histories for top-ten concentration; and register one complete decision rule before its next independent cycle. Additional correlated thresholds or repeating monthly observations would not supply the missing independent evidence.
'''
p.write_text(s);(O/'quantitative_review.md').write_text(s)
lead=[]
for line in s.split('## 1.')[0].splitlines():
    if line.startswith('| ') and not line.startswith('| Finding'):
        cells=[z.strip() for z in line.strip('|').split('|')]
        if len(cells)==3:lead.append(cells)
pd.DataFrame(lead,columns=['finding','verdict','reason']).to_csv(O/'quantitative_adjudication_table.csv',index=False)

rows=[]
for name in ['CPIAUCSL','CPILFESL','PCEPILFE']:
    x=f.fred(name);m=x.reindex(pd.date_range(x.index.min(),x.index.max(),freq='MS'))
    old=x.pct_change(12)*100;correct=m.pct_change(12,fill_method=None)*100
    for t in correct.loc['2026'].index:rows.append(dict(series=name,month=str(t.date()),row_based_yoy=old.get(t,np.nan),calendar_yoy=correct[t]))
pd.DataFrame(rows).to_csv(O/'quantitative_v7_calendar_growth_check.csv',index=False)
print(json.dumps({'checks_pass':all(checks.values()),'source_receipts':len(receipt),'report':str(p)},indent=2))
