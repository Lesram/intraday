"""Post-seal attacks 1–6. Read prior research; write only quantitative_* in phase_c.

Fixed sensitivity choices are explanatory conventions, never chosen by outcome.
All distributions use the supplied frozen/revised histories, not vintage data.
"""
from pathlib import Path
import sys, ast, json, hashlib
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'analogs')]
import factbase as fb
import regime_screen as rs
import analog_scripts as ar
# Override only loader callables in this process, preserving sealed and raw inputs.
fb.ff_factors=lambda:fb._ff_block(str(ROOT/'review/inputs/F-F_Research_Data_Factors.csv'),None,None)
fb.ff_industries_vw=lambda:fb._ff_block(str(ROOT/'review/inputs/12_Industry_Portfolios.csv'),None,None)

def save(d,name):
    d.to_csv(OUT/('quantitative_'+name+'.csv'),index=False)

def months(s):
    x=s.copy();x.index=x.index.to_period('M');return x

def strict_fwd(R,cpi,t,h,asset):
    dates=pd.date_range(t+pd.DateOffset(months=1),periods=h*12,freq='MS')
    r=R[asset].reindex(dates)
    if r.isna().any() or len(r)!=h*12:return np.nan
    c0,c1=cpi.get(t,np.nan),cpi.get(dates[-1],np.nan)
    return ((1+r).prod()*c0/c1-1)*100 if pd.notna(c0) and pd.notna(c1) else np.nan

def selected(scores,n=8,gap=60):
    chosen=[]
    for t in scores.dropna().sort_values(ascending=False).index:
        if all(abs(t.to_period('M').ordinal-z.to_period('M').ordinal)>=gap for z in chosen):
            chosen.append(t)
            if len(chosen)>=n:break
    return chosen

def summary(a):
    a=pd.Series(a).dropna()
    return dict(n=len(a),median=a.median(),mean=a.mean(),minimum=a.min(),maximum=a.max(),negative_pct=(a<0).mean()*100)

def expanding(panel,minhist=120):
    d=pd.DataFrame(index=panel.index,columns=panel.columns,dtype=float)
    for c in panel:
        s=panel[c].dropna()
        for j,t in enumerate(s.index):
            if j>=minhist:d.loc[t,c]=(s.iloc[:j]<s.iloc[j]).mean()*100
    return d

