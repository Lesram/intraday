"""Reconcile research specification only. Writes only named final/contract outputs.
No pipeline execution, live retrieval, archived-outcome rewriting or source mutation.
"""
from pathlib import Path
import csv, json, hashlib, re
from collections import Counter
import pandas as pd

FINAL=Path(__file__).resolve().parents[1]
REVIEW=FINAL.parent
SOURCE=REVIEW/'consolidation/INDICATOR_CONTRACT.csv'
rows=list(csv.DictReader(SOURCE.open()))
fields=list(rows[0])
original={r['indicator_id']:dict(r) for r in rows}
assert len(fields)==42 and len(rows)==21

review_rule=("Review methodology, publisher/source continuity, revision exposure and outcome definitions annually. "
 "Review documented operational usefulness after 24 months: distinct questions resolved, redundant prompts, missing-data burden and follow-up quality. "
 "Demote or retire a redundant/unusable row with a recorded reason. Suspend affected computations immediately on an unbridged source or definition break. "
 "Neither elapsed years nor five/twenty alarms establishes predictive validity. Any predictive promotion requires a separately fixed primary outcome/horizon, "
 "matched baseline, independent or appropriately clustered mature episodes, declared precision requirements, and uncertainty adequate for the proposed use. "
 "Do not retune on a failed evaluation. Preserve original records and do not pool changed economic definitions.")
inventory={
 'claims_rise':'review_flag','sahm':'review_flag','credit_change':'watch','credit_level':'watch',
 'nfci':'watch','curve':'watch','inflation':'watch','inflation_acceleration':'context',
 'core_inflation':'context','brent':'context','equities_gdp':'context','profit_share':'context',
 'orig_cape':'context','orig_top10_weight':'retired','orig_headline_minus_core':'retired',
 'orig_baa_10y_250':'retired','orig_claims_4wk_300k':'retired','orig_hy_oas':'retired',
 'cand_policy_rate_impulse':'candidate','cand_cpi_calendar_completeness':'engineering_control',
 'cand_continuing_claims':'candidate'}
study={'claims_rise':'claims_rise_20pct','sahm':'sahm_050','credit_change':'baa_widening_100',
 'credit_level':'baa_level_300','nfci':'nfci_positive','curve':'curve_inverted',
 'inflation':'inflation_400','inflation_acceleration':'inflation_surge'}
