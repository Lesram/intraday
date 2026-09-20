# Phase A — Independent transcript analysis, sealed before reading Brief 001

## Independent conclusion

The strongest shared pattern is **a stable destination with changing explanations and deadlines**. Both channels return to monetary debasement, financial fragility and the need for an investment process. Bravos repeatedly resolves alarming openings into staying exposed while conditions remain supportive; Jikh repeatedly offers multiple outcomes, then directs viewers to paid content for personal preparation. Neither is fairly described as issuing one continuous, unconditional forecast of an immediate stock-market crash. The harder problem is accountability: original conditional clocks, changing definitions, upstream dependence and the bridge from uncertainty to a commercial solution are not preserved by an isolated true/false count.

This is a corpus conclusion, not a claim that either publisher intentionally misleads. It concerns the selected public sample and does not establish portfolio returns, motive, causation or the quality of missing paid content.

## Coverage, blinding and reproducibility

All **58** raw transcripts were ingested in full and all first-pass spoken text was semantically read by the blind team: the primary reader covered **33 Bravos and the earliest 6 Jikh**, a second reader covered the next **6 Jikh**, and a third covered the latest **13 Jikh**. Full-reading notes, including repaired truncated displays, are in [primary notes](phase_a/semantic_reading_notes.md), [middle Jikh notes](phase_a/jikh_mid_reader.md), and [late Jikh notes](phase_a/jikh_late_reader.md). [Coverage](phase_a/coverage_log.csv) connects every file to its reader and input hash. The raw headers span **March 16–September 16, 2026**; this is seven partial calendar months, not seven complete monthly observations.

There are **28** files with an exactly duplicated second timestamp pass. The parser stops at the first decreasing timestamp and asserts that the removed sequence equals the first pass. The retained corpus contains **187,028 regex-defined word tokens**: **71,033 Bravos; 115,995 Jikh**. These include caption artifacts and are not audio-verified words. Chapter-grouped and short-caption files are combined into complete text; time-local measures use 60-second bins to avoid counting a caption UI difference as a speech difference. See [video metrics](phase_a/video_metrics.csv), [methods and lexicons](phase_a/methods.json), [corpus script](phase_a/analyze_corpus.py), [supplemental script](phase_a/extend_analysis.py), and [manual judgments](phase_a/manual_adjudication.py).

We deliberately did **not** read README/STATE headlines, Brief 001, claims, prior verdicts, analog studies, regime_model.py or processed regime outputs. Raw market data were read through the allowed factbase loader. Nothing outside review was changed. Numbers in this report derive from these saved files or from a dated transcript reference; a transcript number is not thereby verified.

The catalog contains **143 rows: 60 Bravos public, 48 Jikh public and 35 Jikh members-only**. Only **58** public transcripts were selected; **50** public catalog rows are undated/not captured. Therefore the missing **35 paid videos are specifically Jikh's**, and even the public sample is not the complete output of either channel. Conclusions about first appearance mean *first observed in this selected corpus*. Missing paid episodes could contain implementation, corrections or successful calls; they could also contain failures. None is imputed. All counts and narrative absence findings below carry that selection limitation. Source: `corpus/videos.csv`.

## The thesis through time

The [full theme panel](phase_a/theme_by_video.csv) contains every video × theme combination, including zeros. A substantial theme requires at least three lexicon matches and at least one per 1,000 words. This detects subject matter, not endorsement; the semantic reading supplies the argument.

