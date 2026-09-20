"""Independent prediction eligibility and limited outcome recheck; old labels joined only after lock.
Reproduce --check without changing frozen adjudications; --compare uses the existing lock.
"""
from pathlib import Path
import sys, json, hashlib, csv, argparse
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'));import factbase as fb
ASOF=pd.Timestamp('2026-09-18')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def raw_inventory():
 rows=[]
 for p in sorted((ROOT/'claims/predictions').glob('*.md')):
  for line in p.read_text().splitlines():
   c=[v.strip() for v in line.strip().strip('|').split('|')]
   if len(c)==8 and c[0].startswith(('BR-','AJ-')):
    r=dict(zip(['pred_id','timestamp','statement','object','direction','horizon','conditionality','legacy_proposed_scoring'],c))
    r.update(channel=p.name.split('_')[0],publish_date=p.name.split('_')[1],raw_file=str(p.relative_to(ROOT)),sample_hash=hashlib.sha256(('review002:'+c[0]).encode()).hexdigest());rows.append(r)
 return pd.DataFrame(rows)
# Supplement chosen by raw wording (dates/durations and named event targets), before old scores.
SUPPLEMENT={
'BR-20260326-08':('MISS','2026-04-10','Explicit next March CPI print target 3.5–4%; calendar YoY below3.5 in both supplied SA and NSA histories. Revised source reconstruction, not first-release audit.'),
'BR-20260420-21':('PENDING','2027-04-20','Explicit6–12month window has not ended; sizable correction lacks a numerical threshold.'),
'BR-20260423-21':('PENDING','2026-12-31','Possibly by year-end; deadline has not matured and correction magnitude is unspecified.'),
'BR-20260501-28':('PENDING','2026-12-31','Rate-hike-by-year-end claim must remain open.'),
'BR-20260507-16':('PENDING','2027-05-07','At least another year without earnings rollover has not elapsed.'),
'BR-20260511-21':('PENDING','2026-12-31','Explicit end2026 hike deadline remains open.'),
'BR-20260513-25':('PENDING','2028-12-31','Until2028 valuation/profitability narrative cannot fail by Sep2026; exact2028 endpoint unspecified.'),
'BR-20260529-10':('MISS','2026-06-30','Relayed Fed growth estimate~4% forQ2; revised GDPC1 level-derived annualized growth1.4837%, well below target. Not established as original personal forecast; initial release not audited.'),
'BR-20260602-19':('PENDING','2026-12-31','Relayed futures pricing for no rate hike untilDecember is not a mature personal prediction.'),
'BR-20260611-10':('PENDING','2026-12-31','Calendar2026 IPO proceeds window remains open.'),
'BR-20260615-16':('UNSCORABLE','','Hypothetically still could play out describes a remaining model window, not a directional recession forecast.'),
'BR-20260615-23':('PENDING','2026-09-30','Explicit throughSeptember no-recession/steepening conjunction not fully matured.'),
'BR-20260615-25':('PENDING','2027-06-30','Growth through mid2027 deadline remains open.'),
'AJ-20260316-30':('CANNOT_VERIFY','2026-04-11','Relayed officials war-duration claim requires dated primary military/diplomatic evidence; market prices cannot settle it.'),
'AJ-20260331-41':('UNSCORABLE','','Conditional closure duration does not supply a finite subsequent credit-crisis deadline or operational crisis threshold.'),
'AJ-20260407-04':('UNSCORABLE','2026-04-28','A global breaking point has no operational metric, despite a2–3week condition.'),
'AJ-20260420-19':('CANNOT_VERIFY','2026-04-30','Global supplies run out requires a defined inventory universe and dated physical supply data; spot prices are not inventory levels.'),
'AJ-20260420-31':('UNSCORABLE','2026-04-27','Relayed price suppression and blow-up narrative lacks a price threshold and independently verified suppression mechanism.'),
'AJ-20260420-50':('UNSCORABLE','2026-05-04','Explicit possibility offered as alternative scenario; no probability or endorsed directional forecast.'),
'AJ-20260504-45':('PENDING','2026-11-04','Could take another6months is a conditional duration bound; not elapsed.'),
'AJ-20260520-09':('PENDING','2026-09-30','September inventory-floor window not closed; June stress subclaim lacks specified inventory threshold and primary data.'),
'AJ-20260520-10':('CANNOT_VERIFY','2026-07-04','Relayed critical US inventory level never quantified; requires stock data, not WTI.'),
'AJ-20260526-25':('CANNOT_VERIFY','2026-06-30','Quoted Japanese-policy conditional forecast; frozen Japanese rate series is a proxy, and qualifying Middle-East condition/policy decision not independently established.'),
'AJ-20260605-37':('CANNOT_VERIFY','2026-06-26','2–3weeks explicitly dates critical inventories;150–160oil follows conditional on that event. Neither specified inventory threshold nor primary inventory evidence available. Spot-path check is only a diagnostic, not an unconditional MISS.'),
'AJ-20260612-45':('PENDING','2029-06-12','Gold3000 target permits1–3years; cannot fail inSeptember2026.'),
'AJ-20260615-26':('CANNOT_VERIFY','2026-06-17','Explicit unchanged Fed decision; EFFR is flat3.63 before/after but is not official target decision documentation. No independent dated FOMC outcome evidence used.'),
'AJ-20260615-30':('CANNOT_VERIFY','2026-09-03','SPR exhaustion in<80days needs EIA SPR stock path. No supplied SPR series; WTI or yields cannot substitute.'),
'AJ-20260615-36':('CANNOT_VERIFY','2026-06-18','Conditional press-conference wording and next-day reaction require transcript, event timestamp, and verified antecedent; daily index movement alone is insufficient.'),
}
def outcome_evidence():
 c=fb.fred('CPIAUCSL');n=pd.read_csv(ROOT/'data/raw/cpi-us_main_data_cpiai.csv',parse_dates=['Date']).set_index('Date')['Index'];g=fb.fred('GDPC1')
 evidence={'CPI_March2026_SA_calendar_yoy':100*(c.loc['2026-03-01']/c.loc['2025-03-01']-1),'CPI_March2026_NSA_calendar_yoy':100*(n.loc['2026-03-01']/n.loc['2025-03-01']-1),'GDP_Q2_2026_SAAR':100*((g.loc['2026-04-01']/g.loc['2026-01-01'])**4-1)}
 for sid in ['DCOILWTICO','DCOILBRENTEU']:
  s=fb.fred(sid).loc['2026-06-05':'2026-06-26'];evidence[sid+'_Jun5_26_max']=float(s.max());evidence[sid+'_Jun26']=float(s.iloc[-1])
 return evidence

