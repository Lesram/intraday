# Reconciliation notes for the final research package

Prepared 20 September 2026. This is a research reconciliation, not a software release or a new set of blind judgments.

## Coverage and authority

[CHANGE_DISPOSITION.csv](../CHANGE_DISPOSITION.csv) accounts for all 41 items in Consolidation 003's implementation delta: DELTA-01 through DELTA-17, WD-01 through WD-17, and RV-01 through RV-07. It adds F01 through F18 for errors, qualifications and boundaries resolved in finalization. Across the 59 records, 24 are accepted, 33 modified and two rejected. These classifications concern the referenced proposals or assertions; they are not a score of either study's accuracy.

[RESOLUTION_LEDGER.csv](../RESOLUTION_LEDGER.csv) retains every one of the 74 source dispute IDs exactly once. Its final findings accept 40 and modify 34. The source verdict and source status remain explicitly labeled historical fields. A source row marked closed does not mean a future software repair has been implemented.

The final finding, reason and authoritative-destination columns are the operative resolution. The original [delta](../../consolidation/IMPLEMENTATION_DELTA.md) and [ledger](../../consolidation/RESOLUTION_LEDGER.csv), Study 001, sealed Review 002 and their data remain intact. “Applied by final supersession” means the new report, proposed contract or these notes replace an earlier interpretation. It does not mean historical generators, the existing monitor, the dashboard or the trading system were patched.

Software changes in DELTA-01 through DELTA-07, DELTA-09 through DELTA-16, and relevant contract/UI propagation remain deferred until the user's later tool decision. DELTA-08 and DELTA-17 are accepted historical documentation defects but their source files are also preserved. Corrections to figures and interpretation are carried in the final package instead.

## Independence, exposure and disagreement

**C-05 / F01.** Review 002's procedure was label-blind within its declared scope, not fully independent. The readers used the same model family and shared source material. The permitted event scaffold contained evaluative language, including prior outcome labels and severity guidance. The [fact reader's own disclosure](../../phase_c/blind_review_notes.md) acknowledges using event chronology and explicitly disclaims full source/model independence.

Consolidation's 26/72 exposure count is a heuristic based on whole-video dates and keyword matches, not an observed count of judgments causally influenced. Under that rule, a Musk quotation can inherit an Anthropic-IPO date tag and a Lynch quotation a Fed date tag, while the Korean fourteen-million-shareholder proposition can remain untagged because its extracted wording omits “Korea.” All rows could nevertheless be affected by global instructions. The 30.8% versus 54.3% agreement contrast therefore describes tagged groups; it does not identify either the direction or the size of a contamination effect. The claims that contamination “deflates agreement,” “pushed readers apart,” or is immaterial are not retained. Nor does the comparison prove contamination caused adverse judgments. See the [tagging logic](../../consolidation/work/R5_contam.py), [tagged records](../../consolidation/work/R5_contamination_map.csv) and [R5 interpretation](../../consolidation/evidence/R5_review_of_review.md).

**C-04 / C-08 / F14.** The 39 exact and 27 collapsed disagreements are not 39 demonstrated factual errors. Twelve exact changes remain within one broad category. Nine of the 13 supported-to-adverse differences mainly concern severity applied to shortcomings recognized in the earlier notes. The weighted diagnostics likewise cannot be subtracted from 82.14% to manufacture a corrected truth probability. Source access and operationalization matter: a blind UNVERIFIABLE cannot refute a properly specified original calculation merely because the second reader could not reproduce its proxy or benchmark. The [sealed comparison](../../phase_c/second_reader_comparison.md) already states these limitations.

## Prediction provenance and time

**C-06 / F02.** Consolidation's source ledger misstates the locked categories. The preserved lock is 35 UNSCORABLE, 15 PENDING, eight CANNOT_VERIFY and two MISS. Five documented post-lock amendments yield 35 UNSCORABLE, 11 PENDING, seven CANNOT_VERIFY, four HIT and three MISS. No sealed judgment is edited here. Two HIT amendments match explicit pre-supplied HIT judgments; the June Warsh hold shares event chronology. That third match should not be described as another verbatim pre-supplied “score as HITS” instruction. The fact reader's notes are not a record of the separate prediction reader's mental process.

The [lock receipt](../../phase_c/prediction_lock_receipt.json) and [amendment table](../../phase_c/prediction_post_lock_amendments.csv) remain distinct evidence objects. Official dated releases can legitimately resolve event outcomes after a lock, with the changes disclosed. Exposure limits independence; it does not automatically invalidate the official release or prove copying. The June 2 amendment disagrees with the scaffold. Repeated Fed outcomes and a relayed market probability do not establish independent commentator skill.

**P-06 / F03 / F10.** A September-end absence-of-recession forecast remains open as of September 20. September 30 has not arrived, and official recession dating can lag the underlying event. A “by year-end” occurrence can succeed once the specified event happens; an absence claim through an unexpired endpoint cannot be closed merely because it has not happened yet.

WD-17's literal ban on post-video outcome evidence is rejected. A factual as-of check concerns what was observable or available at the stated time. A forecast requires later observations over its declared horizon. A later publication may document a historical fact, but its publication date, revision status and any distinction from contemporaneous knowledge must remain visible. Forecast outcomes must not be smuggled into the earlier factual evidence set.

## Corpus interpretation and practical value

**C-09 / F13.** All channel conclusions concern 58 captured public videos: 33 Bravos and 25 Jikh. The catalog also contains 50 uncaptured public entries and 35 Jikh paid entries. Their omissions can affect specificity, corrections, implementation and success in unknown directions. No conclusion about subscriber returns or the complete services follows.

