"""Manual judgments preserved as explicit data and joined to reproducible evidence."""
from pathlib import Path
import pandas as pd
import re,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import analyze_corpus as a
# Full-context judgments; excerpts localize evidence and are not the entire argument.
items=[
('A01','bravos','2026-05-15','at least 100% in the last 2 years','2026-06-02','single calendar year','CONTRADICTION_DEFINITION','The same attributed official bubble definition changes from two-year absolute plus relative return conditions to one-year absolute return. These cannot be the same exact rule.','Primary NBER paper and operational rule; distinguish research screen from official definition.'),
('A02','bravos','2026-05-11','June of 1999','2026-05-29','January of 1999','CONTRADICTION_HISTORICAL_DATE','Start of the same 1999 Fed hike sequence is dated June versus January. A fixed event does not change when new observations arrive.','Dated FOMC target history.'),
('A03','bravos','2026-05-29','January of 1999','2026-06-02','May of 1999','CONTRADICTION_HISTORICAL_DATE','Same hike onset now moves January to May; correlated with A02, not a third independent forecasting failure.','Dated FOMC target history.'),
('A04','bravos','2026-03-26','as long as oil prices remain above $80','2026-04-23','could easily climb another','MATERIAL_REVISION_NOT_STRICT_CONTRADICTION','Oil-above80 caution becomes near-term upside through nominal earnings before the stated oil invalidator is reached. Stronger profits/labor provide a changed condition, but previous timing is not explicitly reconciled.','Original decision rule including earnings/labor overrides and holding horizon.'),
('A05','bravos','2026-05-07','best way to play this','2026-05-15','significantly reduced our exposure','POSITION_CHANGE_NOT_CONTRADICTION','Semiconductor exposure expected to continue for months becomes substantially reduced eight days later; owning leftovers can satisfy some continued exposure.','Public dated portfolio weights and trade timestamps.'),
('A06','bravos','2026-04-27','expecting economic weakness','2026-06-15','economy is well positioned to grow','HORIZON_CONDITION_DIFFERENCE','Steepening is recession warning in the first discussion and future growth support in the second; the second explicitly conditions on surviving a near-term danger window.','Freeze contemporaneous versus lagged curve definitions and failure conditions.'),
('A07','bravos','2026-06-11','historically small amount of dry powder','2026-08-09','26% of the economy','DENOMINATOR_DIFFERENCE','Low cash relative to equity market capitalization can coexist with high cash relative to GDP. It is not an X/not-X contradiction.','Carry both denominators into dashboard and causal analysis.'),
('A08','bravos','2026-03-20','highest levels since 2025','2026-04-23','weak for the last 6 months','WINDOW_DIFFERENCE','Recent dollar rally/high since2025 can coexist with weakness over six months and near four-year lows; exact index unspecified.','Same dollar index and same endpoint/window.'),
('A09','bravos','2026-05-11','increasingly likely that the Federal Reserve','2026-07-07',"won't be raising interest rates much",'FORECAST_REVISION_NOT_CONTRADICTION','2026-hike expectation weakens after oil and inflation-expectation changes; statements are forecasts at different dates, with changed conditions.','Store dated probability revisions and score each horizon independently.'),
('A10','bravos','2026-08-21','cross back above 5.5%','2026-09-16','nail in the coffin','TRIGGER_REFRAMING','Earlier prior-peak-rate5.5 requirement is replaced by first-hike narrative; later medium-term downturn warning does not explicitly assert the identical bubble-collapse threshold has already passed.','Frozen rate threshold, event definition and lead horizon.'),
('A11','jikh','2026-03-16','grown from basically nothing to 3 trillion','2026-03-31','$9.4 trillion shadow banking','SCOPE_AMBIGUITY','Private-credit universe changes from3trn to9.4trn in15days with the same label. Potential factual inconsistency; differing universe or caption error could explain it.','Named series definition and original audio.'),
('A12','jikh','2026-06-05','almost always','2026-06-12','IPOs','MATERIAL_TIMING_QUALIFICATION','June5 immediate-post-IPO peak generalization is softenedJune12 with1995–2000 multi-year delay. Quantified universe missing, so not strict all-versus-none negation.','Same IPO sample, immediate horizon and full base rate.'),
('A13','jikh','2026-05-20','cash','2026-06-12',"don't have",'IMPLEMENTATION_HORIZON_TENSION','Anti-cash/scarcity framework coexists with personally holding substantial cash and no metals; waiting for a lower entry can reconcile horizons.','Predeclared timing/entry rule and dated weights.'),
('A14','jikh','2026-06-15','97.4','2026-06-22','exactly','RETROSPECTIVE_BRANCH_SELECTION','Preview credits market97.4%hold and supplies bullish/bearish branches. Follow-up stresses correct outcome; does not establish incremental forecasting value.','All branches, premium forecast timestamps, and market-implied null.'),
('A15','jikh','2026-06-22','signed','2026-06-22',"hasn't actually happened",'SAME_VIDEO_STATUS_AMBIGUITY','Opening signed-deal statement versus later deal-not-happened may confuse agreement and implementation. Same-video candidate, not cross-date proof.','Identify precise signed framework, final agreement and implementation dates.'),
('A16','jikh','2026-04-07','4.6 and 4.8','2026-05-04','4.4%','THRESHOLD_DRIFT','Debt-danger zone shifts from4.6–4.8 toward dysfunction above4.4. Different dysfunction versus spiral severity might reconcile; no stable operational event definition.','Lock event definition, yield series and threshold before scoring.'),
('A17','jikh','2026-08-25','this buyer demands no interest','2026-09-02','four or 5% on your money','MATERIAL_FINANCING_MODEL_INCONSISTENCY','Zero-yield stablecoin users are treated as a sovereign no-interest debt buyer; later the issuer earns Treasury interest while users receive zero. The issuer funding cost and sovereign borrowing cost are different quantities.','Distinguish stablecoin holder yield, issuer reserve income, and Treasury debt coupon.'),
('A18','jikh','2026-07-28',"there's no confirmed",'2026-07-28',"they're forcing the wealth",'EPISTEMIC_ESCALATION_NOT_STRICT_CONTRADICTION','An explicitly unconfirmed Article589 rumor resumes as an operating repatriation mechanism. Raw text gives23:31 disclaimer and23:52 forcing mechanism; inconsistent epistemic weight is not a literal factual negation.','Primary legal text and authoritative implementation status.'),
('A19','jikh','2026-08-19',"don't really know for sure",'2026-08-19','makes loans to data center projects','UNSUPPORTED_LINKAGE_NOT_STRICT_CONTRADICTION','Unknown insurer-specific AI exposure is later bridged by a general flow diagram. Raw text localizes1:53 uncertainty and21:17–21:26 connection. Aggregate sector facts do not establish the missing joint exposure.','Firm-level asset look-through linking insurers, private credit, and named AI borrowers.'),
]
rows=[]
for id,ch,da,ca,db,cb,verdict,why,resolve in items:
 r={'id':id,'channel':ch,'a_date':da,'b_date':db,'verdict':verdict,'reason':why,'would_settle':resolve}
 for label,date,cue in [('a',da,ca),('b',db,cb)]:
  v=next(x for x in a.V if x['channel']==ch and x['date']==date); matches=[(sec,s) for sec,s in v['sentences'] if cue.casefold() in s.casefold()]
  r[label+'_file']=v['file'];r[label+'_search_cue']=cue
  if matches:r[label+'_timestamp']=a.ts(matches[0][0]);r[label+'_excerpt']=matches[0][1]
  else:
   pos=v['text'].casefold().find(cue.casefold());offset=0;sec=0
   for t,line in v['rows']:
    if offset>pos:break
    sec=t;offset+=len(line)+1
   r[label+'_timestamp']=a.ts(sec) if pos>=0 else 'SEE_FULL_READER_NOTES';r[label+'_excerpt']=v['text'][max(0,pos-70):pos+200] if pos>=0 else 'Exact cue not found; inspect full reader notes.'
 rows.append(r)
