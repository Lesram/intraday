from pathlib import Path
import pandas as pd
P=Path(__file__).resolve().parent
m=pd.read_csv(P/'indicator_event_metrics.csv')
notes=[
('claims_rise_20pct','Initial claims stress','100 × (4-week average ICSA / trailing 52-week minimum of that 4-week average − 1)','ICSA','weekly; months use last observation','typically days after week end; seasonal revisions; historical study has no vintage panel','1967-01 raw; derived evaluated 1968-01 onward','20%','Round prior, not fitted','Tier 1 diagnostic review','Check whether employment deterioration is broad-based; request human regime review, no trade instruction','Suspend predictive wording unless prospective mature episode hit rate exceeds same-calendar null after 20 independent episodes; retire duplicate review alert if no distinct human decision in 8 quarterly audits'),
('sahm_050','Sahm unemployment rule','SAHMREALTIME: 3-month mean unemployment minus minimum of 3-month means over preceding 12 months','SAHMREALTIME','monthly','monthly observation known in following month; source expressly reconstructs information available then','1959-12 raw; study available 1960-01 onward','0.5 percentage points','Published rule, not fitted','Tier 1 diagnostic review','Check recession-state evidence and labour composition; explicitly mark usually coincident/late','Retire future-onset predictive role now; diagnostic role reviewed if false alarms dominate first 10 prospectively archived independent episodes'),
('curve_inverted','Monthly yield-curve inversion','GS10 − TB3MS; monthly averages, one-month study availability lag','GS10;TB3MS','monthly','one-month conservative study lag; observed daily curves are a different definition','1953-04 raw joint; study 1954-02 onward','<0 percentage points','Economic round boundary, not fitted','Tier 2 watch','Schedule 24-month scenario follow-up; no timing or allocation signal','Remove recession-forecast label if prospective 20 independent episodes fail to exceed same-calendar event baseline; retain rate context'),
('baa_level_300','Baa Treasury spread level','Last BAA10Y observation per completed month','BAA10Y','daily source, monthly test','market days; last-month observation date retained; source corrections possible','1986-01 onward','>=3 percentage points','Round stress prior, not fitted','Tier 2 watch','Describe current credit conditions; historical future-event specificity is poor','Demote to context if no incremental review information beyond spread change over 8 quarterly audits'),
('baa_widening_100','Baa spread acceleration','Month-last BAA10Y minus month-last BAA10Y three calendar months earlier','BAA10Y','daily source, monthly test','market days; native source corrections possible; monthly signal archive','1986-04 derived onward','>=1 percentage point / 3 months','Round deterioration prior, not fitted','Tier 1 diagnostic review','Review credit deterioration and data consistency; sample has only 2 mature onsets, so no predictive probability claim','Do not grant predictive status before substantially more independent episodes; retire duplicate alert if no distinct human review decision in 8 quarterly audits'),
('nfci_positive','National financial conditions','Last NFCI observation in completed month; study availability lag one month','NFCI','weekly, monthly test','conservative one-month study lag; history revises as components/standardization change','1971-01 raw; study available 1971-02 onward','>0','Published index mean boundary, not fitted','Tier 2 watch','Cross-check whether tightening extends beyond corporate credit; do not count correlated measures as independent votes','Demote if no incremental informational value beyond claims and Baa for 8 quarterly audits'),
('inflation_400','CPI inflation level','100 × (CPIAUCSL[m] / CPIAUCSL[m−12 calendar months] − 1)','CPIAUCSL','monthly','typically following month; seasonal revisions; missing periods stay missing','1947-01 raw; study derived after 1954 sample start','>=4% YoY','Round context boundary, not central-bank target','Tier 2 watch','Identify purchasing-power regime and require inflation scenario update; no equity crash forecast','Retire predictive use now; retain descriptive level unless source quality fails'),
('inflation_surge','CPI inflation acceleration','Calendar CPI YoY >=4% AND YoY − YoY 12 calendar months earlier >=2 percentage points','CPIAUCSL','monthly','following-month availability; revised history; exact calendar missingness','1947-01 raw; study derived after lookbacks','>=4% AND >=2pp acceleration','Round compound prior, not fitted','Tier 2 watch','Distinguish persistent level from accelerating inflation; update inflation scenario once per episode','Retire separate card if it adds no interpretation beyond CPI level in 8 quarterly audits')]
cols=['indicator','name','definition','series_ids','frequency','lag_and_revision','history','threshold','threshold_choice','proposed_tier','decision_informed','kill_criterion']
d=pd.DataFrame(notes,columns=cols)
d['source_urls']=d.series_ids.map(lambda s:';'.join('https://fred.stlouisfed.org/series/'+x for x in s.split(';')))
d['free_machine_readable']='Yes, public FRED CSV; collection environment may require browser same-origin capture'
d['performance_table']='phase_b_events/indicator_event_metrics.csv (join on indicator,event,horizon_months,split)'
d['independence_table']='phase_b_events/redundancy.csv; no independent-vote assumption'
d.to_csv(P/'indicator_definitions.csv',index=False)