def screen(R,cpi):
    orig, target_rank, panel=rs.run_screen()
    disk=pd.read_csv(ROOT/'analogs/similarity_scores.csv',index_col=0,parse_dates=True)
    difference=(orig['score_eq']-disk['score_eq']).abs().max()
    ex=expanding(panel)
    tgt=panel.ffill().loc[rs.TARGET_MONTH].copy();tgt['cape']=rs.CAPE_TARGET
    tr=pd.Series({c:(panel.loc[panel.index<rs.TARGET_MONTH,c].dropna()<tgt[c]).mean()*100 for c in panel})
    score_exp=100-(ex-tr).abs().mean(axis=1)
    mask=ex[rs.TIER_A_REQUIRED].notna().all(axis=1)
    score_exp=score_exp[mask]
    score_all=score_exp[ex.notna().all(axis=1)]
    variants={'original_full_sample':orig.loc[orig.has_tierA_backbone,'score_eq'],
              'expanding_primary_same_backbone':score_exp,'expanding_complete_11dims':score_all}
    pickrows=[];returnrows=[]
    for spec,score in variants.items():
        for gap,cutoff,n in [(24,'2023-12-01',12),(60,'2021-07-01',8)]:
            for rank,t in enumerate(selected(score.loc[:cutoff],n,gap),1):
                pickrows.append(dict(spec=spec,gap_months=gap,cutoff=cutoff,rank=rank,date=str(t.date()),score=score[t],n_dims=int(ex.loc[t].notna().sum()) if 'expanding' in spec else orig.loc[t,'n_dims']))
                for h in [1,3,5]:
                    for asset in ['MKT','CASH','GOLD','Enrgy','BusEq','Telcm']:
                        val=strict_fwd(R,cpi,t,h,asset)
                        if asset=='GOLD' and t<pd.Timestamp('1971-08-01'):val=np.nan
                        returnrows.append(dict(spec=spec,gap_months=gap,cutoff=cutoff,rank=rank,date=str(t.date()),horizon=h,asset=asset,real_return=val))
    save(pd.DataFrame(pickrows),'screen_selections');rr=pd.DataFrame(returnrows);save(rr,'screen_returns')
    sums=[]
    for k,d in rr.groupby(['spec','gap_months','horizon','asset']):sums.append(dict(zip(['spec','gap_months','horizon','asset'],k),**summary(d.real_return)))
    save(pd.DataFrame(sums),'screen_return_summary')
    conj=[]
    for spec,ranks in [('full_sample',orig[[f'pct_{c}' for c in panel]].rename(columns=lambda c:c[4:])),('expanding',ex)]:
        eligible=ranks[['cape','credit','unrate','ppi_yoy']].notna().all(axis=1)&(ranks.index<'2024-01-01')
        hit=eligible&(ranks.cape>=90)&(ranks.credit<=20)&(ranks.unrate<=30)&(ranks.ppi_yoy>=75)
        dates=ranks.index[hit]
        conj.append(dict(spec=spec,n_eligible=int(eligible.sum()),n_months=len(dates),years=';'.join(map(str,sorted(set(dates.year)))),dates=';'.join(dates.strftime('%Y-%m'))))
    save(pd.DataFrame(conj),'conjunctive_screen')
    return dict(prior_score_max_abs_difference=difference)

def overlap_and_gold(R,cpi):
    er=pd.read_csv(ROOT/'analogs/episode_returns.csv')
    names=[n for n in er.episode.unique() if n.startswith('S ')]+['M 1999-2000 dotcom [anchor]']
    d=er[er.episode.isin(names)]
    spans=d[(d.asset_or_industry=='MKT')&(d.horizon_years==5)][['episode','start_date','months_used','truncated']].copy()
    spans['start']=pd.to_datetime(spans.start_date);spans['expected_end']=spans.start+pd.DateOffset(months=60)
    chronological=spans.sort_values('start');last=None;keep=[]
    for row in chronological.itertuples():
        if last is None or row.start>=last:keep.append(row.episode);last=row.expected_end
    spans['in_maximum_disjoint_chronological_set']=spans.episode.isin(keep)
    save(spans.drop(columns='start'),'original_episode_maturity')
    pairs=[]
    for i,a in spans.iterrows():
        for j,b in spans.iterrows():
            if j<=i:continue
            sep=abs(a.start.to_period('M').ordinal-b.start.to_period('M').ordinal)
            if sep<60:pairs.append(dict(a=a.episode,b=b.episode,overlap_months=60-sep))
    save(pd.DataFrame(pairs),'overlap_pairs')
    sums=[]
    for label,dd in [('original_including_truncated',d),('complete_horizons_only',d[~d.truncated]),('chronological_disjoint_complete',d[d.episode.isin(keep)&~d.truncated])]:
        for (a,h),x in dd[dd.investable].groupby(['asset_or_industry','horizon_years']):sums.append(dict(sample=label,asset=a,horizon=h,**summary(x.real_return*100)))
    save(pd.DataFrame(sums),'original_sample_sensitivity')
    gold=[]
    for start in ['1871-01-01','1971-08-01','1996-02-01']:
        for h in [1,3,5]:
            vals=[strict_fwd(R,cpi,t,h,'GOLD') for t in R.loc[start:].index]
            gold.append(dict(sample_start=start,horizon=h,**summary(vals)))
    save(pd.DataFrame(gold),'gold_baseline_eras')
    return dict(original_n_episodes=len(spans),max_pairwise_nonoverlapping_5y_starts=len(keep),overlapping_pairs=len(pairs),truncated_5y_episodes=spans.loc[spans.truncated,'episode'].tolist(),screen_n_automatically_selected=12,manually_added_anchor='2000-02')

