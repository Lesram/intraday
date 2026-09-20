# Second-reader comparison, after the blind seal

The 72 independent judgments were sealed at **2026-09-20 05:11:52 UTC** before opening the original labels. All five sealed files still match their SHA-256 digests. Comparison does not revise any blind judgment. Sources newly seen after unblinding, and reasons to question either reader, are kept in this separate record.

There are **39/72 exact-label disagreements (54.2%)** and **27/72 collapsed-class disagreements (37.5%)**. These are inter-reader disagreements, **not 39 proven errors by the original analyst**. Twelve changes stay within the same broad class. Of the thirteen supported-to-adverse changes, nine largely reflect different severity judgments over shortcomings already recognized in the original notes. The largest recurring problem is deciding whether to score the supported factual fragment or the stronger conclusion bundled with it.

## What changed

Supported = TRUE/MOSTLY_TRUE/TRENDING. Adverse = FALSE/MISLEADING. Unresolved = UNVERIFIABLE/OPEN.

| Original → blind | Supported | Adverse | Unresolved | Original total |
|---|---:|---:|---:|---:|
| Supported | 28 | 13 | 5 | 46 |
| Adverse | 0 | 2 | 4 | 6 |
| Unresolved | 4 | 1 | 15 | 20 |
| Blind total | 32 | 16 | 24 | 72 |

Five rows become eligible for the resolved-label denominator and nine become unresolved: the denominator changes from 52 to 48. The sample's supported fraction among resolved rows changes from 46/52 = **88.46%** to 32/48 = **66.67%**. This is partly a change in what is being scored, not a fixed-denominator measurement of how much of the corpus is true.

| Input package | Covered population | Sample | Exact changes | Collapsed changes | Old resolved | Blind resolved |
|---|---:|---:|---:|---:|---:|---:|
| V1 AI | 192 | 8 | 6 | 5 | 7 | 7 |
| V2 equity valuation | 124 | 8 | 3 | 3 | 4 | 3 |
| V3 fiscal/Fed/liquidity | 220 | 8 | 3 | 1 | 8 | 8 |
| V4 oil/geopolitics/tariffs | 165 | 8 | 6 | 4 | 6 | 6 |
| V5 dollar/China/gold | 210 | 8 | 6 | 3 | 7 | 6 |
| V6 Japan/credit/crypto | 137 | 8 | 3 | 2 | 7 | 7 |
| V7 inflation/cycle/labor/housing | 150 | 8 | 7 | 4 | 7 | 8 |
| V8 other | 126 | 8 | 3 | 3 | 4 | 3 |
| V9 self-performance | 106 | 8 | 2 | 2 | 2 | 0 |
| Total | 1,430 | 72 | 39 | 27 | 52 | 48 |

## Package-population weighting

The sample takes eight covered claim rows per package, not eight percent of each package. Using the supplied population counts, the descriptive expansion weight is `N_package / 8`. “Eligible” in the sampling-design file means eligible for selection because an original verdict exists; it does **not** mean resolved or factually supported.

Across the 1,430 covered claim-row population, weighted exact disagreement is **56.69%**, and weighted collapsed disagreement is **37.64%**. Expanded counts are fractional estimates, not observed audits of additional rows: original labels estimate 971 supported, 127.125 adverse and 331.875 unresolved; blind labels estimate 684.5 supported, 348.375 adverse and 397.125 unresolved. The corresponding weighted supported/resolved ratios are **88.42% versus 66.27%**, with resolved-denominator estimates 1,098.125 versus 1,032.875. The estimated eligibility transitions are 99.5 newly resolved and 164.75 newly unresolved covered rows.

These point estimates answer the requested package-weighting question. They are not precise new population truth estimates. The deterministic hash ranking provides a reproducible pseudo-random selection, but there are only eight rows per stratum; repeated underlying facts and channel/topic dependence make the effective independent sample smaller than 72. No independent-binomial confidence interval is asserted. The original sample itself scores 88.4% under the old labels, versus the brief's population headline 82.1%, demonstrating why this sample cannot simply be substituted for the population ledger.

**Do not subtract the sample's 22-point drop from 82.1%, replace 82.1% with 66.3%, or call the disagreement percentage an original-error rate.** The older figure is a ratio of assigned labels over a selected denominator. It combines factual accuracy, source attribution, rounding policy and decisions about which pieces of composite claims count. Neither that ratio nor this second reader's ratio is a probability that a random statement, channel narrative or investment decision is true.