limitations={
 'claims_rise':"Diagnostic association 9/13; strictly future onset 4/8. Signed diagnostic delay median0 months, range−10 to+2. Monthly retrospective sampling differs from native weekly observations and from the proposed next-release confirmation. No calibrated live probability or demonstrated incremental decision value.",
 'sahm':"Diagnostic association8/11; strictly future onset1/4, holdout0/2. Successful diagnostic signals arrived median4 months after recorded recession onset, range−2 to+4. Published SAHMREALTIME preserves contemporary unemployment inputs, but does not establish that every other series or the whole study is vintage-real-time.",
 'credit_change':"Diagnostic association2/2 with false-alarm Wilson interval0–65.8%; no eligible strictly-leading episodes, not a zero-percent leading success rate. Episodes are2008-10 and2020-03, respectively9 and0 months after USREC onset. The small sample and54-combination exposure limit inference; no null experiment proves the2/2 result arose by chance. Watch status is an operational conservatism decision, not evidence that observing credit deterioration has no diagnostic value.",
 'credit_level':"Diagnostic3/8 hits, strictly future onset1/6. Equity-entry-loss false fraction7/8. The latest daily level does not inherit the monthly crossing study's rates. Shares BAA10Y with credit_change; two views of one source are not independent confirmation.",
 'nfci':"Diagnostic5/9 hits; strict future onset3/7, holdout2/2 on only two episodes. Equity-entry-loss0/9. Historical model revisions weaken vintage interpretation. NFCI and credit spreads contain overlapping financial-condition information.",
 'curve':"The retained historical record uses recession_onset@24m, unlike12m records on other rows;12m strict-onset record is5/9 versus6/8 at24m. The extra horizon was listed in the preregistration, but per-indicator primary-event assignment was not. Median successful24m lead9.5 months does not imply a timed equity-loss signal. Other indicators also have positive leads in selected strict-onset cases; the curve is not the only series ever to lead. GS10−TB3MS is a monthly quotation-convention proxy, not dailyT10Y3M.",
 'inflation':"A4% threshold describes inflation already present. Historical equity-entry-loss record2/7 is weak; it is not an inflation forecast. The2/2 inflation-onset alternative is a small timing-dependent cell, not evidence of forecast skill. Calendar endpoint joins must preserve missingness; a missing unrelated interior month does not invalidate an otherwise valid endpoint YoY.",
 'inflation_acceleration':"Context only in the final policy; the2pp AND4% condition is retained as historical research metadata, not a current action threshold. Equity-entry-loss2/7 and both successful episodes overlap headline inflation;4/7 alarm months overlap. Lower classical FPR0.0694 versus0.2835 is a real different statistic, not proof of incremental forecast value. Endpoint acceleration requires CPI(t),CPI(t−12),CPI(t−24); historical paths need all observations their tests consume.",
 'core_inflation':"Context only; shared CPI family, no tested action threshold. The common calendar helper has headline/synthetic gap coverage; regressing that helper to positional shifting would be caught, so it is incorrect to assert all tests would pass. A separately pinned core reference and full source-dependency checks would strengthen future implementation coverage. An unrelated missing interior month is a warning, not automatic endpoint invalidity.",
 'brent':"Spot-price context, not a tradable return or a direct measure of inventories, shipments, production capacity, physical shortages or geopolitical mechanisms. Its loss must mark Brent unavailable and the global report degraded, while independent valid labour calculations remain usable.",
 'equities_gdp':"Stock over annualized flow is the stated conventional construction. Large quarter-to-quarter moves may reflect prices, issuance, coverage or revisions; the ratio alone does not identify their causes. Display same-quarter alignment, vintage and revision context. No alarm or timing probability was validated.",
 'profit_share':"After-tax NIPA corporate profits/GDP, both nominal SAAR in matching quarters. Not S&P EPS or a named company's margins. Accounting revisions and sector composition matter; neither its level nor a shared GDP denominator is an independently validated timing signal.",
}
for r in rows:
 key=r['indicator_id'];r['tier']=inventory[key]
 if key in study:
  r['threshold_provenance']=("Threshold/formula listed in ../phase_b_events/preregistration.json; integrity verified, independent chronology not established by its end-of-run hash. "
   "No per-indicator primary event was preregistered. primary_* and alternative_* preserve retrospectively selected descriptive records, not independent confirmation. "
   "Final classification is a prospective operating judgment; see MONITORING_AND_DECISION_SPEC.md.")
  r['multiple_comparison_exposure']=("54 distinct indicator×event×horizon combinations,162 split rows;11 cells have observed zero false alarms, largest n=3. "
   "No multiplicity-adjusted or causal finding. Complete grid: ../phase_b_events/indicator_event_metrics.csv. "
   "Selected primary-event assignment was not preregistered; all displayed counts are descriptive.")
 if key in limitations:r['known_defects']=limitations[key]+" Evidence: ../PHASE_B_event_validation.md; ../phase_b_events/indicator_event_metrics.csv; ../consolidation/evidence/R8_implementation_audit.md (qualified by this final specification)."
 if r['tier'] in {'review_flag','watch','context'}:
  r['retirement_criterion']=review_rule
  r['retirement_reachability_years']='not a forecast or gate; historical-rate extrapolation in consolidation suggested20 alarms would take median~148 years across8 rows (range~89–393), with large uncertainty'
 if r['tier']=='review_flag':
  r['action_on_trigger']='PROPOSED, NOT IMPLEMENTED: record the observed crossing; request human diagnostic review only after the next distinct source release confirms the condition. Evaluate that confirmation policy separately; it inherits no historical hit rate. No trade, allocation or personalized recommendation.'
 elif r['tier']=='watch':
  r['action_on_trigger']='PROPOSED, NOT IMPLEMENTED: explain the observation and alternative event records in the periodic review. A crossing alone triggers no financial action or claimed forecast. Archive monthly research states regardless of display tier.'
 elif r['tier']=='context':
  r['action_on_trigger']='Context only: describe the observed level/change and its source limits. No crossing alert, market-safety classification or allocation. Any numeric threshold retained elsewhere in this row is historical metadata only.'
  r['retirement_reachability_years']='not_applicable_to_context; no active alarm-count gate'
 r['carried_from']='../consolidation/INDICATOR_CONTRACT.csv; final reconciliation004. Prior lineage: '+r['carried_from']

