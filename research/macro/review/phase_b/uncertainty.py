"""Descriptive uncertainty checks for Phase B; no thresholds are fitted."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

P=Path(__file__).resolve().parent
e=pd.read_csv(P/'episode_returns.csv')
b=pd.read_csv(P/'unconditional_returns.csv')
s=pd.read_csv(P/'selected_episodes.csv')
rng=np.random.default_rng(20260919)
rows=[]
for h in [1,3,5]:
    for metric in ['nominal_cumulative_pct','real_cumulative_pct']:
        base=b[(b.asset=='US_market_total')&(b.horizon_years==h)].dropna(subset=[metric])
        periods=pd.to_datetime(base.date).dt.to_period('M').astype('int64').to_numpy()
        values=base[metric].to_numpy()
        observed=e[(e.specification=='expanding_primary')&(e.asset=='US_market_total')&(e.horizon_years==h)][metric].dropna()
        simulated=[]
        for _ in range(5000):
            selected=[]
            for j in rng.permutation(len(base)):
                if all(abs(periods[j]-periods[k])>=60 for k in selected):
                    selected.append(j)
                    if len(selected)==len(observed):
                        break
            if len(selected)==len(observed):
                simulated.append(np.median(values[selected]))
        simulated=np.array(simulated)
        lower=(simulated<=observed.median()).mean()
        rows.append(dict(asset='US_market_total',horizon_years=h,metric=metric,
            selected_n=len(observed),observed_median=observed.median(),
            simulated_matched_size_nonoverlap_sets=len(simulated),baseline_median_p025=np.quantile(simulated,.025),
            baseline_median_p975=np.quantile(simulated,.975),observed_percentile_in_baseline_medians=lower*100,
            descriptive_two_sided_tail_fraction=min(1,2*min(lower,1-lower))))
pd.DataFrame(rows).to_csv(P/'nonoverlap_baseline_uncertainty.csv',index=False)

subsets=[]
chosen=s[s.specification=='expanding_primary']
for name,dates in [('nearest_four',set(chosen[chosen.nearest_rank<=4].date)),
                  ('free_float_gold_1971plus',set(chosen[chosen.date>='1971-08-31'].date))]:
    for asset in ['US_market_total','T_bill_total','Gold_spot_price']:
        for h in [1,3,5]:
            for metric in ['nominal_cumulative_pct','real_cumulative_pct']:
                v=e[(e.specification=='expanding_primary')&(e.asset==asset)&(e.horizon_years==h)&e.date.isin(dates)][metric].dropna()
                subsets.append(dict(subset=name,asset=asset,horizon_years=h,metric=metric,n=len(v),
                    median=v.median(),minimum=v.min(),maximum=v.max(),negative_pct=(v<0).mean()*100))
pd.DataFrame(subsets).to_csv(P/'small_sample_and_gold_sensitivity.csv',index=False)
print(pd.DataFrame(rows).round(3).to_string(index=False))