def pretty(df):
 rows=[]
 for _,r in df.iterrows():
  rows.append({'Indicator':r.indicator,'Horizon':int(r.horizon_months),'Hits / alarms':f'{int(r.episode_hits)}/{int(r.n_alarm_episodes)}','False alarms':f'{100*r.episode_false_alarm_fraction:.1f}%' if r.n_alarm_episodes else 'undefined (n=0)','95% false interval':f'{100*r.false_alarm_wilson_95_low:.1f}–{100*r.false_alarm_wilson_95_high:.1f}%' if r.n_alarm_episodes else 'undefined','Lead median [min,max]':f'{r.lead_months_median:g} [{r.lead_months_min:g},{r.lead_months_max:g}]' if pd.notna(r.lead_months_median) else 'no hits','Monthly FPR':f'{100*r.classical_fpr:.1f}%','Monthly event baseline':f'{100*r.unconditional_event_probability:.1f}%','Eligible months':int(r.eligible_months)})
 return pd.DataFrame(rows).to_markdown(index=False)
rec=m[(m.event=='recession_onset')&(m.split=='all')]
diag=m[(m.event=='recession_present_or_onset')&(m.split=='all')&(m.horizon_months==12)]
oos=m[(m.event=='recession_onset')&(m.split=='holdout_2000plus')]
eq=m[(m.event=='equity_entry_loss_20')&(m.split=='all')&(m.horizon_months==12)]
text='''# Phase B: independent event validation — frozen thresholds, honest denominators

**Blind analysis dated 2026-09-19.** This study read only the work order, raw data, `data/SOURCES.md`, `scripts/factbase.py`, and narrowly searched `scripts/dashboard.py`. It did not read Brief 001, claims, analogs, verification verdicts, regime outputs, README or STATE. Thresholds, outcomes and split were recorded in `phase_b_events/preregistration.json` before calculation. All figures below derive from supplied FRED bundles captured 2026-09-19 and the supplied Shiller mirror; exact source hashes are in `source_hashes.json`. No external series were silently substituted.

## Conclusion before unblinding

No tested threshold qualifies as a reliable forecast of a 20% equity loss. The curve is a useful **long-horizon recession watch**, but its full-sample 24-month record is only 6 hits in 8 separated onsets: a 25% false-alarm fraction with a 95% interval of roughly 7–59%. Claims, Sahm and fast Baa widening are useful **state-review triggers**; their dashboard action is to examine deteriorating conditions, not to predict a future event or place a trade. Sahm's apparent recession accuracy largely reflects detection after recession has already begun. A zero observed false-alarm count in the two Baa-widening onsets is not strong evidence: its upper 95% false-alarm bound is about 66%.

## Methods and exact definitions

The primary horizon is the next 12 completed months. Curve inversion also has a 24-month horizon, chosen before outcomes for a slow business-cycle relationship. Tests start no earlier than 1954 and end with supplied August 2026 outcomes. Training signals must have outcomes wholly before 2000; holdout signals start January 2000. Boundary-crossing training labels are excluded. A 12-month signal cannot be scored after August 2025, nor a 24-month signal after August 2024. Missing outcome months remove a window, even if it is chronologically mature.

Every alarm is a false-to-true monthly crossing. The first sample month is not counted if already positive; later onsets need at least the forecast horizon since the preceding accepted onset. Onset-only targets exclude a signal if that event is already active. This prevents rewarding a recession alarm merely because recession was already under way. Cooldowns reduce overlapping alarms but do not create truly independent economic experiments. Wilson intervals assume approximate independence and can still be too narrow.

Definitions: claims = four-week ICSA average, at least 20% above its trailing 52-week minimum; Sahm source >=0.5pp; curve = monthly GS10 minus TB3MS <0; BAA10Y >=3pp or widening >=1pp across three calendar month-ends; NFCI >0; inflation level = calendar CPI YoY >=4%; inflation surge = that level AND >=2pp YoY acceleration over twelve calendar months. Thresholds are round priors or named conventions, not optimized values. Claims and Baa use last monthly observations; Sahm, monthly curve, CPI and NFCI have a conservative one-month availability lag. The monitoring implementation should archive actual publication times rather than pretend this coarse lag is exact.

Recession means a USREC 0→1 transition. Inflation event means a calendar CPI YoY transition to >=4%, from below. Credit event means a BAA10Y month-last transition to >=3pp, from below. Equity **entry loss** means a monthly-average Shiller price at least 20% below the signal month's price within the horizon. Equity **peak drawdown** means a loss of at least 20% from a running peak established at or after the signal month. Neither is a daily close drawdown nor a total-return result: monthly averages smooth extremes. A later crash following a large intervening rally can count as peak drawdown while never becoming a 20% loss from the alarm's entry price. Both definitions are supplied, not selected after seeing which looks better.

**Two different false-positive denominators:** alarm false fraction = failed alarm episodes / all mature eligible alarm episodes; classical FPR = alarm-positive nonevent months / all nonevent months, FP/(FP+TN). A rare alarm can have a low classical FPR and still be wrong most times it sounds. Tables report both. Baselines are the event probability of all eligible monthly starting dates for the exact same series/horizon, not event counts divided by alarm counts. Monthly windows overlap, so these are descriptive base rates rather than independent observations. No alarm-frequency null or significance claim is inferred from comparing the episode hit rate to this monthly baseline alone.

## Strict future recession onsets, full available sample

'''+pretty(rec)+'''

The Sahm rule's low strict-leading performance is not a failure of its stated diagnostic purpose. Among its eight full-sample diagnostic hits, the median alarm arrives **4 months after** the recorded USREC onset; its range includes one alarm 2 months before through alarms 4 months after. Exact signed lags are in `recession_diagnostic_delays.csv`. The corresponding claims median is the onset month. USREC labels are the series convention (first month after business-cycle peak), not an assertion that NBER announced a recession at that date.

## Recession already present OR beginning in next 12 months: diagnostic target

'''+pretty(diag)+'''

Median lead zero in this table means the recession is already active. It is not a zero-delay prediction. Diagnostic Baa widening onsets occur at onset and nine months after onset; neither independently leads a future recession under this definition.

## Chronological holdout: strict future recession

'''+pretty(oos)+'''

This holdout has no threshold fitting, but it is **pseudo-out-of-sample**, not a fully reconstructed real-time investment backtest. Most source histories are revised snapshots. SAHMREALTIME specifically reconstructs information available at each historical observation; that advantage does not make every other input vintage-correct. The 2020 recession also demonstrates why an accidental correct timing association is not proof that the curve forecast the causal shock. Post-2000 sample sizes are too small to choose fine distinctions between competing indicators.

## A 20% loss from signal-month equity price within 12 months

'''+pretty(eq)+'''

The complete grid for both equity definitions, recession definitions, inflation onsets and credit onsets is in `indicator_event_metrics.csv`, with separate training and holdout rows. Never report an undefined zero-alarm probability as 0%. CPI>=4% is principally a **description of an inflation regime already present**, so it has few or no eligible episodes for predicting the onset of that same regime. Baa>=3pp has the analogous problem for predicting its own credit-threshold onset; that tautology is not concealed as a perfect signal. Credit event is an explicitly defined spread stress crossing, not a bank default, bankruptcy or systemic crisis.

## Independence, history and limits

All 28 pairwise alarm correlations/Jaccard overlaps, their sample dates and n are in `redundancy.csv`. Claims and Sahm have alarm phi correlation about 0.451 over 703 shared months (1968-01 to 2026-08). NFCI and CPI>=4 have phi about 0.561 over 666 valid shared months (1971-02 to 2026-08), partly reflecting the old high-inflation monetary regime. CPI surge is deliberately a subset of the CPI level condition. No dashboard may count these as independent confirming votes. Correlation is sample-dependent and cannot establish whether their information adds incremental prospective decision value.

The GS10−TB3MS curve uses a constant-maturity ten-year yield and a Treasury-bill series whose quotation convention differs. It is a consistent long historical proxy, **not interchangeable with daily T10Y3M**; near-inversion episodes and crossing dates differ. The curve hit rate cannot be assigned to a different live curve definition. The local BAMLH0A0HYM2 history starts September 2023: it cannot validate a multidecade high-yield spread threshold. No synthetic extension was made. BAA10Y begins January 1986, claims January 1967, NFCI January 1971, Sahm December 1959. Exact first/last evaluated dates are stored per metric. No percentile ranks are used in this event study.

The supplied CPI has no October 2025 value. Exact calendar joins preserve that missingness; outcomes spanning an unobserved inflation month are ineligible. This shrinks inflation-target sample counts and is not evidence of no event. Price and recession target counts are unaffected. The raw series' dates are observation dates, not historical publication timestamps. Daily/weekly last-of-month sampling can be a few days premature for claims releases; coarse one-month lags can also discard useful timeliness. Deployment must record published_at and acquired_at separately and gather vintages prospectively.

No threshold was retuned. No formal multiple-testing-adjusted finding is claimed across this broad event grid. The table supports diagnostics and pre-registered future evaluation, not a new fitted forecasting score. A real validation next step is a locked prospective archive with exact release times, missing-data flags, episode onsets and outcome maturity, plus comparison to independent calendar-spaced null alarms.

## Proposed specification handoff

A small Tier 1 of **claims deterioration, Sahm crossing, and Baa acceleration** is defensible only when 'act' means a human evidence review. Claims and Sahm should share one labour section rather than inflate the vote count. The Baa threshold is retained because a 1pp quarterly widening is a material observed deterioration, not because two examples establish a forecast. Curve, NFCI, Baa level and the two inflation diagnostics are Tier 2 watch/context. Slow valuation measures belong in a separate structural layer supplied by the independent regime study.

`indicator_definitions.csv` includes all eight formulas, sources, frequency and revision limits, history, threshold choices, questions/decisions and kill criteria; join it to metrics by indicator ID. Every recommended threshold carries its full event-specific false-positive record rather than a flattering selected outcome. A diagnostic remains useful only if it changes the quality of a review; no evidence here warrants an automated trading action.

## Reproduction and audit

Run `validate_events.py`, then `build_report.py`, from any directory with pandas/numpy/tabulate available. They write only in this study's directory and the Phase B event report. `source_hashes.json` fingerprints every consumed source. `validation_checks.json` records successful checks of horizon maturity, episode spacing, confusion-matrix denominators, lead ranges and missing CPI preservation. `monthly_evaluation.csv` retains every scored origin month; `alarm_episodes.csv` retains each accepted alarm and first outcome date; `excluded_crossings.csv` records cooldown and ineligibility exclusions; `event_dates.csv` records unconditioned event crossings.

Self-correction log: no threshold or outcome definition was changed after execution. A diagnostic signed-delay table was added after the first run because reporting all already-active recessions as lead zero would hide how late the alarm arrived. This clarification did not alter episode selection or measured rates.
'''
(P.parent/'PHASE_B_event_validation.md').write_text(text)
print('Wrote report and eight indicator definitions.')