def lock():
 raw=raw_inventory();assert len(raw)==288 and raw.pred_id.is_unique
 selected=raw.sort_values('sample_hash').groupby('channel',sort=True).head(16).copy();selected['cohort']='deterministic16_per_channel'
 supplement=raw[raw.pred_id.isin(SUPPLEMENT)&~raw.pred_id.isin(selected.pred_id)].copy();supplement['cohort']='dated_endpoint_diagnostic_supplement'
 df=pd.concat([selected,supplement],ignore_index=True)
 df['independent_label']='UNSCORABLE';df['deadline']='';df['independent_reason']='No unambiguous finite speaker-specified endpoint; inferred ledger horizon is not a forecast deadline. Conditional, scenario or asset-basket wording may add further ambiguity.'
 for pid,(label,deadline,reason) in SUPPLEMENT.items():df.loc[df.pred_id.eq(pid),['independent_label','deadline','independent_reason']]=[label,deadline,reason]
 df.loc[df.pred_id.eq('BR-20260611-24'),['independent_label','deadline','independent_reason']]=['PENDING','2026-12-31','Relayed futures probability by end2026; not mature or a calibrated personal probability.']
 df.loc[df.pred_id.eq('AJ-20260504-28'),['independent_label','deadline','independent_reason']]=['PENDING','2032-05-04','Relayed5–6year munitions-restocking estimate has not matured; no current outcome.']
 df['attribution']=df.apply(lambda r:'relayed_or_scenario' if any(w in (r.statement+' '+r.conditionality).lower() for w in ['relayed','cnn:','jpmorgan','estimate','scenario','outcome 1','outcome 2','clip','futures']) else 'speaker_or_ambiguous',axis=1)
 df['paired_null_eligible']=False
 df['paired_exclusion_reason']='No mature verified direction-only single-metric forecast; explicit numeric targets excluded by preregistration.'
 df.to_csv(OUT/'prediction_independent_locked.csv',index=False)
 raw[['pred_id','channel','publish_date','timestamp','horizon','raw_file','sample_hash']].to_csv(OUT/'prediction_raw_inventory.csv',index=False)
 selected.to_csv(OUT/'prediction_blind_sample.csv',index=False)
 evidence=outcome_evidence();(OUT/'prediction_outcome_evidence.json').write_text(json.dumps(evidence,indent=2))
 receipt={'lock_sha256':sha(OUT/'prediction_independent_locked.csv'),'preregistration_sha256':sha(OUT/'prediction_preregistration.json'),'old_outcomes_read_at_lock':False,'source_inventory':288,'primary_sample':32,'supplement':len(supplement),'labels':df.independent_label.value_counts().to_dict(),'source_hashes':{str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'data/raw/fred_bundle_2026-09-19.json',ROOT/'data/raw/fred_bundle2_2026-09-19.json',ROOT/'data/raw/cpi-us_main_data_cpiai.csv']}}
 (OUT/'prediction_lock_receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))

def check():
 receipt=json.loads((OUT/'prediction_lock_receipt.json').read_text());assert receipt['lock_sha256']==sha(OUT/'prediction_independent_locked.csv')
 df=pd.read_csv(OUT/'prediction_independent_locked.csv');assert len(df)>=32 and df.pred_id.is_unique
 raw=raw_inventory(); assert len(raw)==288 and set(df.pred_id)<=set(raw.pred_id)
 assert set(df.independent_label)<={'HIT','MISS','PARTIAL','UNSCORABLE','PENDING','PENDING_CONDITION','CANNOT_VERIFY'}
 primary=df[df.cohort.eq('deterministic16_per_channel')];assert primary.groupby('channel').size().eq(16).all()
 expected=set(raw.sort_values('sample_hash').groupby('channel').head(16).pred_id);assert set(primary.pred_id)==expected
 pending=pd.to_datetime(df.loc[df.independent_label.eq('PENDING'),'deadline']);assert (pending>ASOF).all()
 e=outcome_evidence();assert e['CPI_March2026_SA_calendar_yoy']<3.5 and e['CPI_March2026_NSA_calendar_yoy']<3.5 and e['GDP_Q2_2026_SAAR']<2
 pd.DataFrame(columns=['pred_id','actual_direction','forecast_hit','no_change_hit','persistence_hit']).to_csv(OUT/'prediction_paired_nulls.csv',index=False)
 result={'checks_passed':8,'checks_failed':0,'independent_rows':len(df),'paired_null_n':0,'reason':'No eligible mature verified direction-only single-metric rows in declared sample and supplement. Undefined accuracy is not0%.','outcome_evidence':e}
 (OUT/'prediction_check_results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

def compare():
 receipt=json.loads((OUT/'prediction_lock_receipt.json').read_text())
 assert receipt['lock_sha256']==sha(OUT/'prediction_independent_locked.csv')
 own=pd.read_csv(OUT/'prediction_independent_locked.csv').fillna('')
 old=pd.read_csv(ROOT/'verify/out/PREDICTIONS/predictions_scored.csv').fillna('')
 assert len(old)==293 and old.pred_id.is_unique
 # Explicitly post-lock primary-source verification; retain original judgment columns.
 sept='https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm'
 june='https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm'
 april='https://www.federalreserve.gov/newsevents/pressreleases/monetary20260429a.htm'
 changes={
 'BR-20260501-28':('HIT',sept,'A hike by year-end is an event-by-deadline claim: Sep16 hike already fulfills it; it need not wait until Dec31.'),
 'BR-20260511-21':('HIT',sept,'Sep16 hike fulfills the explicit year-end event deadline; two repeated calls are not independent successes.'),
 'BR-20260611-24':('HIT',sept,'Event outcome matches the relayed year-end hike direction, not independent verification of historical market probability or personal forecasting skill.'),
 'BR-20260602-19':('MISS',sept,'Sep16 hike breaches no hike before December. This is an outcome comparison for relayed pricing, not evidence that contemporaneous pricing was misquoted.'),
 'AJ-20260615-26':('HIT',june,'Official June17 statement maintained the target range at3.50–3.75%; April29 prior decision confirms same baseline.')}
 own['final_label']=own.independent_label;own['post_lock_primary_source']='';own['post_lock_amendment']=''
 amendments=[]
 for pid,(lab,url,reason) in changes.items():
  prior=own.loc[own.pred_id.eq(pid),'independent_label'].iloc[0]
  own.loc[own.pred_id.eq(pid),['final_label','post_lock_primary_source','post_lock_amendment']]=[lab,url,reason]
  amendments.append(dict(pred_id=pid,locked_label=prior,final_label=lab,primary_url=url,reason=reason))
 pd.DataFrame(amendments).to_csv(OUT/'prediction_post_lock_amendments.csv',index=False)
 paired=pd.DataFrame([dict(pred_id='AJ-20260615-26',actual_direction='flat',forecast_direction='flat',nochange_direction='flat',persistence_direction='flat',forecast_hit=True,no_change_hit=True,persistence_hit=True,baseline_range='3.50–3.75',outcome_range='3.50–3.75',origin='2026-06-15',endpoint='2026-06-17',prior_window_start='2026-05-16',source=april+'; '+june)])
 paired.to_csv(OUT/'prediction_paired_nulls_post_verification.csv',index=False)
 own['post_verified_paired_eligible']=own.pred_id.eq('AJ-20260615-26')
 cols=['pred_id','verdict','measured_outcome','horizon','source','null_nochange','null_persistence']
 joined=own.merge(old[cols],on='pred_id',how='left',suffixes=('','_legacy'),validate='one_to_one')
 assert len(joined)==60 and joined.verdict.ne('').all()
 joined.to_csv(OUT/'prediction_rescore.csv',index=False)
 pd.crosstab(joined.verdict,joined.final_label).to_csv(OUT/'prediction_label_comparison.csv')
 pd.crosstab(joined.cohort,joined.final_label).to_csv(OUT/'prediction_cohort_counts.csv')
 raw=raw_inventory();added=old[~old.pred_id.isin(raw.pred_id)]
 added[['pred_id','channel','video_date','verdict']].to_csv(OUT/'prediction_added_titles.csv',index=False)
 inv=[];receipts=[]
 for pkg in ['V1','V3','V5','V8_9']:
  folder=ROOT/'verify/out'/pkg;csvp=folder/'verdicts.csv';d=pd.read_csv(csvp)
  inv.append(dict(package=pkg,rows=len(d),unique_claim_ids=d.claim_id.nunique(),unique_fact_keys=d.fact_key.nunique(),sha256=sha(csvp),columns=';'.join(d.columns),verdict_counts=json.dumps(d.verdict.value_counts().to_dict(),sort_keys=True)))
  for name in ['SUMMARY.md','facts.md']:
   p=folder/name;receipts.append(dict(path=str(p.relative_to(ROOT)),lines=len(p.read_text().splitlines()),sha256=sha(p),read_mode='full semantic reading, all lines',reader='blind_events'))
 for name in ['SCORECARD.md','scoring.py']:
  p=ROOT/'verify/out/PREDICTIONS'/name;receipts.append(dict(path=str(p.relative_to(ROOT)),lines=len(p.read_text().splitlines()),sha256=sha(p),read_mode='full semantic reading, all lines after blind lock',reader='blind_events'))
 pd.DataFrame(inv).to_csv(OUT/'prediction_package_inventory.csv',index=False)
 (OUT/'prediction_reading_receipts.json').write_text(json.dumps(receipts,indent=2))
 result={'final_labels':own.final_label.value_counts().to_dict(),'locked_labels':own.independent_label.value_counts().to_dict(),'post_lock_primary_amendments':len(changes),'strict_paired_n_before_verification':0,'strict_paired_n_after_verification':1,'strict_paired_forecast_hits':1,'strict_paired_nochange_hits':1,'strict_paired_persistence_hits':1,'legacy_all_counts':old.verdict.value_counts().to_dict(),'legacy_raw_rows':len(raw),'legacy_scored_rows':len(old),'legacy_added_title_rows':len(added),'validation_checks_passed':6,'validation_checks_failed':0}
 (OUT/'prediction_comparison_summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--lock',action='store_true');p.add_argument('--check',action='store_true');p.add_argument('--compare',action='store_true');a=p.parse_args()
 if a.lock:
  assert not (OUT/'prediction_lock_receipt.json').exists(),'Do not overwrite independent lock after seeing legacy scores';lock()
 if a.check:check()
 if a.compare:compare()