| Month | Bravos: dominant interpretation | Jikh: dominant interpretation |
|---|---|---|
| March | Oil shock converts prior optimism into caution. March26 **2:02** explicitly acknowledges a radical stance change; **5:50–6:38** names oil below $80 as an invalidator. Commodity bottleneck opportunities survive the warning. | Private credit, oil and fiscal fragility; several geopolitical outcomes. March31 **26:00 onward** discloses roughly40% cash/net worth, retained equities/BTC and willingness to miss upside. March16 explicitly denies making a categorical crash call. |
| April | April8 treats equity recovery as premature; April23 **4:49–6:28** instead explains strength by nominal earnings and permits another10–15% upside. April27 labor/curve data reduce immediate recession risk. Agricultural stock opportunities become central. | April7 **7:23 onward** debt spiral/printing and digital control; April20 **10:00–13:00** tanker exhaustion and near-term oil convergence deadlines. Physical shortage is presented as reality that financial prices must eventually recognize. |
| May | Profits, tax policy and AI infrastructure keep equities strong; threats move toward late2026/2027, or post2028 tax change. May7 semiconductor exposure expected to persist; May15 substantially reduced exposure. Quant allocation product launches May29. | May4 geopolitical/dollar leverage; May15 digital control. May20 scarce assets win across alternative monetary outcomes; May26 explains rising stocks as anticipation of rescue. Premium content explicitly contains concrete positioning. |
| June | Adoption, liquidity, momentum and low claims support AI/stock strength. June15 **4:00–7:30** gives the yield-curve recession signal a September2026 test, then allows growth through mid2027 if the danger window passes. | AI IPO exit-liquidity story; gold versus digital-dollar systems; a conditional Fed preview. June22 **1:49** presents the realized branch as successful prediction despite June15's market-derived97.4% hold baseline and two price-response branches. |
| July | July7 attributes the oil round trip mainly to dollar/Fed conditions, expecting limited hikes. July23 treats mega-cap underperformance as a potential opportunity while bank lending standards ease. | AI economics, gold settlement, Korean leverage, yen repatriation. July15's $38,000 gold figure is conditional annual-flow arithmetic with a decade-plus horizon, not an immediate target. |
| August | Financial inequality/taxes; China/gold monetary transition; yen and sovereign debt; AI overinvestment. August21 **11:44** uses Fed rates above5.5% as a material unwind threshold, while remaining constructive nearer term. | Currency rescue, sanctions/payment systems, private-credit/insurer exposure, stablecoins and debt management. August10 explicitly rejects equating transaction use of Bitcoin with buy-and-hold demand. |
| September | Financial repression, China's oil buffer, AI funding and PMI/curve. September16 still permits expansion until June2027 despite rate hikes. September9 **1:00–2:00** says earlier oil doomsday forecasts did not occur, without explicitly reviewing the channel's own spring scenarios. | Alleged manufactured cybercrisis; hidden easing; then a long hypothetical evolutionary AI takeover. September10's near-term hike/hold forecast is not revisited in September16's different topic. |

References are the correspondingly dated files in `corpus/transcripts/`; exact file names and reading locations are in the linked coverage notes. These are qualitative changes, not automatically contradictions. The stable Bravos conclusion is usually *participate through a responsive strategy*. The stable Jikh conclusion is often *institutional control/dollar debasement is advancing; understand and prepare*. A changed mechanism can be a reasonable update. The missing step is often explicit resolution of the old deadline or mapping from old decision rule to new rule.

Quantitative theme shares corroborate the rotation. Bravos oil mentions fall from **13.3/1,000 words in March** to a June panel dominated by AI (**8.7/1,000**); August gold and dollar each reach **6.4/1,000**, and September debt/credit **7.9/1,000**. Jikh oil reaches **9.9/1,000 in April**, gold **6.6 in June**, AI **6.0 in July**, and dollar **8.0 in August**. These are lexical observations from [monthly themes](phase_a/monthly_themes.csv), not a fitted sentiment score.

## What stops being followed up

[Phrase tracking](phase_a/tracked_thesis_phrases.csv) supplies a reproducible search aid; manual interpretation is necessary because a mention of a date may concern a different event.

