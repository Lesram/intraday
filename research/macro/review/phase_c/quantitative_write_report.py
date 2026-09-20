from pathlib import Path
import json, hashlib
import pandas as pd

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
def read(name):return pd.read_csv(OUT/('quantitative_'+name+'.csv'))
def tab(d):return d.round(3).to_markdown(index=False)
screen=read('screen_selections');maturity=read('original_episode_maturity');sample=read('original_sample_sensitivity')
cape=read('cape_sensitivity');credit=read('tightening_sensitivity');profit=read('profit_mean_reversion')
con=read('concentration_forward_returns');energy=read('energy_tilt_sensitivity')
rows=[
 ('Original screen arithmetic','AGREE','Full-sample scores reproduce within0.00005;2007/2021 remain leading clusters under several expanding definitions.'),
 ('Exact analog hierarchy and four-month uniqueness','PARTIALLY AGREE','Expanding ranks alter dates/order;four months becomefive,stilltwo clusters;fullyindependentB selectsdifferent episodes.'),
 ('13 independently selected/mature episodes','DISAGREE','Twelve algorithmic starts plus manuallyadded2000anchor;onlyseven disjoint5ystarts,sixmature.'),
 ('Gold+56% and energy+57% five-year medians','DISAGREE','TruncatedNov2021 enters5yaggregate;excluding it changesmedians to25.2%gold and36.0%energy.'),
 ('Gold45pp excess versus own base rate','DISAGREE','Comparator includes1871fixed-pricehistory;floating-era mean rises13.4→26.0%;sample-era choicechangesexcess.'),
 ('CAPE41.3 versus42 reflects conflicting splices','DISAGREE','Different price/CPI dates:partialSeptember41.254 versusAugust42.001;sameearningsproxy.'),
 ('CAPE is extremely elevated','PARTIALLY AGREE','Persists undertestedEPSscenarios,butaggregateNIPAproxy isnotobservedS&Pearnings;precisecomparisonsnotverified.'),
 ('CAPE>=30 five-year baseline−13%/72% is current','DISAGREE','ReturnsstopJune2023;n68not77;updatedhybridn89 gives−5.34%/55.06%;broadmarketonly+3.71%/49.44%.'),
 ('Tightening into calm credit means no crash','DISAGREE','Original7/7reproduces;reasonable1pp/12mfirst-crossdefinitionincludes2000crash among4calmstarts.'),
 ('Profit share untested / old6% equilibrium','PARTIALLY AGREE','Meanreversionwithinepochs,changingequilibria;pre2000modelfailsmodernholdoutversuspersistence.'),
 ('Index concentration deserves monitoring','AGREE','Counts×average-size gives100yindustryweightproxy;BusEq43.19%July2026versus34.94%March2000.'),
 ('Concentration determines future sector loser','CANNOT VERIFY','Onlytwo nonoverlapping5yhigh-concentrationstarts;dominantindustrylostonceandwononce;notop10history.'),
 ('Energy edge disappears by five years','DISAGREE','Differenceofmedians isnotmedianpairedexcess;original5y pairedmedian+10.70pp,58.5%beatmarket.'),
 ('Model thresholds all tested and implemented','DISAGREE','No completeFPRvalidation;codeomitsHYalternative,relativeclaimsandsustainedcondition;killlogicpartlyreversed.'),
]
lead=pd.DataFrame(rows,columns=['finding','verdict','reason'])
# Expand compact machine-oriented drafting text for readable published table.
lead['reason']=lead['reason'].str.replace('within0.','within 0.',regex=False)
lead.to_csv(OUT/'quantitative_adjudication_table.csv',index=False)
selected_credit=credit[(credit.split=='all')&(credit['calm'])&(
 ((credit.onset=='original_repeated_level')&(credit.calm_rule=='full_pct20'))|
 ((credit.onset=='TB3MS_cross_0.25pp_6m')&(credit.calm_rule=='prior_pct20'))|
 ((credit.onset=='TB3MS_cross_1.0pp_12m')&(credit.calm_rule=='prior_pct20'))|
 ((credit.onset=='FEDFUNDS_cross_0.5pp_6m')&(credit.calm_rule=='absolute')))]

