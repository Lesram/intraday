"""Independent Phase C checks. Reads raw snapshot only; never original verdicts."""
from pathlib import Path
import sys,json,pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import factbase as f
OUT=Path(__file__).parent
D={}
def values(id,dates):
 s=f.fred(id)
 return [{'requested':d,'observation':str(f.asof_date(s,d).date()),'value':f.asof(s,d)} for d in dates]
D['sp500_july2025_may2026']=values('SP500',['2025-06-30','2025-07-01','2025-07-31','2026-05-28','2026-05-29'])
s=f.fred('SP500'); july=s['2025-07'];end=f.asof(s,'2026-05-28');D['sp500_gain_for_any_july_close']={'min_pct':float((end/july.max()-1)*100),'max_pct':float((end/july.min()-1)*100)}
D['yields']=values('DGS10',['2026-02-27','2026-04-06','2026-09-04'])+values('DGS30',['2026-09-04'])
s=f.fred('DGS30');prior=s[:'2026-09-04'];now=prior.iloc[-1];D['dgs30_above_current_last']={'now':now,'last_before2026_atleast_now':str(prior[:'2025'][prior[:'2025']>=now].index[-1].date())}
D['oil']=values('DCOILBRENTEU',['2026-02-27','2026-03-20','2026-03-23','2026-03-24','2026-03-25','2026-03-26'])
D['oil_wti']=values('DCOILWTICO',['2026-02-27','2026-03-20','2026-03-23','2026-03-24','2026-03-25','2026-03-26'])
D['yuan']=values('DEXCHUS',['2026-03-27','2026-03-31','2026-05-19','2026-05-20'])
D['dollar']=values('DTWEXBGS',['2025-12-31','2026-01-30','2026-02-27','2026-07-06'])
D['gold_monthly']={str(i.date()):float(x) for i,x in f.gold_monthly()['2025-12':'2026-06'].items()}
ratio=f.fred('FYOINT')/f.fred('FYFR')*100
D['netinterest_revenue']={str(i.date()):float(x) for i,x in ratio['1978':'1995'].items()};D['netinterest_revenue'].update({str(i.date()):float(x) for i,x in ratio['2023':].items()})
D['long_rates_1979_1985']={'DGS10_mean':float(f.fred('DGS10')['1979':'1985'].mean()),'DGS30_mean':float(f.fred('DGS30')['1979':'1985'].mean())}
mm=(f.fred('MMMFFAQ027S')/1000/f.fred('GDP')*100).dropna()
D['mmf_gdp']={str(i.date()):float(x) for i,x in mm.loc[['2000-10-01','2007-10-01','2019-10-01','2026-01-01','2026-04-01']].items()}
c=f.fred('CPIAUCSL');pc=1/c;chg=(c/c.shift(12)-1)*100
D['cpi']={'yoy_1991_2020_max':float(chg['1991':'2020'].max()),'yoy_2021_2026_max':float(chg['2021':'2026-05'].max()),'yoy_2026_may':float(chg.loc['2026-05-01']),'purchasing_power_loss_1991_may2026':float((pc.loc['2026-05-01']/pc.loc['1991-01-01']-1)*100)}
g=f.fred('GDPC1');yoy=(g/g.shift(4)-1)*100;qoq=((g/g.shift(1))**4-1)*100
D['real_gdp_2023_2025']={'yoy':{str(i.date()):float(x) for i,x in yoy['2023':'2025'].items()},'qoq_annualised':{str(i.date()):float(x) for i,x in qoq['2023':'2025'].items()}}
sh=f.shiller();erp=100*sh.Earnings/sh.SP500-f.fred('TB3MS');erp=erp.dropna()
D['trailing_ep_less_3m']={'latest_complete_before_video_date':str(erp[:'2026-08-08'].index[-1].date()),'latest_complete_value':float(erp[:'2026-08-08'].iloc[-1]),'2023_2025_min':float(erp['2023':'2025'].min()),'1989_1991_min':float(erp['1989':'1991'].min()),'1999_2001_min':float(erp['1999':'2001'].min()),'2006_2007_min':float(erp['2006':'2007'].min())}
D['historical_stock_declines']={}
for start,end in [('1929','1932'),('2007','2009')]:
 ss=sh.SP500[start:end];peak=ss.cummax();draw=ss/peak-1;t=draw.idxmin();D['historical_stock_declines'][start+'_'+end]={'peakdate':str(ss[:t].idxmax().date()),'troughdate':str(t.date()),'monthly_avg_drawdown_pct':float(draw.loc[t]*100)}
(OUT/'second_reader_data_checks.json').write_text(json.dumps(D,indent=2)+'\n');print(json.dumps(D,indent=2))