| Earlier proposition / deadline | What appears later | Independent assessment |
|---|---|---|
| Bravos March26 **3:46–5:00**: negative real earnings yield allegedly never fails to precede a20% correction | That precise named rule does not recur in the remaining32 sampled videos; earnings, taxes, liquidity and momentum take over | A retired explanatory rule without a clear closure. Not a proven false forecast without a specified horizon and comparable earnings series. |
| Bravos April20–23: agricultural ETF/stocks with exceptional near-term upside | Later pitches move to AI inputs, allocation models and strategy calls | Named agricultural-pitch lexicon occurs in2 videos; disappearance is not a scored loss. Named tickers and dated prices are missing. |
| Bravos June15: by September2026 the yield-curve recession-window test should clarify failure | September16 uses the curve to support growth untilJune2027 without reporting the original deadline's result | A particularly useful prospective register entry. September19 is still inside September: do not prematurely label a September deadline expired; later recession dating also arrives with delay. |
| Bravos August21:5.5% Fed threshold needed for bubble unwind | September16 emphasizes the current hike as an eventual danger | A load-bearing threshold is not retained consistently in later rhetoric; strict contradiction is not established because horizon/outcome also change. |
| Jikh April20 **11:00–13:00**: last tanker/inventory buffer and short-squeeze week | May/June introduce new inventory deadlines and later institutional explanations | Preserve each deadline with its geography, inventory and condition. Different reserve clocks must not be pooled into a single repeatedly failed forecast. |
| Jikh June30 **23:01–24:00**: possible July4 gold-backed event | July15 keeps the gold-reset narrative with no July4 resolution | Abandoned promoted scenario, explicitly speculative. It must not become a firm personal forecast after the fact. |
| Jikh June5 **18:56–19:13**: big IPOs almost always closely precede peaks | June12 **29:23–29:44** introduces1995–2000 as years of possible delay | Material timing qualification without acknowledging the earlier practical message. |

The exact correction lexicon finds **zero** occurrences of its narrow phrases such as “I was wrong” across58 files. That does **not** mean zero corrections: Bravos March26 acknowledges changing stance, and Jikh June22 explicitly notes adverse outcomes for his policy checklist. Phrase absence cannot replace semantic reading.

## Certainty, hedging and urgency

The frozen lexicon is intentionally simple: certainty includes *will, guaranteed, certainly, definitely, inevitable, must*; hedges include *could, may, might, possibly, perhaps, probably, potentially, likely, unlikely*. It counts grammar in quotes, historical explanations and ads as well as the narrator's forecasts. “Will” is not a probability, and a question or a negation may reverse the meaning. Titles are retained separately.

| Channel/month | Videos | Certainty /1k | Hedges /1k | Urgency /1k |
|---|---:|---:|---:|---:|
| Bravos March |2|4.42|5.01|0.59|
| Bravos April |5|2.17|4.81|1.04|
| Bravos May |6|2.49|4.70|2.11|
| Bravos June |6|2.58|3.64|1.05|
| Bravos July |2|1.22|5.19|1.53|
| Bravos August |8|1.98|4.22|1.32|
| Bravos September |4|1.36|5.46|1.91|
| Jikh March |2|2.11|7.32|1.33|
| Jikh April |2|5.54|3.06|3.54|
| Jikh May |4|2.60|4.40|1.48|
| Jikh June |6|3.86|3.90|0.93|
| Jikh July |4|2.17|3.52|1.35|
| Jikh August |4|1.86|3.39|1.07|
| Jikh September |3|2.73|5.26|2.26|

Source: [monthly rhetoric](phase_a/monthly_rhetoric.csv), dated transcripts and published lexicon. Strong uncertainty language survives strong headline urgency. September16 Jikh's invented future-agent counts particularly require a hypothetical-scenario label; turning them into observed quantitative claims would be a category error.

