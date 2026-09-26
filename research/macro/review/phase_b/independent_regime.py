"""Blind Phase B: transparent regime matching; writes ONLY its own review outputs.

No file under claims, analogs, verify/out or regime_* is read. All thresholds,
distances and episode selection use explanatory data, never forward outcomes.
"""
from pathlib import Path
import sys, json, hashlib, ast
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import factbase as fb

ASOF = pd.Timestamp('2026-09-18')
START = pd.Timestamp('1954-07-31')
N_EPISODES = 8
MIN_HISTORY = 120
SPACING = 60
FEATURES = ['equity_gdp_pct', 'cpi_yoy_pct', 'ip_yoy_pct', 'baa_aaa_pp',
            'curve_10y_3m_pp', 'real_bill_expost_pct']
SCALES = pd.Series([100, 3, 5, .5, 1.5, 3], index=FEATURES)


def monthly(s):
    """Preserve calendar gaps; never treat a row lag as a month lag."""
    s = s.copy()
    s.index = s.index.to_period('M')
    s = s.groupby(level=0).last()
    return s.reindex(pd.period_range(s.index.min(), s.index.max(), freq='M'))


def yoy(s):
    m = monthly(s)
    return (m / m.shift(12) - 1) * 100


def released(s, dates, quarterly=False):
    """Fixed approximate publication delay; not a historical-vintage database.

    Monthly reference month -> next month day 16. Quarter starting month ->
    fifth following month day 16. No backfill across unavailable values.
    """
    s = s.dropna().copy()
    p = s.index.to_period('M') if isinstance(s.index, pd.DatetimeIndex) else s.index
    releases = (p + (5 if quarterly else 1)).to_timestamp() + pd.Timedelta(days=15)
    frame = pd.DataFrame({'release': releases, 'value': s.values, 'reference': p.astype(str)})
    out = pd.merge_asof(pd.DataFrame({'decision': dates}), frame.sort_values('release'),
                        left_on='decision', right_on='release', direction='backward')
    out.index = dates
    return out


def select(scores, n=N_EPISODES):
    chosen = []
    for t in scores.sort_values(kind='stable').index:
        p = t.to_period('M').ordinal
        if all(abs(p - x.to_period('M').ordinal) >= SPACING for x in chosen):
            chosen.append(t)
            if len(chosen) == n:
                break
    return chosen


def forward_return(returns, t, years):
    p = t.to_period('M')
    expected = pd.period_range(p+1, p+12*years, freq='M')
    r = returns.reindex(expected)
    if len(r) != 12*years or r.isna().any():
        return np.nan
    return (np.prod(1+r)-1)*100


def summarize(values):
    s = pd.Series(values).dropna()
    if not len(s):
        return dict(n=0, median=np.nan, mean=np.nan, p10=np.nan, p90=np.nan,
                    minimum=np.nan, maximum=np.nan, negative_pct=np.nan)
    return dict(n=len(s), median=s.median(), mean=s.mean(), p10=s.quantile(.1),
                p90=s.quantile(.9), minimum=s.min(), maximum=s.max(), negative_pct=(s<0).mean()*100)


