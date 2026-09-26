# Phase C quantitative adversarial replication

**Written after the Phase A/B seal in `review/LOG.md` (2026-09-20T04:51:13Z).** This report does not revise the blind findings. It re-executes the prior screen, audits its return aggregation, and supplies sensitivity tests for work-order attacks 1–6. Assessment cutoff remains 2026-09-18. All source data are the supplied capture; no live market series replaced it.

## Adjudication lead table

| Finding | Verdict | Main reason |
|---|---|---|
| Original screen arithmetic | AGREE | Scores reproduce to rounding; 2007/2021 remain important under several expanding definitions. |
| Exact analog hierarchy and four-month uniqueness | PARTIALLY AGREE | Dates/order depend on dimensions and normalization; expanding conjunction gives five months in the same two clusters. |
| Thirteen independent, mature, automatically selected episodes | DISAGREE | Twelve screen starts plus a manually added 2000 anchor; at most seven disjoint five-year intervals, six mature. |
| Gold+56% and energy+57% five-year medians | DISAGREE | Removing the incompletely observed November 2021 row changes medians to +25.2% and +36.0%. |
| Gold 45 pp excess relative to a suitable base rate | DISAGREE | The comparator includes non-investable/fixed-price history; changing the base era materially reduces the excess. |
| CAPE 41.3 versus 42.0 means conflicting splices | DISAGREE | Same proxy, different dates: partial September versus August; the screen mixes September CAPE with August features. |
| Extreme equity valuation | PARTIALLY AGREE | Tested proxy variants remain elevated, but aggregate NIPA profits are not observed S&P earnings. |
| CAPE≥30 five-year−13%/72% baseline is current | DISAGREE | Return history stops June 2023; actual n=68. Updating the outcome series changes the inference materially. |
| Tightening into calm credit precludes a crash | DISAGREE | Original 7/7 is reproducible but a reasonable first-crossing alternative includes the 2000 crash. |
| Profit share should revert to an old 6% norm | DISAGREE | Within-era reversion coexists with shifted levels; the frozen old model loses badly to persistence after 2000. |
| Concentration deserves separate monitoring | AGREE | A 100-year industry-capitalization proxy is available from the raw French file and is elevated today. |
| Concentration identifies a future losing sector | CANNOT VERIFY | Just two independent mature five-year threshold episodes; one favorable, one adverse. |
| Energy's relative edge disappears by five years | DISAGREE | Difference of medians was substituted for median paired excess; the paired five-year excess remains positive in these data. |
| Every model threshold is validated and implemented | DISAGREE | False positives and combined rules were not tested; advertised branches are absent from `score()`. |

## 1. Replicate first, then change the screen

`quantitative_replication.py` imports the original read-only panel/screen functions without invoking their mains. Original `similarity_scores.csv` versus recomputation differs by at most **0.00005 score points**, consistent with four-decimal CSV rounding. Loader callables for French data are redirected **in this process only** to sealed review inputs. The original scripts here use paths relative to their files; no absolute legacy path needed repair. All new writes use explicit `review/phase_c/quantitative_*` targets.

The expanding-primary replication uses each dimension's strictly prior history, minimum 120 observations, for candidate ranks; today's target is ranked against history before the current observation. Equal-weight absolute percentile deviations retain the prior distance formula. A complete 11-dimension variant avoids early dates receiving a seven-dimensional examination while later dates receive eleven. A separate expanding sensitivity evaluates both the historical candidate and today's target in the candidate's historical CDF. Neither definition reproduces the undocumented exact robustness list printed in ANALOGS§1.4; the retained scripts contain no implementation of that advertised expanding check. That uncertainty is different from the original full-sample screen, which reproduces exactly.

Leading six matches under controlled changes:

| spec                            |   rank | date       |   score |   n_dims |
|:--------------------------------|-------:|:-----------|--------:|---------:|
| original_full_sample            |      1 | 2021-11-01 |  88.557 |       11 |
| original_full_sample            |      2 | 2007-10-01 |  85.541 |       11 |
| original_full_sample            |      3 | 1946-06-01 |  80.449 |        7 |
| original_full_sample            |      4 | 2005-09-01 |  80.114 |       11 |
| original_full_sample            |      5 | 2001-02-01 |  79.722 |       11 |
| original_full_sample            |      6 | 2018-06-01 |  79.404 |       11 |
| expanding_primary_same_backbone |      1 | 2007-10-01 |  89.606 |       11 |
| expanding_primary_same_backbone |      2 | 2021-08-01 |  89.502 |       11 |
| expanding_primary_same_backbone |      3 | 2005-10-01 |  84.201 |       11 |
| expanding_primary_same_backbone |      4 | 1946-06-01 |  83.323 |        7 |
| expanding_primary_same_backbone |      5 | 1996-02-01 |  82.928 |       11 |
| expanding_primary_same_backbone |      6 | 2001-02-01 |  82.196 |       11 |
| expanding_complete_11dims       |      1 | 2007-10-01 |  89.606 |       11 |
| expanding_complete_11dims       |      2 | 2021-08-01 |  89.502 |       11 |
| expanding_complete_11dims       |      3 | 2005-10-01 |  84.201 |       11 |
| expanding_complete_11dims       |      4 | 1996-02-01 |  82.928 |       11 |
| expanding_complete_11dims       |      5 | 2001-02-01 |  82.196 |       11 |
| expanding_complete_11dims       |      6 | 2017-09-01 |  81.094 |       11 |