Exploratory correlations use one video as one observation, not independent daily samples. Bravos urgency versus trailing30-day S&P change has Pearson **r=.139** and versus Brent **r=.035**, **n=33**. Jikh corresponding values are **.080** and **.224**, **n=25**. VIX/urgency correlations are **−.122** and **.272**. Bravos certainty/VIX is **.528**, showing that a “rhetoric unrelated to markets” blanket claim would be too strong. These18 unadjusted descriptive comparisons are not a discovery of stable predictive relationships; date clustering, omitted topics, lexical choices and small selected samples matter. All observations and rank correlations are in [market values](phase_a/rhetoric_market_values.csv) and [correlations](phase_a/rhetoric_market_correlations.csv).

There is **no sales contract or campaign calendar**. Consequently the proposed market-versus-sales-calendar test cannot be identified here. Offer language is observable; sales scheduling and causal incentives are not.

## Commercial structure and provenance

Bravos' product changes from specific resource-stock reports in spring to a quant launch in lateMay/June, then strategy calls and event-specific packages. All33 fully read videos contain a product/service invitation, including July7's free model event. Keyword detection catches31/33, which demonstrates why the keyword count is a lower bound. The detected pitch-sentence median is at **96.6% of runtime**, versus **44.3% for Jikh**, whose mid-video sponsor reads shift the statistic. These are sentence-location medians, not precise ad-start medians or percentage of runtime sold.

Sixty-second pitch-marker bins show Bravos certainty **2.93/1k** versus **2.05/1k** elsewhere, and hedging **3.85** versus **4.71**. For Jikh the corresponding certainty rates are **2.26 versus2.99**, hedges **2.00 versus4.46**. Urgency is actually lower in marked pitch minutes in both channels. This rejects the simplistic claim that every pitch has more alarm words. The stronger pattern is a **structural transition from complex threat to an offered solution**, which a local adjective count misses. Bins can mix analysis with promotion; silence between markers does not delimit an entire ad. Sources: [pitch sentences](phase_a/pitch_sentences.csv), [minute bins](phase_a/minute_windows.csv), [comparison](phase_a/pitch_rhetoric_comparison.csv).

Manual late-Jikh audit finds **13/13 closing premium invitations and12/13 distinct external sponsor reads**, with **4 financial and8 media/privacy/lifestyle placements**; July28 also has a closing brokerage promotion. The middle block has **6/6 premium invitations and5/6 sponsor reads**. Examples: June24 **10:34–11:43**, geopolitical uncertainty→Gemini event markets; August5 **10:08–11:07**, what to do→Alpha Picks; September2 **11:08–12:04**, feared digital control→DeleteMe. July15/Zocdoc is much less connected to asset direction. These observed transitions do not prove editorial control or intent. Reader notes preserve exact locations and distinguish caption-uncertain brand spellings.

Source diversity must be measured at the level of **an argument's organizing framework**, not the count of logos. Luke Gromen/FFTT is named in **13/25 Jikh videos (52%)**, including **all6** middle-block videos. The automated count of38 alias hits is not38 independent citations: name andFFTT can occur in the same sentence. Simon Dixon, Ed Zitron, Catherine Austin Fitts and other interpreters supply additional frameworks. At least **9/13** late videos identify an outside interpreter as a substantial explanatory foundation. [Named mentions](phase_a/named_source_mentions.csv) distinguish source names from [citation-like sentences](phase_a/citation_like_sentences.csv); neither can determine the fraction of uncited ideas borrowed.

Bravos frequently discusses the Fed and shows unnamed charts; its163 Fed-name mentions are plainly **not163 independent primary sources**. We cannot identify one upstream source as the origin of most Bravos content from transcripts alone. Neither can we measure accuracy decay at every transmission link when the original chart/paper/newsletter is absent. What we can see is a common transformation: a source supports a component, then the narrator adds a causal mechanism. Examples include China's low bond yield→safe-haven capital inflow; gold exports→a destination and strategic intent; two large marginal exposures→an asserted AI/private-credit/insurer chain. Validating the component does not validate the arrow.