The [full-video analysis](../../PHASE_A_transcript_analysis.md) records conditional endings, explicit revisions, varying horizons and specific mechanism changes. Those examples are enough to reject a universal characterization of uninterrupted unconditional imminent-crash forecasts. They do not estimate a separately coded prevalence rate for “usually” or “often.” Atomization errors are supported by concrete cases, but their corpus-wide magnitude is not established.

Useful factual leads and economic explanations survive. The work supports treating the channels as sources of questions, plausible mechanisms and scenarios to verify. It establishes neither a validated market-timing advantage nor the stronger negative claim that they have no value or no skill. These distinctions apply to both channels, with their different explanatory styles and incomplete observed output.

## Quantitative corrections and their scope

**A-14 / F05.** October 2007 is eligible in the common candidate window; the review cannot be said to structurally exclude every prominent original analog. The [common-window comparison](quantitative_completion.md) separates eligibility from the screen's dimensions and ranking choices.

**A-05 / F06.** Review 002 had already run expanding-rank energy and calm-credit analyses. The distinct unresolved intersection was the joint rich-and-calm pool, defined by high CAPE rank and low Baa-minus-Aaa rank. Its completed results are recorded in [rich_calm_summary.csv](rich_calm_summary.csv), with overlapping and thinned samples kept separate. Completion of an expanding-rank analysis does not make revised historical data real-time or eliminate small-sample uncertainty.

**R-06 / F04.** The 50.2978 CAPE scenario rewrites 38 historical earnings-proxy months after June 2023. It is not the effect of a prospective profit collapse. Review 002's related September sensitivity of 49.6591 also reproduces. The [CAPE scenarios](cape_scenarios.csv) and quantitative supplement distinguish measurement counterfactuals from forward paths. A genuine forward calculation needs assumptions about future earnings, GDP, inflation, prices and the national-profits-to-index-earnings mapping.

**A-10 / F12.** Annualized excess can decline even while cumulative excess remains positive. That arithmetic alone does not validate “a trade, not an allocation.” All energy figures need their own sample, benchmark and maturity labels; the 253 overlapping PPI starts must not be conflated with the 13 analog episodes.

**A-12 / F18.** The proposed fall from +10.70 pp to +2.41 pp changes both sample and benchmark. The [actual sensitivity table](../../consolidation/work/r1_supp_benchmark_sensitivity.csv) gives +9.4468 pp against MKT and +2.4102 pp against EW12 for the same 12 mature analog episodes. For the same 253 PPI starts it gives +10.7019 pp and +6.5936 pp. The benchmark dependence remains real; its magnitude must be reported without mixing samples.

**R-01 / F07.** The [Chicago Fed paper](https://www.chicagofed.org/publications/working-papers/2025/2025-09) resolves the 14% denominator: $849 billion of private credit on life insurers' 2024 balance sheets represented 14% of those balance sheets. It is not 14% of a private-credit market. Dividing by a separate $2 trillion market estimate gives 42.45% arithmetically but does not prove compatible coverage, definitions or dates. The original rebuttal is withdrawn; the speaker's market-share interpretation is not thereby independently verified. The revision and acquisition limits belong in the final source register.

## Engineering and governance boundaries

**V-01 / RV-01.** A matching seal verifies contents against the sealed state. An end-of-run hash does not independently prove preregistration chronology or what conclusions were already visible. It also cannot alone prove no edit-and-revert ever happened. This distinction does not nullify reproduced arithmetic.

**V-07 / F09.** Existing synthetic/headline calendar-helper checks would catch a generic regression of the shared helper to positional YoY. The final specification calls for additional independently pinned values and comparator/prose checks without claiming all core/calendar coverage is absent.

**D-07 / D-09 / F15.** The engineering control validates each statistic's dependencies. Endpoint YoY needs the current and year-earlier observations; the declared twelve-month acceleration additionally needs the two-year-earlier observation. Rolling/path/event tests consume their own complete windows. An unrelated interior gap is visible but need not invalidate a valid endpoint ratio.

**V-08 / F08.** The retained archive has six snapshot and two live acquisitions, rather than eight snapshots. The live acquisitions are within one open month and establish no completed prospective alarm outcome. A later scorer must respect economic-definition continuity across mere software-version changes and keep materially changed definitions in separate nonpooled cohorts.

**V-09 / F17.** An explicitly labeled failure page can intentionally replace a normal display. That is not inherently loss of the last-valid data. Preserve immutable validated artifacts and failed attempts; never label stale values as newly healthy. Dependency-local degradation is a proposed design requirement, not a repair already applied.

**R-10 / RV-07.** Annual methodology/source review and a 24-month utility review are feasible governance commitments. Neither five events nor ten years automatically establishes predictive accuracy. The extrapolated decades-to-centuries waits for twenty rare alarms are rate-based projections, not literal impossibility proofs.

## Validation performed for this reconciliation

The two CSVs were authored and round-trip checked as flat tables, with every cell compared to the intended record. Coverage checks require the exact 41 source correction IDs, all 74 original dispute IDs, unique final correction IDs and nonempty reasons and destinations. Source files were read, not rewritten. Financial computations cited here belong to their named evidence packages; this reconciliation does not claim to have independently rerun every historical analysis. Cross-agent review is not external human peer review.

The final report and proposed contract are authoritative for current interpretation. The existing software is not certified as conforming merely because its future requirements now have explicit dispositions.
