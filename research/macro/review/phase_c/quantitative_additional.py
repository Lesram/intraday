from quantitative_replication import *
import step5_credit as credit

R,cpi=ar.monthly_returns();panel,_=rs.build_panel();cape=panel.cape.dropna()
old=credit.shiller_real_tr()
freal=(1+R.MKT)/(cpi/cpi.shift(1))-1
extended=pd.concat([old,freal.loc[freal.index>old.index[-1]]]).dropna()
rows=[];starts=[]
for method,returns in [('original_Shiller_stops_2023June',old),('Shiller_then_French_extension',extended),('French_market_only',freal.dropna())]:
    for threshold in [30.,35.,40.]:
        for h in [1,3,5]:
            values=[];selected_dates=[]
            for t in cape[cape>=threshold].index:
                w=returns.reindex(pd.date_range(t+pd.DateOffset(months=1),periods=h*12,freq='MS'))
                if not w.isna().any():
                    values.append(((1+w).prod()-1)*100);selected_dates.append(t)
                    starts.append(dict(method=method,threshold=threshold,horizon=h,start=str(t.date()),real_return=values[-1]))
            rows.append(dict(method=method,threshold=threshold,horizon=h,**summary(values),first_start=str(min(selected_dates).date()) if selected_dates else '',last_start=str(max(selected_dates).date()) if selected_dates else ''))
save(pd.DataFrame(rows),'cape_base_rate_freshness');save(pd.DataFrame(starts),'cape_base_rate_starts')

# Alternate expanding normalization: compare target and candidate in the SAME
# historical CDF available before each candidate, rather than today's target rank.
# This is an ex-post comparison to today's state, not an implementable past trade.
tgt=panel.ffill().loc[rs.TARGET_MONTH].copy();tgt['cape']=rs.CAPE_TARGET
dif=pd.DataFrame(index=panel.index,columns=panel.columns,dtype=float)
for c in panel:
    s=panel[c].dropna()
    for j,t in enumerate(s.index):
        if j>=120:
            past=s.iloc[:j]
            dif.loc[t,c]=abs((past<s.iloc[j]).mean()-(past<tgt[c]).mean())*100
score=100-dif.mean(axis=1);score=score[dif[rs.TIER_A_REQUIRED].notna().all(axis=1)]
out=[]
for gap,n,cutoff in [(24,12,'2023-12-01'),(60,8,'2021-07-01')]:
    for rank,t in enumerate(selected(score.loc[:cutoff],n,gap),1):
        out.append(dict(spec='both_vectors_in_candidate_prior_CDF',gap=gap,rank=rank,date=str(t.date()),score=score[t],dimensions=int(dif.loc[t].notna().sum())))
save(pd.DataFrame(out),'alternative_expanding_normalization')

# Assess the original PPI-percentile energy result under prior-history ranks,
# with strict complete horizons and nonoverlapping starts, and matched excess.
ppi=panel.ppi_yoy.dropna();exp=expanding(ppi.to_frame('p'))['p'];full=ppi.rank(pct=True)*100
rows=[]
for method,ranks in [('original_full_sample',full),('expanding_prior',exp)]:
    for h in [1,3,5]:
        candidates=[]
        for t in ranks[ranks>=75].index:
            a=strict_fwd(R,cpi,t,h,'Enrgy');b=strict_fwd(R,cpi,t,h,'MKT')
            if np.isfinite(a) and np.isfinite(b):candidates.append((t,a,b))
        for sample in ['all_overlapping','nonoverlap_chronological']:
            chosen=[]
            for row in candidates:
                if sample=='all_overlapping' or not chosen or row[0].to_period('M').ordinal-chosen[-1][0].to_period('M').ordinal>=h*12:chosen.append(row)
            excess=np.array([x[1]-x[2] for x in chosen]);er=np.array([x[1] for x in chosen]);mr=np.array([x[2] for x in chosen])
            rows.append(dict(method=method,horizon=h,sample=sample,**summary(excess),energy_median=np.median(er),market_median=np.median(mr),beat_market_pct=(excess>0).mean()*100))
save(pd.DataFrame(rows),'energy_tilt_sensitivity')
print(pd.DataFrame(rows).round(2).to_string(index=False))
print(pd.read_csv(OUT/'quantitative_cape_base_rate_freshness.csv').query('threshold==30 and horizon==5').round(3).to_string(index=False))
