"""Audit source verdicts; descriptive standardization, never a causal channel effect."""
from pathlib import Path
import pandas as pd
import numpy as np
import json, hashlib

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
claims=pd.read_csv(ROOT/'claims/claim_ledger.csv').fillna('')
verdicts=pd.concat([pd.read_csv(p).assign(package=p.parent.name) for p in sorted((ROOT/'verify/out').glob('V*/verdicts.csv'))],ignore_index=True)
assert claims.claim_id.is_unique and verdicts.claim_id.is_unique
d=verdicts.merge(claims,on='claim_id',validate='one_to_one')
assert len(d)==1430
d['supported']=d.verdict.isin(['TRUE','MOSTLY_TRUE','TRENDING'])
d['unknown']=d.verdict.eq('UNVERIFIABLE')
d['checkable']=~d.verdict.isin(['UNVERIFIABLE','OPEN'])
d[['claim_id','channel','video_id','video_date','claim_type','thesis_cluster','_scope','package','fact_key','verdict','supported','unknown','checkable']].to_csv(OUT/'verdict_inventory.csv',index=False)
summary={'n_ledger':len(claims),'n_verdicts':len(d),'verdict_counts':d.verdict.value_counts().to_dict(),'by_type_all_ledger':claims.claim_type.value_counts().to_dict(),'by_type_verdicts':d.claim_type.value_counts().to_dict(),'as_of':'2026-09-19','support_definition':'TRUE + MOSTLY_TRUE + TRENDING, reproducing Brief001 arithmetic. Excludes UNVERIFIABLE and OPEN from denominator. TRENDING is not verified truth; omitting it gives865/1058=81.758%.','self_correction':'Initial support definition omitted4 TRENDING labels and failed to reproduce82.1%; corrected by explicitly matching source arithmetic rather than quietly relabeling.'}
rows=[]
for channel,g in d.groupby('channel'):
    k=g[g.checkable]
    rows.append(dict(channel=channel,n_all=len(g),n_checkable=len(k),supported=int(k.supported.sum()),strict_true=int(k.verdict.eq('TRUE').sum()),n_unverifiable=int(g.unknown.sum()),support_pct=100*k.supported.mean(),strict_true_pct=100*k.verdict.eq('TRUE').mean(),unknown_pct=100*g.unknown.mean(),all_rows_lower_pct=100*g.supported.mean(),all_rows_upper_pct=100*(g.supported.sum()+g.unknown.sum()+g.verdict.eq('OPEN').sum())/len(g)))
pd.DataFrame(rows).to_csv(OUT/'composition_channels.csv',index=False)
summary['channels']=rows
for key in ['channel','claim_type','thesis_cluster','package','_scope']:
    t=d.groupby(key).agg(n=('claim_id','size'),unknown_n=('unknown','sum'),unknown_fraction=('unknown','mean'),supported_n=('supported','sum'))
    t.to_csv(OUT/f'composition_by_{key}.csv')

c=d[d.checkable].copy()
adjusted=[];cells=[]
def compare(frame,keys,label,min_per_channel=1):
    frame=frame.copy();frame['stratum']=frame[keys].astype(str).agg('|'.join,axis=1)
    tab=frame.groupby(['stratum','channel']).supported.agg(['size','mean']).unstack('channel')
    eligible=tab['size'].fillna(0).min(axis=1)>=min_per_channel
    sub=tab[eligible];weights=sub['size'].sum(axis=1);weights/=weights.sum()
    rates={ch:float((weights*sub['mean'][ch]).sum()) for ch in ['bravos','jikh']}
    for s in sub.index:
        cells.append(dict(specification=label,stratum=s,weight=weights[s],bravos_n=int(sub['size']['bravos'][s]),jikh_n=int(sub['size']['jikh'][s]),bravos_rate=sub['mean']['bravos'][s],jikh_rate=sub['mean']['jikh'][s]))
    adjusted.append(dict(specification=label,min_per_channel=min_per_channel,strata=len(sub),n_retained=int(sub['size'].sum().sum()),n_available=len(frame),bravos_pct=100*rates['bravos'],jikh_pct=100*rates['jikh'],gap_jikh_minus_bravos_pp=100*(rates['jikh']-rates['bravos'])))
    return sub,weights,frame
compare(c,['claim_type'],'claim_type')
compare(c,['thesis_cluster'],'thesis_cluster')
compare(c,['claim_type','thesis_cluster'],'type_and_topic')
compare(c,['claim_type','thesis_cluster','_scope'],'type_topic_capture_scope')
sub,w,frame=compare(c,['claim_type','thesis_cluster'],'type_topic_min5',5)
compare(c.drop_duplicates(['channel','fact_key']),['claim_type','thesis_cluster'],'one_vote_per_channel_fact_key')
pd.DataFrame(adjusted).to_csv(OUT/'composition_standardized.csv',index=False)
pd.DataFrame(cells).to_csv(OUT/'composition_cells.csv',index=False)
summary['standardized']=adjusted
# Cluster bootstrap retains all claims within sampled videos; fixed pooled stratum weights.
rng=np.random.default_rng(20260919);boot=[]
for _ in range(1500):
    rates={};valid=True
    for ch,g in frame.groupby('channel'):
        videos=g.video_id.unique();draw=rng.choice(videos,len(videos),replace=True)
        sample=pd.concat([g[g.video_id.eq(v)] for v in draw],ignore_index=True)
        means=sample.groupby('stratum').supported.mean().reindex(w.index)
        if means.isna().any():valid=False;break
        rates[ch]=(means*w).sum()
    if valid:boot.append(100*(rates['jikh']-rates['bravos']))
summary['cluster_bootstrap']={'spec':'type_topic_min5','draws':1500,'complete_draws':len(boot),'gap_95_percentile_interval_pp':np.quantile(boot,[.025,.975]).tolist(),'caveat':'Video clusters; common-support fixed weights. Incomplete-cell resamples omitted; descriptive stability, not a causal confidence statement.'}
# Reproducible uniform sample within the unverifiable bucket, selected BEFORE manual categories.
u=d[d.unknown].copy();u['hash']=u.claim_id.map(lambda s:hashlib.sha256(('review002:unverifiable:v1:'+s).encode()).hexdigest())
u.sort_values('hash').head(48)[['claim_id','channel','video_date','claim_type','thesis_cluster','claim_text','source_cited','package','note']].to_csv(OUT/'unverifiable_sample.csv',index=False)
summary['unverifiable_sampling']='48 lowest SHA256(review002:unverifiable:v1:claim_id) among all UNVERIFIABLE rows; simple deterministic uniform-rank sample, not chosen for drama.'
(OUT/'composition_summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