On this same feature set, 2007 and 2021 remain leading clusters, so discarding the whole analog idea would overstate the disagreement. However, the independent blind six-dimension, availability-lagged screen selected 2000, 2017, 2005 and 1964 among its leaders; feature definition and availability are at least as consequential as the percentile convention. None is a forecast model selected on an untouched future test set.

The conjunction is less fragile than the exact similarity ranks:

| spec        |   n_eligible |   n_months | years          | dates                                   |
|:------------|-------------:|-----------:|:---------------|:----------------------------------------|
| full_sample |          909 |          4 | 2000;2021;2022 | 2000-02;2021-11;2021-12;2022-01         |
| expanding   |          789 |          5 | 2000;2021;2022 | 2000-02;2021-10;2021-11;2021-12;2022-01 |

It still isolates two broad episodes. That does not establish two independent repeated laws, and none of its four thresholds was prospectively registered before observing this historical dataset. Varying rank histories changes scoreable months (909 versus 789); the denominator must travel with the numerator. The claim that 1929 is rejected after an equal test is also too strong: earlier dates lack labour, slope or profit measurements and are assigned a different tier.

## 2. The headline five-year winners use an immature and partly hand-selected sample

`report_tables.py` defines SCREEN as all twelve S-prefixed episodes **plus** `M 1999-2000 dotcom [anchor]`. The added 2000 start is therefore not selected by the same greedy rank rule. The distinction is disclosed in code but contradicts the simple prose assertion that the screen alone picked the return set. Separately, 2021-11 has only 56 equity-return months through July 2026; gold/bond extensions reach 57 months. `cross_summary()` filters investability but never filters `truncated`.

The 13 starts generate 13 pairs of overlapping five-year windows. The maximum chronological set of pairwise-disjoint five-year intervals contains 7 starts, of which 6 have mature endpoints. This is an interval-count upper bound, **not an estimate that economic cycles are truly independent**. The brief's warning of approximately six independent episodes is directionally fair; it should have changed the calculations, not just the disclaimer.

Sensitivity retaining the original assets and published outcome rows:

| sample                          | asset   |   n |   median |   mean |   minimum |   maximum |   negative_pct |
|:--------------------------------|:--------|----:|---------:|-------:|----------:|----------:|---------------:|
| original_including_truncated    | CASH    |  13 |   -1.708 | -2.718 |   -24.462 |    13.506 |         69.231 |
| original_including_truncated    | Enrgy   |  13 |   56.692 | 60.672 |   -30.349 |   189.628 |         23.077 |
| original_including_truncated    | GOLD    |  10 |   56.296 | 58.4   |   -43     |   153.668 |         20     |
| original_including_truncated    | MKT     |  13 |   41.458 | 36.676 |   -18.419 |   137.011 |         23.077 |
| complete_horizons_only          | CASH    |  12 |   -1.828 | -2.941 |   -24.462 |    13.506 |         66.667 |
| complete_horizons_only          | Enrgy   |  12 |   35.968 | 56.64  |   -30.349 |   189.628 |         25     |
| complete_horizons_only          | GOLD    |   9 |   25.173 | 53.539 |   -43     |   153.668 |         22.222 |
| complete_horizons_only          | MKT     |  12 |   27.04  | 36.277 |   -18.419 |   137.011 |         25     |
| chronological_disjoint_complete | CASH    |   6 |   -2.568 | -3.219 |   -24.462 |    13.506 |         66.667 |
| chronological_disjoint_complete | Enrgy   |   6 |   35.968 | 33.758 |   -30.349 |    87.185 |         33.333 |
| chronological_disjoint_complete | GOLD    |   4 |   43.752 | 38.377 |   -43     |   109.004 |         25     |
| chronological_disjoint_complete | MKT     |   6 |    9.364 | 25.12  |    -5.918 |    73.131 |         16.667 |

Removing one immature row changes a median sharply because this is a small sample with a gap between central observations. It does not mean the November 2021 path is uninformative; it must be described as a 56/57-month observation, outside a complete five-year aggregate. Neither incomplete outcomes nor annualization can create unobserved months.

