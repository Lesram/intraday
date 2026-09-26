from pathlib import Path
import sys
import pandas as pd

P=Path(__file__).resolve().parent
ROOT=P.parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import factbase as fb

def table(d):
    return d.round(2).to_markdown(index=False)

now=pd.read_csv(P/'current_state.csv')
sel=pd.read_csv(P/'selected_episodes.csv')
ret=pd.read_csv(P/'return_comparisons.csv')
primary=ret[ret.specification=='expanding_primary']
main=primary[~primary.asset.str.startswith('sector')]
sectors=primary[primary.asset.str.startswith('sector')]
sensitivity=ret[(ret.asset=='US_market_total')&(ret.metric=='real_cumulative_pct')]
unc=pd.read_csv(P/'nonoverlap_baseline_uncertainty.csv')
defects=pd.read_csv(P/'cpi_fix_verification.csv')
pr=pd.read_csv(P/'percentile_history_audit.csv')
cols=['asset','horizon_years','episode_n','episode_median','episode_minimum','episode_maximum',
      'episode_negative_pct','unconditional_n','unconditional_median','median_excess_pp']
supp=[]
for k in ['VIXCLS','BAMLH0A0HYM2','DCOILBRENTEU','SAHMREALTIME','GFDEGDQ188S','FEDFUNDS']:
    s=fb.fred(k).loc[:'2026-09-18']
    supp.append(dict(series=k,reference_date=str(s.index[-1].date()),value=s.iloc[-1]))
pd.DataFrame(supp).to_csv(P/'supplemental_current_state.csv',index=False)

