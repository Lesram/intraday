"""Build the indicator contract from the independently sealed event study.
Thresholds are economic priors, never optimized against outcomes.
"""
from pathlib import Path
import csv
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]

DEFINITIONS=[
 # id, title, tier, source IDs, unit, formula, threshold, comparator, study ID, event, horizon
 ("claims_rise","Initial claims above trailing low",1,"ICSA","%","100 × (4-week mean ICSA / minimum of its trailing 52 weekly means − 1); require all 52 averages; sample monthly for historical validation",20,"ge","claims_rise_20pct","recession_present_or_onset",12),
 ("sahm","Sahm unemployment rule",1,"SAHMREALTIME","pp","Published real-time Sahm indicator: 3-month unemployment average minus its minimum over the preceding 12 months",0.5,"ge","sahm_050","recession_present_or_onset",12),
 ("credit_change","Baa credit-spread widening",1,"BAA10Y","pp","Last BAA10Y observation in completed month minus last observation three calendar months earlier",1,"ge","baa_widening_100","recession_present_or_onset",12),
 ("credit_level","Baa credit-spread level",2,"BAA10Y","pp","Moody's Baa yield minus 10-year constant-maturity Treasury yield; latest daily observation",3,"ge","baa_level_300","recession_present_or_onset",12),
 ("nfci","Financial conditions",2,"NFCI","index","Chicago Fed NFCI published weekly; 0 is historical average, positive is tighter than average",0,"gt","nfci_positive","recession_present_or_onset",12),
 ("curve","10-year minus 3-month yield",2,"GS10|TB3MS","pp","Monthly GS10 Treasury yield minus TB3MS discount-basis bill yield; proxy differs from daily T10Y3M",0,"lt","curve_inverted","recession_onset",24),
 ("inflation","Headline inflation",2,"CPIAUCSL","%","100 × (CPIAUCSL at month t / CPIAUCSL at exactly t−12 calendar months − 1); never positional pct_change on dropped missing months",4,"ge","inflation_400","equity_entry_loss_20",12),
 ("inflation_acceleration","Broad inflation acceleration",2,"CPIAUCSL","pp","Calendar headline CPI YoY minus its value 12 calendar months earlier; threshold additionally requires headline CPI YoY ≥4%",2,"ge","inflation_surge","equity_entry_loss_20",12),
 ("core_inflation","Core inflation",3,"CPILFESL","%","100 × (CPILFESL at t / CPILFESL at exactly t−12 calendar months − 1)",None,"","","",None),
 ("brent","Brent spot oil",3,"DCOILBRENTEU","USD/bbl","EIA Europe Brent spot price; latest daily observation; spot-price context, not an investable total return",None,"","","",None),
 ("equities_gdp","Corporate equities relative to GDP",3,"NCBEILQ027S|GDP","%","100 × (NCBEILQ027S in USD millions / 1000) / GDP in USD billions SAAR, joined on the same quarter",None,"","","",None),
 ("profit_share","After-tax corporate profit share",3,"CPATAX|GDP","%","100 × CPATAX / GDP, same quarter and nominal USD billions SAAR; broad NIPA corporations, not S&P per-share earnings",None,"","","",None),
]


def fmt(v): return "unavailable" if pd.isna(v) else f"{100*v:.1f}%"


