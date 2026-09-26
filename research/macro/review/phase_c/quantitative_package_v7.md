# V7 full-package adversarial reading

Read after the blind seal: every line of V7 SUMMARY (163 lines) and facts.md (1,142 lines), including the three opening analyses, all inflation, labor, AI, consumer, business-cycle, housing and promotional sections. The verdict CSV was loaded completely for schema and coverage. It contains 150 claims and 141 unique fact keys; the facts log has 142 fact headings because `debt_gdp_125` has an empty Claims field. SHA-256 receipts are in `quantitative_input_reading_receipts.json`. This is a review of the evidence and reasoning in the package, not a fresh verification of every external citation.

**The package's relative channel accuracy should not be used unchanged.** Its most consequential demonstrable error is the calendar-growth bug: it criticizes Bravos for quoting values that the corrected supplied CPI data support. It also accepts several Jikh figures by inventing an unobserved first print or nowcast while holding Bravos to revised data. Neither problem proves the opposite ranking; both require neutral claim-date rescoring.

## 1. Executed CPI check reverses a repeated criticism

`factbase.fred()` drops missing observations. Computing `pct_change(12)` on a series missing October 2025 compares 13 calendar months in the affected 2026 rows. The following values were executed from the supplied raw CPI, with a complete monthly index and `fill_method=None`; full results are in `quantitative_v7_calendar_growth_check.csv`.

| CPI observation | V7 / 12-row calculation | Correct 12-calendar-month calculation |
|---|---:|---:|
| January 2026 | 2.829% | 2.391% |
| February 2026 | 2.665% | 2.434% |
| April 2026 | 3.947% | 3.779% |
| May 2026 | 4.270% | 4.167% |
| August 2026 | 3.713% | 3.353% |

- `cpi_2026_rise_2.4_to_3.8`, BR-20260529-20: the finding that CPI "never printed 2.4%" in 2026 is false on the supplied calendar-correct series. January and February round to 2.4%; April rounds to 3.8%. The quoted levels are supported, subject to original-vintage confirmation. [facts.md:134](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:134)
- `cpi_2026_rise_2.4_to_4.2`, BR-20260618-14: likewise, the criticism of the 2.4% starting point is wrong; May rounds to 4.2%. [facts.md:141](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:141)
- `cpi_early2026_2.5`, BR-20260326-13: corrected January–February average is approximately 2.413%, not 2.75%. "Around 2.5%" is closer than the verifier says. [facts.md:155](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:155)
- `stablecoin_real_yield_3.7_inflation`, AJ-20260902-55: V7 confirms 3.7% using an incorrect August growth calculation; correct August CPI is 3.353%, and an August CPI observation is not a print available September 2. A quoted Warsh statement must be evaluated against its own date and measure. [facts.md:218](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:218)

Jikh's rounded 4.2% May CPI claim remains supported after correction; the issue is not uniformly adverse to either channel. Core CPI is also affected (August 2.446%, not 2.763%). Core PCE has no analogous gap in this capture and its 2026 growth values match the calendar calculation. The reported real-average-hourly-earnings examples match the separately executed calendar-based wage/CPI ratio (May −0.798%, August −0.259%); they should not be discarded merely because the nearby standalone CPI series was wrong.

## 2. First-print uncertainty is treated asymmetrically

| Claim | V7 treatment | Necessary correction to the review process |
|---|---|---|
| Bravos >120,000 jobs/month, May 29 | FALSE based on current-vintage 12-month average +30.2k and three-month average ~73k | Identify the intended averaging window and recover the contemporaneous release before asserting a factor-of-four falsehood. Current revised history is relevant as a later outturn, not proof of what was knowable that day. [facts:476](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:476) |
| Jikh latest report +172,000, June 15 | MOSTLY_TRUE although no first-print vintage is held; the verifier says such a first print is "entirely consistent" with revisions | Plausibility is not verification. Mark original print unresolved until an actual dated release confirms it. [facts:497](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:497) |
| Jikh savings rate 2.6%, June 5 | TRUE using June's value; V7 admits April's 2.9% was available and speculates "early or quoting a nowcast" | An unnamed nowcast cannot be invented to rescue a mismatched observation. Establish the actual release/vintage or mark the precise figure unresolved at claim date. [facts:802](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:802) |

This does not establish either payroll claim as false. It establishes unequal burdens of proof. The same rule must govern both channels: compare like measure, horizon and original release; distinguish a later revision; do not fill a missing source with a favorable assumption.

## 3. Claims and counterevidence use different timestamps or objects

