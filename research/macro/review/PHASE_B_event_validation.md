# Phase B: independent event validation — frozen thresholds, honest denominators

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

| Indicator         |   Horizon | Hits / alarms   | False alarms    | 95% false interval   | Lead median [min,max]   | Monthly FPR   | Monthly event baseline   |   Eligible months |
|:------------------|----------:|:----------------|:----------------|:---------------------|:------------------------|:--------------|:-------------------------|------------------:|
| baa_level_300     |        12 | 1/6             | 83.3%           | 43.6–97.0%           | 1 [1,1]                 | 10.2%         | 10.9%                    |               440 |
| baa_widening_100  |        12 | 0/0             | undefined (n=0) | undefined            | no hits                 | 0.0%          | 11.0%                    |               437 |
| claims_rise_20pct |        12 | 4/8             | 50.0%           | 21.5–78.5%           | 7.5 [1,10]              | 5.1%          | 15.8%                    |               607 |
| curve_inverted    |        12 | 5/9             | 44.4%           | 18.9–73.3%           | 8 [5,11]                | 5.5%          | 16.0%                    |               752 |
| curve_inverted    |        24 | 6/8             | 25.0%           | 7.1–59.1%            | 9.5 [5,16]              | 5.1%          | 30.8%                    |               740 |
| inflation_400     |        12 | 2/7             | 71.4%           | 35.9–91.8%           | 4.5 [1,8]               | 21.2%         | 16.1%                    |               744 |
| inflation_surge   |        12 | 2/7             | 71.4%           | 35.9–91.8%           | 3.5 [1,6]               | 4.9%          | 16.4%                    |               732 |
| nfci_positive     |        12 | 3/7             | 57.1%           | 25.0–84.2%           | 10 [4,10]               | 16.7%         | 14.5%                    |               581 |
| sahm_050          |        12 | 1/4             | 75.0%           | 30.1–95.4%           | 2 [2,2]                 | 17.2%         | 14.4%                    |               693 |

The Sahm rule's low strict-leading performance is not a failure of its stated diagnostic purpose. Among its eight full-sample diagnostic hits, the median alarm arrives **4 months after** the recorded USREC onset; its range includes one alarm 2 months before through alarms 4 months after. Exact signed lags are in `recession_diagnostic_delays.csv`. The corresponding claims median is the onset month. USREC labels are the series convention (first month after business-cycle peak), not an assertion that NBER announced a recession at that date.

## Recession already present OR beginning in next 12 months: diagnostic target

| Indicator         |   Horizon | Hits / alarms   | False alarms   | 95% false interval   | Lead median [min,max]   | Monthly FPR   | Monthly event baseline   |   Eligible months |
|:------------------|----------:|:----------------|:---------------|:---------------------|:------------------------|:--------------|:-------------------------|------------------:|
| baa_level_300     |        12 | 3/8             | 62.5%          | 30.6–86.3%           | 0 [0,1]                 | 10.2%         | 17.6%                    |               476 |
| baa_widening_100  |        12 | 2/2             | 0.0%           | 0.0–65.8%            | 0 [0,0]                 | 0.0%          | 17.8%                    |               473 |
| claims_rise_20pct |        12 | 9/13            | 30.8%          | 12.7–57.6%           | 0 [0,10]                | 5.1%          | 26.2%                    |               692 |
| curve_inverted    |        12 | 6/10            | 40.0%          | 16.8–68.7%           | 7.5 [0,11]              | 5.5%          | 26.4%                    |               859 |
| inflation_400     |        12 | 2/7             | 71.4%          | 35.9–91.8%           | 4.5 [1,8]               | 21.2%         | 26.3%                    |               847 |
| inflation_surge   |        12 | 2/7             | 71.4%          | 35.9–91.8%           | 3.5 [1,6]               | 4.9%          | 26.7%                    |               835 |
| nfci_positive     |        12 | 5/9             | 44.4%          | 18.9–73.3%           | 4 [0,10]                | 16.7%         | 24.1%                    |               655 |
| sahm_050          |        12 | 8/11            | 27.3%          | 9.7–56.6%            | 0 [0,2]                 | 17.2%         | 24.7%                    |               788 |

