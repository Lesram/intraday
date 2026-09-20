"""Bounded final reconciliation. Read frozen studies; write only this directory.

No source/sealed generator executes. Imported factbase and regime_screen are
read-only loader/panel functions, whose output writers are main-guarded.
All historical observations are revised-history proxies, not data vintages.
"""
from pathlib import Path
import sys, json, hashlib
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'analogs')]
import factbase as fb
import regime_screen as rs

ASOF = pd.Timestamp('2026-09-18')
HORIZONS = [1, 3, 5]
FEATURES = ['equity_gdp_pct', 'cpi_yoy_pct', 'ip_yoy_pct', 'baa_aaa_pp',
            'curve_10y_3m_pp', 'real_bill_expost_pct']
DESIGN = {
    'task': 'MACRO_FINAL_004', 'asof': str(ASOF.date()),
    'screen_calendar': ['1964-07', '2021-07'],
    'selected_episodes': 8, 'minimum_spacing_months': 60,
    'eligibility': 'common finite scores, all 60 next-month total returns in all 14 assets, exact FRED CPI at origin and 1/3/5-year endpoints',
    'outcomes': 'nominal and real cumulative total returns; French MKT, RF and 12 value-weighted industries; next month through horizon endpoint',
    'original_expanding': 'strict-prior per-dimension percentile, minimum 120 observations per dimension, original 7-feature backbone and mean absolute distance; current target fixed at original CAPE41.3/Aug2026 vector',
    'review_expanding': 'strict-prior joint-history percentiles, 120 joint observations, 6 dimensions, RMS distance; original approximate availability lags and Sep18 target',
    'joint_pool': 'CAPE percentile>=90 AND Baa-Aaa percentile<=20; original full-history average ranks versus strict-prior expanding ranks, minimum120 observations',
    'joint_pool_windows': {'matched_screen': ['1964-07','2021-07'], 'extended_CPI_overlap': ['1947-01','2021-07']},
    'joint_secondary': 'chronological greedy 60-month spacing, identical for all horizons; start at earliest qualifying month; also report per-horizon spacing as sensitivity',
    'no_optimization': 'thresholds, model definitions, return universe, dates and spacing fixed before examining outcomes',
    'limits': ['revised histories, not vintage data', 'current target chosen today', 'original feature availability remains original, without review release lags', 'selection spacing prevents overlapping return windows, not independent macro observations', 'no portfolio allocation or forecast inferred']
}

def write_json(name, obj):
    assert name.startswith(('quantitative_', 'common_', 'rich_calm_', 'cape_'))
    (OUT/name).write_text(json.dumps(obj, indent=2, default=str)+'\n')

def save(name, d):
    assert name.startswith(('quantitative_', 'common_', 'rich_calm_', 'cape_'))
    d.to_csv(OUT/(name+'.csv'), index=False, float_format='%.10g')

def monthly(s):
    s=s.copy(); s.index=s.index.to_period('M')
    s=s.groupby(level=0).last()
    return s.reindex(pd.period_range(s.index.min(),s.index.max(),freq='M'))

def expanding(x):
    out=pd.DataFrame(index=x.index,columns=x.columns,dtype=float)
    for c in x:
        s=x[c].dropna()
        for j,t in enumerate(s.index):
            if j>=120: out.loc[t,c]=(s.iloc[:j]<s.iloc[j]).mean()*100
    return out

def released(s, dates, quarterly=False):
    s=s.dropna(); p=s.index.to_period('M') if isinstance(s.index,pd.DatetimeIndex) else s.index
    frame=pd.DataFrame({'release':(p+(5 if quarterly else 1)).to_timestamp()+pd.Timedelta(days=15), 'value':s.values})
    out=pd.merge_asof(pd.DataFrame({'decision':dates}),frame.sort_values('release'),left_on='decision',right_on='release',direction='backward')
    out.index=dates
    return out.value