The original gold mean of 58.40% is compared to an 1871-onward five-year mean of 13.41%, producing roughly 45 pp excess. But that denominator contains fixed-price and non-investable eras excluded from the selected numerator:

| sample_start   |   horizon |    n |   median |   mean |   minimum |   maximum |   negative_pct |
|:---------------|----------:|-----:|---------:|-------:|----------:|----------:|---------------:|
| 1871-01-01     |         5 | 1808 |   -4.23  | 13.415 |   -66.897 |   281.877 |         57.024 |
| 1971-08-01     |         5 |  601 |   12.528 | 26.039 |   -66.897 |   204.236 |         44.759 |
| 1996-02-01     |         5 |  307 |   32.151 | 43.118 |   -42.999 |   164.99  |         25.081 |

Floating-era mean 26.04% cuts the original excess to 32.36 pp; restricting starts to the first modern selected date, 1996-02, gives a 43.12% mean and 15.28 pp original excess. After also excluding the immature selected outcome, the selected mean is 53.54%, about 10.42 pp above that 1996+ comparator. These are sensitivity choices, not a claim that 1996 is uniquely correct. They show why 45 pp is not a stable asset property. Gold remains **spot-price return**, not a costs-inclusive investment return. The raw input has no observed Treasury total-return index; the prior bond numbers are a yield-based par-bond model. Its asserted tens-of-basis-points accuracy is not validated against an actual index in this package.

## 3. CAPE reconciliation: mostly a dating problem, but the earnings proxy is real uncertainty

The work-order suspicion of different splices is not supported. Full V2 facts/SUMMARY explicitly says 42.0 is August and 41.3 is partial September. Isolating and executing the original `cape_series()` reproduces its cached series to **1.42×10⁻¹⁴**. The exact scale is **0.06035823815** index-EPS units per billion dollars of NIPA profits; the latest proxy EPS is **236.6915112**. The 12 FRED S&P closes from September 1–17 average **7643.185**. August Shiller average price is 7711.32.

Reconstruction with the documented monthly CPI interpolation and a September extrapolation using the last monthly growth gives 41.25448, rounding to 41.3. The original August model gives 42.000708. A flat September CPI gives 41.41611; that extrapolation assumption is not an observed price-index release. The screen hardcodes 41.3 as its August target while the regime model outputs 42.0 from August prices. These can be reconciled; they should not be presented as the same timestamp.

| month      |   price |     cpi |   proxy_EPS |   trailing_mean_real_EPS |   cape |
|:-----------|--------:|--------:|------------:|-------------------------:|-------:|
| 2026-08-01 | 7711.32 | 332.885 |     236.692 |                    0.552 | 42.001 |
| 2026-09-01 | 7643.19 | 334.203 |     236.692 |                    0.554 | 41.254 |

Tested September sensitivity (the post-splice changes affect only earnings after June 2023):

| spec                                      | month   |   cape | note                                                                                    |
|:------------------------------------------|:--------|-------:|:----------------------------------------------------------------------------------------|
| published_model_original_code_August      | 2026-08 | 42.001 | AST-isolated exact source function                                                      |
| interpolated_gap_August                   | 2026-08 | 42.001 | same EPS proxy, missing CPI interpolated                                                |
| September_partial_price_recent_CPI_growth | 2026-09 | 41.254 | 12 daily closes through Sep17; CPI extrapolated by latest monthly growth                |
| postsplice_EPS_multiplier_0.85            | 2026-09 | 43.714 | only post2023June EPS changed; scenario, not estimate                                   |
| postsplice_EPS_multiplier_1.15            | 2026-09 | 39.057 | only post2023June EPS changed; scenario, not estimate                                   |
| freeze_June 2023_real_EPS                  | 2026-09 | 42.4   | flat real per-share EPS after splice                                                    |
| postsplice_profitshare_pre2000_median     | 2026-09 | 49.659 | aggregate share fixed at 6.098744%; GDP-linked EPS only after2023June; stress scenario  |
| postsplice_profitshare_fixed_8pct         | 2026-09 | 46.097 | aggregate share fixed at 8.000000%; GDP-linked EPS only after2023June; stress scenario  |
| postsplice_profitshare_fixed_10pct        | 2026-09 | 42.864 | aggregate share fixed at 10.000000%; GDP-linked EPS only after2023June; stress scenario |
| September_CPI_carried_flat                | 2026-09 | 41.416 | no September inflation extrapolation                                                    |

The±15% earnings scenarios and frozen-real-earnings scenario reproduce V2's approximate 39–44 range. The broader assertion that *every* assumption lands there is unwarranted: replacing post-splice aggregate earnings growth with GDP-linked profits at the pre 2000 median share 6.10% gives 49.66; fixed 8% gives 46.10. These are stress scenarios, not estimates of true EPS or a forecast that profits will return there.