by={r['indicator_id']:r for r in rows}
by['inflation_acceleration']['threshold_rationale']='Historical2pp acceleration AND headline>=4% retained unchanged for audit; final role is descriptive context. It supplies no separately validated independent confirmation.'
by['credit_change']['consolidation_verdict']='DEMOTE_TO_WATCH_FINAL'
by['inflation_acceleration']['consolidation_verdict']='DEMOTE_TO_CONTEXT_FINAL'
by['nfci']['threshold_rationale']='Published index mean boundary (0 = historical average). Strict > is the declared comparator and has an explicit boundary test; it is not a calibrated recession probability.'
by['orig_cape']['threshold_rationale']='Context only. Retain the original <20 /20–30 />30 />35 ladder as research lineage, not an operational trigger. Its exact historical base rate is sensitive to stale earnings and the return-universe construction; broader-market sensitivities are not exact S&P repairs.'
by['orig_cape']['known_defects']+=(" Final clarification: any42.000708 value is the archived August2026 CP-proxy estimate, not a current official Shiller reading. "
 "Context role does not authorize displaying this stale splice as current CAPE; require clear date/proxy labeling and a separately sourced update before use.")
by['orig_cape']['confidence']='low for current level; descriptive historical context only'
by['orig_headline_minus_core']['action_on_trigger']='Inactive in the final proposed system. Do not derive an energy allocation from this historical threshold; the existing prototype is unchanged by this research specification.'
by['orig_headline_minus_core']['threshold_rationale']='Historical >0.5 pp headline-minus-core boundary retained for audit only. This difference is not the energy contribution or proof of supply-led rather than broad inflation; component weights and contributions are required.'
by['orig_headline_minus_core']['known_defects']=("Retired as an unsupported allocation policy. The original comparison subtracted separate return medians rather than measuring paired energy-minus-market returns. Correct pairing gives positive five-year excess in the original commodity-rich sample (10.70 pp across253 overlapping starts), which contradicts the simple claim that the measured cumulative edge was wholly given back. It does not prove a permanent energy allocation or formally falsify every possible use of energy. Sample, benchmark, horizon, investability and costs remain material; annualized attenuation likewise does not establish a timed trade. Headline-minus-core CPI also cannot isolate energy or causally identify supply shocks. See ../phase_c/quantitative_energy_tilt_sensitivity.csv and FINAL_RESEARCH.md section6.")
by['orig_headline_minus_core']['retirement_criterion']='Retired because this threshold does not support the proposed inflation-cause classification or energy-allocation action. Re-entry requires a separately fixed decision rule, correct component measurement, paired investable returns, declared horizon/baselines and costs, and suitable independent evidence. Positive historical paired excess alone neither certifies an allocation nor rejects every energy use.'

