# Phase B — Independent regime and return analysis

**Blind version; assessment date 2026-09-19; market cutoff 2026-09-18.** This report was written before reading Brief 001, claims, verdicts, analogs, regime code, or processed regime outputs. README and STATE were deliberately not read. The independent event study is recorded under `review/phase_b_events/`; this report supplies the regime and return component. All numbers below come from the accompanying reproducible outputs and the explicitly identified frozen input files, not a live market feed.

## Plain answer

The observed state combines exceptionally high corporate equity value relative to US output, unusually narrow corporate credit differentiation, modest industrial growth, and inflation above 3%; it does not show contemporaneous broad financial stress. The independent historical screen supports a wide set of outcomes, not a crash forecast. Across eight selected, nonoverlapping five-year episodes, US equity **total** returns over one year ranged from **−27.9% to +23.5% after inflation**, with median **+4.6%**; over five years they ranged from **−24.1% to +129.8%**, median **+24.6% cumulative**. Those are historical scenario observations, not calibrated forecast intervals. Omitting the valuation dimension changes the five-year median to **+48.1%**, versus a **+42.9%** unconditional monthly-start median, so even the sign of relative underperformance is specification-sensitive. The eight-episode median is not unusual in randomly selected eight-episode, nonoverlapping reference sets. Inflation, recessions, and crisis timing require their own monitored evidence; valuation supplies no reliable date.

## What the inputs actually support

The supplied instruction says the dashboard CPI defect was fixed. **The actual file is not fixed.** Its `yoy()` function still executes `s.pct_change(months) * 100`. This was tested by compiling only the function's syntax tree, so importing the dashboard could not overwrite files outside review. CPI and core CPI both omit October 2025. The supplied UNRATE series also omits that month. A calendar-preserving monthly index and an exactly 12-month denominator are necessary; if that denominator is absent, the result is missing, not a nearby month's growth rate. Synthetic missing-month and missing-denominator tests passed.

Latest CPI comparisons, reference August 2026, source FRED `CPIAUCSL` and `CPILFESL`, captured 2026-09-19:

| series   |   calendar_yoy |   dashboard_yoy |   difference_pp | row_lag_base_date   | correct_base_month   |
|:---------|---------------:|----------------:|----------------:|:--------------------|:---------------------|
| CPIAUCSL |           3.35 |            3.71 |            0.36 | 2025-07-01          | 2025-08              |
| CPILFESL |           2.45 |            2.76 |            0.32 | 2025-07-01          | 2025-08              |

The percentile defect is methodological, not a sortable cosmetic issue. A row ranked on three years cannot be compared with another ranked on forty years without explicitly qualifying the different histories. Latest values are 2026-09-17; sample sizes below are native-frequency observations, not independent samples:

| series       | last_date   |   value |     n | history_start   |   own_history_percentile | common_history_start   |   common_history_percentile |
|:-------------|:------------|--------:|------:|:----------------|-------------------------:|:-----------------------|----------------------------:|
| BAMLH0A0HYM2 | 2026-09-17  |    2.7  |   787 | 2023-09-19      |                     9.91 | 2023-09-19             |                        9.91 |
| BAA10Y       | 2026-09-17  |    1.44 | 10178 | 1986-01-02      |                     1.83 | 2023-09-19             |                        5.61 |
| DFII10       | 2026-09-17  |    2.61 |  5932 | 2003-01-02      |                    98.75 | 2023-09-19             |                       99.6  |

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

| indicator            |   value |   expanding_percentile | percentile_history_start   |   percentile_n | reference_month   | assumed_available   |
|:---------------------|--------:|-----------------------:|:---------------------------|---------------:|:------------------|:--------------------|
| equity_gdp_pct       |  255.65 |                 100    | 1954-07-31                 |            866 | 2026-04           | 2026-09-16          |
| cpi_yoy_pct          |    3.35 |                  59.93 | 1954-07-31                 |            866 | 2026-08           | 2026-09-16          |
| ip_yoy_pct           |    1.42 |                  36.03 | 1954-07-31                 |            866 | 2026-08           | 2026-09-16          |
| baa_aaa_pp           |    0.44 |                   2.89 | 1954-07-31                 |            866 | 2026-08           | 2026-09-16          |
| curve_10y_3m_pp      |    0.96 |                  38.34 | 1954-07-31                 |            866 | 2026-08           | 2026-09-16          |
| real_bill_expost_pct |    0.37 |                  41.69 | 1954-07-31                 |            866 | 2026-08           | 2026-09-16          |

