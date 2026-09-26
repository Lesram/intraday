"""Blind corpus analysis. Reads corpus/** and raw data via factbase only; writes phase_a.
Run PYTHONDONTWRITEBYTECODE=1 python review/phase_a/analyze_corpus.py.
Lexical counts describe speech, not calibrated confidence. Contradiction candidates require adjudication.
"""
from pathlib import Path
from collections import Counter,defaultdict
import re,csv,json,hashlib,sys,itertools
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
import factbase as fb
THEMES={
'oil_energy':r'\b(?:oil|brent|crude|gasoline|energy prices|hormuz)\b',
'inflation':r'\b(?:inflation|inflationary|deflation|cpi|consumer price)\b',
'recession_labor':r'\b(?:recession|unemployment|jobless|layoffs|labor market|labour market|jobs report)\b',
'debt_credit':r'\b(?:debt|deficit|credit|default|bankrupt\w*)\b',
'dollar_fx':r'\b(?:dollar|currency|currencies|yen|yuan|renminbi)\b',
'gold_silver':r'\b(?:gold|silver|precious metal\w*)\b',
'ai_tech':r'\b(?:ai|artificial intelligence|nvidia|tech|technology|data centers?)\b',
'valuation_bubble':r'\b(?:bubble|valuation\w*|overvalued|undervalued|price.to.earnings|cape)\b',
'liquidity_rates':r'\b(?:liquidity|interest rates?|rate cuts?|rate hikes?|federal reserve|quantitative easing|quantitative tightening)\b',
'china_deglobalization':r'\b(?:china|chinese|tariffs?|deglobal\w*|brics)\b',
'rotation_manufacturing':r'\b(?:rotation|manufacturing|pmi|commodities|commodity|small caps?|industrial\w*)\b',
'crypto':r'\b(?:bitcoin|crypto\w*|stablecoins?)\b',
'digital_control':r'\b(?:digital (?:id|identity|control)|cbdc\w*|programmable money|control grid|surveillance|biometric\w*)\b',
'housing':r'\b(?:housing|mortgage\w*|real estate|home prices)\b'}
MARKERS={
'certainty':r'\b(?:will|guaranteed|certainly|definitely|inevitable|inevitably|must)\b',
'hedge':r'\b(?:could|may|might|possibly|perhaps|probably|potentially|likely|unlikely)\b',
'urgency':r'\b(?:urgent|urgently|emergency|imminent|immediately|crisis|crash|collapse|warning|dangerous|danger|last chance|once in a lifetime|never before|about to)\b',
'correction':r'\b(?:i was wrong|we were wrong|i got it wrong|we got it wrong|my mistake|our mistake|i stand corrected|we stand corrected|changed my mind|changed our mind)\b'}
SOURCES={
'Simon_Dixon':r'\bsimon dixon\b','Ed_Zitron':r'\bed (?:zitron|zitran|citron)\b','Jeff_Currie':r'\bjeff (?:currie|curry)\b','Northstar':r'\bnorthstar\b','Azure_Capital':r'\bazure capital\b','BCA_Research':r'\bbca(?: research)?\b','CME':r'\b(?:cme|fedwatch)\b','Luke_Gromen':r'\b(?:(?:luke|l)\s+(?:groman|gromen|growman|grman|gman|grumman|roman|crowman)|fftt)\b','Catherine_Austin_Fitts':r'\baustin (?:fitts|fitz|fits)\b','Chris_Martenson':r'\bchris (?:martenson|martinson)\b','Benjamin_Cowen':r'\bbenjamin (?:cowen|cowan)\b','Richard_Werner':r'\brichard werner\b','NBER':r'\b(?:nber|national bureau of economic research)\b','Gartner':r'\bgartner\b','Moody_Zandi':r'\b(?:moody\w*|mark zandi)\b','ECB':r'\b(?:european central bank|ecb)\b','BIS':r'\b(?:bank (?:for|of) international settlements|bis)\b','Our_World_in_Data':r'\bour world in data\b','Fed':r'\b(?:federal reserve|the fed|powell|fomc)\b','BLS':r'\b(?:bureau of labor statistics|bls)\b','BEA':r'\b(?:bureau of economic analysis|bea)\b',
'ISM':r'\b(?:ism|institute for supply management)\b','CBO':r'\b(?:congressional budget office|cbo)\b','IMF':r'\b(?:imf|international monetary fund)\b',
'Goldman_Sachs':r'\bgoldman(?: sachs)?\b','JP_Morgan':r'\b(?:jp\s*morgan|j\.p\.\s*morgan|jamie dimon)\b','Bank_of_America':r'\bbank of america\b','Morgan_Stanley':r'\bmorgan stanley\b',
'BofA_Hartnett':r'\bhartnett\b','Dalio':r'\bdalio\b','Buffett_Berkshire':r'\b(?:buffett|buffet|berkshire)\b','Burry':r'\bburry\b','Druckenmiller':r'\bdruckenmiller\b','Michael_Hartnett':r'\bmichael hartnett\b',
'Bloomberg':r'\bbloomberg\b','Reuters':r'\breuters\b','Financial_Times':r'\bfinancial times\b','CNBC':r'\bcnbc\b','Wall_Street_Journal':r'\bwall street journal\b',
'World_Gold_Council':r'\bworld gold council\b','FINRA':r'\bfinra\b','Bravos':r'\bbravos\b','Andrei_Jikh':r'\b(?:andrei jikh|andre jik|andrei jik)\b'}
PITCH=r'\b(?:sponsor(?:ed|ing)?|kikoff|kickoff|plaud|tello|delete me|ground news|gemini predictions|zocdoc|zoc doc|seeking alpha|funvest|members section|premium memberships?|join the membership|book a (?:call|slot)|strategy sessions?|special (?:launch )?offer|special invitation|bravos pro|bravo pro|strategy calls?|premium members?|premium membership|premium community|patreon|moomoo|moo moo|we?bull|robinhood|rocket money|groundfloor|ground floor|sofi|so fi|public\.com|join our|join my|link (?:in|below)|link in the description|free stocks?|free shares?)\b'
FAMILIES={
'oil_direction':(r'\b(?:oil|crude|brent|gasoline)\b',r'\b(?:rise|rising|risen|higher|surge\w*|soar\w*|increase\w*|up|spik\w*)\b',r'\b(?:fall\w*|lower|declin\w*|drop\w*|down|crash\w*|collaps\w*)\b'),
'inflation_direction':(r'\b(?:inflation|consumer prices|cpi)\b',r'\b(?:rise|rising|risen|higher|accelerat\w*|increase\w*|up|surge\w*)\b',r'\b(?:fall\w*|lower|declin\w*|drop\w*|down|cool\w*|decelerat\w*)\b'),
'dollar_direction':(r'\b(?:dollar|dxy)\b',r'\b(?:rise|rising|higher|strength\w*|surge\w*|up|rally\w*)\b',r'\b(?:fall\w*|lower|weak\w*|declin\w*|drop\w*|down|collaps\w*)\b'),
'gold_direction':(r'\b(?:gold|silver)\b',r'\b(?:rise|rising|higher|surge\w*|soar\w*|increase\w*|up|rally\w*)\b',r'\b(?:fall\w*|lower|declin\w*|drop\w*|down|crash\w*|collaps\w*)\b'),
'rates_direction':(r'\b(?:interest rates?|rate cuts?|rate hikes?|yields?)\b',r'\b(?:rise|rising|higher|hike\w*|increas\w*|up|surge\w*)\b',r'\b(?:fall\w*|lower|declin\w*|drop\w*|down|cuts?|cutting)\b'),
'stocks_direction':(r'\b(?:stock market|stocks|s&p|s and p|equities|nasdaq)\b',r'\b(?:rise|rising|higher|surge\w*|soar\w*|increase\w*|up|rally\w*|bullish)\b',r'\b(?:fall\w*|lower|declin\w*|drop\w*|down|crash\w*|collaps\w*|bearish)\b'),
'recession_presence':(r'\brecession\b',r'\b(?:enter\w*|heading|coming|inevitable|will|imminent|risk)\b',r'\b(?:no recession|not a recession|avoid\w*|unlikely|won.t|will not|soft landing|not in a recession)\b')}
def count(p,s):return len(re.findall(p,s,re.I))
def ts(sec):return f'{sec//60}:{sec%60:02}'
def write(name,rows):
 pd.DataFrame(rows).to_csv(OUT/name,index=False)