## Cross-channel convergence: shared inputs, not demonstrated copying

The first-observed substantial-theme table covers13 themes present in both channels. Jikh appears earlier for11; Bravos earlier for2. The result is heavily affected by the corpus starting four days earlier for Jikh and by selected older videos. A133-day lead for observed China/deglobalization discussion or a35-day lead for metals is **not**133/35 days of demonstrated investment information advantage. [All first-observed dates](phase_a/cross_channel_first_observed.csv) carry file/timestamp evidence.

A complete comparison of **33×25=825 video pairs** yields only **4 pairs with any exact shared10-word phrase**, **58 overlapping windows** in total. The largest is Bravos August25/Jikh May26 (**38 windows**) and is mainly a shared opening news/interview clip. Bravos September9/Jikh April20 has **12**, also including the same IMF news wording. The remaining pairs concern a quoted Chinese gold statement and a common Japan/bond-market phrase. Consecutive overlapping windows are not independent matches. See [all pair scores](phase_a/cross_channel_phrase_overlap.csv) and [matched phrases](phase_a/shared_10word_phrases.csv). This establishes shared language and common upstream material; it does not establish who watched whom. Paraphrase borrowing also cannot be excluded by a low exact-match score.

## Did themes precede prices?

The price exercise deliberately distinguishes *first observed subject mention* from *a forecast*. The raw snapshot is revised data, not contemporaneous vintages. Daily first-theme context uses a one-day lag; monthly gold/CPI/unemployment uses a conservative45-day reference-date lag to avoid silently using a completed-month number midmonth. This is not a substitute for actual release calendars. Rate-series percentage changes in the data table are relative changes in the quoted rate, not percentage-point changes or asset returns.

Brent first crossed **$90 on March6 ($95.74)** and **$100 on March12 ($102.38)** in2026. Jikh's first selected oil-heavy video is March16, **10/4 calendar days after those crossings**; Bravos March20 is **14/8 days after**. Prior30-day Brent changes at the respective lagged observation were **+47.56% and+59.17%**. Both discussions follow a large move already in progress. This does not rule out earlier unavailable warnings. Sources: raw EIA-mirror Brent series, [crossing table](phase_a/round_threshold_crossings_2026.csv), [context](phase_a/first_theme_price_context.csv).

The first Bravos AI-heavy video March26 precedes another **+13.25% NASDAQ Composite change over30 days** and **+16.68% over90**, while the preceding30 days were **−3.08%**. It does not follow that a theme keyword forecasts the index: March26's practical message was caution and resource rotation. The first Jikh AI mention similarly occurs inside a risk discussion. Semantic direction and horizon must be retained.

Selected dated scenario paths illustrate why a single end-date verdict fails:

| Public reference | Market path from previous available observation | What it establishes |
|---|---|---|
| Jikh April20 oil squeeze/convergence discussion | Brent$98.63 April17→$113.89 April27 (**+15.47% in7calendar days**), then$80.46 June19 (**−18.42% by60days**) | Directional near-term oil warning was not simply wrong; later weakness does not erase the first week. We lack the specified futures/dated physical spread, so cannot verify convergence itself. |
| Bravos March26 oil<$80 invalidator | First subsequent below80 observation **June18,$79.35** | April's return to bullish stock framing happened before that particular invalidator. Other changed conditions may explain it. |
| Bravos April23 possible10–15% stock upside over months | S&P$7,137.90 April22→7,498.96 July22 (**+5.06%**); maximum to then **+6.61%** | The specified upside range was not reached within90calendar days in this proxy. “Before all said and done” has no fixed terminal date, so this is not a definitive miss. |
| Jikh March31 cautious40%-cash disclosure | S&P6,343.72 March30→7,440.43 June29 (**+17.29%**), maximum **+19.96%** | There was opportunity cost relative to full equity exposure over that window. It is not his portfolio return: timing, cash interest, remaining holdings and weights are incomplete, and he explicitly accepted missed upside. |