calendar=by['cand_cpi_calendar_completeness']
calendar.update({
 'display_name':'CPI calendar dependencies and gap visibility (engineering control)',
 'tier':'engineering_control','layer':'data_health',
 'question_answered':'Are the exact observations required by each declared calculation available, correctly dated and finite, and are other capture gaps visible?',
 'action_on_trigger':'PROPOSED, NOT IMPLEMENTED: mark only dependent calculations unavailable when a required input is missing/invalid; surface a global degraded-data banner and preserve valid independent rows. Report unrelated calendar gaps as warnings without discarding valid endpoint calculations.',
 'formula_plain':'Per calculation count missing/invalid required input dates. Headline/core YoY(t):t,t−12. Acceleration YoY(t)−YoY(t−12):t,t−12,t−24. Rolling windows, consecutive crossing states and historical path/onset outcomes require every observation actually consumed by that rule. Report interior calendar gaps separately.',
 'formula_machine':'required_missing = sum(not finite(value[date]) for date in declared_dependency_set); invalid if required_missing>0 or denominator<=0. Reindex to calendar before lagging; preserve NA; never shift a dropna-collapsed monthly series.',
 'units':'missing/invalid required observations per computation; separate gap-warning count',
 'threshold_value':'0','threshold_comparator':'gt',
 'threshold_rationale':'Engineering validity condition, not a fitted economic threshold: one missing required dependency invalidates that computation. An unrelated interior gap does not invalidate endpoint growth.',
 'threshold_provenance':'Final004 arithmetic/data-integrity specification. Requires deterministic dependency and regression tests, not predictive event validation.',
 'primary_event_definition':'not_applicable_engineering_control','alternative_event_definition':'not_applicable_engineering_control',
 'multiple_comparison_exposure':'Not a financial event-study candidate; it does not enlarge the54-combination macro grid. Validate using reference values, missing-required-endpoint cases, unrelated-gap cases, duplicate dates, invalid denominators and calendar-path cases.',
 'known_defects':'The consolidation proposed rejecting any gap in a13-month window and incorrectly claimed a common-helper positional regression could pass all existing tests. Endpoint YoY does not use every interior month; August2026 headline/core remain valid despite missing October2025. Acceleration additionally needs August2024 for that endpoint. A missing month can still invalidate a historical path/outcome window or crossing chain. Existing helper coverage is useful but not a complete source-lineage test suite. See ../pipeline/test_monitor.py and evidence/contract_validation.json.',
 'retirement_criterion':'Do not retire calendar identity merely because no recent error occurred. Review dependencies when formulas or source definitions change; maintain deterministic checks and visibly separate warning from computational invalidity.',
 'retirement_reachability_years':'not_applicable_engineering_control',
 'consolidation_verdict':'RECLASSIFY_AS_ENGINEERING_CONTROL_FINAL','confidence':'high for arithmetic requirements; future implementation unverified'})

for key in ['cand_policy_rate_impulse','cand_continuing_claims']:
 r=by[key]
 r['action_on_trigger']='No operational threshold, alert or financial action. Research candidate only; data acquisition and method design are separate future work, not implemented here.'
 r['threshold_provenance']='No adopted threshold. Any future definition and primary event/horizon must be fixed before its evaluation; secondary endpoints must also be declared and all reported.'
 r['threshold_rationale']='No operational threshold adopted. Candidate numerical definitions must be fixed before research evaluation; operational adoption requires evidence appropriate to the stated use. Do not import another series threshold or choose a favorable result after evaluation.'
 r['retirement_criterion']='Review annually whether a distinct question and feasible data remain. If not pursued after24 months, archive the proposal as dormant rather than imply evidence or active monitoring. No automatic promotion after a date or episode count.'
 r['multiple_comparison_exposure']='No final threshold/event result. Future financial-event evaluation enlarges the search space and must report its scope; do not import another series threshold or select the best endpoint after outcomes.'
 r['retirement_reachability_years']='not_tested'
by['cand_policy_rate_impulse']['known_defects']=("No final operational definition or unique predictive value is established. Define series, lookback, crossing/cooldown and one primary outcome/horizon before evaluation; if both recession-onset and equity-entry-loss outcomes are examined, name their confirmatory/exploratory status and publish both. Compare on identical eligible dates against calendar/non-alarm baselines and test added information beyond the existing curve, which already contains TB3MS. Prior repeated-level and first-crossing variants produce different episodes; do not retrospectively choose their best result. Evidence: ../phase_c/quantitative_tightening_sensitivity.csv.")
by['cand_continuing_claims']['question_answered']='Does continued insured unemployment add useful information beyond initial claims and the unemployment-rate gap? It is not itself a direct measurement of unemployment duration.'
by['cand_continuing_claims']['known_defects']=("No threshold or matched event study adopted. Acquire a dated, hashed official history before testing; capture whether it was available at each analysis date. Define one primary outcome/horizon and declared secondary outcomes before evaluation. Measure incremental information/operational utility beyond claims_rise and Sahm; unique alarm months alone do not establish incremental predictive value. Keep it within the labour family. Public source reference: https://fred.stlouisfed.org/series/CCSA.")

