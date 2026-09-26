"""Supplemental deterministic audit: citations, phrase overlap, omissions, selected call paths.
Read allowed data only. Writes phase_a. No claims of causal copying.
"""
from pathlib import Path
import sys,re,json,hashlib
from collections import defaultdict
import pandas as pd
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import analyze_corpus as a
O=a.OUT
# Separate a named institution mention from a citation-like sentence.
CITE=r'\b(?:according|says?|said|estimat\w*|report\w*|research|study|survey|chart from|quote|predict\w*|analogy|framework|points? out|noticed|credit to|warn\w*|projects?|projections?)\b'
cites=[]
for v in a.V:
 for sec,s in v['sentences']:
  if not re.search(CITE,s,re.I):continue
  for name,pat in a.SOURCES.items():
   if re.search(pat,s,re.I):cites.append({'file':v['file'],'channel':v['channel'],'date':v['date'],'timestamp':a.ts(sec),'source':name,'sentence':s})
pd.DataFrame(cites).to_csv(O/'citation_like_sentences.csv',index=False)
# Full cross-channel video-pair overlap, phrase windows counted once per video.
def shingle(v,n=10):
 words=re.findall(r'[a-z0-9]+',v['text'].lower()); return {' '.join(words[i:i+n]) for i in range(len(words)-n+1)}
S={v['file']:shingle(v) for v in a.V}; pairs=[];examples=[]
for x in [v for v in a.V if v['channel']=='bravos']:
 for y in [v for v in a.V if v['channel']=='jikh']:
  inter=S[x['file']]&S[y['file']];union=S[x['file']]|S[y['file']]
  pairs.append({'bravos_file':x['file'],'bravos_date':x['date'],'jikh_file':y['file'],'jikh_date':y['date'],'intersection_10grams':len(inter),'jaccard':len(inter)/len(union),'smaller_document_overlap':len(inter)/min(len(S[x['file']]),len(S[y['file']])),'jikh_minus_bravos_days':(pd.Timestamp(y['date'])-pd.Timestamp(x['date'])).days})
  if inter:
   for phrase in sorted(inter):examples.append({'bravos_file':x['file'],'jikh_file':y['file'],'phrase':phrase})
pd.DataFrame(pairs).sort_values('intersection_10grams',ascending=False).to_csv(O/'cross_channel_phrase_overlap.csv',index=False)
pd.DataFrame(examples).to_csv(O/'shared_10word_phrases.csv',index=False)
# Counts over hand-noticed proposition phrases; absence in selected corpus not a correction/failure by itself.
TRACK={
'negative_real_earnings_yield':r'real earnings yield|earnings yield.{0,80}negative',
'oil_80_threshold':r'\$80|80 a barrel|eighty',
'agriculture_stock_pitch':r'agricultural stocks|grain.{0,25}(?:play|bet)|agricultural ETF',
'2year_yield_over_fed':r'2.year yield|two.year yield',
'September2026_or_3month_window_phrase':r'September of 2026|September 2026|3.month (?:danger )?window',
'Fed_55_bubble_threshold':r'5\.5%',
'oil_deadline_April20':r'\bApril 20\b|mid.{0,3}to late April',
'July4_gold_reset':r'\bJuly (?:4|fourth)\b|\b4th of July\b',
'gold_revaluation':r'revalu\w* (?:the |its )?gold|repric\w* (?:the |its )?gold|gold.{0,35}(?:revalu|repric)',
'digital_control_grid':r'digital control grid|programmable money',
'100year_monetary_cycle':r'every hundred years|global monetary cycle'}
tracked=[]
for v in a.V:
 for label,pat in TRACK.items():
  n=a.count(pat,v['text'])
  tracked.append({'file':v['file'],'date':v['date'],'channel':v['channel'],'thesis_phrase':label,'mentions':n,'first_time':next((a.ts(sec) for sec,s in v['sentences'] if re.search(pat,s,re.I)),'')})
pd.DataFrame(tracked).to_csv(O/'tracked_thesis_phrases.csv',index=False)
# Specific calendar-dated call paths; contemporaneous value uses prior available trading-day observation.
scenarios=[('Jikh_oil_convergence_Apr20','jikh_2026-04-20_f353QO5Dgus.txt','brent','2026-04-20',[7,30,60]),('Bravos_oil_80_invalidator','bravos_2026-03-26_d2xewVN_eDE.txt','brent','2026-03-26',[30,60,90]),('Bravos_SP500_10to15_possible','bravos_2026-04-23_iq599kyAjVA.txt','SP500','2026-04-23',[30,60,90]),('Jikh_cash_position','jikh_2026-03-31_Dt45p4wuNow.txt','SP500','2026-03-31',[30,60,90]),('Bravos_hyperscaler_bullish_proxy','bravos_2026-07-23_QNFLN6IvB88.txt','NASDAQCOM','2026-07-23',[30])]
rows=[]
for label,file,series,date,horizons in scenarios:
 s=a.fb.brent_daily() if series=='brent' else a.fb.fred(series);d=pd.Timestamp(date);base=s.loc[:d-pd.Timedelta(days=1)]
 for h in horizons:
  e=d+pd.Timedelta(days=h);f=s.loc[:e]
  if e>s.index.max():continue
  path=s.loc[d:e]
  rows.append({'scenario':label,'file':file,'video_date':date,'series':series,'base_obs_date':str(base.index[-1].date()),'base':base.iloc[-1],'horizon_calendar_days':h,'end_obs_date':str(f.index[-1].date()),'end':f.iloc[-1],'return_pct':(f.iloc[-1]/base.iloc[-1]-1)*100,'path_min':path.min(),'path_max':path.max(),'path_max_return_pct':(path.max()/base.iloc[-1]-1)*100,'note':'Price change only. No total return, actual portfolio exposure, source-specific futures contract, causal inference or post-hoc horizon optimization.'})
pd.DataFrame(rows).to_csv(O/'selected_dated_scenario_price_paths.csv',index=False)
# Stratified mechanical-pair falsification sample; selected independently of actual content by deterministic hash.
P=pd.read_csv(O/'opposite_direction_candidate_pairs.csv'); D=pd.read_csv(O/'directional_predicates.csv').set_index('predicate_id')
P['sample_hash']=P.pair_id.map(lambda z:hashlib.sha256(('phase_a_v1:'+z).encode()).hexdigest())
sample=P.sort_values('sample_hash').groupby(['channel','family']).head(2).sort_values(['channel','family','a_date']);rows=[]
for r in sample.to_dict('records'):
 x=D.loc[r['a_predicate']];y=D.loc[r['b_predicate']]
 rows.append(r|{'a_file':x.file,'a_timestamp':x.timestamp,'a_statement':x.sentence,'b_file':y.file,'b_timestamp':y.timestamp,'b_statement':y.sentence})
pd.DataFrame(rows).to_csv(O/'contradiction_pair_sample.csv',index=False)
print('Citations',len(cites),'cross-channel video pairs',len(pairs),'shared10gram occurrences',len(examples),'sample',len(rows))