def performance(table,study,event,horizon):
    if not study:
        return ("Not estimated: context indicator has no alarm/event claim (n=0 tested triggers).", "Not applicable: no threshold fires; no false-positive denominator. It may not be promoted to a trigger without a preregistered event study.")
    subset=table[(table.indicator==study)&(table.event==event)&(table.horizon_months==horizon)]
    descriptions=[]; falses=[]
    for split,label in [("all","Full"),("holdout_2000plus","Holdout 2000+")]:
        selected=subset[subset.split==split]
        if selected.empty: continue
        r=selected.iloc[0]
        lead="unavailable" if pd.isna(r.lead_months_median) else f"{r.lead_months_median:g}m ({r.lead_months_min:g}–{r.lead_months_max:g})"
        descriptions.append(f"{label} {r.first_signal_month}–{r.last_signal_month}: {int(r.episode_hits)}/{int(r.n_alarm_episodes)} matured alarm episodes; hit {fmt(r.episode_hit_rate)}; median lead {lead}; monthly unconditional event rate {fmt(r.unconditional_event_probability)} across {int(r.eligible_months)} eligible months")
        falses.append(f"{label}: {int(r.episode_false_alarms)}/{int(r.n_alarm_episodes)} episode false alarms = {fmt(r.episode_false_alarm_fraction)} (Wilson 95% {fmt(r.false_alarm_wilson_95_low)}–{fmt(r.false_alarm_wilson_95_high)}); classical monthly FPR {int(r.classical_fp_months)}/{int(r.classical_fp_months+r.classical_tn_months)} = {fmt(r.classical_fpr)}")
    return (f"Event: {event}, horizon {horizon}m. "+". ".join(descriptions)+". Diagnostic event includes recession already in progress where named; no forecast claim. Revised-history chronological holdout, not vintage-real-time proof.",". ".join(falses)+". Monthly windows overlap; episode observations remain only approximately independent.")


