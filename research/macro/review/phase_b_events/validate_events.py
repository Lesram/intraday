"""Independent frozen-threshold event study. Writes only to this review subdirectory."""
from pathlib import Path
import sys, json, math, hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
import factbase as fb
START=pd.Period('1954-01','M'); END=pd.Period('2026-08','M')
INDEX=pd.period_range(START,END,freq='M')

def mon(s,agg='last'):
    return s.groupby(s.index.to_period('M')).agg(agg).reindex(INDEX)
def keep_valid(s,condition):
    return condition.where(s.notna()).astype('boolean')
raw={k:fb.fred(k) for k in ['ICSA','SAHMREALTIME','GS10','TB3MS','BAA10Y','NFCI','USREC','CPIAUCSL']}
claims_w=raw['ICSA'].rolling(4,min_periods=4).mean()
claims=mon(100*(claims_w/claims_w.rolling(52,min_periods=52).min()-1))
sahm=mon(raw['SAHMREALTIME']).shift(1)
curve=(mon(raw['GS10'])-mon(raw['TB3MS'])).shift(1)
baa=mon(raw['BAA10Y'])
nfci=mon(raw['NFCI']).shift(1)
cpi=mon(raw['CPIAUCSL'])
yoy=(cpi/cpi.shift(12)-1)*100
surge_base=yoy.shift(1)
accel=surge_base-surge_base.shift(12)
values=pd.DataFrame({'claims_rise_20pct':claims,'sahm_050':sahm,'curve_inverted':curve,
'baa_level_300':baa,'baa_widening_100':baa-baa.shift(3),'nfci_positive':nfci,
'inflation_surge':surge_base,'inflation_400':surge_base})
alarms=pd.DataFrame({
'claims_rise_20pct':keep_valid(claims,claims>=20),
'sahm_050':keep_valid(sahm,sahm>=.5),
'curve_inverted':keep_valid(curve,curve<0),
'baa_level_300':keep_valid(baa,baa>=3),
'baa_widening_100':keep_valid(baa-baa.shift(3),baa-baa.shift(3)>=1),
'nfci_positive':keep_valid(nfci,nfci>0),
'inflation_surge':keep_valid(surge_base.where(accel.notna()),(surge_base>=4)&(accel>=2)),
'inflation_400':keep_valid(surge_base,surge_base>=4)})
price=mon(fb.shiller()['SP500'])
rec=mon(raw['USREC'])
series={'recession':rec,'inflation':yoy,'credit':baa,'equity_price':price}
onsets={'recession':(rec.eq(1)&rec.shift().eq(0)),
'inflation':(yoy.ge(4)&yoy.shift().lt(4)),
'credit':(baa.ge(3)&baa.shift().lt(3))}
event_rows=[]
for kind,flags in onsets.items():
 for date in flags[flags].index:
  event_rows.append({'event':kind+'_onset','date':str(date),'value':series[kind].loc[date]})
price_dd=price/price.cummax()-1
for date in (price_dd.le(-.2)&price_dd.shift().gt(-.2)).loc[lambda s:s].index:
 event_rows.append({'event':'equity_historical_running_peak_20pct_crossing','date':str(date),'value':price_dd.loc[date]})
pd.DataFrame(event_rows).to_csv(OUT/'event_dates.csv',index=False)
values.assign(cpi_yoy_change_12m=accel).to_csv(OUT/'monthly_indicator_values.csv',index_label='signal_month')
alarms.to_csv(OUT/'monthly_alarm_flags.csv',index_label='signal_month')

KINDS=['recession_onset','recession_present_or_onset','equity_entry_loss_20','equity_peak_drawdown_20','inflation_onset_400','credit_onset_300']
def evaluate(t,h,kind):
    """Returns None for unavailable/ineligible; otherwise y, first event period, lead."""
    futures=pd.period_range(t+1,t+h,freq='M')
    if futures[-1]>END: return None
    if kind.startswith('recession'):
        if pd.isna(rec.loc[t]) or rec.reindex(futures).isna().any(): return None
        if kind=='recession_onset':
            if rec.loc[t]==1: return None
            flags=onsets['recession'].reindex(futures)
        else:
            futures=pd.period_range(t,t+h,freq='M')
            flags=rec.reindex(futures).eq(1)
    elif kind.startswith('inflation'):
        if pd.isna(yoy.loc[t]) or yoy.reindex(futures).isna().any() or yoy.loc[t]>=4: return None
        flags=onsets['inflation'].reindex(futures)
    elif kind.startswith('credit'):
        if pd.isna(baa.loc[t]) or baa.reindex(futures).isna().any() or baa.loc[t]>=3: return None
        flags=onsets['credit'].reindex(futures)
    else:
        if pd.isna(price.loc[t]) or price.reindex(futures).isna().any(): return None
        if kind=='equity_entry_loss_20':
            flags=(price.reindex(futures)/price.loc[t]-1).le(-.2)
        else:
            path=price.reindex(pd.period_range(t,t+h,freq='M'))
            flags=(path/path.cummax()-1).le(-.2).iloc[1:]
    hit=bool(flags.any())
    first=flags[flags].index[0] if hit else None
    return hit,str(first) if hit else '',first.ordinal-t.ordinal if hit else np.nan

