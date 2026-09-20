"""Uniform60day operationalization; this is NOT original-horizon forecast accuracy."""
from pathlib import Path
import ast,json,sys,hashlib
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent));import prediction_checks as p
ROOT=p.ROOT;OUT=p.OUT
# Directions selected from raw wording before return calculations. Conditional rows retained/flagged.
DIRECTIONS={
'BR-20260326-03':-1,'BR-20260408-19':1,'BR-20260408-20':-1,'BR-20260423-19':1,'BR-20260423-20':1,'BR-20260427-29':1,'BR-20260501-27':1,'BR-20260529-27':1,'BR-20260615-29':1,'BR-20260618-17':1,'BR-20260618-22':1,
'AJ-20260316-28':1,'AJ-20260331-46':1,'AJ-20260504-48':-1,'AJ-20260520-35':1,'AJ-20260615-25':-1}
EXPLICIT={
'BR-20260326-26':'Conjunction across commodities/oil/CPI; not single-metric endpoint',
'BR-20260602-20':'Conjunction liquidity/tech; NasdaqComposite not Nasdaq100',
'BR-20260602-30':'Nasdaq100/SOX/AI basket not NasdaqComposite',
'BR-20260611-17':'Funding-flow/relative weakness, not outright price direction',
'BR-20260611-26':'Path and eventual peak, not endpoint direction',
'AJ-20260316-13':'Recession plus correction conjunction/path',
'AJ-20260331-39':'Multi-outcome menu with4legs',
'AJ-20260420-13':'Retailgasoline notBrent',
'AJ-20260420-18':'Inventory notprice','AJ-20260420-19':'Inventory notprice','AJ-20260420-28':'Futures-physical spread notspotprice','AJ-20260420-31':'Futures notspotprice','AJ-20260420-32':'Futures notspotprice','AJ-20260520-09':'Inventory notprice','AJ-20260520-10':'Inventory notprice','AJ-20260526-43':'Paywalled target, downsidequestion not necessarily directionprediction','AJ-20260605-37':'Inventory antecedent plus pricepath target','AJ-20260612-43':'Physicalshortages notprice','AJ-20260615-38':'Two-sided dollarconditional signal rule, no single sign'}
ns={'B':'bravos','J':'jikh','FRED':'FRED','EV':'EVENTS_2026'}
def val(n):
 if isinstance(n,ast.Name):return ns[n.id]
 if isinstance(n,ast.BinOp) and isinstance(n.op,ast.Add):return val(n.left)+val(n.right)
 return ast.literal_eval(n)
records=[]
for node in ast.walk(ast.parse((ROOT/'verify/out/PREDICTIONS/scoring.py').read_text())):
 if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='add':records.append([val(a) for a in node.args])
raw=p.raw_inventory().set_index('pred_id');audit=[];rows=[]
MAP={'SP500':'SP500','NASDAQ':'NASDAQCOM','BRENT':'DCOILBRENTEU','WTI':'DCOILWTICO','BTC':'CBBTCUSD','USD':'DTWEXBGS'}
def direction(r):return 1 if r>2 else -1 if r< -2 else 0
def point(s,d):
 a=s.loc[:d]; assert len(a) and (d-a.index[-1]).days<=7;return a.index[-1],float(a.iloc[-1])
for r in records:
 if not r[-1]:continue
 pid,key=r[0],r[-4];reason=''
 if pid not in raw.index:reason='Addedscorerrow absentrawledger'
 elif key not in MAP:reason='No exact mapped daily priceseries; monthly/sector/proxy omitted'
 elif pid not in DIRECTIONS:reason=EXPLICIT.get(pid,'Title has no explicitly stated price direction')
 audit.append({'pred_id':pid,'series_key':key,'included':not bool(reason),'exclusion_reason':reason})
 if reason:continue
 x=raw.loc[pid];d=pd.Timestamp(x.publish_date);end=d+pd.Timedelta(days=60)
 assert end<=p.ASOF
 s=p.fb.fred(MAP[key]);past_t,past=point(s,d-pd.Timedelta(days=60));origin_t,origin=point(s,d);end_t,last=point(s,end)
 actual_return=100*(last/origin-1);prior_return=100*(origin/past-1);actual=direction(actual_return);forecast=DIRECTIONS[pid];pers=direction(prior_return)
 rows.append({'pred_id':pid,'channel':x.channel,'series':MAP[key],'video_date':str(d.date()),'endpoint':str(end.date()),'origin_observed':str(origin_t.date()),'end_observed':str(end_t.date()),'prior_observed':str(past_t.date()),'return_pct':actual_return,'prior_return_pct':prior_return,'actual_direction':actual,'forecast_direction':forecast,'forecast_correct':forecast==actual,'always_up_correct':actual==1,'no_change_correct':actual==0,'persistence_direction':pers,'persistence_correct':pers==actual,'conditionality':x.conditionality,'basis':'Researcher60day endpoint; conditional antecedents not verified; no originalforecast accuracy claim'})
df=pd.DataFrame(rows);assert len(df)==len(DIRECTIONS)
summary=[]
for channel in ['all','bravos','jikh']:
 sub=df if channel=='all' else df[df.channel.eq(channel)]
 for method in ['forecast','always_up','no_change','persistence']:
  c=sub[method+'_correct'];f=sub.forecast_correct
  summary.append({'channel':channel,'method':method,'n':len(sub),'correct':int(c.sum()),'accuracy':float(c.mean()),'forecast_wins_method_loses':int((f&~c).sum()),'forecast_loses_method_wins':int((~f&c).sum())})
df.to_csv(OUT/'prediction_benchmark_rows.csv',index=False);pd.DataFrame(summary).to_csv(OUT/'prediction_benchmark_summary.csv',index=False);pd.DataFrame(audit).to_csv(OUT/'prediction_benchmark_selection.csv',index=False)
print(pd.DataFrame(summary).to_string(index=False))
print('selection',len(audit),'included',len(df),'unique_asset_origin',len(df[['series','video_date']].drop_duplicates()))