- `corporate_profits_record` on June 15 and `earnings_up_wages_flat` on June 5 are supported using **2026 Q2** profit share, a quarter that was still underway. The "as of 2026-04-01" label is the observation's quarter-start index, not publication availability. The June record assertion needs Q4/Q1 releases and contemporaneous vintages. [facts:774](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:774)
- A May 1 core-inflation statement is assessed using a May observation and later August average. Core PCE's April observation is similarly called available on May 11. Release dates must be tracked independently of monthly date labels. [facts:176](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:176), [facts:190](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:190)
- April 8 aluminum strength is confirmed with the May peak; April 20 commodity claims use a complete April monthly mean. These later observations can document persistence but cannot adjudicate the earlier numerical statement. [facts:390](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:390)
- The commodity breakout on September 10 is confirmed by a September 14 article. An after-date source can validly report an earlier event, but V7 does not establish that the cited breakout had already happened by September 10. [facts:369](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:369)
- The sentiment/stock-expectations claim is assessed using the actual S&P price level, while the claimed stock-expectations survey series is explicitly absent. Price and consumer expectations of future price are different variables. A useful related calculation cannot justify TRUE for the specific claimed divergence. [facts:760](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:760)
- PPI 6% is criticized with PPIACO, the all-commodities index. Before calling the number understated, establish whether the speaker meant the headline final-demand PPI or a different producer-price measure. A broader commodity index cannot silently substitute for that release. [facts:169](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:169)
- The Moody's 12-month recession-probability chart is unidentified, appropriately UNVERIFIABLE. Comparing it to a smoothed probability of an already occurring recession does not disprove it: forecast target, horizon and information set differ. [facts:1035](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:1035)
- `gdpnow_4_to_below2_2026q1` compares end-of-quarter figures from **different forecast quarters**, not recoverable snapshots of one Q1 forecast. This cannot confirm that the Q1 nowcast fell along the claimed intra-quarter path. [facts:951](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:951)

## 4. Several claimed contradictions are compatible time windows

V7 calls a curve flattening in early 2026 versus steepening **since mid-2023** a direct contradiction. Both can be true: −0.90 in July 2023 to +0.68 in January 2026 is a steepening; +0.68 to +0.36 thereafter is a flattening. Whether the commentator improperly extrapolates the long trend into the present must be judged from the surrounding transcript, not by equating the two baselines. [facts:979](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:979), [facts:986](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:986)

Similarly, saying breakevens were rising in March and later broadly stable through July is not automatically an internal contradiction. The quoted "toward levels not seen since 2022" can still be imprecise, but the separate stability statement refers to a later and longer observation window. The blind transcript analysis should control the contradiction label.

The inversion review tests **uninversion when a recession has not already begun**, then uses that restricted four-event subset to dismiss a claim about recessions following **inversions**. It is a useful distinct test, not the same proposition. The original inversion's onset and uninversion signal must each have its own denominator, follow-up horizon, release lag and false-positive definition. The blind Phase B event study provides another explicitly defined monthly GS10−TB3MS series; its 6/8 result cannot be transferred to T10Y2Y. [facts:11](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:11)

## 5. Internal arithmetic and inference repairs

1. The stated top-five profit-share quarters are 2026 Q2, 2025 Q4, **2021 Q2**, 2026 Q1 and **2021 Q3**. Only three of those are in the last five quarters. The supplied data reproduce that list exactly; "four of five" is an arithmetic error. [facts:52](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:52)
2. A comparable core-inflation average in **1994** means "highest since the 1980s" overstates elapsed rarity, not understates it as V7 says. [facts:190](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:190)
3. June 2025 through July 2026 contains **14** calendar months, not 13 consecutive months. V7 alternately describes 13 consecutive and 14-of-15 observations. Recover the actual flagged dates before using the duration multiplier. Its two 1980 points also remain one episode. [facts:81](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:81)
4. Gasoline +50% is MOSTLY_TRUE despite no gasoline series and prose saying it is "almost certainly overstated". That is weak evidence for the numerical verdict; crude is an explicitly imperfect proxy. [facts:355](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:355)
5. A promotional unspecified-stock strategy cannot be falsified with a drawdown in **spot Brent**. The pitch deserves UNVERIFIABLE/unsupported certainty, but the purported counterexample is not the claimed portfolio, entry rule or holding period. [facts:1130](/Users/marselkei/VS/intra/research/macro/verify/out/V7/facts.md:1130)
6. Low claims and falling unemployment do not make every labor deterioration claim false: the same package confirms very weak payroll growth, lower participation, low hiring and declining real hourly pay. "They are wrong about the direction" collapses distinct labor indicators into one outcome. The defensible conclusion is mixed labor conditions without broad recession stress, not a single universal direction.

## What remains useful

The package openly identifies many missing sources, distinguishes some current-vintage revisions, identifies the limit of labor-share reconstruction, and flags small event counts. Its arithmetic caveats about real versus nominal data, oil versus pump prices and level versus flow are useful when applied consistently. The supplied data do support several central observations: low layoffs, elevated profit share, weak household sentiment, an early-2026 inflation rebound, and the absence of an already registered recession as of the cutoff. Those observations do not validate every quoted figure, causal story or forecast.

To repair the package, rescore affected rows neutrally using calendar-correct growth, exact quoted measures, publication timestamps and original-release evidence. Preserve unsupported claims as unresolved. Report the score both before and after corrections without converting this targeted audit into a fresh unsupported channel ranking.