def main():
    table=pd.read_csv(ROOT/"phase_b_events/indicator_event_metrics.csv")
    correlations=pd.read_csv(ROOT/"phase_b_events/redundancy.csv")
    rows=[]
    names={r[8]:r[1] for r in DEFINITIONS if r[8]}
    questions={
        "claims_rise":"Have unemployment-insurance claims deteriorated materially from their recent low?",
        "sahm":"Has unemployment risen enough to warrant a recession-state review?",
        "credit_change":"Have corporate funding conditions worsened rapidly over three completed months?",
        "credit_level":"How elevated is the current Baa funding premium relative to Treasuries?",
        "nfci":"Are broad financial conditions tighter than the index's historical average?",
        "curve":"Does the monthly term structure warrant a longer-horizon recession watch?",
        "inflation":"Is consumer-price inflation in the predeclared elevated-inflation regime?",
        "inflation_acceleration":"Is inflation both elevated and accelerating, rather than simply remaining high?",
        "core_inflation":"How much inflation pressure remains when food and energy are excluded?",
        "brent":"How is the current energy-price shock evolving?",
        "equities_gdp":"How large is corporate equity value relative to annual domestic output?",
        "profit_share":"How elevated are broad corporate profits relative to GDP, independently of per-share index earnings?",
    }
    history={"ICSA":"1967-01-07; transformed after full 55-week warm-up", "SAHMREALTIME":"1959-12; source-defined real-time index", "BAA10Y":"1986-01-02; consistent yield-spread proxy, not OAS", "NFCI":"1971-01-08; model and history revised", "GS10|TB3MS":"1953-04; monthly discount-bill proxy", "CPIAUCSL":"1947-01; YoY from1948; October2025 missing", "CPILFESL":"1957-01; YoY from1958; October2025 missing", "DCOILBRENTEU":"1987-05-20; spot-price history", "NCBEILQ027S|GDP":"1947Q1 common quarterly coverage; accounting definitions/revisions matter", "CPATAX|GDP":"1947Q1; NIPA accounting history revised"}
    for key,name,tier,sids,unit,definition,threshold,comp,study,event,horizon in DEFINITIONS:
        rate,fpr=performance(table,study,event,horizon)
        freq="Quarterly; typically 60–90 days after quarter end; major historical revisions" if "GDP" in sids else "Daily business days; 1–5 business-day publication delay; occasional corrections" if sids in ("BAA10Y","DCOILBRENTEU") else "Weekly; claims about 5 days, NFCI about 5 days after observation; revisions possible" if sids in ("ICSA","NFCI") else "Monthly; first or second following-month release; CPI seasonal factors revise, SahmREALTIME retains contemporary unemployment basis"
        threshold_text="No action threshold: context only" if threshold is None else f"{'<' if comp=='lt' else '>' if comp=='gt' else '≥'} {threshold:g} {unit}"
        if key=="inflation_acceleration":threshold_text+=" AND headline CPI YoY ≥4%"
        rationale="Published convention (Sahm 0.5; curve 0; NFCI 0) or round economic prior (claims20%, Baa3pp/1pp, CPI4%/2pp acceleration). Fixed before outcomes in phase_b_events/preregistration.json; never selected to maximize hit rate."
        independence="No validated full correlation matrix for this context measure; no equal-weight composite or independence claim. Equities/GDP and profit/GDP share the GDP denominator; headline and core CPI overlap."
        if study:
            independence="See phase_b_events/redundancy.csv: pairwise binary-alarm phi and Jaccard with n and coverage; common macro drivers preclude counting correlated flags as independent votes. Claims/Sahm share labor exposure; Baa/NFCI share credit exposure; headline/acceleration share CPI."
            peers=correlations[(correlations.indicator_a==study)|(correlations.indicator_b==study)].copy()
            peers["absolute_phi"]=peers.alarm_phi_correlation.abs()
            for _,pair in peers.sort_values("absolute_phi",ascending=False).head(2).iterrows():
                other=pair.indicator_b if pair.indicator_a==study else pair.indicator_a
                independence+=f" Largest absolute measured phi: {names.get(other,other)} {pair.alarm_phi_correlation:+.3f}, n={int(pair.n_months)} monthly observations, {pair.first_month}–{pair.last_month}."
        action=("Request a diagnostic review after confirmation on next source release; record recession already underway separately. No position or price action." if tier==1 else "Watch and explain in monthly report; crossing alone changes no allocation or trading rule." if tier==2 else "Context only, no action; inform long-horizon scenario discussion, never timing.")
        kill=("Retire from alerts if after 20 NEW nonoverlapping matured alarm episodes its preregistered event association fails to exceed matched nonalarm baseline, or the alert produces no documented distinct review decision over 24 monthly audits. Suspend immediately on source/definition break; do not retune on the failed sample." if tier<3 else "Retire if consistent source disappears, accounting definition breaks without bridge, or 24 monthly audits show no distinct scenario information. No historical trigger skill claimed.")
        sampling="Operational values use latest available source observations; monthly derivations require completed periods. Historical performance uses monthly threshold crossings and coarse release lags, not every daily/weekly flag. Prospective scores use final acquired state in closed UTC months; exact publication times are unknown until separately captured."
        if study:rate+=" Monthly-validation record only: native-frequency transient flags do not inherit this hit rate."
        rows.append(dict(id=key,name=name,tier=tier,definition=definition,source="FRED; underlying BLS/DOL/Chicago Fed/Moody's/BEA/Federal Reserve/EIA as identified on series page; free CSV, no API key required",series_ids=sids,source_url=" | ".join("https://fred.stlouisfed.org/series/"+sid for sid in sids.split("|")),frequency_and_lag=freq,revision_behaviour="Current-source revisions; historical tests use supplied 2026-09-19 snapshot. SAHMREALTIME retains its contemporary unemployment basis; other histories may revise. Historical release calendars unavailable; conservative lag in event study. Archive new observations prospectively.",history=history[sids],what_it_is_for=questions[key],thresholds=threshold_text,threshold_selection=rationale if threshold is not None else "No fitted threshold",measured_base_rate=rate,false_positive_rate=fpr,independence=independence,action_it_informs=action,kill_criterion=kill,unit=unit,threshold_value="" if threshold is None else threshold,threshold_comparator=comp,condition_id="inflation" if key=="inflation_acceleration" else "",condition_threshold="4" if key=="inflation_acceleration" else "",study_indicator_id=study,event_definition=event,horizon_months="" if horizon is None else horizon,evidence_as_of="2026-09-19",evidence_file="phase_b_events/indicator_event_metrics.csv" if study else "PHASE_B_independent_regime_analysis.md",sampling_note=sampling))
    with (ROOT/"indicators.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(f"Wrote {len(rows)} indicator contracts; {sum(r['tier']==1 for r in rows)} diagnostic Tier1 flags")


if __name__=="__main__":main()
