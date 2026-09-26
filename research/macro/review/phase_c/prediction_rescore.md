# Independent prediction rescoring

The original scorecard is not a defensible estimate of either channel's forecasting skill. Its arithmetic reproduces, but many verdicts rely on reviewer-invented horizons, substituted assets, incomplete windows, or single components of a multi-part claim. A stricter reading leaves few completed, well-defined forecasts. That is a limitation of the record, not evidence that every excluded forecast was wrong.

## Design, sequence and coverage

Before reading scored outcomes, I wrote `prediction_preregistration.json`, parsed all 29 raw prediction files, and selected 16 IDs per channel by the SHA-256 ordering of `review002:` plus prediction ID. The raw ledger contains **288 unique predictions: 162 Bravos and 126 Jikh**. A separately labeled 28-row diagnostic supplement selected explicit dates/durations and named events from raw wording. The resulting **60 judgments** were locked before joining prior scores. The lock, its hash and source hashes are preserved in `prediction_independent_locked.csv` and `prediction_lock_receipt.json`.

Rules require a finite endpoint stated by the speaker, a defined object and outcome, a verified condition, and mature observation coverage. A later evaluator's “how to score” column is not the speaker's forecast horizon. Explicit targets receive no invented 10% tolerance. Directional classes use fixed deadbands; no-change and persistence must predict the same class on the same rows. Relayed forecasts remain labeled as relayed. Revised historical data cannot verify what the first release said.

After locking, I read the complete original `verify/out/PREDICTIONS/SCORECARD.md` (475 lines) and `scoring.py` (676 lines), read all 293 scored CSV rows by machine, and examined the discrepant cases. There is no separately named `PREDICTION_SCORECARD.md` in this package; SCORECARD.md is the supplied scorecard. The scorer adds **five Jikh title rows absent from the raw ledger**, recorded in `prediction_added_titles.csv`. Thus 293 is not the count in the underlying 288-row prediction register.

## Results and transparent amendments

The blind locked labels were 35 UNSCORABLE, 15 PENDING, eight CANNOT_VERIFY and two MISS. The deterministic 32-row cohort contained 30 UNSCORABLE and two PENDING; the supplement supplied the specific completed cases. I then fetched official Fed releases and made **five documented post-lock amendments**, preserving all original labels. Four hike/no-hike outcomes were already settled by September 16; a by-deadline event can resolve before its deadline. The June 17 hold also became verifiable from a primary source. This is a disclosed correction to the initially over-cautious pending classification, not an alteration to the blind lock.

| Cohort | HIT | MISS | PENDING | CANNOT_VERIFY | UNSCORABLE |
|---|---:|---:|---:|---:|---:|
| Deterministic 32 | 1 | 0 | 1 | 0 | 30 |
| Diagnostic supplement 28 | 3 | 3 | 10 | 7 | 5 |
| Total 60, after primary verification | **4** | **3** | **11** | **7** | **35** |

Do not report 4/7 as a channel hit rate. The seven completed rows are selected, include relayed forecasts and repeated versions of one Fed outcome, and do not constitute seven independent personal predictions. The row-level record in `prediction_rescore.csv` retains wording, attribution, reasons, old labels, blind labels and final amendments. The primary sample is especially informative about testability, rather than outcome accuracy.

Among the 60 audited rows, the original scorecard called 14 HIT, 15 MISS, eight PARTIAL, 19 NOT_YET_DUE and four UNFALSIFIABLE. After verification, eight of the original 14 hits are UNSCORABLE and two CANNOT_VERIFY; four remain HIT. Of the original 15 misses, two remain MISS, eight become UNSCORABLE, three CANNOT_VERIFY and two PENDING. These are methodological reclassifications, not proof that the excluded calls would have succeeded.

### Concrete adjudications

