# Composition, denominators and the unverifiable bucket

Source: supplied claim ledger and all eight verdict CSVs (nine input packages), captured2026-09-19. Reproduction: `composition_audit.py`; manual taxonomy: `classify_unverifiable.py`. All calculations postdate the blind A/B seal.

## What82.1% actually counts

The ledger contains2,553 rows. Exactly1,430 receive factual verdicts:724 DATA_POINT,250 SOURCE_CITATION,223 POLICY_FACT,127 RECOMMENDATION and106 SELF_PERFORMANCE. All492 CAUSAL,203 HISTORICAL_ANALOGY and428 PREDICTION rows are absent from this factual verdict denominator. Predictions have a separate selected register; this is not verification of82.1% of everything the channels say.

The1,430 verdicts comprise476 TRUE,389 MOSTLY_TRUE,371 UNVERIFIABLE,125 MISLEADING,64 FALSE,4 TRENDING and1 OPEN. The headline is869/1,058=82.14%, which includes the4 TRENDING labels as successes and excludes371 UNVERIFIABLE plus1 OPEN. TRUE+MOSTLY_TRUE alone gives865/1,058=81.76%; strict TRUE gives476/1,058=44.99%. These are label summaries under different rubrics, not independent truth probabilities. This corrects our initial replication omission of TRENDING; no source labels were changed.

The same convention reproduces Bravos360/465=77.42% and Jikh509/593=85.83%. There are666 versus764 total factual-verdict rows and201 versus170 UNVERIFIABLE. Unsupported claims cannot all be assigned false, or all assigned true. On the intentionally broader all-verdict denominator, pessimistic/optimistic unresolved-label bounds are54.05–84.23% and66.62–89.01%; these are identification bounds, not confidence intervals. The overlap is substantial.

## Does composition explain the channel gap?

Direct standardization reweights each channel to the pooled claim mix in common-support cells. It controls observed categories without claiming random assignment. Full cell counts and weights are in `composition_cells.csv`.

| Standardization | Rows retained /1,058 | Cells | Bravos | Jikh | Jikh minus Bravos |
|---|---:|---:|---:|---:|---:|
| Raw |1,058|—|77.42%|85.83%|8.42pp|
| Claim type |1,058|5|78.89%|85.13%|6.24pp|
| Topic |1,055|17|75.56%|86.50%|10.93pp|
| Claim type ×topic |930|36|78.53%|85.25%|6.73pp|
| Type ×topic ×capture scope |871|57|78.87%|84.11%|5.24pp|
| Type ×topic, at least5/channel/cell |760|20|75.96%|83.84%|7.88pp|
| One row/channel/fact_key, then type ×topic |775 of891 unique facts|36|78.48%|85.50%|7.02pp|

The raw gap shrinks under type/capture controls but does not disappear. Topic-only adjustment increases it. Therefore “entirely a composition artifact” is unsupported. Neither does a stable point estimate prove superior accuracy. Videos cluster claims and the rubric itself has judgment errors. A1,500-draw within-channel video-cluster bootstrap for the minimum5 specification retains862 draws with all needed cells; its percentile interval is−0.29 to14.13pp. Discarding empty-cell draws can distort coverage, so report this as a stability diagnostic, not a calibrated significance test. A larger independently adjudicated, prospectively sampled corpus is needed.

##371 UNVERIFIABLE is not a random missing-data bucket

Unverifiable rates are67/724 datapoints(9.25%),23/223 policy facts(10.31%),85/250 citations(34%),108/127 recommendations(85.04%) and88/106 self-performance claims(83.02%). Advice and proprietary performance dominate missingness. This is a measurement-design effect as well as a disclosure problem. The brief's description “371 claims nobody examined” is inaccurate: the original facts files often describe attempted checks.

A uniform deterministic hash-rank sample of48 of371 rows was chosen before manual taxonomy. Unlike the72-row verdict experiment, this taxonomy openly uses the prior reason as context. Each compound row receives one primary category; category counts are not new true/false labels.

| Main obstacle | n/48 | Interpretation |
|---|---:|---|
| Public evidence missing |13|A named filing, time series, clip or survey could settle it.|
| Private/proprietary performance |9|Need voluntary records, a dated complete journal or disclosed model.|
| Commercial service or offer |8|Archived price/terms or authorized membership access could test parts.|
| Normative/rhetorical |7|Advice or sales evaluation has no simple factual truth score.|
| Underspecified measurement |6|Fix universe, window, denominator or outcome before testing.|
| Vague/untimed inference |5|Unbounded conditional or private-intent claim lacks resolution.|

Thus13/48 are plainly public-evidence gaps and another8 are commercial claims testable in principle. Only a subset is unfalsifiable as constructed. No fair review should recode the entire bucket as false or structurally unknowable.

Selected repairs from `unverifiable_review.csv`: a four-videos-per-month service claim was given a note about untestable market timing; a dated index-inclusion prediction was excluded under RECOMMENDATION; a wide economic range was called unfalsifiable simply because it was wide; and “cash/equities low” versus “cash/GDP high” was called a contradiction despite different denominators. These are ontology and review errors, not evidence that the underlying claims are true.

## Missing videos and sensitivity

The143-row catalogue contains60 Bravos public,48 Jikh public and35 Jikh members-only rows. The captured corpus has33 Bravos and25 Jikh public transcripts. Therefore27 Bravos public and23 Jikh public entries are also absent; the paywall is not the only selection mechanism. All35 paid omissions belong to Jikh, so this particular paywall limitation must not be assigned symmetrically to Bravos.

Missing paid content could contain more precise predated calls, successful calls or worse calls. Public pitches explicitly direct viewers to paid entries/targets, making missingness plausibly related to forecast specificity. Direction and size of bias are unidentified without access. If H successes are observed among N mature calls and M eligible missing calls exist, the sharp binary range is H/(N+M) to(H+M)/(N+M). M is unknown:35 videos is not35 predictions. Do not manufacture an adjusted hit rate. Every channel comparison here applies to captured public material only; nothing proves the complete public or paid service record.