The latest supplemental observations show the important calendar mismatch between slow context and fast prices:

| series       | reference_date   |   value |
|:-------------|:-----------------|--------:|
| VIXCLS       | 2026-09-17       |   15.44 |
| BAMLH0A0HYM2 | 2026-09-17       |    2.7  |
| DCOILBRENTEU | 2026-09-15       |  130.8  |
| SAHMREALTIME | 2026-08-01       |   -0.07 |
| GFDEGDQ188S  | 2026-01-01       |  122.59 |
| FEDFUNDS     | 2026-08-01       |    3.63 |

Source keys: VIXCLS is Cboe VIX (index points); BAMLH0A0HYM2 is HY OAS (%); DCOILBRENTEU is Brent ($/barrel); SAHMREALTIME is percentage-point Sahm gap; GFDEGDQ188S is federal debt/GDP (%); FEDFUNDS is effective fed funds (%). Brent at $130.80 on September 15 is a material current shock that the six-dimensional monthly screen does **not** encode. No exact historical twin is asserted. The combination of low VIX and narrow spreads measures priced calm, not proof of safety.

## Screen design, selected before return inspection

Primary specification: equal-weight root-mean-square distance between six **strictly prior expanding-history** percentiles. For candidate month t, its percentile CDF contains only months earlier than t; the current CDF contains only months earlier than September 18, 2026. The first 120 months are a training minimum, giving candidate dates July 1964 onward. No return outcome enters distance, weights, thresholds, or selection.

To avoid pretending observation dates were publication dates, monthly inputs become available the next month on day 16; quarterly inputs become available in the fifth month after the quarter's start, on day 16. These are uniform approximations, not historical release calendars. Missing readings retain the last available value; missing source dates are reported. **This is a revised-data, approximate-availability historical simulation, not a genuine real-time-vintage backtest.** Vintage revisions, publication-date variation, repeated quarterly readings, and structural change remain material limitations. Periods before 1964 have no chance to be selected under this design.

Eligible candidate dates end August 2021 so a five-year outcome can in principle mature by the September 2026 cutoff. Sort by explanatory distance; accept the nearest date, then successive dates at least 60 calendar months from every accepted date, until eight dates are selected. Forward intervals therefore do not overlap, including the exactly 60-month-separated 2000 and 2005 pair. Economic independence is still not guaranteed. Eight is a declared descriptive sample budget, not a discovered optimum. The eighth candidate is considerably less similar than the first; nearest-four sensitivity is also supplied.

Primary episodes (nearest-first):

|   nearest_rank | date       |   distance |   equity_gdp_pct |   cpi_yoy_pct |   ip_yoy_pct |   baa_aaa_pp |   curve_10y_3m_pp |   real_bill_expost_pct |
|---------------:|:-----------|-----------:|-----------------:|--------------:|-------------:|-------------:|------------------:|-----------------------:|
|              1 | 2000-03-31 |      14.42 |           155.41 |          3.22 |         4.31 |         0.61 |              0.97 |                   2.33 |
|              2 | 2017-10-31 |      15.81 |           142.46 |          2.18 |         1.06 |         0.67 |              1.17 |                  -1.15 |
|              3 | 2005-03-31 |      16.64 |           107.9  |          3.05 |         3.89 |         0.62 |              1.63 |                  -0.51 |
|              4 | 1964-07-31 |      21.49 |            73.9  |          1.31 |         5.97 |         0.44 |              0.69 |                   2.17 |
|              5 | 1993-11-30 |      24.36 |            66.31 |          2.75 |         2.89 |         0.64 |              2.31 |                   0.27 |
|              6 | 2011-07-31 |      29.01 |           107.87 |          3.5  |         2.37 |         0.76 |              2.96 |                  -3.46 |
|              7 | 1973-04-30 |      31.29 |            77.73 |          4.83 |         9.5  |         0.74 |              0.62 |                   1.26 |
|              8 | 1988-11-30 |      37.76 |            48.48 |          4.26 |         3.12 |         0.9  |              1.45 |                   3.09 |

Sensitivity designs: (1) fixed economic units **100 pp equity/GDP, 3 pp inflation, 5 pp IP growth, 0.5 pp Baa−Aaa, 1.5 pp curve, 3 pp real bill**, equal weights; these round scales were not fitted to returns; (2) omit valuation to expose its influence; (3) full-sample ranks as a deliberately biased diagnostic, not the primary result. Full selected dates and explanatory values are in `phase_b/selected_episodes.csv`. The fixed-scale screen's leading dates are 2018-03 and 2000-03; it also includes 2007-11, 1967-12, 2013-02, 1993-11, 1973-05 and 1988-11. Absolute inflation similarity and relative historical rarity answer different questions; their disagreement is information, not a reason to select the prettier return result.