NIPA total after-tax profits include a different corporate universe, tax/accounting definitions, foreign-income treatment and share-count dynamics from S&P per-share GAAP earnings. Interpolation borrows subsequent-quarter information, and the proxy ignores buybacks. A correct 1929 arithmetic check does not validate a 2023–2026 splice. **Observed forward-earnings and repurchase-adjusted histories were not present in the raw package.** A quoted FactSet forward P/E in V2 is not enough to reconstruct an annual history or a comparable CAPE. This review therefore does not invent a numerical buyback correction or treat a guessed 2–5 point haircut as measured evidence. Settling the precise level requires publisher EPS/share-count histories and a defined index universe.

### A more material CAPE error: the baseline outcomes are stale

`step5_credit.shiller_real_tr()` promises a French-data extension in its docstring, but returns only the supplied Shiller real-price/dividend calculation. The last valid total-return month is June 2023. Consequently the published five-year CAPE≥30 calculation ends with June 2018 starts and **n=68**, not the 77 shown repeatedly in prose (77 belongs to its three-year row).

Holding the threshold fixed and adding the already available post 2023 outcomes changes the result:

| method                          |   threshold |   horizon |   n |   median |   mean |   minimum |   maximum |   negative_pct | first_start   | last_start   |
|:--------------------------------|------------:|----------:|----:|---------:|-------:|----------:|----------:|---------------:|:--------------|:-------------|
| original_Shiller_stops_2023June |          30 |         5 |  68 |  -12.528 | -4.831 |   -50.822 |    43.653 |         72.059 | 1929-08-01    | 2018-06-01   |
| Shiller_then_French_extension   |          30 |         5 |  89 |   -5.342 |  8.409 |   -50.822 |    69.508 |         55.056 | 1929-08-01    | 2021-07-01   |
| French_market_only              |          30 |         5 |  89 |    3.705 | 10.192 |   -51.33  |    74.687 |         49.438 | 1929-08-01    | 2021-07-01   |

The hybrid extension is explicitly S&P/Shiller through June 2023 then French broad-US-market thereafter; it is not a perfect S&P series. The all-French row provides a consistent broad-market universe but still pairs that universe with S&P CAPE. Neither should replace the original with false precision. Together they establish that the headline−13% median/72% negative cannot be treated as a current, universe-invariant expected-return estimate. The complete individual starts, thresholds 30/35/40, and 1/3/5 year outcomes are supplied. Dense overlapping months are not independent evidence; the sign change under plausible asset-universe choice is especially important.

## 4. Tightening into calm credit: what survives and what fails

The original **7/7 positive three-year real outcomes** reproduces. It is a legitimate description of those selected onsets. But its onset definition is a level condition with a 24-month cooldown: a new onset can occur while the old tightening condition remains continuously true. It is not strictly a transition from easing to tightening. Three-year return windows can overlap because the cooldown is only 24 months.

Sensitivities were fixed before inspecting their returns: TB3MS or FEDFUNDS; first crossings of 0.25 pp/6 months, 0.5 pp/6 months, or 1 pp/12 months;24 month cooldown; calm credit at prior 10th/20th/30th percentile, original full-sample 20th, or round absolute 0.6 pp Baa−Aaa /1.5 pp Baa−GS10. All reported outcomes require 36 complete months. Drawdown includes initial wealth 1.0 before the first return, correcting another weakness of the original cumulative-path computation. Full and post 2000 splits are retained; low counts are not pooled across correlated variants.

Selected calm-only panels:

| spread   | onset                   | calm_rule   |   n |   median |   negative_pct |   drawdown20_pct |   worst_drawdown |
|:---------|:------------------------|:------------|----:|---------:|---------------:|-----------------:|-----------------:|
| BAA_AAA  | FEDFUNDS_cross_0.5pp_6m | absolute    |   2 |   14.896 |          0     |            0     |          -15.486 |
| BAA_AAA  | TB3MS_cross_0.25pp_6m   | prior_pct20 |   5 |   24.346 |          0     |            0     |          -15.486 |
| BAA_AAA  | TB3MS_cross_1.0pp_12m   | prior_pct20 |   4 |   25.301 |         25     |           25     |          -44.995 |
| BAA_AAA  | original_repeated_level | full_pct20  |   7 |   24.346 |          0     |            0     |          -15.486 |
| BAA_GS10 | FEDFUNDS_cross_0.5pp_6m | absolute    |   8 |   14.896 |         25     |           37.5   |          -33.553 |
| BAA_GS10 | TB3MS_cross_0.25pp_6m   | prior_pct20 |   1 |   23.608 |          0     |            0     |          -15.486 |
| BAA_GS10 | TB3MS_cross_1.0pp_12m   | prior_pct20 |   1 |   25.309 |          0     |            0     |          -16.479 |
| BAA_GS10 | original_repeated_level | full_pct20  |   7 |   20.47  |         14.286 |           28.571 |          -41.196 |

