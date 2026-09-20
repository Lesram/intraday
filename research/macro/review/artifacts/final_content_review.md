# Final content QA — independent quantitative reader

Scope: full reading of PHASE_C_adjudication.md, PHASE_D_indicator_spec.md, PHASE_E_dashboard_spec.md and README.md; full machine inspection of all 12 indicators.csv rows; comparisons against sealed Phase B returns/event metrics, Phase C quantitative outputs, original analog disclosure, and the generated report. Read-only source/A–B integrity check completed. Root files were not edited by this reviewer. Root advised that the two Phase C result placeholders are deliberately awaiting the other readers.

## Actionable findings

| Priority | Finding | Exact repair / status |
|---|---|---|
| P2 | Phase C originally called 0.242 a lower-tail fraction | It is the **two-sided** descriptive tail fraction. Lower-tail rank is 0.1210898, or 12.10898th percentile, among 4,955 successful matched-size sets. **Root corrected this during review; verified on reread at line 54.** |
| P2 | Phase C table says the November 2021 endpoint was "silently clipped" | Original ANALOGS.md:156 explicitly defines `*` as truncated and marks all November 2021 five-year rows. The real defect is that a flagged incomplete observation enters the headline five-year aggregate because `cross_summary()` does not exclude it. Say that; use 56 equity-return months and 57 gold/bond months rather than a universal 56. |
| P2 | Generated recurring report still requests action on "two independent fast-state crossings" | `pipeline/output/report.md` and `pipeline/monitor.py:281` conflict with the careful Phase D/E treatment of dependence. Replace with deterioration across distinct labour and credit families, without asserting statistical independence. The report should follow the same language as the specification. |
| P3 | Phase C numbered headings use `##1–2`, `##3`, etc. | Add a space after the Markdown heading marker so they render as headings. Also perform a final prose spacing pass: many root-document numbers and ordinary words run together, e.g. `are4.57%`, `all1,430`, `byatleast60`. Preserve literal identifiers and CSV fields. |
| Delivery check | Deliberate second-reader and prediction placeholders remain while those tasks finish | Replace `SECOND_READER_RESULTS` and `PREDICTION_RESULTS`, reconcile final sample sizes with their artifacts, and only then retain README's statement that all five phases are complete. These are known integration tasks, not additional methodological objections. |

## Numerical checks that passed

- Blind eight-episode real market medians: 4.571%, 26.498%, 24.632% at 1/3/5 years. Five-year range −24.12% to +129.84%. Omit-valuation median 48.09% versus unconditional 42.88%.
- Original return sample: 12 algorithmic starts plus one manual anchor; maximum 7 pairwise nonoverlapping five-year intervals, 6 mature. Excluding the immature row gives market median 27.04% (n=12), energy 35.968% (n=12), gold 25.173% (n=9). The term "independent" remains qualified; interval separation is not proof of economic independence.
- CAPE≥30: original n=68, median −12.528%, 72.059% negative; extended hybrid n=89, median −5.342%, 55.056% negative; consistent French market n=89, median +3.705%, 49.438% negative. Main text correctly labels the French universe substitution.
- Calm-credit sensitivity: the stated first-crossing variant has n=4, with February 2000 real three-year return −44.133% and nominal monthly total-return path drawdown −44.995%. The two quantities are different outcomes; current language does not label the drawdown real.
- Pre-2000 trained profit-share model five-year holdout RMSE 4.1745 pp versus persistence 1.5787 pp. Main text correctly rejects a universal old equilibrium without claiming permanence.
- French industry capitalization proxy: BusEq 34.9355% in March 2000, 43.1896% in July 2026, and 45.2656% in June 2026. Main text preserves the index/industry universe caveat.
- Energy paired excess: original five-year n=253, median +10.702 pp, mean +8.716 pp, wins 58.498%; expanding n=233, median +13.743 pp, wins 61.373%; chronological nonoverlap n=11 with 8 wins and median +26.077 pp.
- Calendar CPI: January 2.3912%, February 2.4340%, April 3.7792%, May 4.1666%, August 3.3530%; core August 2.4462%. Main text correctly narrows which V7 criticisms are invalidated.
- Phase D current-or-next-12-month recession diagnostics: claims 9/13, Sahm 8/11, Baa acceleration 2/2; holdouts 3/5, 2/4, 2/2. False-alarm Wilson intervals match the CSV. The n=2 warning is prominent.
- Strict future recession outcomes: claims 4/8, Sahm 1/4, credit acceleration n=0. Equity entry-loss false alarms: 10/13, 7/11, 1/2. All match the event study.
- Curve 24-month recession onset: 6/8 hits, holdout 3/4, lead median 9.5 months and range 5–16; false-alarm interval 7.1478–59.0730%. Main text retains the GS10−TB3MS definition.