| Prediction | Final judgment | Evidence and limitation |
|---|---|---|
| BR-20260326-08, next March CPI around 3.5–4% | MISS | Exact calendar YoY is 3.286% in supplied seasonally adjusted data and 3.256% in NSA data. Original PARTIAL used its 10% tolerance. This is revised-data reconstruction, not a first-release audit. |
| BR-20260529-10, relayed Q2 GDP near 4% | MISS for the stated estimate | Supplied GDPC1 quarter levels imply 1.484% annualized growth. Attribution is relayed; initial GDP vintage was not audited. |
| BR-20260501-28 and BR-20260511-21, hike by year-end | HIT | [September 16 FOMC statement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm) raised the target range to 3.75–4.00%. Repeated versions of one event. |
| BR-20260611-24, quoted year-end hike pricing | HIT on event direction only | Same September event. It does not verify the quoted historical probability or a personally originated forecast. |
| BR-20260602-19, quoted no hike before December | MISS on event direction only | September hike breaches the quoted outcome; does not establish that the contemporaneous market pricing was misreported. |
| AJ-20260615-26, June 17 Fed unchanged | HIT | [June 17 FOMC statement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm) maintained 3.50–3.75%; the [April 29 prior decision](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260429a.htm) establishes the same baseline. |
| AJ-20260605-37, critical inventories in 2–3 weeks, then $150–160 oil | CANNOT_VERIFY | The stated short deadline attaches to inventories; price follows a conditional chain. The supplied data lack the specified inventory universe/threshold. Brent's June 5–26 maximum of $97.46 is a price diagnostic, not sufficient to adjudicate the physical antecedent. |
| AJ-20260615-30, SPR exhaustion then oil/inflation/rates rise | CANNOT_VERIFY | No SPR series supplied. Two downstream variables moving higher cannot earn partial credit for a chain whose initial event is unverified. |
| AJ-20260612-45, gold $3,000 potentially in 1–3 years | PENDING | September 2026 is inside the explicitly allowed multi-year window. |
| AJ-20260316-30, relayed war-duration estimate | CANNOT_VERIFY | A ceasefire is not automatically the war's end or reopening of transport. Requires dated primary diplomatic/military evidence and an operational endpoint. |

The frozen corpus and data define this retrospective exercise. Seven unresolved policy/physical-event cases are not silently converted into market-price tests. Primary-source follow-up here verifies the listed Fed outcomes, not all geopolitical and inventory events.

## Strict paired nulls

Before primary verification, **zero** rows satisfied the preregistered direction-only, mature, single-metric eligibility rule. The empty `prediction_paired_nulls.csv` records that result; accuracy is undefined, not zero.

After primary verification, one row qualifies: the June Fed hold. The actual direction, forecast, no-change null and preceding policy-direction persistence are all flat; **all three score 1/1**. The target range was unchanged over the relevant prior interval and at the June meeting. `prediction_paired_nulls_post_verification.csv` keeps this separate. One consensus hold provides no evidence of incremental forecast skill. Explicit reach-by-deadline targets are excluded from this direction-class comparison under the preregistered rules.

## Separate 60-day benchmark experiment

To provide a meaningful matched comparison without inventing original forecast deadlines, I separately preregistered a **researcher-defined 60-calendar-day endpoint experiment** in `prediction_benchmark_design.json`, after the original score audit but before calculating these returns. This is sensitivity analysis, not a reclassification of original forecasts.

The original scorer flags 69 asset rows. I inventoried all 69 and retained 16 with an explicit directional reading and a suitable supplied daily price series: 11 Bravos, five Jikh. They represent only 12 distinct asset/date cells. Exclusions are recorded individually in `prediction_benchmark_selection.csv`: inventory or gasoline replaced by oil, futures/spot mismatches, broad indexes substituted for narrower indexes, unnamed baskets, multi-part statements, title-only directions and unsuitable monthly prices. Conditional rows retained for this experiment are explicitly treated as hypothetical unconditional directions; their antecedents are not claimed to have occurred.

Each retained row uses the same asset, origin and 60-day outcome for all four methods. Actual returns above +2% are up, below −2% down, otherwise flat. Always-up predicts up; no-change predicts flat; persistence predicts the prior 60-day return class. All endpoints are fully matured. Daily origin prices are the final observation on or before the publication date; unavailable intraday publication times make this a descriptive date-based experiment, not an executable signal backtest.

| Same 16 outcomes | Correct | Accuracy |
|---|---:|---:|
| Selected channel direction | 10/16 | 62.5% |
| Always up | 14/16 | 87.5% |
| Prior 60-day persistence | 11/16 | 68.8% |
| No change within ±2% | 1/16 | 6.3% |