def review_scores():
    dates=pd.date_range('1954-07-31',ASOF,freq='ME').union(pd.DatetimeIndex([ASOF]))
    def yoy(k):
        s=monthly(fb.fred(k));return (s/s.shift(12)-1)*100
    raw={'equity_gdp_pct':fb.fred('NCBEILQ027S')/1000/fb.fred('GDP')*100,
         'cpi_yoy_pct':yoy('CPIAUCSL'),'ip_yoy_pct':yoy('INDPRO'),
         'baa_aaa_pp':fb.fred('BAA')-fb.fred('AAA'),
         'curve_10y_3m_pp':fb.fred('GS10')-fb.fred('TB3MS')}
    x=pd.DataFrame({c:released(s,dates,c=='equity_gdp_pct') for c,s in raw.items()})
    x['real_bill_expost_pct']=released(fb.fred('TB3MS'),dates)-x.cpi_yoy_pct
    x=x[FEATURES].dropna()
    ranks=pd.DataFrame(index=x.index,columns=x.columns,dtype=float)
    for j,t in enumerate(x.index):
        if j>=120:ranks.loc[t]=x.iloc[:j].lt(x.loc[t]).mean()*100
    score=np.sqrt(((ranks-ranks.loc[ASOF])**2).mean(axis=1))
    oldx=pd.read_csv(ROOT/'review/phase_b/features_history.csv',index_col=0,parse_dates=True)
    olds=pd.read_csv(ROOT/'review/phase_b/all_candidate_distances.csv',index_col=0,parse_dates=True).expanding_primary
    checks={'review_feature_max_error':float((x-oldx).abs().max().max()),
            'review_score_max_error':float((score-olds).abs().max())}
    score.index=score.index.to_period('M')
    return score[~score.index.duplicated(keep='last')], checks

def select(scores,n=8,gap=60,chronological=False):
    seq=scores.dropna().sort_index().index if chronological else scores.dropna().sort_values(kind='stable').index
    chosen=[]
    for t in seq:
        if all(abs(t.ordinal-z.ordinal)>=gap for z in chosen):
            chosen.append(t)
            if n is not None and len(chosen)==n: break
    return chosen

def stats(v):
    v=pd.Series(v).dropna()
    return dict(n=len(v),median=v.median(),mean=v.mean(),minimum=v.min(),maximum=v.max(),negative_pct=(v<0).mean()*100)

def returns_and_eligibility():
    ff=fb._ff_block(str(ROOT/'review/inputs/F-F_Research_Data_Factors.csv'),None,None)
    ind=fb._ff_block(str(ROOT/'review/inputs/12_Industry_Portfolios.csv'),None,None)
    r=pd.DataFrame({'MKT':(ff['Mkt-RF']+ff.RF)/100,'CASH':ff.RF/100}).join(ind/100)
    r.index=r.index.to_period('M');cpi=monthly(fb.fred('CPIAUCSL'))
    origins=pd.period_range('1947-01','2021-07',freq='M'); cache={}; audit=[]
    for p in origins:
        complete=True; reasons=[]
        for h in HORIZONS:
            expected=pd.period_range(p+1,p+12*h,freq='M'); block=r.reindex(expected)
            nominal=((1+block).prod()-1)*100
            valid=block.notna().all();nominal=nominal.where(valid)
            c0,c1=cpi.get(p,np.nan),cpi.get(p+12*h,np.nan)
            real=((1+nominal/100)*c0/c1-1)*100
            if not valid.all():complete=False;reasons.append(f'{h}y_returns')
            if not np.isfinite(c0) or not np.isfinite(c1):complete=False;reasons.append(f'{h}y_CPI_endpoint')
            cache[p,h]={'nominal':nominal,'real':real}
        audit.append(dict(month=str(p),eligible_outcomes=complete,exclusion=';'.join(reasons)))
    return r,cpi,cache,pd.DataFrame(audit).set_index('month')