Sources and all horizons are saved in [scenario paths](phase_a/selected_dated_scenario_price_paths.csv). Equity figures are index levels, not dollars paid for an index share; all returns here are price returns. The study has no retail sentiment time series, so cannot establish leading retail sentiment. Forecast-value evaluation requires a prospectively frozen event and null, not retrofitting whatever later moved.

## Contradictions: systematic search with semantic adjudication

The detector extracts **818** directional sentences across seven families, then writes **all13,500** same-channel, later-date, opposite-polarity pairs. This is an auditable candidate universe, **not13,500 contradictions**. A deterministic SHA-ranked sample of **2 per channel×family =28** was manually adjudicated; **0/28** are strict same-proposition X/not-X contradictions. Historical versus current events, distinct countries, conditional branches, negation scope, unrelated word objects and decimal sentence splitting explain the apparent conflicts. This is evidence against using lexical contradiction counts, not a confidence interval proving that the channels never contradict themselves. See [predicates](phase_a/directional_predicates.csv), [all candidate pairs](phase_a/opposite_direction_candidate_pairs.csv), and [28 judgments](phase_a/contradiction_sample_adjudicated.csv).

Full semantic reading finds the following more useful instances. The [curated table](phase_a/curated_contradictions_and_revisions.csv) records both dates, files, timestamps, verdict, reason and what would settle each.

| ID | Earlier → later | Classification |
|---|---|---|
|A01|Bravos May15 **1:32**: attributed bubble rule requires+100% over2years plus relative condition → June2 **0:51**: rule is+100% in1calendar year|**Definition contradiction.** Same attributed official rule cannot have both operational definitions.|
|A02/A03|Bravos May11 **6:54**:1999 hikes began June → May29 **7:57**:January → June2 **5:42**:May|**Fixed-event contradiction**, one underlying historical inconsistency expressed in two pairs; not independent forecasting errors.|
|A04|Bravos March26 **8:30** oil-above80 caution → April23 **5:55** possible10–15% upside|Material change in practical outlook; new profit/labor evidence means not strict logical contradiction.|
|A05|Bravos May7 **5:30** semiconductor exposure → May15 **2:16** significantly reduced|Position change; retained exposure and new prices can reconcile.|
|A06|Bravos April27 **5:42** steepening/weakness → June15 **7:30** steepening/growth|Different horizons and an explicit survival condition.|
|A07|Bravos June11 **5:32** low cash/market cap → August9 **0:59** high cash/GDP|Different denominators; compatible.|
|A08/A09|Dollar strength versus multi-year weakness; May11 hike expectation versusJuly7 little/no hike expectation|Different windows or an updated forecast, not immutable factual contradiction.|
|A10|Bravos August21 **11:44** Fed5.5 threshold → September16 **19:04** hike danger|Trigger reframing; freeze outcome/horizon before scoring.|
|A11|Jikh March16 **1:18** private credit3trn → March31 **1:18**9.4trn under same label|Scope/caption ambiguity; source universes required.|
|A12|Jikh June5 **19:13** IPO peak timing → June12 **29:23** years may remain|Unacknowledged timing qualification.|
|A13|Jikh May20 **23:46** cash/scarcity argument → June12 **30:22** substantial cash/no metals|Implementation/horizon tension; not hypocrisy established.|
|A14|Jikh June15 **1:03** market97.4%hold and two branches → June22 **1:49** successful-call framing|Retrospective branch selection; incremental skill unproven.|
|A15|Jikh June22 **0:00** signed deal → same video**22:02** not happened|Agreement versus implementation ambiguity.|
|A16|Jikh April7 **7:23** yield danger4.6–4.8 → May4 **20:02** dysfunction4.4|Threshold drift; different severity definitions could reconcile.|
|A17|Jikh August25 **26:50–27:13** zero-interest stablecoin user becomes no-interest buyer of US debt → September2 **24:02–24:17** issuer receives Treasury4–5% while user gets0|**Material financing-model inconsistency.** The issuer's funding cost and Treasury's borrowing cost are distinct. Later correct mechanics undermine earlier asserted mechanism.|
|A18/A19|Jikh July28 **23:31–23:52** unconfirmed Article589 resumes as operating mechanism; August19 **1:53** unknown insurer AI exposure becomes asserted aggregate flow **21:17–21:26**|Epistemic escalation/unsupported linkage, not direct numerical X/not-X.|