## Concrete verification defects, distinct from severity disagreements

The paired CSV contains a case-specific assessment for every exact disagreement. Particularly reviewable defects are:

1. **Pump gasoline, BR-20260320-12.** The original MOSTLY_TRUE note substitutes a crude-oil move and hypothetical pass-through for pump prices, and cites March 31 after the March 20 video. [AAA's March 19 release](https://southjersey.aaa.com/news/gas-prices-new-jersey-march-19) gives a US national increase of about 33% over the preceding month, materially below 50%. This is stronger than merely disagreeing about tone.
2. **Scope propagation, AJ-20260720-05.** A true nationwide count of roughly fourteen million Korean shareholders was copied to the different claim that those people drove two specific stocks mostly with borrowed money. The identical original fact key and explanation do not establish the causal proposition. This is an atom-to-fact mapping defect, even without estimating the true fraction of retail-driven demand.
3. **Wrong proposition, AJ-20260504-11.** The original TRUE evidence concerns Gromen's gold-import/trade-surplus framework and Hamiltonian attribution dated July 15. The sampled May 4 claim is about OPEC being unnecessary under a gold-backed reserve currency. Valid attribution of one idea does not verify another.
4. **Return versus benchmark, BR-20260629-41.** The sample contains only the 468% five-year return. Its original MISLEADING note attacks an eight-times-S&P comparison from another passage and itself says the strategy return is unverified. Split the private return and benchmark arithmetic into separate atoms.
5. **As-of and metric mismatch, BR-20260629-25.** Original TRUE support uses a September 6 source and 2027 capex/cloud-revenue figures for a June 29 claim about 2026 capex/operating cash flow. Earlier research supports the approximate capex pressure, but it does not repair the original evidence path automatically.
6. **Later observations in an as-of review.** The original April 20 oil-alternatives verdict invokes May/Q2 offsets and a June 30 price outcome. Its June 18 purchasing-power check extends to August, and the April 8 GDP check includes Q1/Q2 2026 values unavailable that day. Some directions remain right using prior information; the calendar defect still needs correction.
7. **Real regulation, untested mechanism.** SLR and NSFR dates/rules can be correct while “markets ran smooth because of relief” or “unallocated gold can no longer operate at scale” remains unsupported. Original TRUE labels check the regulatory fragment without proving the stronger mechanism. The [Fed's SLR intermediation analysis](https://www.federalreserve.gov/econres/notes/feds-notes/dealers-treasury-market-intermediation-and-the-supplementary-leverage-ratio-20230803.html) and [Basel NSFR standard](https://www.bis.org/committees/bcbs/basel-framework/standard/nsf?allChapters=true) make that distinction inspectable.

These findings warrant corrections to evidence, claim matching and interpretation. They do not establish that every related channel assertion is false.

## Where caution about the second reader is essential

The original utilities verdict supplies a Ken French proxy that the blind reader did not independently operationalize. The original cash/earnings-yield verdict uses a custom splice whereas the blind reader stopped at stale raw Shiller earnings. Those unresolved blind judgments cannot overturn valid calculations if the underlying series and vintage are sound. The original diesel-crack evidence supports a large rise; the dispute is a missing identical benchmark/base period, not denial of the shortage.

The S&P rule, model survival-instinct, Anthropic revenue/run-rate, Norway proposal, CDS lead time, World ID and martial-law rows often share the same underlying caveat in both reviews. Different supported/adverse labels expose a severity rule that needs to be stated explicitly. For GENIUS programmability, the claim says **can**; the original distinction between technically possible and legally mandated is defensible, while the blind reader's implication-based adverse judgment is deliberately retained as a contestable judgment. For the 1933/1934 gold repricing, chronology is agreed and only the policy-date tolerance differs.

New public evidence can legitimately resolve old UNVERIFIABLE labels without implying carelessness: dated stock-price tables, an actual July 2025 headline and Treasury's August 24 announcement are examples. Several unchanged labels also acquire stronger evidence: the Fed paper directly states the 37% Cayman estimate, NAIC corroborates the PE-insurer asset magnitude and Kikoff's own terms contain the +86-point selected cohort. A present-day sponsor page still does not establish every historical offer term or independent causal performance.

The sealed original judgments, comparison script, paired assessments, per-package exact and collapsed confusion counts, and machine-readable weighted summary are supplied together. That audit trail is the result; a single replacement accuracy percentage would discard the very distinctions the review found important.