def cape():
    tree=ast.parse((ROOT/'scripts/regime_model.py').read_text())
    fun=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='cape_series')
    env={'pd':pd,'np':np,'fb':fb};exec(compile(ast.Module(body=[fun],type_ignores=[]),'<isolated cape_series>','exec'),env)
    model=env['cape_series']();cached=pd.read_csv(ROOT/'data/processed/cape_recomputed.csv',index_col=0,parse_dates=True).iloc[:,0]
    sh=fb.shiller();price=sh.SP500.dropna();earn=sh.Earnings.dropna();cpi0=sh['Consumer Price Index'].dropna()
    cp=fb.fred('CPIAUCSL').reindex(pd.date_range('1947-01-01','2026-08-01',freq='MS')).interpolate(limit_area='inside')
    cpi=pd.concat([cpi0,cp[cp.index>cpi0.index[-1]]*cpi0.iloc[-1]/cp[cpi0.index[-1]]])
    prof=fb.fred('CPATAX').resample('MS').interpolate();k=earn.iloc[-1]/prof.loc[:earn.index[-1]].iloc[-1]
    earn_base=pd.concat([earn,prof[prof.index>earn.index[-1]]*k]).reindex(price.index).ffill()
    sept=fb.fred('SP500').loc['2026-09-01':'2026-09-17'];price.loc[pd.Timestamp('2026-09-01')]=sept.mean()
    earn_base=earn_base.reindex(price.index).ffill();cpi=cpi.reindex(price.index)
    cpi.loc['2026-09-01']=cpi.loc['2026-08-01']**2/cpi.loc['2026-07-01']
    def calculate(e,c=cpi):return (price/c)/(e/c).rolling(120).mean()
    spliced=calculate(earn_base)
    rows=[dict(spec='published_model_original_code_August',month='2026-08',cape=model.iloc[-1],note='AST-isolated exact source function'),
          dict(spec='interpolated_gap_August',month='2026-08',cape=spliced.loc['2026-08-01'],note='same EPS proxy, missing CPI interpolated'),
          dict(spec='September_partial_price_recent_CPI_growth',month='2026-09',cape=spliced.iloc[-1],note='12 daily closes through Sep17; CPI extrapolated by latest monthly growth')]
    for shock in [.85,1.15]:
        e=earn_base.copy();e.loc[e.index>'2023-06-01']*=shock
        rows.append(dict(spec=f'postsplice_EPS_multiplier_{shock}',month='2026-09',cape=calculate(e).iloc[-1],note='only post2023June EPS changed; scenario, not estimate'))
    e=earn_base.copy();mask=e.index>'2023-06-01';e.loc[mask]=earn.iloc[-1]*cpi.loc[mask]/cpi.loc['2023-06-01']
    rows.append(dict(spec='freeze_June2023_real_EPS',month='2026-09',cape=calculate(e).iloc[-1],note='flat real per-share EPS after splice'))
    share=(fb.fred('CPATAX')/fb.fred('GDP')*100).dropna()
    normalized_shares={'pre2000_median':share.loc[:'1999'].median(),'fixed_8pct':8.,'fixed_10pct':10.}
    gdp=fb.fred('GDP').resample('MS').interpolate().reindex(price.index).ffill()
    for name,level in normalized_shares.items():
        e=earn_base.copy();e.loc[mask]=k*gdp.loc[mask]*level/100
        rows.append(dict(spec='postsplice_profitshare_'+name,month='2026-09',cape=calculate(e).iloc[-1],note=f'aggregate share fixed at {level:.6f}%; GDP-linked EPS only after2023June; stress scenario'))
    cflat=cpi.copy();cflat.loc['2026-09-01']=cflat.loc['2026-08-01']
    rows.append(dict(spec='September_CPI_carried_flat',month='2026-09',cape=calculate(earn_base,cflat).iloc[-1],note='no September inflation extrapolation'))
    save(pd.DataFrame(rows),'cape_sensitivity')
    decomposition=[]
    for t in ['2026-08-01','2026-09-01']:
        decomposition.append(dict(month=t,price=price[t],cpi=cpi[t],proxy_EPS=earn_base[t],trailing_mean_real_EPS=((earn_base/cpi).rolling(120).mean())[t],cape=spliced[t]))
    save(pd.DataFrame(decomposition),'cape_inputs')
    return dict(model_vs_cached_max_error=float((model-cached).abs().max()),september_price_observations=len(sept),september_price_mean=sept.mean(),splice_scale=k,proxy_EPS=earn_base.iloc[-1],replicated_1929sep=model.loc['1929-09-01'],published_41_3_is_partial_September_not_August=True)