report=f'''# Phase C quantitative adversarial replication

**Written after the Phase A/B seal in `review/LOG.md` (2026-09-20T04:51:13Z).** This report does not revise the blind findings. It re-executes the prior screen, audits its return aggregation, and supplies sensitivity tests for work-order attacks1–6. Assessment cutoff remains2026-09-18. All source data are the supplied capture; no live market series replaced it.

## Adjudication lead table

| Finding | Verdict | Main reason |
|---|---|---|
| Original screen arithmetic | AGREE | Scores reproduce to rounding; 2007/2021 remain important under several expanding definitions. |
| Exact analog hierarchy and four-month uniqueness | PARTIALLY AGREE | Dates/order depend on dimensions and normalization; expanding conjunction gives five months in the same two clusters. |
| Thirteen independent, mature, automatically selected episodes | DISAGREE | Twelve screen starts plus a manually added 2000 anchor; at most seven disjoint five-year intervals, six mature. |
| Gold+56% and energy+57% five-year medians | DISAGREE | Removing the incompletely observed November2021 row changes medians to+25.2% and+36.0%. |
| Gold45pp excess relative to a suitable base rate | DISAGREE | The comparator includes non-investable/fixed-price history; changing the base era materially reduces the excess. |
| CAPE41.3 versus42.0 means conflicting splices | DISAGREE | Same proxy, different dates: partial September versus August; the screen mixes September CAPE with August features. |
| Extreme equity valuation | PARTIALLY AGREE | Tested proxy variants remain elevated, but aggregate NIPA profits are not observed S&P earnings. |
| CAPE≥30 five-year−13%/72% baseline is current | DISAGREE | Return history stops June2023; actual n=68. Updating the outcome series changes the inference materially. |
| Tightening into calm credit precludes a crash | DISAGREE | Original7/7 is reproducible but a reasonable first-crossing alternative includes the2000 crash. |
| Profit share should revert to an old6% norm | DISAGREE | Within-era reversion coexists with shifted levels; the frozen old model loses badly to persistence after2000. |
| Concentration deserves separate monitoring | AGREE | A100-year industry-capitalization proxy is available from the raw French file and is elevated today. |
| Concentration identifies a future losing sector | CANNOT VERIFY | Just two independent mature five-year threshold episodes; one favorable, one adverse. |
| Energy's relative edge disappears by five years | DISAGREE | Difference of medians was substituted for median paired excess; the paired five-year excess remains positive in these data. |
| Every model threshold is validated and implemented | DISAGREE | False positives and combined rules were not tested; advertised branches are absent from `score()`. |

## 1. Replicate first, then change the screen

`quantitative_replication.py` imports the original read-only panel/screen functions without invoking their mains. Original `similarity_scores.csv` versus recomputation differs by at most **0.00005 score points**, consistent with four-decimal CSV rounding. Loader callables for French data are redirected **in this process only** to sealed review inputs. The original scripts here use paths relative to their files; no absolute legacy path needed repair. All new writes use explicit `review/phase_c/quantitative_*` targets.

The expanding-primary replication uses each dimension's strictly prior history, minimum120 observations, for candidate ranks; today's target is ranked against history before the current observation. Equal-weight absolute percentile deviations retain the prior distance formula. A complete11-dimension variant avoids early dates receiving a seven-dimensional examination while later dates receive eleven. A separate expanding sensitivity evaluates both the historical candidate and today's target in the candidate's historical CDF. Neither definition reproduces the undocumented exact robustness list printed in ANALOGS§1.4; the retained scripts contain no implementation of that advertised expanding check. That uncertainty is different from the original full-sample screen, which reproduces exactly.

Leading six matches under controlled changes:

{tab(screen[(screen.gap_months==24)&(screen['rank']<=6)][['spec','rank','date','score','n_dims']])}

On this same feature set,2007 and2021 remain leading clusters, so discarding the whole analog idea would overstate the disagreement. However, the independent blind six-dimension, availability-lagged screen selected2000,2017,2005 and1964 among its leaders; feature definition and availability are at least as consequential as the percentile convention. None is a forecast model selected on an untouched future test set.

The conjunction is less fragile than the exact similarity ranks:

{tab(read('conjunctive_screen'))}

It still isolates two broad episodes. That does not establish two independent repeated laws, and none of its four thresholds was prospectively registered before observing this historical dataset. Varying rank histories changes scoreable months (909 versus789); the denominator must travel with the numerator. The claim that1929 is rejected after an equal test is also too strong: earlier dates lack labour, slope or profit measurements and are assigned a different tier.

## 2. The headline five-year winners use an immature and partly hand-selected sample

`report_tables.py` defines SCREEN as all twelve S-prefixed episodes **plus** `M 1999-2000 dotcom [anchor]`. The added2000 start is therefore not selected by the same greedy rank rule. The distinction is disclosed in code but contradicts the simple prose assertion that the screen alone picked the return set. Separately,2021-11 has only56 equity-return months throughJuly2026; gold/bond extensions reach57 months. `cross_summary()` filters investability but never filters `truncated`.

The13starts generate13pairs of overlapping five-year windows. The maximum chronological set of pairwise-disjoint five-year intervals contains7starts, of which6have mature endpoints. This is an interval-count upper bound, **not an estimate that economic cycles are truly independent**. The brief's warning of approximatelysix independent episodes is directionally fair; it should have changed the calculations, not just the disclaimer.

Sensitivity retaining the original assets and published outcome rows:

{tab(sample[(sample.asset.isin(['MKT','CASH','GOLD','Enrgy']))&(sample.horizon==5)][['sample','asset','n','median','mean','minimum','maximum','negative_pct']])}

Removing one immature row changes a median sharply because this is a small sample with a gap between central observations. It does not mean the November2021 path is uninformative; it must be described as a56/57-month observation, outside a complete five-year aggregate. Neither incomplete outcomes nor annualization can create unobserved months.

The original gold mean of58.40% is compared to an1871-onward five-year mean of13.41%, producing roughly45pp excess. But that denominator contains fixed-price and non-investable eras excluded from the selected numerator:

{tab(read('gold_baseline_eras').query('horizon==5'))}

Floating-era mean26.04% cuts the original excess to32.36pp; restricting starts to the first modern selected date,1996-02, gives a43.12% mean and15.28pp original excess. After also excluding the immature selected outcome, the selected mean is53.54%, about10.42pp above that1996+ comparator. These are sensitivity choices, not a claim that1996 is uniquely correct. They show why45pp is not a stable asset property. Gold remains **spot-price return**, not a costs-inclusive investment return. The raw input has no observed Treasury total-return index; the prior bond numbers are a yield-based par-bond model. Its asserted tens-of-basis-points accuracy is not validated against an actual index in this package.

## 3. CAPE reconciliation: mostly a dating problem, but the earnings proxy is real uncertainty

The work-order suspicion of different splices is not supported. Full V2 facts/SUMMARY explicitly says42.0 isAugust and41.3 ispartialSeptember. Isolating and executing the original `cape_series()` reproduces its cached series to **1.42×10⁻¹⁴**. The exact scale is **0.06035823815** index-EPS units per billion dollars of NIPA profits; the latest proxy EPS is **236.6915112**. The12FRED S&P closes fromSeptember1–17 average **7643.185**. August Shiller average price is7711.32.

Reconstruction with the documented monthly CPI interpolation and aSeptember extrapolation using the last monthly growth gives41.25448, rounding to41.3. The original August model gives42.000708. A flatSeptember CPI gives41.41611; that extrapolation assumption is not an observed price-index release. The screen hardcodes41.3 as itsAugust target while the regime model outputs42.0 fromAugust prices. These can be reconciled; they should not be presented as the same timestamp.

{tab(read('cape_inputs'))}

Tested September sensitivity (the post-splice changes affect only earnings afterJune2023):

{tab(cape)}

The±15% earnings scenarios and frozen-real-earnings scenario reproduce V2's approximate39–44range. The broader assertion that *every* assumption lands there is unwarranted: replacing post-splice aggregate earnings growth with GDP-linked profits at the pre2000median share6.10% gives49.66; fixed8% gives46.10. These are stress scenarios, not estimates of true EPS or a forecast that profits will return there.

NIPA total after-tax profits include a different corporate universe, tax/accounting definitions, foreign-income treatment and share-count dynamics from S&P per-share GAAP earnings. Interpolation borrows subsequent-quarter information, and the proxy ignores buybacks. A correct1929 arithmetic check does not validate a2023–2026 splice. **Observed forward-earnings and repurchase-adjusted histories were not present in the raw package.** A quoted FactSet forward P/E in V2 is not enough to reconstruct an annual history or a comparable CAPE. This review therefore does not invent a numerical buyback correction or treat a guessed2–5point haircut as measured evidence. Settling the precise level requires publisher EPS/share-count histories and a defined index universe.

### A more material CAPE error: the baseline outcomes are stale

`step5_credit.shiller_real_tr()` promises a French-data extension in its docstring, but returns only the supplied Shiller real-price/dividend calculation. The last valid total-return month isJune2023. Consequently the published five-yearCAPE≥30 calculation ends withJune2018 starts and **n=68**, not the77shown repeatedly in prose (77belongs to its three-year row).

Holding the threshold fixed and adding the already available post2023 outcomes changes the result:

{tab(read('cape_base_rate_freshness').query('threshold==30 and horizon==5'))}

The hybrid extension is explicitly S&P/Shiller throughJune2023 then French broad-US-market thereafter; it is not a perfect S&P series. The all-French row provides a consistent broad-market universe but still pairs that universe with S&P CAPE. Neither should replace the original with false precision. Together they establish that the headline−13%median/72%negative cannot be treated as a current, universe-invariant expected-return estimate. The complete individual starts, thresholds30/35/40, and1/3/5year outcomes are supplied. Dense overlapping months are not independent evidence; the sign change under plausible asset-universe choice is especially important.

## 4. Tightening into calm credit: what survives and what fails

The original **7/7positive three-year real outcomes** reproduces. It is a legitimate description of those selected onsets. But its onset definition is a level condition with a24-month cooldown: a new onset can occur while the old tightening condition remains continuously true. It is not strictly a transition from easing to tightening. Three-year return windows can overlap because the cooldown is only24months.

Sensitivities were fixed before inspecting their returns: TB3MS or FEDFUNDS; first crossings of0.25pp/6months,0.5pp/6months, or1pp/12months;24month cooldown; calm credit at prior10th/20th/30th percentile, original full-sample20th, or round absolute0.6ppBaa−Aaa /1.5ppBaa−GS10. All reported outcomes require36complete months. Drawdown includes initial wealth1.0 before the first return, correcting another weakness of the original cumulative-path computation. Full and post2000 splits are retained; low counts are not pooled across correlated variants.

Selected calm-only panels:

{tab(selected_credit[['spread','onset','calm_rule','n','median','negative_pct','drawdown20_pct','worst_drawdown']])}

Most strict Baa−Aaa calm variants still look comparatively benign, so the fair judgment is **partial replication of a small historical association**, not its disappearance under every check. However, a1pp/12month first-crossing bill definition with prior-history bottom-quintile credit yields four episodes:1955-09,1966-08,1994-05 and**2000-02**. The last has**−44.13%real three-year return and−44.99%monthly total-return drawdown**. That single defensible variant refutes the universal no-crash inference. Treasury-spread variants also admit losses; yield-leg definitions cannot be interchanged casually. HY OAS starts only2023in this supplied capture, so it cannot independently adjudicate past cycles.

Zero failures in seven independent Bernoulli trials would still permit a one-sided95%upper failure probability of about**34.8%** (`1−0.05^(1/7)`); actual episode dependence weakens even that illustrative bound. The post2000 calm samples are generally tiny or absent. Settling a deployable rule requires one frozen onset/credit definition, vintage-aware inputs, a stated loss event, full false-positive accounting and new independent cycles. A positive three-year endpoint also does not prove no intervening crash.

## 5. Profit share: mean reversion exists, but the level has moved

Series: `100×CPATAX/GDP`, quarterly1947Q1–2026Q2,318observations. These are revised macro histories, not real-time forecasts. Three calendar eras were chosen explicitly to test the structural-break concern rather than optimize trading performance:

{tab(read('profit_era_levels'))}

For each1/3/5year horizon, regress future change in share on its current level with an intercept. Newey–West covariance usesh−1quarter lags to recognize mechanically overlapping outcomes. Regressions keep both start and endpoint inside an era. Coefficients and intervals remain model-dependent; these are descriptive tests, not proof of stationarity or causal mean reversion.

Five-year regressions:

{tab(profit.query('horizon_quarters==20'))}

Within-era negative slopes are compatible with reversion toward different levels: roughly6.1%,7.4%,10.3%. The full-sample five-year slope is weak relative to its robust standard error. A single6%ceiling fails empirically: average share has exceeded10%through the2010–2026 era. The latest12.07%is above that modern mean, so downside margin scenarios remain sensible; neither permanent12%nor imminent return to6%is established.

Freeze a linear reversion model using only outcomes fully observed before2000; evaluate after2000 against the no-change/current-share forecast:

{tab(read('profit_forward_holdout'))}

The old-equilibrium model loses at all three horizons, with five-yearRMSE**4.175pp** versus**1.579pp**for persistence and a−4.024ppforecast bias. Overlapping holdout rows mean86rows are not86independent cycles. Even without claiming a formal significance level, this is strong evidence against mechanically importing the old mean.

Nonoverlapping high-start evidence is especially sparse: for profit share≥10%, only **two complete five-year starts** can be selected chronologically (2010Q3,2018Q2); one subsequently declined and one increased, with median change−0.058pp. The four nonoverlapping three-year starts have three declines and one increase. This supplies an actual mean-reversion test and makes its limits visible. A true contemporary validation requires additional cycles and sector/index-consistent EPS, not another aggregate-profit splice.

## 6. A longer concentration proxy is available, but not the claimed top-ten series

The French archive includes **Number of Firms in Portfolios** and **Average Firm Size** after its return blocks. For each month/industry, estimated capitalization iscount×average size; normalize across12industries forweight. Industry HHI isΣweight²; effective industry count is1/HHI. **Return columns were never used as weights.** The primary publisher confirms these portfolios classify NYSE/AMEX/NASDAQ stocks by SIC eachJune, so they are not S&P500/GICS sectors. [French12-industry methodology](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_12_ind_port.html).

Representative maxima and current reading:

{tab(read('concentration_landmarks'))}

The long proxy establishes unusually large business-equipment exposure today: **43.19%July2026**, versus**34.94%March2000**, with the supplied record peak45.27%June2026. It cannot recover firm-leveltop-ten weights, AI exposure, risk contribution, or establish that an index ceases to diversify at30%. The finance share in the2005–2009 window peaks near21.6%, a different form of concentration from the business-equipment episodes.

Round context thresholds: largest industry≥25%, or HHI≥0.15. Mature nonoverlapping outcome panels:

{tab(con.query("sample=='nonoverlap_chronological'")[['indicator','level','horizon','n','median','negative_pct','dominant_sector_median_excess_pp','dominant_sector_underperforms_pct']])}

At five years there are onlytwo independent starts for either threshold. Largest-industry≥25%selects1999-10 and2018-06: market real returns **−16.81%and+42.22%**; the dominant industry underperforms once and outperforms once. HHI≥0.15 selects2000-01 and2020-04, also one adverse/one favorable endpoint. This supports monitoring exposure concentration and stress-testing it; it does not demonstrate a profitable rotation rule. A clean next step would require firm-level market-cap histories, stable classification, matched industry-weight/covariance risk attribution and a prospectively specified portfolio comparator.

## 7. Additional critical test: the energy tilt uses the wrong relative-return summary

The prior report subtracts the market's unconditional-within-selected-period median from energy's separate median. **`median(Energy)−median(Market)` is not `median(Energy−Market)`** because their middle-ranked episodes need not be the same. For an energy-versus-market assertion, paired excess is the relevant observation.

Recompute the same PPI≥75th-percentile selection with complete horizons, plus expanding-rank and nonoverlapping sensitivities:

{tab(energy)}

Even the original full-sample five-year set has **n=253, median paired excess+10.70pp, mean+8.72pp,58.5%wins** despite separate medians energy39.89%versus market48.83%. With expanding ranks, **n=233, paired median+13.74pp,61.4%wins**. A chronological five-year nonoverlap sample has11starts and8energy wins. These are small-cycle, selection-sensitive descriptive associations, **not proof that energy will outperform**. They do invalidate the claimed disappearance of the relative edge at five years and the use of that claim to dismiss a supercycle. This is a mathematical adjudication of the reported statistic, not adoption of either commentator's narrative.

## 8. Model and V2-package reading observations

The full V2 SUMMARY and facts log were read after sealing, including all89fact sections corresponding to124verdict rows. The CSV was loaded to confirm coverage/schema. Several evaluations violate the promised claim-date boundary: March26's weak-economy statement is countered usingAugustISM/Septemberclaims; May profit-share statements are evaluated using2026Q2data; aMay13valuation composite citesAugust7forwardP/E. These examples require row-level re-adjudication in the root review, even where their eventual conclusion might remain unchanged.

The original model's slow/fast separation is useful. Its implementation is not ready as a validated decision rule:

- `score()` implements onlyBaa>2.5, claims>300k andSahm≥0.5 for stress. The documentedHY>5 alternative, claims+25%relative-to-low alternative and one-month credit persistence are absent.
- Proxy real-rate percentiles are built partly from forward-filled Shiller CPI/long-rate values after2023, while the current1.39value is hardcoded. Historical realized-inflation-adjusted yield is also not interchangeable with today's forward-looking TIPS real yield.
- Credit crossing while equities still make highs can be a **lead**, not necessarily a lag, contrary to the stated kill criterion.
- Valuation labels and rate/credit readings are hardcoded rather than derived uniformly; conditional expected-return claims inherit stale baselines.
- No held-out false-positive record for the combined two-trigger reduce rule exists. Multiple correlated indicators do not automatically provide independent confirmation.

## What the prior quantitative study got right that the blind study did not supply

It identified the useful Baa−Aaa long-history substitution, explicitly warned about very small effective samples, separated nominal from real outcomes, marked gold's pre-float non-investability, and inspected 2000 sector dispersion in useful detail. The four-condition conjunction remains confined to dot-com/post-COVID episodes under the tested expanding specification. The original calm-credit association is reproducible under its own rule; rejecting the universal interpretation must not erase that measured fact. The V2 package itself already documented the September/AugustCAPE distinction and±15%EPS sensitivity, correcting the work-order premise that the two numbers came from irreconcilable splices.

The blind approach contributed an independent dimension choice and chronological availability discipline; its weakness is equally real: equity/GDP has structural/universe problems of its own, and eight analogs are still only eight. The improved method should preserve both the independent derivation and source-level decomposition, then demand definitions, paired outcomes, complete horizons, matching baseline eras, explicit revisions and prospective evaluation before converting descriptive history into operational thresholds.

## Reproduce and inspect

Run `quantitative_replication.py`, `quantitative_additional.py`, then `quantitative_write_report.py` with the review's pandas/numpy/tabulate environment. All outputs begin`quantitative_` in this directory. `quantitative_validation.json` contains exact replication errors, sample/maturity checks and original analog input hashes. Every numerical claim above has an underlying complete CSV, rather than only printed tables. Primary market source methodology was additionally checked2026-09-20: the [French data library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) notes the2025FIZ→CIZ transition and changed dividend-reinvestment timing; monthly capture versions therefore matter.
'''
# Improve readability of number/word boundaries introduced in drafting without
# changing numerical values or source identifiers inside the machine CSVs.
import re
def prose_spacing(line):
    if line.startswith('|'): return line
    pieces=re.split(r'(`[^`]*`)',line)
    for j in range(0,len(pieces),2):
        x=pieces[j]
        x=re.sub(r'(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])',' ',x)
        x=re.sub(r',(?![ \d])',', ',x)
        x=re.sub(r',(?=\d)',', ',x)
        x=re.sub(r'%(?=[A-Za-z])','% ',x)
        for name in ['TB3MS','GS10','HHI12','S&P500','V2']:
            spaced=re.sub(r'(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])',' ',name)
            x=x.replace(spaced,name)
        for a,b in {'throughJuly':'through July','approximatelysix':'approximately six','isAugust':'is August','ispartialSeptember':'is partial September','fromSeptember':'from September','aSeptember':'a September','flatSeptember':'flat September','itsAugust':'its August','fromAugust':'from August','afterJune':'after June','isJune':'is June','withJune':'with June','throughJune':'through June','yearCAPE':'year CAPE','ppBaa':'pp Baa','usesh':'uses h','iscount':'is count','forweight':'for weight','isΣ':'is Σ','eachJune':'each June','onlytwo':'only two','leveltop':'level top','usingAugustISM/Septemberclaims':'using August ISM/September claims','aMay':'a May','citesAugust':'cites August','forwardP/E':'forward P/E','onlyBaa':'only Baa','andSahm':'and Sahm','documentedHY':'documented HY','AugustCAPE':'August CAPE','five-yearRMSE':'five-year RMSE','ppforecast':'pp forecast','begin`':'begin `','10 th':'10th','20 th':'20th','30 th':'30th','75 th':'75th','Q 1':'Q1','Q 2':'Q2','Q 3':'Q3'}.items():x=x.replace(a,b)
        pieces[j]=x
    return ''.join(pieces)
report='\n'.join(prose_spacing(line) for line in report.splitlines())+'\n'
(OUT/'quantitative_adjudication.md').write_text(report)
(OUT/'quantitative_review.md').write_text(report)
receipt=[]
for name in ['facts.md','SUMMARY.md','verdicts.csv']:
    p=ROOT/'verify/out/V2'/name
    d=dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size,read_after_blind_seal=True)
    if name.endswith('csv'):
        df=pd.read_csv(p);d.update(rows=len(df),columns=list(df.columns))
    receipt.append(d)
(OUT/'quantitative_v2_reading_receipt.json').write_text(json.dumps(receipt,indent=2))
print('Wrote quantitative review and V2 reading receipt')