def parse(p):
 raw=p.read_text(); meta={}; rows=[]
 for l in raw.splitlines():
  m=re.match(r'(\d+:\d+(?::\d+)?)\t(.*)',l)
  if m:
   secs=sum(int(n)*60**i for i,n in enumerate(m[1].split(':')[::-1])); rows.append((secs,m[2]))
  elif ':' in l and not rows:
   k,v=l.split(':',1);meta[k]=v.strip()
 resets=[i for i in range(1,len(rows)) if rows[i][0]<rows[i-1][0]]
 n=resets[0] if resets else len(rows)
 if resets and rows[:n]!=rows[n:]:raise ValueError(f'Non-exact repeat {p}')
 rows=rows[:n]; offsets=[]; parts=[]; off=0
 for secs,s in rows: offsets.append((off,secs));parts.append(s);off+=len(s)+1
 text=' '.join(parts)
 sentences=[]
 for m in re.finditer(r'[^.!?]+[.!?]?',text):
  s=m[0].strip()
  if not s:continue
  sec=next((t for o,t in reversed(offsets) if o<=m.start()),0)
  sentences.append((sec,s))
 return {'file':p.name,'video_id':meta['video_id'],'channel':p.name.split('_')[0],'date':meta['publish_date'][:10],'title':meta['title'],'title_urgency':count(MARKERS['urgency'],meta['title']),'length_sec':int(meta['length_sec']),'words':len(re.findall(r"\b[\w’']+\b",text)),'raw_timestamp_rows':n*(2 if resets else 1),'retained_rows':n,'duplicate_second_pass':bool(resets),'last_timestamp':ts(rows[-1][0]),'input_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'text':text,'rows':rows,'sentences':sentences}
V=[parse(p) for p in sorted((ROOT/'corpus/transcripts').glob('*.txt'))]
metrics=[];themes=[];sources=[];pitch=[];windows=[];pred=[];digest=[]
for v in V:
 base={k:x for k,x in v.items() if k not in ['text','rows','sentences']};t=v['text'];metrics.append(base|{k:count(p,t) for k,p in MARKERS.items()}|{k+'_per_1k':count(p,t)/v['words']*1000 for k,p in MARKERS.items()})
 for theme,p in THEMES.items():
  matches=[(sec,s) for sec,s in v['sentences'] if re.search(p,s,re.I)]
  themes.append({k:base[k] for k in ['file','channel','date','video_id']}|{'theme':theme,'mentions':count(p,t),'mentions_per_1k':count(p,t)/v['words']*1000,'first_timestamp':ts(matches[0][0]) if matches else '', 'substantial':count(p,t)>=3 and count(p,t)/v['words']*1000>=1})
 for source,p in SOURCES.items():
  n=count(p,t)
  if n:sources.append({'file':v['file'],'channel':v['channel'],'date':v['date'],'source':source,'mentions':n,'first_timestamp':ts(next(sec for sec,s in v['sentences'] if re.search(p,s,re.I)))})
 # sixty-second bins avoid caption UI granularity artifacts
 bins=defaultdict(list)
 for sec,s in v['rows']:bins[sec//60].append(s)
 pitch_bins=set()
 for b,ss in bins.items():
  bt=' '.join(ss); n=count(PITCH,bt)
  if n:pitch_bins.add(b)
  windows.append({'file':v['file'],'channel':v['channel'],'date':v['date'],'start_sec':b*60,'words':len(re.findall(r"\b[\w’']+\b",bt)),'pitch_mentions':n,**{k:count(p,bt) for k,p in MARKERS.items()},**{k:count(p,bt) for k,p in THEMES.items()}})
 for sec,s in v['sentences']:
  if re.search(PITCH,s,re.I):pitch.append({'file':v['file'],'channel':v['channel'],'date':v['date'],'timestamp':ts(sec),'sec':sec,'position_fraction':sec/v['length_sec'],'markers':'|'.join(m[0] for m in re.finditer(PITCH,s,re.I)),'sentence':s})
  if len(s.split())>90:continue
  for family,(topic,pos,neg) in FAMILIES.items():
   if not re.search(topic,s,re.I):continue
   up=bool(re.search(pos,s,re.I));dn=bool(re.search(neg,s,re.I))
   if up==dn:continue
   pred.append({'predicate_id':f'P{len(pred)+1:05}','file':v['file'],'channel':v['channel'],'date':v['date'],'timestamp':ts(sec),'family':family,'polarity':1 if up else -1,'modal_future':bool(re.search(r'\b(?:will|would|could|may|might|likely|expect|forecast|predict|going to|about to)\b',s,re.I)),'sentence':s})
 # reproducible contextual review packet: opening and closing words plus theme-specific two first sentences
 sections=[f"\n### {v['file']} — {v['title']}\nOPEN: {' '.join(t.split()[:130])}\nCLOSE: {' '.join(t.split()[-130:])}"]
 for theme,p in THEMES.items():
  matches=[(sec,s) for sec,s in v['sentences'] if re.search(p,s,re.I)]
  if count(p,t)>=3:
   sections.append(theme+': '+' | '.join(f'[{ts(sec)}] {s[:260]}' for sec,s in matches[:2]))
 digest.append('\n'.join(sections))
write('video_metrics.csv',metrics);write('theme_by_video.csv',themes);write('named_source_mentions.csv',sources);write('pitch_sentences.csv',pitch);write('minute_windows.csv',windows);write('directional_predicates.csv',pred)
# Full-text working packet deliberately not persisted in final deliverables.
# Exhaustive within-detector pair inventory: pairs are not factual contradictions.
pairs=[]
for (ch,fam),g in itertools.groupby(sorted(pred,key=lambda p:(p['channel'],p['family'],p['date'],p['predicate_id'])),key=lambda p:(p['channel'],p['family'])):
 group=list(g)
 for i,a in enumerate(group):
  for b in group[i+1:]:
   if a['date']<b['date'] and a['polarity']!=b['polarity']:
    pairs.append({'pair_id':f'C{len(pairs)+1:06}','channel':ch,'family':fam,'a_predicate':a['predicate_id'],'a_date':a['date'],'b_predicate':b['predicate_id'],'b_date':b['date'],'days_between':(pd.Timestamp(b['date'])-pd.Timestamp(a['date'])).days,'both_future_modal':a['modal_future'] and b['modal_future'],'status':'UNADJUDICATED_CANDIDATE'})
write('opposite_direction_candidate_pairs.csv',pairs)
M=pd.DataFrame(metrics);M['month']=M.date.str[:7]
monthly=M.groupby(['channel','month']).agg(n_videos=('file','count'),words=('words','sum'),certainty=('certainty','sum'),hedge=('hedge','sum'),urgency=('urgency','sum'),correction=('correction','sum')).reset_index()
for k in MARKERS:monthly[k+'_per_1k']=monthly[k]/monthly.words*1000
monthly.to_csv(OUT/'monthly_rhetoric.csv',index=False)
T=pd.DataFrame(themes);T['month']=T.date.str[:7]
MT=T.groupby(['channel','month','theme']).agg(mentions=('mentions','sum'),substantial_videos=('substantial','sum')).reset_index().merge(monthly[['channel','month','words','n_videos']],on=['channel','month'])
MT['mentions_per_1k']=MT.mentions/MT.words*1000;MT.to_csv(OUT/'monthly_themes.csv',index=False)
# Topic first-use across channels, descriptive common-topic timing only.
conv=[]
for theme,g in T[T.substantial].groupby('theme'):
 d={ch:gg.sort_values(['date','file']).iloc[0] for ch,gg in g.groupby('channel')}
 if len(d)==2:conv.append({'theme':theme,'bravos_first':d['bravos']['date'],'bravos_file':d['bravos']['file'],'bravos_time':d['bravos']['first_timestamp'],'jikh_first':d['jikh']['date'],'jikh_file':d['jikh']['file'],'jikh_time':d['jikh']['first_timestamp'],'jikh_minus_bravos_days':(pd.Timestamp(d['jikh']['date'])-pd.Timestamp(d['bravos']['date'])).days})
write('cross_channel_first_observed.csv',conv)
# Price changes available before and after observed theme appearance, no causal inference.
series={'oil_energy':fb.brent_daily(),'dollar_fx':fb.fred('DTWEXBGS'),'inflation':fb.fred('CPIAUCSL'),'recession_labor':fb.fred('UNRATE'),'liquidity_rates':fb.fred('DGS10'),'valuation_bubble':fb.fred('SP500'),'ai_tech':fb.fred('NASDAQCOM'),'debt_credit':fb.fred('BAMLH0A0HYM2'),'gold_silver':fb.gold_monthly()}
lead=[]
for ch in ['bravos','jikh']:
 for theme,s in series.items():
  g=T[(T.channel==ch)&(T.theme==theme)&T.substantial].sort_values('date')
  if g.empty:continue
  f=g.iloc[0];d=pd.Timestamp(f.date);lag_days=45 if theme in ['gold_silver','inflation','recession_labor'] else 1;x=s.loc[:d-pd.Timedelta(days=lag_days)]
  if x.empty:continue
  row={'channel':ch,'theme':theme,'file':f.file,'timestamp':f.first_timestamp,'first_substantial_date':str(d.date()),'series':s.name,'assumed_publication_lag_days':lag_days,'at_obs_date':str(x.index[-1].date()),'at_value':x.iloc[-1],'observation_lag_days':(d-x.index[-1]).days}
  for days in [-90,-30,30,90]:
   end=d+pd.Timedelta(days=days);prior=s.loc[:end-pd.Timedelta(days=lag_days)]
   if len(prior) and end<=s.index.max():
    row[f'd{days}_obs_date']=str(prior.index[-1].date());row[f'd{days}_value']=prior.iloc[-1];row[f'd{days}_pct_vs_video']=(prior.iloc[-1]/x.iloc[-1]-1)*100
    row[f'pre{abs(days)}_pct' if days<0 else f'post{days}_pct']=(x.iloc[-1]/prior.iloc[-1]-1)*100 if days<0 else (prior.iloc[-1]/x.iloc[-1]-1)*100
  lead.append(row)
write('first_theme_price_context.csv',lead)
# Deliberate round event thresholds independent of narrative dates, restricted 2026.
events=[]
for name,s,threshold,op in [('Brent_above_90',fb.brent_daily(),90,'ge'),('Brent_above_100',fb.brent_daily(),100,'ge'),('Brent_below_80',fb.brent_daily(),80,'le'),('VIX_above_30',fb.fred('VIXCLS'),30,'ge')]:
 h=s.loc['2026-01-01':];state=h.ge(threshold) if op=='ge' else h.le(threshold)
 crossing=state&~state.shift(fill_value=False)
 for date in h.index[crossing]:events.append({'event':name,'date':str(date.date()),'value':h.loc[date],'series':s.name})
write('round_threshold_crossings_2026.csv',events)
# Correlations of rhetorical intensity with contemporaneous / preceding 30-day market variables.
market=[]
for _,m in M.iterrows():
 d=pd.Timestamp(m.date);row={'file':m.file,'channel':m.channel,'date':m.date,'urgency_per_1k':m.urgency_per_1k,'certainty_per_1k':m.certainty_per_1k,'hedge_per_1k':m.hedge_per_1k}
 for name,s in [('sp500',fb.fred('SP500')),('brent',fb.brent_daily()),('vix',fb.fred('VIXCLS'))]:
  row[name+'_asof']=fb.asof(s,m.date);row[name+'_30d_pct']=(fb.asof(s,m.date)/fb.asof(s,str((d-pd.Timedelta(days=30)).date()))-1)*100
 market.append(row)
K=pd.DataFrame(market);K.to_csv(OUT/'rhetoric_market_values.csv',index=False)
cs=[]
for ch,g in K.groupby('channel'):
 for rhetoric in ['urgency_per_1k','certainty_per_1k','hedge_per_1k']:
  for marketvar in ['sp500_30d_pct','brent_30d_pct','vix_asof']:
   cs.append({'channel':ch,'n':len(g),'rhetoric':rhetoric,'market_variable':marketvar,'pearson_r':g[rhetoric].corr(g[marketvar]),'spearman_rho':g[rhetoric].rank().corr(g[marketvar].rank())})
write('rhetoric_market_correlations.csv',cs)
# Compare rhetoric inside pitch-marked minutes vs all other minutes; correlated/minute not independent n.
W=pd.DataFrame(windows);W['pitch_bin']=W.pitch_mentions.gt(0)
P=W.groupby(['channel','pitch_bin']).agg(minutes=('file','size'),words=('words','sum'),certainty=('certainty','sum'),hedge=('hedge','sum'),urgency=('urgency','sum')).reset_index()
for k in ['certainty','hedge','urgency']:P[k+'_per_1k']=P[k]/P.words*1000
P.to_csv(OUT/'pitch_rhetoric_comparison.csv',index=False)
(OUT/'methods.json').write_text(json.dumps({'scope':'Blind Phase A. No claims, prior report, prior verdicts or analogs opened.','coverage':'All 58 transcript files fully ingested; complete first timestamp pass. Full semantic reading by team is separately recorded in semantic_reading_notes.md, jikh_mid_reader.md and jikh_late_reader.md; working contextual packets are not retained in final deliverables.','deduplication':'At first declining timestamp; exact equality of retained pass and removed pass required.','themes':THEMES,'rhetoric':MARKERS,'sources':SOURCES,'pitch':PITCH,'directional_families':FAMILIES,'substantial_theme':'at least 3 regex matches and at least 1 mention per 1000 words','candidate_pairs':'Every same-channel, same-family, opposite-polarity sentence pair with strictly different increasing dates; only single-polarity sentences <=90 words; no truth/horizon/attribution check until manual adjudication.','price_context_caveat':'First use left censored by selected corpus. Daily series assumed one-day lag; gold, CPI and unemployment conservative45-day lag on reference date. Raw snapshot is revised vintage, not original releases. No lead-lag causal test.', 'input_video_count':len(V),'words':int(M.words.sum()),'duplicate_file_count':int(M.duplicate_second_pass.sum()),'n_directional_predicates':len(pred),'n_candidate_pairs':len(pairs)},indent=2))
print(json.dumps({'videos':len(V),'dedup_words':int(M.words.sum()),'duplicates':int(M.duplicate_second_pass.sum()),'predicates':len(pred),'pairs':len(pairs),'output':str(OUT)}))