Median lead zero in this table means the recession is already active. It is not a zero-delay prediction. Diagnostic Baa widening onsets occur at onset and nine months after onset; neither independently leads a future recession under this definition.

## Chronological holdout: strict future recession

| Indicator         |   Horizon | Hits / alarms   | False alarms    | 95% false interval   | Lead median [min,max]   | Monthly FPR   | Monthly event baseline   |   Eligible months |
|:------------------|----------:|:----------------|:----------------|:---------------------|:------------------------|:--------------|:-------------------------|------------------:|
| baa_level_300     |        12 | 1/5             | 80.0%           | 37.6–96.4%           | 1 [1,1]                 | 16.0%         | 12.9%                    |               280 |
| baa_widening_100  |        12 | 0/0             | undefined (n=0) | undefined            | no hits                 | 0.0%          | 12.9%                    |               280 |
| claims_rise_20pct |        12 | 1/3             | 66.7%           | 20.8–93.9%           | 5 [5,5]                 | 6.1%          | 12.9%                    |               280 |
| curve_inverted    |        12 | 2/4             | 50.0%           | 15.0–85.0%           | 7.5 [7,8]               | 11.9%         | 12.9%                    |               280 |
| curve_inverted    |        24 | 3/4             | 25.0%           | 4.6–69.9%            | 8 [7,16]                | 10.2%         | 23.5%                    |               268 |
| inflation_400     |        12 | 1/3             | 66.7%           | 20.8–93.9%           | 1 [1,1]                 | 12.7%         | 12.9%                    |               280 |
| inflation_surge   |        12 | 1/3             | 66.7%           | 20.8–93.9%           | 1 [1,1]                 | 7.8%          | 12.9%                    |               280 |
| nfci_positive     |        12 | 2/2             | 0.0%            | 0.0–65.8%            | 7 [4,10]                | 2.5%          | 12.9%                    |               280 |
| sahm_050          |        12 | 0/2             | 100.0%          | 34.2–100.0%          | no hits                 | 16.0%         | 12.9%                    |               280 |

This holdout has no threshold fitting, but it is **pseudo-out-of-sample**, not a fully reconstructed real-time investment backtest. Most source histories are revised snapshots. SAHMREALTIME specifically reconstructs information available at each historical observation; that advantage does not make every other input vintage-correct. The 2020 recession also demonstrates why an accidental correct timing association is not proof that the curve forecast the causal shock. Post-2000 sample sizes are too small to choose fine distinctions between competing indicators.

## A 20% loss from signal-month equity price within 12 months

| Indicator         |   Horizon | Hits / alarms   | False alarms   | 95% false interval   | Lead median [min,max]   | Monthly FPR   | Monthly event baseline   |   Eligible months |
|:------------------|----------:|:----------------|:---------------|:---------------------|:------------------------|:--------------|:-------------------------|------------------:|
| baa_level_300     |        12 | 1/8             | 87.5%          | 52.9–97.8%           | 8 [8,8]                 | 11.8%         | 7.4%                     |               476 |
| baa_widening_100  |        12 | 1/2             | 50.0%          | 9.5–90.5%            | 5 [5,5]                 | 0.9%          | 7.4%                     |               473 |
| claims_rise_20pct |        12 | 3/13            | 76.9%          | 49.7–91.8%           | 9 [7,10]                | 15.6%         | 7.7%                     |               692 |
| curve_inverted    |        12 | 2/10            | 80.0%          | 49.0–94.3%           | 12 [12,12]              | 9.9%          | 6.6%                     |               859 |
| inflation_400     |        12 | 2/7             | 71.4%          | 35.9–91.8%           | 6 [2,10]                | 28.4%         | 6.7%                     |               847 |
| inflation_surge   |        12 | 2/7             | 71.4%          | 35.9–91.8%           | 6 [2,10]                | 6.9%          | 6.8%                     |               835 |
| nfci_positive     |        12 | 0/9             | 100.0%         | 70.1–100.0%          | no hits                 | 27.5%         | 7.2%                     |               655 |
| sahm_050          |        12 | 4/11            | 63.6%          | 35.4–84.8%           | 5.5 [5,12]              | 21.5%         | 7.2%                     |               788 |

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