def tightening(R,cpi):
    tb=rs._grid(fb.fred('TB3MS'));ff=rs._grid(fb.fred('FEDFUNDS'))
    spreads={'BAA_AAA':rs._grid(fb.fred('BAA'))-rs._grid(fb.fred('AAA')),
             'BAA_GS10':rs._grid(fb.fred('BAA'))-rs._grid(fb.fred('GS10'))}
    definitions=[]
    # Original permits a new "onset" in an uninterrupted cycle every24months.
    definitions.append(('original_repeated_level',ar.tightening_onsets().index))
    for rate_name,rate in [('TB3MS',tb),('FEDFUNDS',ff)]:
        for rise,look in [(.25,6),(.5,6),(1.,12)]:
            flag=(rate-rate.shift(look))>=rise;cross=flag&~flag.shift(1,fill_value=False)
            dates=[]
            for t in flag.index[cross]:
                if not dates or t.to_period('M').ordinal-dates[-1].to_period('M').ordinal>=24:dates.append(t)
            definitions.append((f'{rate_name}_cross_{rise}pp_{look}m',pd.DatetimeIndex(dates)))
    records=[]
    for spread_name,spread in spreads.items():
        spread=spread.dropna();rank=expanding(spread.to_frame('s'))['s'];full=spread.rank(pct=True)*100
        for onset_name,dates in definitions:
            for rule in ['prior_pct10','prior_pct20','prior_pct30','full_pct20','absolute']:
                for t in dates:
                    if t not in spread.index:continue
                    if rule=='absolute':calm=spread[t]<=(.6 if spread_name=='BAA_AAA' else 1.5)
                    else:
                        r=full.get(t,np.nan) if rule=='full_pct20' else rank.get(t,np.nan)
                        if pd.isna(r):continue
                        calm=r<=int(rule[-2:])
                    outcome=strict_fwd(R,cpi,t,3,'MKT')
                    if pd.isna(outcome):continue
                    w=R.MKT.reindex(pd.date_range(t+pd.DateOffset(months=1),periods=36,freq='MS'))
                    wealth=np.r_[1.,np.cumprod(1+w.to_numpy())];draw=(wealth/np.maximum.accumulate(wealth)-1).min()*100
                    records.append(dict(spread=spread_name,onset=onset_name,calm_rule=rule,date=str(t.date()),calm=bool(calm),credit=spread[t],real_3y=outcome,maxdrawdown_3y=draw,post2000=t.year>=2000))
    rec=pd.DataFrame(records);save(rec,'tightening_all_episodes')
    rows=[]
    for keys,g in rec.groupby(['spread','onset','calm_rule','calm']):
        for split,gg in [('all',g),('pre2000',g[~g.post2000]),('2000plus',g[g.post2000])]:
            if not len(gg):continue
            rows.append(dict(zip(['spread','onset','calm_rule','calm'],keys),split=split,**summary(gg.real_3y),drawdown20_pct=(gg.maxdrawdown_3y<=-20).mean()*100,worst_drawdown=gg.maxdrawdown_3y.min()))
    save(pd.DataFrame(rows),'tightening_sensitivity')