## Forward asset returns and unconditional reference

US market = Ken French `Mkt-RF + RF`, compounded; bills = compounded RF; sectors = twelve value-weighted industry total-return portfolios. A horizon begins with the next calendar month's return, after the episode's month-end. Real return is `(1 + nominal return) / (CPI_endpoint / CPI_start) − 1`, using exact endpoint calendar months and leaving any missing endpoint uncomputed. All percentages below are **cumulative**, not annualized. Fees and taxes are excluded.

Unconditional comparison uses every monthly start in the same July 1964–August 2021 candidate calendar, separately requiring complete asset/horizon data. Thus it controls the broad era; it is **not** the entire 1926–2026 history. Its 684–686 rows overlap heavily and must not be presented as hundreds of independent five-year experiments. Every primary return panel has **n=8** complete episodes.

Nominal returns (sample range is minimum–maximum, not a confidence interval):

| asset           |   horizon_years |   episode_n |   episode_median |   episode_minimum |   episode_maximum |   episode_negative_pct |   unconditional_n |   unconditional_median |   median_excess_pp |
|:----------------|----------------:|------------:|-----------------:|------------------:|------------------:|-----------------------:|------------------:|-----------------------:|-------------------:|
| US_market_total |               1 |           8 |             6.72 |            -25.75 |             29.26 |                   25   |               686 |                  13.52 |              -6.8  |
| US_market_total |               3 |           8 |            34.83 |            -42.32 |             70.86 |                   12.5 |               686 |                  39.43 |              -4.59 |
| US_market_total |               5 |           8 |            49.33 |            -14.31 |            158.33 |                   12.5 |               685 |                  74.21 |             -24.89 |
| T_bill_total    |               1 |           8 |             3.71 |              0.02 |              8.4  |                    0   |               686 |                   4.8  |              -1.09 |
| T_bill_total    |               3 |           8 |            13.05 |              0.07 |             23.72 |                    0   |               686 |                  15.26 |              -2.21 |
| T_bill_total    |               5 |           8 |            19.84 |              0.19 |             35.24 |                    0   |               685 |                  26.52 |              -6.68 |
| Gold_spot_price |               1 |           8 |             0.84 |             -8.04 |             89.01 |                   37.5 |               686 |                   3.79 |              -2.95 |
| Gold_spot_price |               3 |           8 |            10.15 |            -16.66 |            123.04 |                   25   |               686 |                  11.76 |              -1.61 |
| Gold_spot_price |               5 |           8 |            25    |            -21.39 |            156.45 |                   37.5 |               686 |                  37.79 |             -12.79 |

Real returns:

| asset           |   horizon_years |   episode_n |   episode_median |   episode_minimum |   episode_maximum |   episode_negative_pct |   unconditional_n |   unconditional_median |   median_excess_pp |
|:----------------|----------------:|------------:|-----------------:|------------------:|------------------:|-----------------------:|------------------:|-----------------------:|-------------------:|
| US_market_total |               1 |           8 |             4.57 |            -27.9  |             23.51 |                   37.5 |               686 |                   9.92 |              -5.35 |
| US_market_total |               3 |           8 |            26.5  |            -46.36 |             57.19 |                   25   |               686 |                  24.22 |               2.27 |
| US_market_total |               5 |           8 |            24.63 |            -24.12 |            129.84 |                   25   |               684 |                  42.88 |             -18.25 |
| T_bill_total    |               1 |           8 |             0.58 |             -2.18 |              3.58 |                   37.5 |               686 |                   0.45 |               0.13 |
| T_bill_total    |               3 |           8 |             2.51 |             -5.03 |              8.01 |                   37.5 |               686 |                   1.62 |               0.9  |
| T_bill_total    |               5 |           8 |             0.94 |            -12.72 |             13.17 |                   37.5 |               684 |                   1.39 |              -0.45 |
| Gold_spot_price |               1 |           8 |            -0.76 |            -10.71 |             71.72 |                   62.5 |               686 |                   0.65 |              -1.41 |
| Gold_spot_price |               3 |           8 |             1.28 |            -25.17 |            101.78 |                   50   |               686 |                   0.67 |               0.61 |
| Gold_spot_price |               5 |           8 |             4.37 |            -30.06 |            127.84 |                   37.5 |               685 |                  15.05 |             -10.68 |