report=f'''# Phase B — Independent regime and return analysis

**Blind version; assessment date 2026-09-19; market cutoff 2026-09-18.** This report was written before reading Brief 001, claims, verdicts, analogs, regime code, or processed regime outputs. README and STATE were deliberately not read. The independent event study is recorded under `review/phase_b_events/`; this report supplies the regime and return component. All numbers below come from the accompanying reproducible outputs and the explicitly identified frozen input files, not a live market feed.

## Plain answer

The observed state combines exceptionally high corporate equity value relative to US output, unusually narrow corporate credit differentiation, modest industrial growth, and inflation above 3%; it does not show contemporaneous broad financial stress. The independent historical screen supports a wide set of outcomes, not a crash forecast. Across eight selected, nonoverlapping five-year episodes, US equity **total** returns over one year ranged from **−27.9% to +23.5% after inflation**, with median **+4.6%**; over five years they ranged from **−24.1% to +129.8%**, median **+24.6% cumulative**. Those are historical scenario observations, not calibrated forecast intervals. Omitting the valuation dimension changes the five-year median to **+48.1%**, versus a **+42.9%** unconditional monthly-start median, so even the sign of relative underperformance is specification-sensitive. The eight-episode median is not unusual in randomly selected eight-episode, nonoverlapping reference sets. Inflation, recessions, and crisis timing require their own monitored evidence; valuation supplies no reliable date.

## What the inputs actually support

The supplied instruction says the dashboard CPI defect was fixed. **The actual file is not fixed.** Its `yoy()` function still executes `s.pct_change(months) * 100`. This was tested by compiling only the function's syntax tree, so importing the dashboard could not overwrite files outside review. CPI and core CPI both omit October 2025. The supplied UNRATE series also omits that month. A calendar-preserving monthly index and an exactly 12-month denominator are necessary; if that denominator is absent, the result is missing, not a nearby month's growth rate. Synthetic missing-month and missing-denominator tests passed.

Latest CPI comparisons, reference August 2026, source FRED `CPIAUCSL` and `CPILFESL`, captured 2026-09-19:

{table(defects[defects.date=='2026-08-01'][['series','calendar_yoy','dashboard_yoy','difference_pp','row_lag_base_date','correct_base_month']])}

The percentile defect is methodological, not a sortable cosmetic issue. A row ranked on three years cannot be compared with another ranked on forty years without explicitly qualifying the different histories. Latest values are 2026-09-17; sample sizes below are native-frequency observations, not independent samples:

{table(pr)}

The own-history and common-history columns deliberately show both definitions; neither implies a universal economic percentile. The main screen uses one common historical start for all its explanatory dimensions.

Self-correction: the first default `rg --files` inventory appeared to omit Ken French archives because ignored files were hidden. A subsequent explicit inventory found them; they were safely extracted under `review/inputs/`. This report uses the provided archives, not an undocumented replacement download. Both series end July 2026. Shiller's supplied earnings and dividend columns stop June 2023, and PE10 stops September 2023. No current Shiller CAPE or recent S&P total return was manufactured from those blanks.

## Regime dimensions and current readings

Definitions are transportable levels and calendar changes:

- **Corporate equity/GDP:** `100 × (NCBEILQ027S / 1000) / GDP`, percentage points. This is a valuation/context proxy, not an S&P P/E; US national equity claims and US output have different scopes, including foreign earnings and changing corporate composition.
- **Inflation:** `100 × (CPI_t / CPI_(t−12 calendar months) − 1)`.
- **Production growth:** the same formula for INDPRO.
- **Credit differentiation:** monthly Moody's Baa yield minus Aaa yield, percentage points. Both are corporate yields; this is not HY OAS and not a direct default probability.
- **Yield-curve slope:** monthly GS10 minus TB3MS, percentage points.
- **Ex-post real bill yield:** TB3MS minus calendar CPI YoY. This is a transparent backward-looking proxy; it is not an expected real risk-free rate.

Current snapshot, as of September 18; GDP/equity reference `2026-04` means **2026 Q2**, not an April-only reading. Percentiles use the strictly earlier common monthly decision history starting July 31, 1954, with **866** observations:

{table(now)}

The latest supplemental observations show the important calendar mismatch between slow context and fast prices:

{table(pd.DataFrame(supp))}

Source keys: VIXCLS is Cboe VIX (index points); BAMLH0A0HYM2 is HY OAS (%); DCOILBRENTEU is Brent ($/barrel); SAHMREALTIME is percentage-point Sahm gap; GFDEGDQ188S is federal debt/GDP (%); FEDFUNDS is effective fed funds (%). Brent at $130.80 on September 15 is a material current shock that the six-dimensional monthly screen does **not** encode. No exact historical twin is asserted. The combination of low VIX and narrow spreads measures priced calm, not proof of safety.

## Screen design, selected before return inspection

Primary specification: equal-weight root-mean-square distance between six **strictly prior expanding-history** percentiles. For candidate month t, its percentile CDF contains only months earlier than t; the current CDF contains only months earlier than September 18, 2026. The first 120 months are a training minimum, giving candidate dates July 1964 onward. No return outcome enters distance, weights, thresholds, or selection.

To avoid pretending observation dates were publication dates, monthly inputs become available the next month on day 16; quarterly inputs become available in the fifth month after the quarter's start, on day 16. These are uniform approximations, not historical release calendars. Missing readings retain the last available value; missing source dates are reported. **This is a revised-data, approximate-availability historical simulation, not a genuine real-time-vintage backtest.** Vintage revisions, publication-date variation, repeated quarterly readings, and structural change remain material limitations. Periods before 1964 have no chance to be selected under this design.

Eligible candidate dates end August 2021 so a five-year outcome can in principle mature by the September 2026 cutoff. Sort by explanatory distance; accept the nearest date, then successive dates at least 60 calendar months from every accepted date, until eight dates are selected. Forward intervals therefore do not overlap, including the exactly 60-month-separated 2000 and 2005 pair. Economic independence is still not guaranteed. Eight is a declared descriptive sample budget, not a discovered optimum. The eighth candidate is considerably less similar than the first; nearest-four sensitivity is also supplied.

Primary episodes (nearest-first):

{table(sel[sel.specification=='expanding_primary'][['nearest_rank','date','distance']+list(now.indicator)])}

Sensitivity designs: (1) fixed economic units **100 pp equity/GDP, 3 pp inflation, 5 pp IP growth, 0.5 pp Baa−Aaa, 1.5 pp curve, 3 pp real bill**, equal weights; these round scales were not fitted to returns; (2) omit valuation to expose its influence; (3) full-sample ranks as a deliberately biased diagnostic, not the primary result. Full selected dates and explanatory values are in `phase_b/selected_episodes.csv`. The fixed-scale screen's leading dates are 2018-03 and 2000-03; it also includes 2007-11, 1967-12, 2013-02, 1993-11, 1973-05 and 1988-11. Absolute inflation similarity and relative historical rarity answer different questions; their disagreement is information, not a reason to select the prettier return result.

## Forward asset returns and unconditional reference

US market = Ken French `Mkt-RF + RF`, compounded; bills = compounded RF; sectors = twelve value-weighted industry total-return portfolios. A horizon begins with the next calendar month's return, after the episode's month-end. Real return is `(1 + nominal return) / (CPI_endpoint / CPI_start) − 1`, using exact endpoint calendar months and leaving any missing endpoint uncomputed. All percentages below are **cumulative**, not annualized. Fees and taxes are excluded.

Unconditional comparison uses every monthly start in the same July 1964–August 2021 candidate calendar, separately requiring complete asset/horizon data. Thus it controls the broad era; it is **not** the entire 1926–2026 history. Its 684–686 rows overlap heavily and must not be presented as hundreds of independent five-year experiments. Every primary return panel has **n=8** complete episodes.

Nominal returns (sample range is minimum–maximum, not a confidence interval):

{table(main[main.metric=='nominal_cumulative_pct'][cols])}

Real returns:

{table(main[main.metric=='real_cumulative_pct'][cols])}

**Gold is spot-price return**, using monthly average price marks, excluding storage and insurance. It is not mislabeled total return or a futures-strategy return. The 1964 observation includes a fixed-price monetary regime; `small_sample_and_gold_sensitivity.csv` separately excludes pre-August-1971 starts (n=7). **No bond total-return series is present in the allowed inputs.** Treasury yields alone cannot establish bond-holder returns; bond winners/losers remain unavailable. International total returns and currency-hedged variants are likewise not established here.

US market real-return sensitivity:

{table(sensitivity[['specification','horizon_years','episode_n','episode_median','episode_negative_pct','median_excess_pp']])}

The sign of five-year excess return reverses when valuation is omitted. This is stronger evidence against a confident mechanical regime forecast than any one selected historical analogy is evidence for it.

## Sector winners and losers, with the base rate kept visible

The CSVs contain every episode, twelve industries, each horizon, nominal and real returns. This compact panel gives real medians, empirical ranges, and difference from each industry's **own unconditional median**, so a high-return industry is not automatically called a conditional winner:

{table(sectors[sectors.metric=='real_cumulative_pct'][['asset','horizon_years','episode_n','episode_median','episode_minimum','episode_maximum','median_excess_pp']])}

Illustrations, not validated sector selection rules: durables have a one-year median real return of −14.4%, about 19.0 pp below their own baseline; health has a three-year median of +42.4%, 18.6 pp above its baseline; business equipment has a five-year median of +48.7%, 17.3 pp above its baseline. Business equipment's five-year real sample range is nevertheless −69.0% to +246.5%. Nominal same-date excess returns versus the broad market are separately provided in `sector_relative_returns.csv`. Twelve sectors × three horizons × several screens create substantial multiple-comparison risk. No sector allocation recommendation follows.

## Can the historical result be distinguished from ordinary sampling noise?

For each broad-market horizon/return type, 5,000 random-order greedy selections attempted to draw eight eligible start months at least 60 months apart; successful sets and their median distributions are below. Seed = 20260919; unsuccessful draws that could not fill eight were excluded and counted implicitly by the reported successful totals. The greedy method changes marginal date probabilities; these are **descriptive matched-size reference distributions**, not exact randomization p-values or evidence of causality. They do, however, prevent comparing eight independent episodes against an artificially precise overlapping baseline.

{table(unc)}

None of the observed medians is outside the simulated central 95% range. The real five-year median sits near the 12th percentile of reference medians, not an overwhelming outlier. Stronger evidence would require pre-registered thresholds/weights, historical release vintages, more independent cycles, held-out future observations, stability to economic scales and valuation omission, and errors assessed across the complete family of tested asset/horizon claims. No threshold was optimized to improve these outcomes.

## What leads what: independent event-study component

The separate blind study under `phase_b_events/` preregisters round candidate thresholds, uses an availability lag, counts alarm episodes and non-alarm months, separates pre-2000 training from 2000+ pseudo-out-of-sample observations, and distinguishes strictly future onsets from diagnosis of events already underway. Full definitions and denominators live in that study's report and `indicator_event_metrics.csv`.

- A negative monthly 10y−3m curve precedes recession onset within 24 months in **6/8** eligible alarm episodes; **2/8 (25%)** are false alarms. For post-2000 observations: **3/4** hits, **1/4** false alarms. Median lead among full-sample hits is **9.5 months**, range **5–16**; the false-alarm 95% interval is approximately **7–59%** overall and **5–70%** in holdout. This is a recession watch signal with broad uncertainty, not an equity sell date.
- Claims up at least 20% from their stated prior low precede a *new* recession in the next 12 months in **4/8** episodes (holdout **1/3**). Allowing recession already in progress increases apparent success to **9/13** (holdout **3/5**). Reporting only that larger number would disguise diagnosis as prediction.
- Sahm at least 0.5 pp has strictly future recession-onset hits **1/4** (holdout **0/2**), versus current-or-next-year recession diagnosis **8/11** (holdout **2/4**). Among diagnostic hits, detection occurs a median **4 months after** recession onset. It is useful context about deterioration, not a promised lead indicator.

No candidate is established as a dependable advance equity-crash trigger. False-alarm fraction `false alarms / alarms` and classical false-positive rate `FP / (FP+TN)` answer different questions; the event-study CSV supplies both rather than calling precision a false-positive rate. Sample sizes, full definitions, missing months, right-censoring, overlapping monthly windows, and revised-history limits matter as much as headline hit rates.

## Reproduction and source record

Run `review/phase_b/independent_regime.py`, then `review/phase_b/uncertainty.py`, then `review/phase_b/write_report.py`, using Python with pandas, numpy and tabulate. The scripts write only the phase-B review directory and this report. Input hashes are in `phase_b/input_hashes.json`; validation results are in `phase_b/validation.json`; the root review log seals the complete blind output before Phase C. These scripts do not mutate the trading platform, invoke its live components, or require its settings.

| Input | Source and coverage used | Evidence location |
|---|---|---|
| CPI, production, rates, corporate yields, equity/GDP, fast-state supplements | Federal Reserve Bank of St. Louis [FRED](https://fred.stlouisfed.org/), exact series IDs above; original publisher definitions retained; bundles captured 2026-09-19 | `data/raw/fred_bundle_2026-09-19.json`, `fred_bundle2_2026-09-19.json` |
| Equity, bill and sector total returns | [Ken French Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html), monthly July 1926–July 2026; retrospective revisions possible | `review/inputs/F-F_Research_Data_Factors.csv`, `12_Industry_Portfolios.csv` |
| Gold monthly spot averages | supplied LBMA/MeasuringWorth mirror provenance in `data/SOURCES.md`; August 2026 endpoint | `data/raw/gold-prices_main_data_monthly.csv` |
| CPI bug/source semantics | original dashboard function, isolated AST evaluation; no import side effects | `scripts/dashboard.py`, `phase_b/cpi_fix_verification.csv` |
| Expanding screen, all return rows and uncertainty | this independent derivation, September 2026 information cutoff | every CSV under `review/phase_b/` |

The original source bundles and supplied mirrors are accepted as research inputs, not independently audited market databases. A production monitor must validate publisher metadata, observation vintage, unit changes and release timing before interpreting alerts. This limitation does not erase the reproducible arithmetic errors or the wide outcome dispersion established here.
'''
(ROOT/'review/PHASE_B_independent_regime_analysis.md').write_text(report)
print('Wrote blind Phase B report')