def summary_rows(cache,dates,label,extra=None):
    rows=[]
    for h in HORIZONS:
        for kind in ['nominal','real']:
            a=pd.DataFrame([cache[t,h][kind] for t in dates])
            for asset in a:
                rows.append(dict(specification=label,horizon_years=h,return_basis=kind,asset=asset,**(extra or {}),**stats(a[asset])))
            for asset in a.columns.difference(['MKT','CASH']):
                rows.append(dict(specification=label,horizon_years=h,return_basis=kind,asset=asset+' minus MKT',**(extra or {}),**stats(a[asset]-a.MKT)))
    return rows

def detail_rows(cache,dates,label,extra=None):
    rows=[]
    for p in dates:
        for h in HORIZONS:
            for a,n in cache[p,h]['nominal'].items():
                rows.append(dict(specification=label,month=str(p),horizon_years=h,asset=a,nominal_cumulative_pct=n,real_cumulative_pct=cache[p,h]['real'][a],**(extra or {})))
    return rows

def main():
    write_json('quantitative_design.json',DESIGN)
    original,target,panel=rs.run_screen()
    old=pd.read_csv(ROOT/'analogs/similarity_scores.csv',index_col=0,parse_dates=True)
    checks={'original_full_score_max_error':float((original.score_eq-old.score_eq).abs().max())}
    ex=expanding(panel)
    target_values=panel.ffill().loc[rs.TARGET_MONTH].copy(); target_values['cape']=rs.CAPE_TARGET
    exp_target=pd.Series({c:(panel.loc[panel.index<rs.TARGET_MONTH,c].dropna()<target_values[c]).mean()*100 for c in panel})
    original_exp=(ex-exp_target).abs().mean(axis=1).where(ex[rs.TIER_A_REQUIRED].notna().all(axis=1))
    original_full=(100-original.score_eq).where(original.has_tierA_backbone)
    original_exp.index=original_exp.index.to_period('M');original_full.index=original_full.index.to_period('M')
    review,replication=review_scores();checks.update(replication)
    scores=pd.DataFrame({'original_expanding_recomputed':original_exp,'review_expanding_recomputed':review,'original_full_history_diagnostic':original_full})
    R,cpi,cache,audit=returns_and_eligibility()
    calendar=pd.period_range('1964-07','2021-07',freq='M')
    idx=pd.PeriodIndex(audit.index[audit.eligible_outcomes],freq='M')
    eligible=calendar.intersection(idx).intersection(scores.dropna().index)
    audit['in_common_screen_calendar']=audit.index.isin(calendar.astype(str))
    audit['in_common_screen_eligible']=audit.index.isin(eligible.astype(str))
    save('common_eligibility',audit.reset_index())
    save('common_screen_scores',scores.reindex(calendar).rename_axis('month').reset_index())
    picks=[];summaries=[];details=[]
    for name in scores:
        chosen=select(scores.loc[eligible,name])
        for rank,p in enumerate(chosen,1):
            picks.append(dict(specification=name,rank=rank,month=str(p),distance=float(scores.loc[p,name]),n_dimensions=int(ex.loc[p.to_timestamp()].notna().sum()) if name=='original_expanding_recomputed' else (6 if name.startswith('review') else int(original.loc[p.to_timestamp(),'n_dims']))))
        summaries.extend(summary_rows(cache,chosen,name));details.extend(detail_rows(cache,chosen,name))
        assert len(chosen)==8 and all(abs(a.ordinal-b.ordinal)>=60 for i,a in enumerate(chosen) for b in chosen[i+1:])
    summaries.extend(summary_rows(cache,eligible,'unconditional_same_eligible_months'))
    details.extend(detail_rows(cache,eligible,'unconditional_same_eligible_months'))
    save('common_screen_selections',pd.DataFrame(picks));save('common_screen_returns',pd.DataFrame(details))
    save('common_screen_summary',pd.DataFrame(summaries))
    # Joint original Q3 rule, preserving feature histories and full-rank tie convention.
    full_ranks=panel[['cape','credit']].rank(pct=True)*100
    strict_full=panel[['cape','credit']].apply(lambda s:s.map(lambda v:(s.dropna()<v).mean()*100 if pd.notna(v) else np.nan))
    allranks={'full_history_original':full_ranks,'expanding_prior':ex[['cape','credit']], 'full_history_strict_tie_sensitivity':strict_full}
    joint_rows=[];joint_summaries=[];joint_details=[]
    for window,(lo,hi) in DESIGN['joint_pool_windows'].items():
        base=pd.period_range(lo,hi,freq='M').intersection(idx)
        # Identical eligible dates for both rank conventions; do not change the CDF reference history.
        commonrank=ex[['cape','credit']].dropna().index.to_period('M')
        base=base.intersection(commonrank)
        joint_summaries.extend(summary_rows(cache,base,'unconditional_same_eligible_months',dict(window=window,sample='monthly_pool')))
        joint_details.extend(detail_rows(cache,base,'unconditional_same_eligible_months',dict(window=window,sample='monthly_pool')))
        for p in base:
            joint_rows.append(dict(window=window,specification='unconditional_same_eligible_months',sample='monthly_pool',month=str(p),cape_pct=np.nan,credit_pct=np.nan))
        for name,ranks in allranks.items():
            ranks=ranks.copy();ranks.index=ranks.index.to_period('M');ranks=ranks.reindex(base)
            flag=(ranks.cape>=90)&(ranks.credit<=20)
            dates=ranks.index[flag]
            subs={'monthly_pool':dates,'chronological_60m':select(pd.Series(0.,index=dates),None,60,True)}
            for sample,chosen in subs.items():
                for p in chosen:joint_rows.append(dict(window=window,specification=name,sample=sample,month=str(p),cape_pct=ranks.loc[p,'cape'],credit_pct=ranks.loc[p,'credit']))
                joint_summaries.extend(summary_rows(cache,chosen,name,dict(window=window,sample=sample)))
                joint_details.extend(detail_rows(cache,chosen,name,dict(window=window,sample=sample)))
            for h in [1,3]:
                chosen=select(pd.Series(0.,index=dates),None,h*12,True)
                sample=f'chronological_{h*12}m'
                for p in chosen:
                    joint_rows.append(dict(window=window,specification=name,sample=sample,month=str(p),cape_pct=ranks.loc[p,'cape'],credit_pct=ranks.loc[p,'credit']))
                rows=summary_rows(cache,chosen,name,dict(window=window,sample=sample))
                joint_summaries.extend([r for r in rows if r['horizon_years']==h])
                rawrows=detail_rows(cache,chosen,name,dict(window=window,sample=sample))
                joint_details.extend([r for r in rawrows if r['horizon_years']==h])
    joint=pd.DataFrame(joint_summaries)
    save('rich_calm_membership',pd.DataFrame(joint_rows));save('rich_calm_summary',joint);save('rich_calm_returns',pd.DataFrame(joint_details))
    # Verify original full-history selection before imposing shared maturity/window.
    fullflag=(full_ranks.cape>=90)&(full_ranks.credit<=20)&(full_ranks.index<'2022-01-01')
    oldjoint=pd.read_csv(ROOT/'analogs/rich_and_calm.csv')
    checks['original_joint_membership_exact']=set(full_ranks.index[fullflag].strftime('%Y-%m'))==set(oldjoint.month)
    checks['original_joint_months_before_maturity']=int(fullflag.sum())
    checks['common_calendar_months']=len(calendar);checks['common_eligible_months']=len(eligible)
    checks['common_excluded_months']=list(calendar.difference(eligible).astype(str))
    checks['original_2007oct_eligible']='2007-10' in eligible.astype(str)
    checks['original_2007oct_expanding_similarity_rank']=int(scores.loc[eligible,'original_expanding_recomputed'].rank(method='min').loc['2007-10'])
    checks['models_recomputed']=True
    # Every summary cell must have complete raw constituent rows, including the
    # unconditional reference and horizon-specific secondary thinning samples.
    for label,summarydata,rawdata,keys in [
            ('common',pd.DataFrame(summaries),pd.DataFrame(details),['specification','horizon_years']),
            ('rich_calm',joint,pd.DataFrame(joint_details),['window','specification','sample','horizon_years'])]:
        assert not rawdata.duplicated(keys+['month','asset']).any()
        counts=rawdata.groupby(keys+['asset']).size()
        for row in summarydata.to_dict('records'):
            constituent=row['asset'].removesuffix(' minus MKT')
            key=tuple(row[k] for k in keys)
            assert counts.loc[key+(constituent,)]==row['n']
            if row['asset'].endswith(' minus MKT'):
                assert counts.loc[key+('MKT',)]==row['n']
        checks[label+'_summary_cells_with_complete_raw_rows']=len(summarydata)
        checks[label+'_raw_return_rows']=len(rawdata)
    # CAPE arithmetic: exact August splice; historical rewrites kept distinct from forward paths.
    sh=fb.shiller();price=sh.SP500.dropna();earn=sh.Earnings.dropna();c0=sh['Consumer Price Index'].dropna();cp=fb.fred('CPIAUCSL')
    cm=pd.concat([c0,cp.loc[c0.index[-1]:].iloc[1:]*(c0.iloc[-1]/cp.loc[:c0.index[-1]].iloc[-1])]).reindex(price.index).ffill()
    profit=fb.fred('CPATAX').resample('MS').interpolate();gdp=fb.fred('GDP').resample('MS').interpolate()
    k=earn.iloc[-1]/profit.loc[:earn.index[-1]].iloc[-1]
    e=pd.concat([earn,profit.loc[earn.index[-1]:].iloc[1:]*k]).reindex(price.index).ffill()
    share=(fb.fred('CPATAX')/fb.fred('GDP')*100).dropna()
    historical=share.loc['1947':'1989'].mean();current=share.iloc[-1]
    def cape(ee,pp=price,cc=cm):return ((pp/cc)/(ee/cc).rolling(120).mean()).iloc[-1]
    post=e.index>earn.index[-1]; retro=e.copy();retro.loc[post]=gdp.reindex(e.index).ffill().loc[post]*historical/100*k
    latest=e.copy();latest.iloc[-1]*=historical/current
    cape_rows=[dict(scenario='original_August_proxy',month='2026-08',cape=cape(e),past_proxy_months_changed=0),
               dict(scenario='pre1990_mean_rewrites_all_postsplice_months',month='2026-08',cape=cape(retro),past_proxy_months_changed=int(post.sum())),
               dict(scenario='latest_month_only_scale_illustration',month='2026-08',cape=cape(latest),past_proxy_months_changed=1)]
    # Independently reproduce Review002's September sensitivity, without its generator.
    cpgrid=cp.reindex(pd.date_range('1947-01-01','2026-08-01',freq='MS')).interpolate(limit_area='inside')
    cc=pd.concat([c0,cpgrid.loc[cpgrid.index>c0.index[-1]]*(c0.iloc[-1]/cpgrid.loc[c0.index[-1]])])
    pp=price.copy();pp.loc['2026-09-01']=fb.fred('SP500').loc['2026-09-01':'2026-09-17'].mean()
    cc=cc.reindex(pp.index);cc.loc['2026-09-01']=cc.loc['2026-08-01']**2/cc.loc['2026-07-01']
    ee=e.reindex(pp.index).ffill();mask=ee.index>earn.index[-1];median=share.loc[:'1999'].median()
    ee.loc[mask]=gdp.reindex(pp.index).ffill().loc[mask]*median/100*k
    cape_rows.append(dict(scenario='review002_September_pre2000_median_rewrite',month='2026-09',cape=cape(ee,pp,cc),past_proxy_months_changed=int(mask.sum())))
    save('cape_scenarios',pd.DataFrame(cape_rows))
    # Short independent numerical check of the already-settled profit forward holdout.
    q=share.copy();q.index=q.index.to_period('Q');q=q.reindex(pd.period_range(q.index.min(),q.index.max(),freq='Q'))
    fits=[]
    for h in [4,12,20]:
        y=q.shift(-h);train=(q.index+h<pd.Period('2000Q1'))&q.notna()&y.notna();test=(q.index>=pd.Period('2000Q1'))&q.notna()&y.notna()
        b=np.linalg.lstsq(np.c_[np.ones(train.sum()),q[train]],y[train],rcond=None)[0]
        pred=b[0]+b[1]*q[test]
        fits.append(dict(horizon_quarters=h,n_train=int(train.sum()),n_test=int(test.sum()),mr_rmse=np.sqrt(((pred-y[test])**2).mean()),persistence_rmse=np.sqrt(((q[test]-y[test])**2).mean()),mr_bias=(pred-y[test]).mean(),frozen_equilibrium=b[0]/(1-b[1])))
    fits=pd.DataFrame(fits);save('cape_profit_holdout_replication',fits)
    oldfits=pd.read_csv(ROOT/'review/phase_c/quantitative_profit_forward_holdout.csv')
    checks['profit_holdout_max_abs_error']=float((fits-oldfits).abs().max().max())
    checks['cape_baseline_abs_error']=abs(cape(e)-42.000708232528666)
    checks['cape_review002_abs_error']=abs(cape(ee,pp,cc)-49.65907449948276)
    checks['cape_consolidation_scenario_abs_error']=abs(cape(retro)-50.2977657689269)
    checks['profit_current_pct']=current;checks['profit_pre1990_mean_pct']=historical
    checks['profit_fixed_GDP_change_pct']=(historical/current-1)*100
    checks['cape_rewritten_history_months']=int(post.sum())
    checks['cape_rewritten_history_range']=[str(e.index[post][0].date()),str(e.index[post][-1].date())]
    checks['cape_past_months_in_denominator_unchanged']=120-int(post.sum())
    assert checks['original_full_score_max_error']<.000051
    assert checks['review_feature_max_error']<1e-9 and checks['review_score_max_error']<1e-9
    assert checks['original_joint_membership_exact'] and checks['common_calendar_months']==685
    assert checks['common_eligible_months']==684 and checks['common_excluded_months']==['2020-10']
    assert checks['profit_holdout_max_abs_error']<1e-9
    assert max(checks[k] for k in ['cape_baseline_abs_error','cape_review002_abs_error','cape_consolidation_scenario_abs_error'])<1e-9
    checks['status']='PASS';checks['limitations']=DESIGN['limits']
    write_json('quantitative_validation.json',checks)
    inputs=['scripts/factbase.py','analogs/regime_screen.py','analogs/step5_credit.py',
            'data/raw/s-and-p-500_main_data_data.csv','data/raw/fred_bundle_2026-09-19.json','data/raw/fred_bundle2_2026-09-19.json',
            'review/inputs/F-F_Research_Data_Factors.csv','review/inputs/12_Industry_Portfolios.csv',
            'review/phase_b/features_history.csv','review/phase_b/all_candidate_distances.csv',
            'review/phase_c/quantitative_profit_forward_holdout.csv','analogs/similarity_scores.csv','analogs/rich_and_calm.csv']
    write_json('quantitative_input_receipt.json',{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs})
    print(json.dumps(checks,indent=2))
    print(pd.DataFrame(summaries).query("asset=='MKT' and return_basis=='real'").to_string(index=False))
    print(joint.query("asset=='MKT' and return_basis=='real' and window=='matched_screen' and sample in ['monthly_pool','chronological_60m']").to_string(index=False))

if __name__=='__main__': main()