def main():
    OUT.mkdir(exist_ok=True)
    config = dict(asof=str(ASOF.date()), training_start=str(START.date()), minimum_history_months=MIN_HISTORY,
        dimensions=FEATURES, primary='equal-weight RMS difference in strictly prior expanding percentiles',
        fixed_scale_sensitivity=SCALES.to_dict(), selected_episodes=N_EPISODES,
        minimum_spacing_months=SPACING, outcome_horizons_years=[1,3,5],
        selection_cutoff='latest complete month with 60 months to asof; no outcomes enter ranking',
        lags='monthly reference+1m+15d; quarterly reference+5m+15d; approximate, not vintage data')
    (OUT/'design.json').write_text(json.dumps(config, indent=2))

    # Execute ONLY the AST of dashboard.yoy, avoiding its destructive top-level code.
    tree=ast.parse((ROOT/'scripts/dashboard.py').read_text())
    node=next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='yoy')
    env={'pd':pd}; exec(compile(ast.Module(body=[node],type_ignores=[]),'<dashboard.yoy isolated>','exec'),env)
    defects=[]
    for k in ['CPIAUCSL','CPILFESL']:
        raw=fb.fred(k); date_yoy=yoy(raw); positional=env['yoy'](raw)
        for t in raw.index[raw.index>='2025-09-01']:
            v=date_yoy.loc[t.to_period('M')]
            defects.append(dict(series=k,date=str(t.date()),calendar_yoy=v,
                dashboard_yoy=positional.loc[t],difference_pp=positional.loc[t]-v,
                row_lag_base_date=str(raw.index[raw.index.get_loc(t)-12].date()),
                correct_base_month=str(t.to_period('M')-12)))
    pd.DataFrame(defects).to_csv(OUT/'cpi_fix_verification.csv',index=False)
    assert 'pct_change' in ast.unparse(node), 'Source changed: re-audit claimed defect'
    synthetic=pd.Series(np.arange(100,126,dtype=float), index=pd.date_range('2020-01-01',periods=26,freq='MS'))
    synthetic=synthetic.drop(pd.Timestamp('2020-10-01'))
    assert np.isclose(yoy(synthetic).loc['2021-08'],(119/107-1)*100)
    assert pd.isna(yoy(synthetic).loc['2021-10'])
    assert not np.isclose(env['yoy'](synthetic).loc['2021-08-01'],yoy(synthetic).loc['2021-08'])

    gaprows=[]
    for k in ['CPIAUCSL','CPILFESL','INDPRO','UNRATE','BAA','AAA','GS10','TB3MS']:
        m=monthly(fb.fred(k))
        gaprows.append(dict(series=k,start=str(m.index.min()),end=str(m.index.max()),
                            missing_months=';'.join(m.index[m.isna()].astype(str))))
    pd.DataFrame(gaprows).to_csv(OUT/'calendar_gap_audit.csv',index=False)
    ranks=[]
    for k in ['BAMLH0A0HYM2','BAA10Y','DFII10']:
        s=fb.fred(k).loc[:ASOF]; v=s.iloc[-1]
        ranks.append(dict(series=k,last_date=str(s.index[-1].date()),value=v,n=len(s),
            history_start=str(s.index[0].date()),own_history_percentile=fb.percentile_rank(s,v),
            common_history_start='2023-09-19',
            common_history_percentile=fb.percentile_rank(s,v,'2023-09-19')))
    pd.DataFrame(ranks).to_csv(OUT/'percentile_history_audit.csv',index=False)

    dates=pd.date_range(START, ASOF, freq='ME').union(pd.DatetimeIndex([ASOF]))
    refs={}
    equity=(fb.fred('NCBEILQ027S')/1000/fb.fred('GDP')*100).dropna()
    raw_features={'equity_gdp_pct':equity,'cpi_yoy_pct':yoy(fb.fred('CPIAUCSL')),
                  'ip_yoy_pct':yoy(fb.fred('INDPRO')),
                  'baa_aaa_pp':fb.fred('BAA')-fb.fred('AAA'),
                  'curve_10y_3m_pp':fb.fred('GS10')-fb.fred('TB3MS')}
    x=pd.DataFrame(index=dates)
    for name,s in raw_features.items():
        r=released(s,dates,name=='equity_gdp_pct'); x[name]=r['value']; refs[name]=r
    # Real bill yield uses the same CPI and bill reference-month proxies.
    bill=released(fb.fred('TB3MS'),dates)
    x['real_bill_expost_pct']=bill['value']-x['cpi_yoy_pct']
    refs['real_bill_expost_pct']=bill
    x=x[FEATURES].dropna()
    # Rank against history strictly before each row; no current/future value enters its reference CDF.
    rank=pd.DataFrame(index=x.index,columns=FEATURES,dtype=float)
    for j,t in enumerate(x.index):
        if j>=MIN_HISTORY:
            rank.loc[t]=(x.iloc[:j].lt(x.loc[t]).mean()*100)
    target=x.loc[ASOF]; target_rank=rank.loc[ASOF]
    cutoff=ASOF-pd.DateOffset(years=5)
    eligible=rank.dropna().loc[:cutoff]
    primary=np.sqrt(((eligible-target_rank)**2).mean(axis=1))
    fixed=np.sqrt((((x.loc[eligible.index]-target)/SCALES)**2).mean(axis=1))
    # Diagnostic only: deliberately look-ahead-contaminated rank as comparison.
    full_rank=x.rank(pct=True)*100
    full=np.sqrt(((full_rank.loc[eligible.index]-full_rank.loc[ASOF])**2).mean(axis=1))
    omit=np.sqrt(((eligible.drop(columns='equity_gdp_pct')-target_rank.drop('equity_gdp_pct'))**2).mean(axis=1))
    scores=pd.DataFrame({'expanding_primary':primary,'fixed_economic_scale':fixed,
                         'full_sample_diagnostic':full,'omit_valuation_sensitivity':omit})
    x.to_csv(OUT/'features_history.csv',index_label='decision_date')
    rank.to_csv(OUT/'expanding_percentiles.csv',index_label='decision_date')
    scores.to_csv(OUT/'all_candidate_distances.csv',index_label='decision_date')
    now=[]
    for name in FEATURES:
        r=refs[name].loc[ASOF]
        now.append(dict(indicator=name,value=target[name],expanding_percentile=target_rank[name],
            percentile_history_start=str(x.index.min().date()),percentile_n=len(x)-1,
            reference_month=r['reference'],assumed_available=str(r['release'].date())))
    pd.DataFrame(now).to_csv(OUT/'current_state.csv',index=False)

    allselections=[]; selected_by={}
    for spec in scores:
        chosen=select(scores[spec]); selected_by[spec]=chosen
        for order,t in enumerate(chosen,1):
            allselections.append(dict(specification=spec,nearest_rank=order,date=str(t.date()),distance=scores.loc[t,spec],**x.loc[t].to_dict()))
        for a,b in zip(sorted(chosen)[:-1],sorted(chosen)[1:]):
            assert b.to_period('M').ordinal-a.to_period('M').ordinal>=SPACING
    pd.DataFrame(allselections).to_csv(OUT/'selected_episodes.csv',index=False)

    ff=fb._ff_block(str(ROOT/'review/inputs/F-F_Research_Data_Factors.csv'),None,None)
    ind=fb._ff_block(str(ROOT/'review/inputs/12_Industry_Portfolios.csv'),None,None)
    returns=pd.DataFrame({'US_market_total':(ff['Mkt-RF']+ff['RF'])/100,'T_bill_total':ff['RF']/100})
    returns=returns.join(ind.add_prefix('sector_')/100)
    returns.index=returns.index.to_period('M')
    # Gold is explicitly spot price return, excluding storage/insurance/trading costs.
    gold=monthly(fb.gold_monthly()); returns=returns.join(gold.pct_change(fill_method=None).rename('Gold_spot_price'),how='outer')
    cpi=monthly(fb.fred('CPIAUCSL'))
    episode_rows=[]; base_rows=[]
    for spec, chosen in selected_by.items():
        for t in chosen:
            p=t.to_period('M')
            for h in [1,3,5]:
                inf=cpi.get(p+12*h,np.nan)/cpi.get(p,np.nan)
                for asset in returns:
                    nom=forward_return(returns[asset],t,h)
                    real=((1+nom/100)/inf-1)*100 if np.isfinite(nom) and np.isfinite(inf) else np.nan
                    episode_rows.append(dict(specification=spec,date=str(t.date()),horizon_years=h,
                        asset=asset,nominal_cumulative_pct=nom,real_cumulative_pct=real,
                        endpoint=str(p+12*h),return_kind='spot price (monthly-average marks)' if asset=='Gold_spot_price' else 'total return'))
    episodes=pd.DataFrame(episode_rows); episodes.to_csv(OUT/'episode_returns.csv',index=False)
    # Unconditional monthly starts: same candidate calendar and full return coverage per asset/horizon.
    for t in eligible.index:
        p=t.to_period('M')
        for h in [1,3,5]:
            inf=cpi.get(p+12*h,np.nan)/cpi.get(p,np.nan)
            for asset in returns:
                nom=forward_return(returns[asset],t,h)
                real=((1+nom/100)/inf-1)*100 if np.isfinite(nom) and np.isfinite(inf) else np.nan
                base_rows.append(dict(date=str(t.date()),horizon_years=h,asset=asset,
                    nominal_cumulative_pct=nom,real_cumulative_pct=real))
    bases=pd.DataFrame(base_rows); bases.to_csv(OUT/'unconditional_returns.csv',index=False)
    summaries=[]
    for spec in selected_by:
        for asset in returns:
            for h in [1,3,5]:
                e=episodes.query('specification==@spec and asset==@asset and horizon_years==@h')
                b=bases.query('asset==@asset and horizon_years==@h')
                for metric in ['nominal_cumulative_pct','real_cumulative_pct']:
                    es=summarize(e[metric]); bs=summarize(b[metric])
                    summaries.append(dict(specification=spec,asset=asset,horizon_years=h,metric=metric,
                        **{'episode_'+k:v for k,v in es.items()}, **{'unconditional_'+k:v for k,v in bs.items()},
                        median_excess_pp=es['median']-bs['median']))
    pd.DataFrame(summaries).to_csv(OUT/'return_comparisons.csv',index=False)

    # Industry returns versus the broad market for SAME dates, not price-only claims.
    relative=[]
    e=episodes.query("specification=='expanding_primary'")
    for h in [1,3,5]:
        table=e.query('horizon_years==@h').pivot(index='date',columns='asset',values='nominal_cumulative_pct')
        for asset in ind.add_prefix('sector_').columns:
            v=table[asset]-table['US_market_total']
            relative.append(dict(horizon_years=h,asset=asset,n=v.notna().sum(),
                median_excess_vs_market_pp=v.median(),beat_market_pct=(v.dropna()>0).mean()*100))
    pd.DataFrame(relative).to_csv(OUT/'sector_relative_returns.csv',index=False)
    # Pairwise observed correlations describe redundancy, not statistical independence.
    x.corr().to_csv(OUT/'feature_correlations.csv',index_label='indicator')
    provenance=[]
    paths=[ROOT/'data/raw/fred_bundle_2026-09-19.json',ROOT/'data/raw/fred_bundle2_2026-09-19.json',
           ROOT/'data/raw/gold-prices_main_data_monthly.csv',ROOT/'scripts/factbase.py',ROOT/'scripts/dashboard.py',
           ROOT/'review/inputs/F-F_Research_Data_Factors.csv',ROOT/'review/inputs/12_Industry_Portfolios.csv']
    for p in paths:
        provenance.append(dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size))
    (OUT/'input_hashes.json').write_text(json.dumps(provenance,indent=2))
    (OUT/'validation.json').write_text(json.dumps(dict(calendar_gap_test='PASS',missing_denominator_test='PASS',
        row_lag_mismatch_demonstrated='PASS',independent_episode_spacing_test='PASS',
        no_future_history_in_expanding_cdf='construction: x.iloc[:j]',
        ff_latest_month=str(ff.index.max().date()),industry_latest_month=str(ind.index.max().date()),
        primary_complete_episode_counts=episodes.query("specification=='expanding_primary' and asset=='US_market_total'").groupby('horizon_years')['nominal_cumulative_pct'].count().to_dict(),
        missing_bond_total_return='No suitable total-return series in allowed raw inputs; yield is not a bond return.'),indent=2))
    print(pd.DataFrame(now).to_string(index=False))
    print(pd.DataFrame(allselections)[['specification','nearest_rank','date','distance']].to_string(index=False))


if __name__=='__main__':
    main()