The channel directions beat always-up on zero rows and lost to it on four; versus persistence, they won two and lost three. Bravos direction was correct 8/11, Jikh 2/5. These small, overlapping and selected samples do not support significance tests or a general channel ranking. They show that a fair same-outcome null can outperform these selected directions during this particular upward-biased sample. They do not show the original open-ended forecasts were wrong or that an actual subscriber portfolio lost money.

## Original scorecard/code audit

The original **54 HIT + 27 PARTIAL + 64 MISS + 115 NOT_YET_DUE + 33 UNFALSIFIABLE = 293** reproduces. Its strict scored rate is 54/145 = 37.2%; half-credit rate is 67.5/145 = 46.6%. The 113 rows with mapped nulls contain 45 hits, 22 partials and 46 misses; no-change records 28/113 and persistence 42/113. The arithmetic is internally consistent; the outcome definitions are not consistently comparable.

Material defects:

1. **Verdicts are manually embedded in `add()` calls.** The script reproduces those choices; it does not derive every verdict from declared rules. A hardcoded temporary import path also limits portability. Reproducible output is not independent validation of the embedded judgments.
2. **Missing-month YoY bug.** `_yoy` uses `shift(12)` after missing October 2025 is dropped. In 2026 this compares some values with 13 calendar months earlier. Exact January/February CPI is about 2.4%, April 3.8%, May 4.2%, August 3.35%; the old values are 2.83%, 2.66%, 3.95%, 4.27%, 3.71%. `prediction_cpi_calendar_audit.csv` contains all eight comparisons. Some verdicts survive correction—for example May still reaches 4–5%—so changes must be evaluated row by row.
3. **Evaluator-invented horizons.** “Eventually,” “coming months” and title implications are routinely mapped to September 19 or an inferred three/six-month date. This is an operationalization chosen later, not an original dated prediction.
4. **Premature judgments.** BR-20260507-01 is MISS using July data despite a stated 6–12-month test; BR-20260615-23 is a hit before September ends. Endpoint and cumulative no-event statements cannot be settled merely because their interim path agrees. Conversely, genuine event-by-deadline successes can settle early; this distinction prompted the disclosed Fed amendments above.
5. **Different classes for forecasts and nulls.** Original directional price forecasts can receive credit for any positive return while the no-change null receives credit inside a ±2% band. A modest positive move can therefore count as both up and flat under different rules. A null must use the same actual class as the forecast.
6. **Asset and outcome substitutions.** National corporate profits substitute for S&P/Mag7 earnings; broad Health substitutes for biotech; Brent prices substitute for gasoline, inventories and physical shortages. Some conjunctions score the easiest component and ignore the rest.
7. **Conditionality inferred using subsequent events.** The June press-conference hawkish condition is justified partly by a September hike. The FOMC tone and a specified event reaction require the actual transcript, an ex ante tone rule and aligned prices.
8. **Incorrectly paired benchmark.** The original S&P always-long 68/69 statistic compares an S&P outcome against forecasts on other assets and events. It is a broad market backdrop, not paired accuracy. An S&P rally cannot adjudicate a physical-supply forecast.
9. **Attribution and dependence.** Repeated hike calls, quoted futures probabilities, relayed analyst scenarios and personally endorsed forecasts share the same score totals. Multiple rows can earn credit from the same event. Seven strongly worded statements do not establish statistical probability calibration.
10. **Unscorable does not mean permanently unknowable.** The scorecard's “half ... cannot be scored by anyone, ever” confuses pending horizons, unmet conditions, private evidence and genuinely undefined statements.

## Portfolio claims and validation limits

Neither the original scorecard nor this audit establishes actual portfolio underperformance. Required missing inputs include complete dated holdings, trade instructions available before execution, weighting and capital rules, exits, treatment of leverage/cash/dividends, financing and fees, and the complete rather than selected public/premium signal history. A Nasdaq Composite leverage illustration cannot replace QQQ/TQQQ execution records. Public-record gaps justify “not independently verified,” not assertions that pre-public performance must be fabricated or hypothetical. Further details appear in `package_review_events.md`.

Reproduction: run `prediction_checks.py --check --compare` and `prediction_benchmark.py` from the review environment. The first preserves the independent hash, verifies source/sample/count integrity, regenerates joins and separate amendments, and reports eight lock/evidence checks plus six comparison assertions with no failures. The benchmark validates mature endpoints, available observations and complete inclusion accounting. No original ledger, scored package or sealed Phase A/B file was changed.