Most strict Baa−Aaa calm variants still look comparatively benign, so the fair judgment is **partial replication of a small historical association**, not its disappearance under every check. However, a 1 pp/12 month first-crossing bill definition with prior-history bottom-quintile credit yields four episodes:1955-09, 1966-08, 1994-05 and**2000-02**. The last has**−44.13% real three-year return and−44.99% monthly total-return drawdown**. That single defensible variant refutes the universal no-crash inference. Treasury-spread variants also admit losses; yield-leg definitions cannot be interchanged casually. HY OAS starts only 2023 in this supplied capture, so it cannot independently adjudicate past cycles.

Zero failures in seven independent Bernoulli trials would still permit a one-sided 95% upper failure probability of about**34.8%** (`1−0.05^(1/7)`); actual episode dependence weakens even that illustrative bound. The post 2000 calm samples are generally tiny or absent. Settling a deployable rule requires one frozen onset/credit definition, vintage-aware inputs, a stated loss event, full false-positive accounting and new independent cycles. A positive three-year endpoint also does not prove no intervening crash.

## 5. Profit share: mean reversion exists, but the level has moved

Series: `100×CPATAX/GDP`, quarterly 1947 Q1–2026 Q2, 318 observations. These are revised macro histories, not real-time forecasts. Three calendar eras were chosen explicitly to test the structural-break concern rather than optimize trading performance:

|       era |   n |   mean |   median |   minimum |   maximum |
|----------:|----:|-------:|---------:|----------:|----------:|
| 1947_1989 | 172 |  6.095 |    6.061 |     4.096 |     8.127 |
| 1990_2009 |  80 |  6.985 |    6.922 |     4.714 |     9.287 |
| 2010_2026 |  66 | 10.303 |   10.268 |     9.051 |    12.071 |

For each 1/3/5 year horizon, regress future change in share on its current level with an intercept. Newey–West covariance uses h−1 quarter lags to recognize mechanically overlapping outcomes. Regressions keep both start and endpoint inside an era. Coefficients and intervals remain model-dependent; these are descriptive tests, not proof of stationarity or causal mean reversion.

Five-year regressions:

| regime    |   horizon_quarters |   n |   intercept |   slope_change_on_level |   hac_slope_se |   hac_t |   implied_equilibrium |
|:----------|-------------------:|----:|------------:|------------------------:|---------------:|--------:|----------------------:|
| full      |                 20 | 298 |       1.365 |                  -0.151 |          0.103 |  -1.465 |                 9.057 |
| pre1990   |                 20 | 152 |       6.353 |                  -1.043 |          0.105 |  -9.901 |                 6.093 |
| 1990_2009 |                 20 |  60 |       7.821 |                  -1.053 |          0.22  |  -4.782 |                 7.429 |
| 2010plus  |                 20 |  46 |      11.309 |                  -1.097 |          0.347 |  -3.164 |                10.31  |

Within-era negative slopes are compatible with reversion toward different levels: roughly 6.1%, 7.4%, 10.3%. The full-sample five-year slope is weak relative to its robust standard error. A single 6% ceiling fails empirically: average share has exceeded 10% through the 2010–2026 era. The latest 12.07% is above that modern mean, so downside margin scenarios remain sensible; neither permanent 12% nor imminent return to 6% is established.

Freeze a linear reversion model using only outcomes fully observed before 2000; evaluate after 2000 against the no-change/current-share forecast:

|   horizon_quarters |   n_train |   n_test |   mr_rmse |   persistence_rmse |   mr_bias |   frozen_equilibrium |
|-------------------:|----------:|---------:|----------:|-------------------:|----------:|---------------------:|
|                  4 |       208 |      102 |     1.587 |              0.822 |    -1.385 |                6.194 |
|                 12 |       200 |       94 |     3.326 |              1.395 |    -3.168 |                6.122 |
|                 20 |       192 |       86 |     4.175 |              1.579 |    -4.024 |                6.121 |

The old-equilibrium model loses at all three horizons, with five-year RMSE**4.175 pp** versus**1.579 pp**for persistence and a−4.024 pp forecast bias. Overlapping holdout rows mean 86 rows are not 86 independent cycles. Even without claiming a formal significance level, this is strong evidence against mechanically importing the old mean.

Nonoverlapping high-start evidence is especially sparse: for profit share≥10%, only **two complete five-year starts** can be selected chronologically (2010 Q3, 2018 Q2); one subsequently declined and one increased, with median change−0.058 pp. The four nonoverlapping three-year starts have three declines and one increase. This supplies an actual mean-reversion test and makes its limits visible. A true contemporary validation requires additional cycles and sector/index-consistent EPS, not another aggregate-profit splice.