# Readable prose spacing only; identifiers, formulas and immutable evidence fields stay literal.
for r in rows:
 for f in ['known_defects','retirement_criterion','retirement_reachability_years','threshold_rationale','question_answered','action_on_trigger','independence_note']:
  r[f]=re.sub(r'(?<=[a-z])(?=[0-9−≥])',' ',r[f])
  r[f]=re.sub(r'(?<=[0-9])(?=[a-z])',' ',r[f])

# Preserve financial thresholds and all empirical fields exactly. No new backtest.
empirical=['primary_event_definition','primary_hits_over_alarms','primary_false_alarm_fraction',
 'primary_false_alarm_ci95','primary_median_lead_months','alternative_event_definition',
 'alternative_hits_over_alarms','alternative_false_alarm_fraction','classical_fpr','eligible_months',
 'holdout_hits_over_alarms','equity_drawdown_false_alarm_fraction']
for r in rows:
 if r['indicator_id']=='cand_cpi_calendar_completeness':continue
 for f in empirical+['threshold_value','threshold_comparator']:
  assert r[f]==original[r['indicator_id']][f],(r['indicator_id'],f)
assert Counter(r['tier'] for r in rows)=={'review_flag':2,'watch':5,'context':6,'retired':5,'candidate':2,'engineering_control':1}
assert len({r['indicator_id'] for r in rows})==21

with (FINAL/'INDICATOR_CONTRACT.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

metrics=pd.read_csv(REVIEW/'phase_b_events/indicator_event_metrics.csv')
joins=[]
for key,sid in study.items():
 r=by[key]
 for prefix,split,field in [('primary','all','primary_hits_over_alarms'),('alternative','all','alternative_hits_over_alarms'),('primary','holdout_2000plus','holdout_hits_over_alarms')]:
  event,h=re.match(r'(\w+)@(\d+)m',r[prefix+'_event_definition']).groups()
  s=metrics[(metrics.indicator==sid)&(metrics.event==event)&(metrics.horizon_months==int(h))&(metrics.split==split)]
  assert len(s)==1
  x=s.iloc[0];expected=f'{int(x.episode_hits)}/{int(x.n_alarm_episodes)}' if x.n_alarm_episodes else 'undefined_n0'
  assert r[field]==expected,(key,field,r[field],expected)
  joins.append(dict(indicator_id=key,event=event,horizon_months=int(h),split=split,contract_field=field,value=expected))
with (FINAL/'evidence/contract_empirical_joins.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(joins[0]));w.writeheader();w.writerows(joins)

# Simple reference examples: endpoint identity versus path completeness.
p=pd.period_range('2024-08','2026-08',freq='M')
s=pd.Series(range(100,125),index=p,dtype=float);s.loc['2025-10']=float('nan')
assert pd.notna(s['2026-08']/s['2025-08']-1)
assert pd.notna((s['2026-08']/s['2025-08']-1)-(s['2025-08']/s['2024-08']-1))
assert s.loc['2025-08':'2026-08'].isna().any()
broken=s.copy();broken.loc['2025-08']=float('nan');assert pd.isna(broken['2026-08']/broken['2025-08']-1)
assert pd.isna((broken['2026-08']/broken['2025-08']-1)-(broken['2025-08']/broken['2024-08']-1))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
result=dict(schema_fields=len(fields),rows=len(rows),unique_ids=21,inventory=dict(Counter(r['tier'] for r in rows)),
 active_financial_rows=13,tested_historical_alarm_definitions=8,proposed_review_or_watch_threshold_definitions=7,
 empirical_join_checks=len(joins),empirical_join_failures=0,financial_thresholds_and_empirical_fields_unchanged=True,
 calendar_dependency_examples_passed=5,implementation_changed=False,
 source_sha256=sha(SOURCE),final_contract_sha256=sha(FINAL/'INDICATOR_CONTRACT.csv'),
 validation_scope='Research contract consistency only; no future monitoring software has been implemented or certified.')
(FINAL/'evidence/contract_validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