def split_of(t,h):
    if t+h<=pd.Period('1999-12','M'):return 'training_pre2000'
    if t>=pd.Period('2000-01','M'):return 'holdout_2000plus'
    return 'split_boundary_excluded'

def wilson(k,n):
    if n==0:return (np.nan,np.nan)
    z=1.96; p=k/n; d=1+z*z/n
    mid=(p+z*z/(2*n))/d; half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return mid-half,mid+half

panel=[]; episodes=[]; rejected=[]
for name in alarms:
    hs=[12,24] if name=='curve_inverted' else [12]
    signal=alarms[name]
    # A false->true crossing must have an observed false previous month.
    crosses=signal.eq(True)&signal.shift().eq(False)
    for h in hs:
        for kind in KINDS:
            last_episode=None
            for t in INDEX:
                if pd.isna(signal.loc[t]):continue
                ev=evaluate(t,h,kind)
                if ev is None:
                    if crosses.loc[t] is np.True_ or (not pd.isna(crosses.loc[t]) and bool(crosses.loc[t])):
                        rejected.append({'indicator':name,'horizon_months':h,'event':kind,'signal_month':str(t),'reason':'outcome unavailable, immature, or already active for onset-only target'})
                    continue
                y,event_date,lead=ev
                row={'indicator':name,'horizon_months':h,'event':kind,'signal_month':str(t),'split':split_of(t,h),'signal_value':values.loc[t,name],'alarm':int(signal.loc[t]),'outcome':int(y),'first_event_month':event_date,'lead_months':lead}
                panel.append(row)
                if not pd.isna(crosses.loc[t]) and bool(crosses.loc[t]):
                    if last_episode is None or t.ordinal-last_episode.ordinal>=h:
                        episodes.append(row); last_episode=t
                    else:
                        rejected.append({'indicator':name,'horizon_months':h,'event':kind,'signal_month':str(t),'reason':f'within {h}m cooldown of {last_episode}'})
panel=pd.DataFrame(panel); ep=pd.DataFrame(episodes)
panel.to_csv(OUT/'monthly_evaluation.csv',index=False)
ep.to_csv(OUT/'alarm_episodes.csv',index=False)
pd.DataFrame(rejected).to_csv(OUT/'excluded_crossings.csv',index=False)
summary=[]
for (name,h,kind),p in panel.groupby(['indicator','horizon_months','event']):
 for split in ['all','training_pre2000','holdout_2000plus']:
  q=p if split=='all' else p[p.split==split]
  e=ep[(ep.indicator==name)&(ep.horizon_months==h)&(ep.event==kind)]
  if split!='all':e=e[e.split==split]
  n=len(e); hits=int(e.outcome.sum()); fp=n-hits
  neg=q[q.outcome==0]; pos=q[q.outcome==1]
  classical_fp=int(neg.alarm.sum()); classical_tn=len(neg)-classical_fp
  tp=int(pos.alarm.sum()); fn=len(pos)-tp
  lo,hi=wilson(fp,n)
  nonalarm=q[q.alarm==0]
  leads=e.loc[e.outcome==1,'lead_months']
  summary.append({'indicator':name,'horizon_months':h,'event':kind,'split':split,
  'eligible_months':len(q),'first_signal_month':q.signal_month.min() if len(q) else '',
  'last_signal_month':q.signal_month.max() if len(q) else '',
  'unconditional_event_probability':q.outcome.mean(),'nonalarm_event_probability':nonalarm.outcome.mean(),
  'n_alarm_episodes':n,'episode_hits':hits,'episode_false_alarms':fp,
  'episode_hit_rate':hits/n if n else np.nan,'episode_false_alarm_fraction':fp/n if n else np.nan,
  'false_alarm_wilson_95_low':lo,'false_alarm_wilson_95_high':hi,
  'lead_months_median':leads.median(),'lead_months_min':leads.min(),'lead_months_max':leads.max(),
  'classical_fp_months':classical_fp,'classical_tn_months':classical_tn,'classical_fpr':classical_fp/len(neg) if len(neg) else np.nan,
  'classical_tp_months':tp,'classical_fn_months':fn,'monthly_sensitivity':tp/len(pos) if len(pos) else np.nan,
  'note':'Revised-history pseudo-OOS; overlapping monthly windows. Episode intervals assume independence only approximately.'})