## 6. A longer concentration proxy is available, but not the claimed top-ten series

The French archive includes **Number of Firms in Portfolios** and **Average Firm Size** after its return blocks. For each month/industry, estimated capitalization is count×average size; normalize across 12 industries for weight. Industry HHI is Σweight²; effective industry count is 1/HHI. **Return columns were never used as weights.** The primary publisher confirms these portfolios classify NYSE/AMEX/NASDAQ stocks by SIC each June, so they are not S&P500/GICS sectors. [French 12-industry methodology](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_12_ind_port.html).

Representative maxima and current reading:

| window           | date       |   HHI12 |   top_industry_weight |   BusEq_weight | top_industry   |   effective_industries |
|:-----------------|:-----------|--------:|----------------------:|---------------:|:---------------|-----------------------:|
| 1926-07..1930-12 | 1927-06-01 |   0.124 |                 0.218 |          0.052 | Other          |                  8.061 |
| 1960-01..1979-12 | 1960-01-01 |   0.12  |                 0.225 |          0.095 | Manuf          |                  8.327 |
| 1998-01..2001-12 | 2000-03-01 |   0.174 |                 0.349 |          0.349 | BusEq          |                  5.742 |
| 2005-01..2009-12 | 2006-10-01 |   0.119 |                 0.216 |          0.157 | Money          |                  8.389 |
| 2020-01..2026-07 | 2026-06-01 |   0.244 |                 0.453 |          0.453 | BusEq          |                  4.098 |
| latest           | 2026-07-01 |   0.228 |                 0.432 |          0.432 | BusEq          |                  4.379 |

The long proxy establishes unusually large business-equipment exposure today: **43.19% July 2026**, versus**34.94% March 2000**, with the supplied record peak 45.27% June 2026. It cannot recover firm-level top-ten weights, AI exposure, risk contribution, or establish that an index ceases to diversify at 30%. The finance share in the 2005–2009 window peaks near 21.6%, a different form of concentration from the business-equipment episodes.

Round context thresholds: largest industry≥25%, or HHI≥0.15. Mature nonoverlapping outcome panels:

| indicator           |   level |   horizon |   n |   median |   negative_pct |   dominant_sector_median_excess_pp |   dominant_sector_underperforms_pct |
|:--------------------|--------:|----------:|----:|---------:|---------------:|-----------------------------------:|------------------------------------:|
| top_industry_weight |    0.25 |         1 |  10 |    9.94  |         20     |                              6.548 |                              20     |
| top_industry_weight |    0.25 |         3 |   3 |    9.096 |         33.333 |                             20.327 |                              33.333 |
| top_industry_weight |    0.25 |         5 |   2 |   12.703 |         50     |                              9.253 |                              50     |
| HHI12               |    0.15 |         1 |   7 |    9.2   |         42.857 |                              2.332 |                              28.571 |
| HHI12               |    0.15 |         3 |   3 |   24.589 |         33.333 |                              8.319 |                              33.333 |
| HHI12               |    0.15 |         5 |   2 |   22.681 |         50     |                             -6.061 |                              50     |

At five years there are only two independent starts for either threshold. Largest-industry≥25% selects 1999-10 and 2018-06: market real returns **−16.81% and+42.22%**; the dominant industry underperforms once and outperforms once. HHI≥0.15 selects 2000-01 and 2020-04, also one adverse/one favorable endpoint. This supports monitoring exposure concentration and stress-testing it; it does not demonstrate a profitable rotation rule. A clean next step would require firm-level market-cap histories, stable classification, matched industry-weight/covariance risk attribution and a prospectively specified portfolio comparator.

## 7. Additional critical test: the energy tilt uses the wrong relative-return summary

The prior report subtracts the market's unconditional-within-selected-period median from energy's separate median. **`median(Energy)−median(Market)` is not `median(Energy−Market)`** because their middle-ranked episodes need not be the same. For an energy-versus-market assertion, paired excess is the relevant observation.

Recompute the same PPI≥75th-percentile selection with complete horizons, plus expanding-rank and nonoverlapping sensitivities:

| method               |   horizon | sample                   |   n |   median |   mean |   minimum |   maximum |   negative_pct |   energy_median |   market_median |   beat_market_pct |
|:---------------------|----------:|:-------------------------|----:|---------:|-------:|----------:|----------:|---------------:|----------------:|----------------:|------------------:|
| original_full_sample |         1 | all_overlapping          | 270 |    4.213 |  8.172 |   -28.888 |    88.365 |         34.815 |           9.949 |           4.063 |            65.185 |
| original_full_sample |         1 | nonoverlap_chronological |  32 |    6.309 |  7.679 |   -25.266 |    44.358 |         34.375 |          11.738 |           3.466 |            65.625 |
| original_full_sample |         3 | all_overlapping          | 270 |    7.058 |  6.139 |   -73.801 |   104.533 |         40     |          29.176 |          24.349 |            60     |
| original_full_sample |         3 | nonoverlap_chronological |  14 |   18.465 | 15.411 |   -56.036 |    66.151 |         35.714 |          23.499 |          17.919 |            64.286 |
| original_full_sample |         5 | all_overlapping          | 253 |   10.702 |  8.716 |   -82.373 |   146.535 |         41.502 |          39.885 |          48.826 |            58.498 |
| original_full_sample |         5 | nonoverlap_chronological |  11 |   26.077 | 26.341 |   -58.542 |   118.284 |         27.273 |          72.192 |          46.115 |            72.727 |
| expanding_prior      |         1 | all_overlapping          | 250 |    5.35  |  9.177 |   -26.93  |    88.365 |         33.6   |          10.388 |           3.718 |            66.4   |
| expanding_prior      |         1 | nonoverlap_chronological |  29 |    7.326 |  8.312 |   -25.266 |    44.358 |         34.483 |          12.42  |           2.052 |            65.517 |
| expanding_prior      |         3 | all_overlapping          | 250 |    8.227 |  6.638 |   -73.801 |    87.681 |         38.8   |          28.628 |          23.157 |            61.2   |
| expanding_prior      |         3 | nonoverlap_chronological |  14 |   16.658 | 13.232 |   -56.036 |    66.151 |         35.714 |          30.614 |          18.377 |            64.286 |
| expanding_prior      |         5 | all_overlapping          | 233 |   13.743 | 10.879 |   -82.373 |   146.535 |         38.627 |          41.256 |          48.355 |            61.373 |
| expanding_prior      |         5 | nonoverlap_chronological |  11 |   26.077 | 20.674 |   -72.544 |   118.284 |         27.273 |          72.192 |          46.115 |            72.727 |

Even the original full-sample five-year set has **n=253, median paired excess+10.70 pp, mean+8.72 pp, 58.5% wins** despite separate medians energy 39.89% versus market 48.83%. With expanding ranks, **n=233, paired median+13.74 pp, 61.4% wins**. A chronological five-year nonoverlap sample has 11 starts and 8 energy wins. These are small-cycle, selection-sensitive descriptive associations, **not proof that energy will outperform**. They do invalidate the claimed disappearance of the relative edge at five years and the use of that claim to dismiss a supercycle. This is a mathematical adjudication of the reported statistic, not adoption of either commentator's narrative.

## 8. Model and V2-package reading observations

The full V2 SUMMARY and facts log were read after sealing, including all 89 fact sections corresponding to 124 verdict rows. The CSV was loaded to confirm coverage/schema. Several evaluations violate the promised claim-date boundary: March 26's weak-economy statement is countered using August ISM/September claims; May profit-share statements are evaluated using 2026 Q2 data; a May 13 valuation composite cites August 7 forward P/E. These examples require row-level re-adjudication in the root review, even where their eventual conclusion might remain unchanged.

The original model's slow/fast separation is useful. Its implementation is not ready as a validated decision rule:

- `score()` implements only Baa>2.5, claims>300 k and Sahm≥0.5 for stress. The documented HY>5 alternative, claims+25% relative-to-low alternative and one-month credit persistence are absent.
- Proxy real-rate percentiles are built partly from forward-filled Shiller CPI/long-rate values after 2023, while the current 1.39 value is hardcoded. Historical realized-inflation-adjusted yield is also not interchangeable with today's forward-looking TIPS real yield.
- Credit crossing while equities still make highs can be a **lead**, not necessarily a lag, contrary to the stated kill criterion.
- Valuation labels and rate/credit readings are hardcoded rather than derived uniformly; conditional expected-return claims inherit stale baselines.
- No held-out false-positive record for the combined two-trigger reduce rule exists. Multiple correlated indicators do not automatically provide independent confirmation.

## What the prior quantitative study got right that the blind study did not supply

It identified the useful Baa−Aaa long-history substitution, explicitly warned about very small effective samples, separated nominal from real outcomes, marked gold's pre-float non-investability, and inspected 2000 sector dispersion in useful detail. The four-condition conjunction remains confined to dot-com/post-COVID episodes under the tested expanding specification. The original calm-credit association is reproducible under its own rule; rejecting the universal interpretation must not erase that measured fact. The V2 package itself already documented the September/August CAPE distinction and±15% EPS sensitivity, correcting the work-order premise that the two numbers came from irreconcilable splices.

The blind approach contributed an independent dimension choice and chronological availability discipline; its weakness is equally real: equity/GDP has structural/universe problems of its own, and eight analogs are still only eight. The improved method should preserve both the independent derivation and source-level decomposition, then demand definitions, paired outcomes, complete horizons, matching baseline eras, explicit revisions and prospective evaluation before converting descriptive history into operational thresholds.