## All twelve requested attack areas

| Attack | Main-report coverage | Assessment |
|---|---|---|
| 1 Full-sample ranks | §1–2 and quantitative appendix | Complete; fixed-feature partial replication and changed independent dimensions are distinguished. |
| 2 Small/effective sample | §1–2 | Complete after the tail-label correction; maturity and manual anchor are prominent. |
| 3 CAPE splice | §3 | Complete; dates reconciled; unavailable forward/buyback histories stated; tested sensitivities linked. |
| 4 Calm-credit onset robustness | §4 | Complete; adverse sensitivity retained beside original 7/7. |
| 5 Profit-share reversion | §5 | Complete; structural-era and chronological pseudo-holdout evidence. |
| 6 Concentration | §6 | Complete within supplied data; weights constructed from firm count×size, not returns. |
| 7 Unverifiable missingness | §7–8 | Sampling design, nonrandom composition and six-category counts included. |
| 8 Blind second reader | §7–8 | Protocol/72 sample stated; final result insertion pending deliberately. |
| 9 HIT/MISS/PARTIAL rescoring | §9/11 | Rule differences and dual sample designs stated; final result insertion pending deliberately. |
| 10 Channel composition | §10/12 | Counts, several adjusted gaps, retained n and clustered uncertainty included. |
| 11 Null forecasters | §9/11 | Matched outcome/horizon requirement and operationalization sensitivity stated; final estimates pending. |
| 12 Missing paid material | §10/12 | All 35 belong to Jikh; additional 50 public gaps and unidentified bias disclosed. |

The required comparison of atomization versus narrative reading and the "what the first report got right" section are present. None of the unresolved data gaps is covertly filled with an estimate treated as fact.

## Specification and build-contract consistency

The CSV has exactly 12 unique indicator rows: 3 Tier 1, 5 Tier 2 and 4 Tier 3. Every required specification field is nonempty. Tier 3 explicitly has no trigger or false-positive denominator. Eight scored rows map to exact study indicator/event/horizon keys. All source IDs together form the 12-series set stated by Phase E: ICSA, SAHMREALTIME, BAA10Y, NFCI, GS10, TB3MS, CPIAUCSL, CPILFESL, DCOILBRENTEU, NCBEILQ027S, GDP and CPATAX.

Operational thresholds agree between prose and CSV. Inflation acceleration correctly requires both at least 2 pp acceleration and at least 4% headline inflation. The source formula parity receipt reports numerical equality to the sealed historical study after its declared availability shifts. The native-frequency/monthly-validation distinction is explicit. The completed-month credit definition is consistent with the formula contract.

Tier 1 is clearly a diagnostic-review action, not an allocation action. This fits the work order's explicit prohibition on recurring-report trade recommendations. Calm credit is not described as safety; current diagnostic success is not called forecast success. Slow valuation remains context. The retirement rules are policy judgments and are disclosed as such. No background scheduler or automatic messaging is falsely claimed.

This content QA does not substitute for the separate pipeline unit tests or browser check. It confirms their documentation is consistent except for the generated independence wording noted above. Final test counts should be regenerated by root after all repairs.

## Integrity result

Read-only SHA-256 comparison against `artifacts/blind_seal.json`: **75/75 files match; zero missing or changed**. Read-only comparison against `artifacts/source_manifest.json`, resolving paths from repository root: **344/344 files match; zero missing or changed**. No sealed generator was rerun and no source or root deliverable was edited by this QA task.
