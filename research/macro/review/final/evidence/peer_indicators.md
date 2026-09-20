# Indicator and monitoring peer review

Reviewed 20 September 2026. Scope: the executive summary and sections 5, 7 and 10 of `FINAL_RESEARCH.md`, plus bounded numerical checks of its new quantitative supplement. This is a cross-agent review of the synthesis. The reviewer also authored the final indicator contract/specification, so the contract checks below are transparent self-validation, not a separate independent certification. No pipeline, UI, frozen study or source file was changed during this final review.

**Disposition: no blocking numerical or operational inconsistency remains in the assigned sections.** The report appropriately treats the contract as a proposed future specification. It does not claim monitoring implementation, financial execution authority or prospective predictive validation.

## Issues resolved during review

- **Preregistration chronology and endpoint selection:** the earlier draft's unqualified pre-calculation language was corrected. Section 7, line 189, now distinguishes the archived design and authors' reported sequence from independently timestamped chronology. An end-of-run seal proves matching file integrity, not independent chronology. The per-indicator primary-event assignment is absent from the archived design. Neither the new contract nor a later prospectively registered policy repairs that historical omission.
- **Off-cycle review authority:** specification section 5 now limits automatic economic-threshold review requests to the two diagnostic flags, while allowing a user request, manually verified major event or data-integrity incident to prompt review. These additional review reasons do not acquire predictive validation.
- **Retired energy-allocation rule:** the final contract retires the unsupported allocation policy and incorrect cause classification. Positive paired energy excess alone neither validates that allocation nor formally disproves every possible use of energy exposure. The synthesis's section 6 makes the corresponding limit explicit.

## Numerical checks and meaning

| Item | Evidence checked | Result |
|---|---|---|
| Dated snapshot, section 5 | Archived `review/pipeline/output/latest.json` and final quantitative validation | Claims rise 2.1357%, Sahm −0.07 pp, Baa–Treasury 1.44 pp, NFCI −0.56, curve +0.96 pp, headline/core CPI 3.3530%/2.4462%, Brent 130.80, equity/GDP 255.6507%, profit/GDP 12.0712% agree with rounding. The report discloses different observation dates and qualifies the CAPE proxy. This is an archived capture, not a refreshed market claim. |
| Claims and Sahm, section 7 and summary | Frozen event metrics and the final contract's exact empirical joins | Diagnostic hits 9/13 and 8/11; false-alarm fractions 4/13 and 3/11; strict future-onset hits 4/8 and 1/4; equity entry-loss hits 3/13 and 4/11. Post-2000 diagnostic results 3/5 and 2/4 match. Median Sahm diagnostic timing is four months after onset. |
| Baa widening | Same frozen metrics | Diagnostic 2/2 and equity 1/2 match. Strict future recession onset has zero eligible alarms, hence no defined leading success fraction. The report does not turn two episodes into a calibrated prediction. |
| Curve | Same frozen metrics | Separate 24-month future-onset result 6/8, post-2000 3/4, median lead 9.5 months and range 5–16 match. Its horizon is not silently pooled with the 12-month diagnostic results. |
| Uncertainty and multiplicity | Frozen metrics, archived design and consolidation calculations | 54 indicator/event/horizon combinations and 162 split rows; eleven zero-false-alarm cells, largest n=3. Reported descriptive Wilson intervals agree. Alarm false fractions are distinguished from classical false-positive rates, and dependency/selection caveats remain visible. |
| Contract inventory | `contract_validation.json` and final CSV | 21 unique rows, 42 fields; 13 active financial measures = 2 review + 5 watch + 6 context; 5 retired + 2 candidates + 1 engineering control. Eight historical alarm definitions were studied; these are not 21 validated signals. All 24 primary/alternative/holdout count joins pass, with financial thresholds and historical empirical fields preserved. |
| Prospective policy | Final specification and synthesis section 10 | Next-release confirmation is a new policy without inherited monthly accuracy. Source-local invalidity, visible global degraded status, preserved failure evidence, cross-version episode handling and contract-specific outcomes are requirements for a later build. No software change is implied. |

The equity outcome is a 20% decline from the signal month's monthly-average price, not a daily peak-to-trough drawdown or investment return. The report preserves this distinction. Weekly source updates and monthly historical sampling also remain explicitly different policies. Claims/Sahm phi approximately 0.451 supports grouping them as one family, not treating two flags as independent votes.

## Bounded quantitative cross-check

I independently aggregated the saved individual return rows; I did not independently reimplement the model-fitting and selection code. From `common_screen_returns.csv`, the real broad-market medians for the original expanding model are −1.728446%, 2.545806% and 26.453270% at one/three/five years; the review model gives 4.571168%, 26.497796% and 24.632033%. Each has eight origins. These match the rounded synthesis table and supplement.

From `rich_calm_returns.csv`, on the matched calendar at five years, the original full-history monthly pool has 24 origins, median −11.202413% and 16 losses. The expanding pool has 74, median +10.185316% and 28 losses. Chronological 60-month thinning gives n=2/6, medians +39.630984%/+31.457858%, and losses 0/2 and 2/6. These match the report. The tiny thinned samples are not presented as a favorable strategy.

The profit/CAPE replication evidence reports 12.07115999% current profit share, 6.09463014% pre-1990 mean share and −49.51081627% fixed-GDP change. The CAPE 42.0007→50.2978 scenario rewrites 38 already-dated proxy months, leaving 82 denominator months unchanged. The report correctly describes a retrospective denominator replacement rather than a forward effect of profits halving. The five-year mean-reversion/persistence RMSEs 4.1745/1.5787 match the rounded 4.17/1.58. These checks validate presentation and arithmetic against the supplied replication artifacts; they do not establish a future equilibrium.

Evidence: [contract checks](contract_validation.json), [exact joins](contract_empirical_joins.csv), [quantitative validation](quantitative_validation.json), [common return rows](common_screen_returns.csv), [joint-pool return rows](rich_calm_returns.csv), [CAPE scenarios](cape_scenarios.csv), [profit holdout replication](cape_profit_holdout_replication.csv).

## Boundaries retained

No future monitoring software was executed or certified. No calendar deadline or five/twenty-event count automatically promotes a diagnostic measure to a predictor. Annual source/methodology review and a 24-month utility review are feasible governance policies; the 89–393-year alarm accumulation estimates are uncertain historical-rate extrapolations, not impossibility proofs. Calendar dependency checks are engineering controls, and exact YoY endpoint validity must not be confused with uninterrupted path requirements. The predominantly US panel and an untested geopolitical event layer do not constitute a validated global risk score or a personalized allocation policy.