**Gold is spot-price return**, using monthly average price marks, excluding storage and insurance. It is not mislabeled total return or a futures-strategy return. The 1964 observation includes a fixed-price monetary regime; `small_sample_and_gold_sensitivity.csv` separately excludes pre-August-1971 starts (n=7). **No bond total-return series is present in the allowed inputs.** Treasury yields alone cannot establish bond-holder returns; bond winners/losers remain unavailable. International total returns and currency-hedged variants are likewise not established here.

US market real-return sensitivity:

| specification              |   horizon_years |   episode_n |   episode_median |   episode_negative_pct |   median_excess_pp |
|:---------------------------|----------------:|------------:|-----------------:|-----------------------:|-------------------:|
| expanding_primary          |               1 |           8 |             4.57 |                   37.5 |              -5.35 |
| expanding_primary          |               3 |           8 |            26.5  |                   25   |               2.27 |
| expanding_primary          |               5 |           8 |            24.63 |                   25   |             -18.25 |
| fixed_economic_scale       |               1 |           8 |             2.21 |                   50   |              -7.71 |
| fixed_economic_scale       |               3 |           8 |             8.87 |                   50   |             -15.36 |
| fixed_economic_scale       |               5 |           8 |            23.33 |                   25   |             -19.56 |
| full_sample_diagnostic     |               1 |           8 |             3.46 |                   37.5 |              -6.46 |
| full_sample_diagnostic     |               3 |           8 |            15.83 |                   37.5 |              -8.4  |
| full_sample_diagnostic     |               5 |           8 |            22.12 |                   25   |             -20.77 |
| omit_valuation_sensitivity |               1 |           8 |             5.19 |                   25   |              -4.73 |
| omit_valuation_sensitivity |               3 |           8 |            26.5  |                   12.5 |               2.27 |
| omit_valuation_sensitivity |               5 |           8 |            48.09 |                   12.5 |               5.2  |

The sign of five-year excess return reverses when valuation is omitted. This is stronger evidence against a confident mechanical regime forecast than any one selected historical analogy is evidence for it.

## Sector winners and losers, with the base rate kept visible

The CSVs contain every episode, twelve industries, each horizon, nominal and real returns. This compact panel gives real medians, empirical ranges, and difference from each industry's **own unconditional median**, so a high-return industry is not automatically called a conditional winner:

| asset        |   horizon_years |   episode_n |   episode_median |   episode_minimum |   episode_maximum |   median_excess_pp |
|:-------------|----------------:|------------:|-----------------:|------------------:|------------------:|-------------------:|
| sector_NoDur |               1 |           8 |             4.14 |            -24.57 |             32.5  |              -4.61 |
| sector_NoDur |               3 |           8 |            23.19 |            -18.4  |             63.68 |               1.85 |
| sector_NoDur |               5 |           8 |            33.48 |            -17.29 |            121.84 |              -3.01 |
| sector_Durbl |               1 |           8 |           -14.39 |            -27    |              8.17 |             -19.03 |
| sector_Durbl |               3 |           8 |             0.39 |            -36.97 |             68.76 |             -11.74 |
| sector_Durbl |               5 |           8 |            23.37 |            -16.44 |            117.15 |              -2.97 |
| sector_Manuf |               1 |           8 |            -1.89 |            -15.87 |             19.79 |             -11.38 |
| sector_Manuf |               3 |           8 |            25.05 |            -27.98 |             64.65 |              -0.13 |
| sector_Manuf |               5 |           8 |            26.04 |            -22.59 |            101.91 |             -11.21 |
| sector_Enrgy |               1 |           8 |             1.84 |            -17.02 |             26.01 |              -7.27 |
| sector_Enrgy |               3 |           8 |            19.87 |            -55.07 |             54.42 |              -1.57 |
| sector_Enrgy |               5 |           8 |            33.19 |             -8.95 |             80.26 |              -1.31 |
| sector_Chems |               1 |           8 |             0.75 |            -16.86 |             26.61 |              -6.1  |
| sector_Chems |               3 |           8 |            22.01 |             -7.92 |             73.13 |              -0.31 |
| sector_Chems |               5 |           8 |            29.16 |            -28.81 |            118.93 |              -3.99 |
| sector_BusEq |               1 |           8 |             6.89 |            -61.63 |             16.13 |              -2.16 |
| sector_BusEq |               3 |           8 |            28.73 |            -77.35 |            114.85 |               6.29 |
| sector_BusEq |               5 |           8 |            48.68 |            -68.97 |            246.52 |              17.3  |
| sector_Telcm |               1 |           8 |            -0.63 |            -43.49 |             44.97 |              -6.89 |
| sector_Telcm |               3 |           8 |            12.2  |            -71.35 |             76.11 |              -7.13 |
| sector_Telcm |               5 |           8 |             5.92 |            -63.13 |            115.93 |             -19.85 |
| sector_Utils |               1 |           8 |             5.84 |            -28.27 |             35.42 |              -1.29 |
| sector_Utils |               3 |           8 |            12.12 |            -13.82 |             39.43 |              -5.78 |
| sector_Utils |               5 |           8 |            31.73 |            -13.62 |             64.27 |              -1.44 |
| sector_Shops |               1 |           8 |             9.75 |            -23.87 |             20.68 |               0.84 |
| sector_Shops |               3 |           8 |            16.12 |            -30.2  |             71.16 |             -10.18 |
| sector_Shops |               5 |           8 |            41.44 |            -29.24 |            102.58 |              -9.71 |
| sector_Hlth  |               1 |           8 |             6.78 |            -20.72 |             39.38 |              -1.69 |
| sector_Hlth  |               3 |           8 |            42.4  |            -38.13 |            110.87 |              18.59 |
| sector_Hlth  |               5 |           8 |            43.1  |            -44.84 |            224.59 |              -3.34 |
| sector_Money |               1 |           8 |             0.56 |            -18.36 |             24.52 |              -8.1  |
| sector_Money |               3 |           8 |             5.13 |            -27.95 |             86.64 |             -18.32 |
| sector_Money |               5 |           8 |            31.59 |            -34.18 |            180.7  |             -15.19 |
| sector_Other |               1 |           8 |             0.69 |            -22.81 |             27.28 |              -7.52 |
| sector_Other |               3 |           8 |            14.54 |            -42.84 |             62.99 |              -5.79 |
| sector_Other |               5 |           8 |            23.44 |            -15.14 |             62.33 |              -9.27 |