def ols_hac(x,y,lags):
    good=np.isfinite(x)&np.isfinite(y);x=np.asarray(x)[good];y=np.asarray(y)[good]
    X=np.c_[np.ones(len(x)),x];beta=np.linalg.lstsq(X,y,rcond=None)[0];u=y-X@beta
    z=X*u[:,None];S=z.T@z
    for j in range(1,min(lags,len(x)-1)+1):
        cross=z[j:].T@z[:-j];S+=(1-j/(lags+1))*(cross+cross.T)
    bread=np.linalg.inv(X.T@X);cov=bread@S@bread
    return beta,np.sqrt(np.diag(cov)),len(x)

def profits():
    share=(fb.fred('CPATAX')/fb.fred('GDP')*100).dropna();share.index=share.index.to_period('Q')
    share=share.reindex(pd.period_range(share.index.min(),share.index.max(),freq='Q'))
    save(share.rename('profit_share_pct').rename_axis('quarter').reset_index(),'profit_share_history')
    fits=[];high=[]
    for h in [4,12,20]:
        dy=share.shift(-h)-share
        for regime,lo,hi in [('full','1947Q1','2026Q2'),('pre1990','1947Q1','1989Q4'),('1990_2009','1990Q1','2009Q4'),('2010plus','2010Q1','2026Q2')]:
            s=share.loc[lo:hi];end=s.index+h
            good=end<=pd.Period(hi,freq='Q');s=s[good];y=dy.reindex(s.index)
            if y.notna().sum()<10:continue
            beta,se,n=ols_hac(s.to_numpy(),y.to_numpy(),h-1)
            fits.append(dict(regime=regime,horizon_quarters=h,n=n,intercept=beta[0],slope_change_on_level=beta[1],hac_slope_se=se[1],hac_t=beta[1]/se[1],implied_equilibrium=-beta[0]/beta[1]))
        for level in [8.,10.]:
            allhigh=share[(share>=level)&dy.notna()]
            for sample in ['all_overlapping','nonoverlap_chronological']:
                dates=[]
                for t in allhigh.index:
                    if sample=='all_overlapping' or not dates or t.ordinal-dates[-1].ordinal>=h:dates.append(t)
                d=dy.reindex(dates)
                high.append(dict(level=level,horizon_quarters=h,sample=sample,**summary(d),decline_pct=(d<0).mean()*100,dates=';'.join(map(str,dates))))
    save(pd.DataFrame(fits),'profit_mean_reversion');save(pd.DataFrame(high),'profit_high_start_outcomes')
    moments=[]
    for era,lo,hi in [('1947_1989','1947Q1','1989Q4'),('1990_2009','1990Q1','2009Q4'),('2010_2026','2010Q1','2026Q2')]:
        s=share.loc[lo:hi];moments.append(dict(era=era,n=s.count(),mean=s.mean(),median=s.median(),minimum=s.min(),maximum=s.max()))
    save(pd.DataFrame(moments),'profit_era_levels')
    out=[]
    for h in [4,12,20]:
        # Train only on outcomes fully known before2000; test endpoints after2000.
        y=share.shift(-h);train=(share.index+h<pd.Period('2000Q1'))&share.notna()&y.notna()
        test=(share.index>=pd.Period('2000Q1'))&share.notna()&y.notna()
        X=np.c_[np.ones(train.sum()),share[train]];beta=np.linalg.lstsq(X,y[train],rcond=None)[0]
        pred=beta[0]+beta[1]*share[test];persist=share[test];actual=y[test]
        out.append(dict(horizon_quarters=h,n_train=int(train.sum()),n_test=int(test.sum()),mr_rmse=float(np.sqrt(((pred-actual)**2).mean())),persistence_rmse=float(np.sqrt(((persist-actual)**2).mean())),mr_bias=float((pred-actual).mean()),frozen_equilibrium=beta[0]/(1-beta[1])))
    save(pd.DataFrame(out),'profit_forward_holdout')