summary=pd.DataFrame(summary)
summary.to_csv(OUT/'indicator_event_metrics.csv',index=False)
corr=[]
for i,a in enumerate(alarms):
 for b in list(alarms)[i+1:]:
  pair=alarms[[a,b]].dropna().astype(float)
  intersect=((pair[a]==1)&(pair[b]==1)).sum(); union=((pair[a]==1)|(pair[b]==1)).sum()
  corr.append({'indicator_a':a,'indicator_b':b,'first_month':str(pair.index.min()),'last_month':str(pair.index.max()),'n_months':len(pair),'alarm_phi_correlation':pair[a].corr(pair[b]),'alarm_jaccard':intersect/union if union else np.nan})
pd.DataFrame(corr).to_csv(OUT/'redundancy.csv',index=False)
# Snapshot all source files consumed, to make this study repeatable without changing sources.
paths=['scripts/factbase.py','data/raw/fred_bundle_2026-09-19.json','data/raw/fred_bundle2_2026-09-19.json','data/raw/s-and-p-500_main_data_data.csv']
manifest={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
manifest['preregistration_sha256']=hashlib.sha256((OUT/'preregistration.json').read_bytes()).hexdigest()
(OUT/'source_hashes.json').write_text(json.dumps(manifest,indent=2)+'\n')
chosen=summary[(summary.split=='all')&(summary.horizon_months==12)&summary.event.isin(['recession_onset','equity_entry_loss_20'])]
print(chosen[['indicator','event','n_alarm_episodes','episode_hits','episode_false_alarm_fraction','classical_fpr','unconditional_event_probability','lead_months_median']].to_string(index=False))
# Signed diagnostic delay: positive values mean recession started BEFORE the alarm.
starts=pd.PeriodIndex([r['date'] for r in event_rows if r['event']=='recession_onset'],freq='M')
delay_rows=[]
for _,r in ep[(ep.event=='recession_present_or_onset')&(ep.outcome==1)].iterrows():
 t=pd.Period(r.signal_month,freq='M')
 if r.lead_months==0:
  onset=starts[starts<=t][-1]; delay=t.ordinal-onset.ordinal
 else:
  onset=pd.Period(r.first_event_month,freq='M'); delay=-r.lead_months
 delay_rows.append({'indicator':r.indicator,'signal_month':r.signal_month,'horizon_months':r.horizon_months,'recession_onset':str(onset),'months_after_onset':delay,'split':r.split})
pd.DataFrame(delay_rows).to_csv(OUT/'recession_diagnostic_delays.csv',index=False)
checks=[]
for (name,h,kind),e in ep.groupby(['indicator','horizon_months','event']):
 dates=pd.PeriodIndex(e.signal_month,freq='M')
 assert all(t+h<=END for t in dates)
 assert all(np.diff(dates.asi8)>=h)
 assert len(e)==int(e.outcome.sum())+int((1-e.outcome).sum())
 assert e[e.outcome==1].lead_months.between(0 if kind=='recession_present_or_onset' else 1,h).all()
checks.append('All alarm windows mature; cooldown at least horizon; episode denominators reconcile; leads in prescribed horizon.')
assert pd.isna(cpi.loc[pd.Period('2025-10')])
assert pd.isna(yoy.loc[pd.Period('2025-10')])
checks.append('Missing 2025-10 CPI remains missing; never bridged with positional year-on-year arithmetic.')
for _,r in summary.iterrows():
 if r.n_alarm_episodes:
  assert abs(r.episode_hit_rate+r.episode_false_alarm_fraction-1)<1e-12
 assert r.classical_fp_months+r.classical_tn_months+r.classical_tp_months+r.classical_fn_months==r.eligible_months
checks.append('All confusion-matrix denominators equal eligible monthly observations.')
(OUT/'validation_checks.json').write_text(json.dumps({'passed':checks,'failed':[]},indent=2)+'\n')