Illustrations, not validated sector selection rules: durables have a one-year median real return of −14.4%, about 19.0 pp below their own baseline; health has a three-year median of +42.4%, 18.6 pp above its baseline; business equipment has a five-year median of +48.7%, 17.3 pp above its baseline. Business equipment's five-year real sample range is nevertheless −69.0% to +246.5%. Nominal same-date excess returns versus the broad market are separately provided in `sector_relative_returns.csv`. Twelve sectors × three horizons × several screens create substantial multiple-comparison risk. No sector allocation recommendation follows.

## Can the historical result be distinguished from ordinary sampling noise?

For each broad-market horizon/return type, 5,000 random-order greedy selections attempted to draw eight eligible start months at least 60 months apart; successful sets and their median distributions are below. Seed = 20260919; unsuccessful draws that could not fill eight were excluded and counted implicitly by the reported successful totals. The greedy method changes marginal date probabilities; these are **descriptive matched-size reference distributions**, not exact randomization p-values or evidence of causality. They do, however, prevent comparing eight independent episodes against an artificially precise overlapping baseline.

| asset           |   horizon_years | metric                 |   selected_n |   observed_median |   simulated_matched_size_nonoverlap_sets |   baseline_median_p025 |   baseline_median_p975 |   observed_percentile_in_baseline_medians |   descriptive_two_sided_tail_fraction |
|:----------------|----------------:|:-----------------------|-------------:|------------------:|-----------------------------------------:|-----------------------:|-----------------------:|------------------------------------------:|--------------------------------------:|
| US_market_total |               1 | nominal_cumulative_pct |            8 |              6.72 |                                     4970 |                  -0.19 |                  23.77 |                                     13.64 |                                  0.27 |
| US_market_total |               1 | real_cumulative_pct    |            8 |              4.57 |                                     4971 |                  -4.5  |                  19.75 |                                     21.36 |                                  0.43 |
| US_market_total |               3 | nominal_cumulative_pct |            8 |             34.83 |                                     4958 |                  23.96 |                  57.67 |                                     33.48 |                                  0.67 |
| US_market_total |               3 | real_cumulative_pct    |            8 |             26.5  |                                     4958 |                   5.82 |                  40.82 |                                     63.47 |                                  0.73 |
| US_market_total |               5 | nominal_cumulative_pct |            8 |             49.33 |                                     4967 |                  43.14 |                 105.04 |                                      5.7  |                                  0.11 |
| US_market_total |               5 | real_cumulative_pct    |            8 |             24.63 |                                     4955 |                  15.4  |                  66.18 |                                     12.11 |                                  0.24 |

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