def concentration(R,cpi):
    path=str(ROOT/'review/inputs/12_Industry_Portfolios.csv')
    counts=fb._ff_block(path,'Number of Firms in Portfolios',None)
    sizes=fb._ff_block(path,'Average Firm Size',None)
    cap=counts*sizes;weights=cap.div(cap.sum(axis=1),axis=0);weights.index=weights.index.to_period('M').to_timestamp()
    proxy=pd.DataFrame({'HHI12':weights.pow(2).sum(axis=1),'top_industry_weight':weights.max(axis=1),'BusEq_weight':weights.BusEq,'top_industry':weights.idxmax(axis=1)})
    proxy['effective_industries']=1/proxy.HHI12
    save(proxy.reset_index(names='date'),'industry_concentration_history')
    save(weights.reset_index(names='date'),'industry_weights')
    # Round prior thresholds, not fitted: one industry at least25% or HHI>=.15.
    rows=[]
    for indicator,level in [('top_industry_weight',.25),('HHI12',.15)]:
        hits=proxy[indicator]>=level
        for h in [1,3,5]:
            valid=[]
            for t in proxy.index[hits]:
                m=strict_fwd(R,cpi,t,h,'MKT')
                if pd.notna(m):valid.append(t)
            for sample in ['all_months','nonoverlap_chronological']:
                dates=[]
                for t in valid:
                    if sample=='all_months' or not dates or t.to_period('M').ordinal-dates[-1].to_period('M').ordinal>=h*12:dates.append(t)
                vals=[];rel=[]
                for t in dates:
                    m=strict_fwd(R,cpi,t,h,'MKT');dom=proxy.loc[t,'top_industry'];s=strict_fwd(R,cpi,t,h,dom)
                    vals.append(m);rel.append(s-m)
                rows.append(dict(indicator=indicator,level=level,horizon=h,sample=sample,**summary(vals),dominant_sector_median_excess_pp=pd.Series(rel).median(),dominant_sector_underperforms_pct=(pd.Series(rel)<0).mean()*100,dates=';'.join(t.strftime('%Y-%m') for t in dates)))
    save(pd.DataFrame(rows),'concentration_forward_returns')
    landmarks=[]
    for start,end in [('1926-07','1930-12'),('1960-01','1979-12'),('1998-01','2001-12'),('2005-01','2009-12'),('2020-01','2026-07')]:
        d=proxy.loc[start:end];t=d.top_industry_weight.idxmax();landmarks.append(dict(window=start+'..'+end,date=str(t.date()),**proxy.loc[t].to_dict()))
    landmarks.append(dict(window='latest',date=str(proxy.index[-1].date()),**proxy.iloc[-1].to_dict()))
    save(pd.DataFrame(landmarks),'concentration_landmarks')

def main():
    OUT.mkdir(exist_ok=True)
    R,cpi=ar.monthly_returns()
    audit={};audit['screen']=screen(R,cpi);audit['overlap']=overlap_and_gold(R,cpi);audit['cape']=cape()
    tightening(R,cpi);profits();concentration(R,cpi)
    inputs=[]
    for p in sorted((ROOT/'analogs').glob('*')):
        if p.is_file():inputs.append(dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    audit['analogs_inputs']=inputs
    (OUT/'quantitative_validation.json').write_text(json.dumps(audit,indent=2,default=str))
    print(json.dumps({k:v for k,v in audit.items() if k!='analogs_inputs'},indent=2,default=str))

if __name__=='__main__':main()