## Reproduce and inspect

Run `quantitative_replication.py`, `quantitative_additional.py`, then `quantitative_write_report.py` with the review's pandas/numpy/tabulate environment. All outputs begin`quantitative_` in this directory. `quantitative_validation.json` contains exact replication errors, sample/maturity checks and original analog input hashes. Every numerical claim above has an underlying complete CSV, rather than only printed tables. Primary market source methodology was additionally checked 2026-09-20: the [French data library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) notes the 2025 FIZ→CIZ transition and changed dividend-reinvestment timing; monthly capture versions therefore matter.

## Source-code anchors and evidentiary limits

All dated forward comparisons here use the supplied revised history. Expanding percentiles remove future observations from the ranking window; they **do not restore the original data vintage, original release calendar, historical accounting definitions, or an untouched test set**. The frozen profit-share model is a chronological pseudo-out-of-sample test. Its error comparison is evidence about this dataset, not a simulated implementable vintage strategy. The independent Phase B report uses approximate availability lags but is likewise not an ALFRED vintage reconstruction.

| Issue | Original source anchor | Executed review evidence |
|---|---|---|
| Mixed target timestamp | [regime_screen.py:44](/Users/marselkei/VS/intra/research/macro/analogs/regime_screen.py:44) | quantitative_cape_inputs.csv; quantitative_screen_selections.csv |
| Full-history ranks and candidate scoring | [regime_screen.py:171](/Users/marselkei/VS/intra/research/macro/analogs/regime_screen.py:171) | quantitative_screen_selections.csv; quantitative_alternative_expanding_normalization.csv |
| Manual 2000 anchor | [report_tables.py:23](/Users/marselkei/VS/intra/research/macro/analogs/report_tables.py:23) | quantitative_original_episode_maturity.csv |
| Aggregation omits the maturity filter | [report_tables.py:78](/Users/marselkei/VS/intra/research/macro/analogs/report_tables.py:78) | quantitative_original_sample_sensitivity.csv; quantitative_overlap_pairs.csv |
| Incomplete horizons are returned | [analog_scripts.py:110](/Users/marselkei/VS/intra/research/macro/analogs/analog_scripts.py:110) | quantitative_original_episode_maturity.csv |
| CAPE aggregate-profit splice | [regime_model.py:47](/Users/marselkei/VS/intra/research/macro/scripts/regime_model.py:47) | quantitative_cape_sensitivity.csv; quantitative_validation.json |
| Missing promised return extension | [step5_credit.py:28](/Users/marselkei/VS/intra/research/macro/analogs/step5_credit.py:28) | quantitative_cape_base_rate_freshness.csv; quantitative_cape_base_rate_starts.csv |
| Repeated tightening levels rather than first crossings | [analog_scripts.py:218](/Users/marselkei/VS/intra/research/macro/analogs/analog_scripts.py:218) | quantitative_tightening_all_episodes.csv; quantitative_tightening_sensitivity.csv |
| Separate energy/market medians | [step5_credit.py:184](/Users/marselkei/VS/intra/research/macro/analogs/step5_credit.py:184) | quantitative_energy_tilt_sensitivity.csv |
| Energy-edge inference | [regime_model.py:129](/Users/marselkei/VS/intra/research/macro/scripts/regime_model.py:129) | quantitative_energy_tilt_sensitivity.csv |
| Stale context series and hardcoded reading | [regime_model.py:144](/Users/marselkei/VS/intra/research/macro/scripts/regime_model.py:144) | Source inspection; separate TIPS and backward-inflation definitions required |
| Implemented stress criteria | [regime_model.py:164](/Users/marselkei/VS/intra/research/macro/scripts/regime_model.py:164) | Source inspection; Phase B event metrics provide individual-trigger diagnostics |
| Reversed lead/lag kill criterion | [regime_model.py:189](/Users/marselkei/VS/intra/research/macro/scripts/regime_model.py:189) | Source inspection |

The complete source-reading receipt covers all 15 original analog files (7 CSVs, 4 Python files, 3 text outputs and ANALOGS.md), plus V2 and V7. CSVs were loaded in full and inspected numerically; receipt language does not imply that every cell of a large CSV was visually read. V2's 124 rows map to 89 fact keys. V7 has 150 rows/141 fact keys but 142 fact headings because the unassigned debt-to-GDP section has no claim ID. The separate V7 adjudication records semantic findings from all 1,142 facts-log lines and all 163 SUMMARY lines.

To settle the remaining issues: retain a true index-EPS/share-count history; obtain the original vintages and release timestamps; use completed, prospectively specified events; validate bonds against an observed total-return index; acquire firm-level capitalization histories for top-ten concentration; and register one complete decision rule before its next independent cycle. Additional correlated thresholds or repeating monthly observations would not supply the missing independent evidence.