pd.DataFrame(rows).to_csv(a.OUT/'curated_contradictions_and_revisions.csv',index=False)
J={
'C000008':('WINDOW_DIFFERENCE','Multi-year oil/dollar association versus later realized dollar drawdown; neither states opposite same-interval proposition.'),
'C000173':('LEXICAL_FALSE_POSITIVE','Marketing pennies on the dollar is not an exchange-rate claim.'),
'C000416':('LEXICAL_FALSE_POSITIVE','Gold co-occurs with lower rates in A, and show up in B; directions attach to different objects.'),
'C000404':('HISTORICAL_PERIOD_DIFFERENCE','2026metal rally versus1950s/60s reserve-backing decline.'),
'C000548':('DIFFERENT_OBJECTS','Inflation declines versus equity earnings catch-up under high inflation.'),
'C000611':('HISTORICAL_PERIOD_DIFFERENCE','Conditional2026oil reversal versus reason for1999hikes.'),
'C001159':('REALIZED_STATE_CHANGE','March oil rise and July oil decline are compatible observations in a round trip.'),
'C001325':('LEXICAL_FALSE_POSITIVE','China economic rise is not oil-price upside.'),
'C001934':('DIFFERENT_OBJECTS','Conditional Fed policy stance and foreign long yields can both rise; heuristic direction failed.'),
'C003168':('DIFFERENT_OBJECTS','Historical railway investments decline versus higher demanded bond yield.'),
'C003450':('NEGATION_SCOPE','Both passages actually say no current recession; phrase heading into recession is nested hypothetical.'),
'C003457':('HISTORICAL_PERIOD_DIFFERENCE','Current conditional recession avoidance versus2001realized recession.'),
'C006515':('NEGATION_OBJECT','Both passages support stock upside; down belongs to Federal Reserve direction.'),
'C006513':('REALIZED_STATE_CHANGE','June broad-market prior rally versusJulymega-cap pullback, different interval/universe.'),
'C007941':('DIFFERENT_OBJECTS','Both actually describe dollar weakness; up belongs to stocks.'),
'C008235':('HORIZON_CONDITION_DIFFERENCE','Past dollar decline versus possible initial dollar rally in debt deleveraging.'),
'C008722':('NOT_REQUIRED_VS_REALIZED','Gold need not rise for accounting revaluation; past gold fall does not negate that.'),
'C008726':('NOT_REQUIRED_VS_HISTORY','Present accounting mechanism versus historical post2007gold path.'),
'C008904':('DECIMAL_SPLIT_AND_OBJECT','Sentence splitter cutsCPI3.x; lower belongs to rates, not inflation.'),
'C008901':('DECIMAL_SPLIT_AND_ATTRIBUTION','CPIobservation versus campaign promise/quoted preference, not opposite factual stance.'),
'C009123':('HISTORICAL_PERIOD_DIFFERENCE','Previous recessions with rising oil versuscurrentoil decline.'),
'C009451':('LEVEL_VS_COUNTERFACTUAL','Suppression hypothesis can coexist with higher oil from supply shock.'),
'C011394':('COUNTRY_DIFFERENCE','Japan increasing rates versusUSlowering rates.'),
'C011355':('COUNTRY_AND_ATTRIBUTION','BOJboard vote versusquestion aboutFedchaircommitment.'),
'C012591':('SCENARIO_VS_OBSERVATION','Hypothetical stableoil lowers risk versuscurrentearnertop10support no recession.'),
'C012592':('SCENARIO_VS_OBSERVATION','Conditional future recession chain versuscurrentno-recession observation.'),
'C012662':('GENERAL_VS_SINGLE_DAY','General employment/stocks association versusone-daydecline; decimal truncated.'),
'C013117':('HISTORICAL_PERIOD_DIFFERENCE','Historical infrastructure bankruptcies versuscurrentAIspending.')}
sample=pd.read_csv(a.OUT/'contradiction_pair_sample.csv');sample['manual_verdict']=sample.pair_id.map(lambda z:J[z][0]);sample['manual_reason']=sample.pair_id.map(lambda z:J[z][1]);sample['strict_contradiction']=False
sample.to_csv(a.OUT/'contradiction_sample_adjudicated.csv',index=False)
print('curated',len(rows),'mechanicalsample',len(sample))
print(pd.DataFrame(rows)[['id','a_timestamp','b_timestamp']].to_string(index=False))