The complete first-pass reading and reproducible candidate inventory are broader than anecdotes, but **we cannot certify detection of every possible semantic contradiction** in58 long transcripts. The identified strict conflicts and all other candidates are separated deliberately. Original audio, charts, external source definitions and missing videos could settle or change some classifications.

## What atomization probably misses — hypotheses to check in Phase C

1. **Forecast ancestry:** whether the probability was quoted from CME, a newsletter framework or the narrator's independent view; June15→June22 illustrates why a correct outcome need not beat a null.
2. **Scenario trees and later branch selection:** every alternative must remain attached to the original call, with conditional and unconditional scores separated.
3. **Unresolved clocks:** publication-date forecasts, new inventory geographies and revised thresholds must form a version history, not replace earlier entries.
4. **Causal arrows:** verified endpoints do not establish purpose, mechanism, aggregation or an unobserved joint exposure.
5. **Scope and denominators:** nominal/real/gold-relative, government/consumer financing costs, market value/flow, level/change, and all-retirement/specific-index claims must travel together.
6. **Invented and quoted speech:** September16 Jikh's hypothetical numbers and Bravos' news clips are not the narrator's own observations or unconditional forecasts.
7. **Commercial architecture:** the timing of a pitch, public uncertainty versus paid implementation, changing products and recurring limited-time language are part of the message.
8. **Missingness is informative:** Jikh May4 explicitly says some detailed updates move behind membership partly because public distribution affects the algorithm. Public-selection bias is plausibly non-random, but its sign is unidentified.
9. **Fairness to actual nuance:** attribution of Karp's incentive, Bitcoin settlement versus investment demand, admissions that the model may be wrong, and long holding horizons must survive extraction.
10. **Temporal model stability:** a historical onset date or bubble definition is a more direct contradiction than two economically different scenarios pointing in opposite directions.

Atomization remains the right tool for checking a precise quantity against a dated source. Corpus analysis is better at following how confidence, conditions, commercial framing and explanatory responsibility move across time. Its weakness is subjective semantic interpretation; the saved notes, explicit non-contradiction judgments and repeatable counts make that interpretation inspectable.

## Corrections and limitations recorded before sealing

- An early tool display was truncated. All missing raw-text ranges were re-read; the full-reading claim is based on repaired coverage, not previews.
- Initial date-based gold/CPI examples risked using a monthly observation before its completed month; first-theme context was corrected to a conservative45-day lag. Original release vintages remain unavailable, so this is descriptive rather than point-in-time backtesting.
- Initial source lexicons omitted named interpreters and some caption spellings; the final published lexicon incorporates semantic-reader findings. It is exploratory, not preregistered.
- Some phrase searches initially matched July14 as July4 or unrelated mentions of “another week.” Word boundaries and narrower calendar phrases were applied; the table remains a search aid requiring manual interpretation.
- The September curve deadline has **not expired as of September19**. It is a follow-up obligation, not a settled miss.
- No source-accuracy propagation rate, sales-calendar causality, causal copying, complete channel track record or paid-content performance is estimated. Missing source originals, exposure records, event calendars and selected/paywalled videos prevent those estimates.

No Phase C knowledge is incorporated. Subsequent disagreements with this report belong in Phase C; this record is to remain unchanged after hashing.
