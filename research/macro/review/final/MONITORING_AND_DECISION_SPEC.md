# Final monitoring and decision specification

**Research specification 004, dated 20 September 2026. Implementation is deferred.** This document and [INDICATOR_CONTRACT.csv](INDICATOR_CONTRACT.csv) describe the proposed future monitor. They do not change the existing pipeline, dashboard, scheduling or trading platform. No live alerts, personalized allocations, position sizes or execution decisions are authorized by this specification.

The monitor's purpose is to organize evidence for a human review: what changed, how reliably it was measured, whether it adds information, and what remains unknown. A threshold is a reason to examine its stated question. It is not a probability of a crash, recession, safe market or investment return.

## 1. Authoritative inventory

The CSV has **21 rows and 42 fields**, comprising 13 active financial measures, five retired financial rules, two research candidates and one engineering control. It is not a set of 21 tested signals. Eight historical alarm definitions were studied; seven remain proposed review/watch thresholds, while the inflation-acceleration threshold remains historical metadata on a context row.

| Status | Count | Measures | Proposed use |
|---|---:|---|---|
| Review flag | 2 | Initial-claims deterioration; real-time Sahm gap | Confirm on the next distinct source release, then request a human labour-state review. |
| Watch | 5 | Baa widening; Baa level; NFCI; yield curve; headline inflation | Explain changes in the periodic review. No financial action follows from a crossing. |
| Context | 6 | Inflation acceleration; core inflation; Brent; equities/GDP; after-tax profits/GDP; historical CAPE context | Describe levels, changes and assumptions. No threshold alert or traffic-light market forecast. |
| Retired | 5 | Original top-ten concentration literal; energy-tilt rule; Baa 2.50pp rule; absolute claims 300k rule; short-history HY rule | Retain as research lineage. Do not compute an operational action from their stored thresholds. |
| Research candidate | 2 | Policy-rate impulse; continuing claims | No adopted threshold or event result. Research only if it answers an additional question. |
| Engineering control | 1 | CPI calendar dependencies and gap visibility | Mark invalid dependent calculations and visible data gaps; never count as economic evidence. |

The calendar row retains its legacy ID `cand_cpi_calendar_completeness` to preserve lineage, but its authoritative `tier` is `engineering_control`. Names and numeric fields alone must never determine behavior: consumers must enforce the tier. For context and retired rows, retained numeric thresholds are audit metadata only. The CAPE row is historical context: the archived proxy estimate is not an official current Shiller CAPE reading and must not be silently carried forward as one.

This inventory supersedes inconsistent counts in the prior consolidation's operating prose. It does not rewrite the prior files. The complete change dispositions and quantitative limitations belong to the final research report and resolution ledger.

## 2. What the historical evidence establishes

**No per-indicator primary-event assignment was preregistered.** The sealed design listed thresholds, six event definitions, a 12-month primary horizon, an additional 24-month curve horizon, declustering and sample splits. It did not say which event would be the primary displayed result for each indicator. The CSV's `primary_*` fields preserve the subsequently selected descriptive record; they are not claims of confirmatory validation. Their retained field names are a schema convenience, not a chronology claim. An end-of-run hash establishes integrity when matched, not independent proof of preregistration timing. See [the design](../phase_b_events/preregistration.json), [full metrics](../phase_b_events/indicator_event_metrics.csv) and [Phase B report](../PHASE_B_event_validation.md).

| Historical definition | Selected descriptive result | Required alternative reading |
|---|---|---|
| Claims ≥20% above trailing low | Recession already present or beginning within 12m: 9/13 | Strict future onset: 4/8; equity-entry-loss false fraction 10/13. |
| Sahm ≥0.50pp | Diagnostic recession: 8/11 | Strict future onset: 1/4; successful diagnoses arrived median four months after onset. |
| Baa three-month widening ≥1pp | Diagnostic recession: 2/2, false-fraction 95% interval 0–65.8% | Zero eligible leading episodes, so leading probability is undefined. Both observed successes were coincident or late. |
| Baa level ≥3pp | Diagnostic recession: 3/8 | Strict future onset: 1/6. |
| NFCI >0 | Diagnostic recession: 5/9 | Strict future onset: 3/7; equity-entry-loss record 0/9. |
| Curve <0 | Strict recession onset within 24m: 6/8 | At 12m: 5/9. Do not rank different horizons as though they answer one question. |
| Headline CPI ≥4% | Equity-entry loss ≥20% within 12m: 2/7 | Elevated inflation is primarily an observed state, not a forecast of its own onset. |
| CPI acceleration ≥2pp with CPI ≥4% | Same equity target: 2/7 | Both successful episodes overlap headline inflation; the value remains useful context without a separate action flag. |

The source grid contains 54 indicator/event/horizon combinations and 162 rows across splits. Eleven rows have zero observed false alarms, the largest on three alarms. This makes small perfect cells weak evidence; it does not prove any particular cell arose by chance. Historical false-alarm fractions, classical monthly FPRs, eligible dates, holdout counts and uncertainty remain attached to their exact outcome, horizon and series. [Join checks](evidence/contract_empirical_joins.csv) verify all 24 primary, alternative and holdout count mappings in the final contract.

The records are monthly, mostly revised-history simulations with approximate release lags. Native daily/weekly values, exact acquired release timing and the proposed next-release confirmation policy **do not inherit those hit rates**. Neither a source-local latest value nor confirmation on a later release retroactively makes the historical study vintage-correct.

## 3. Formula and calendar contract

Financial thresholds and historical outcomes remain unchanged. The CSV records exact formulas, units and series. Claims use a four-week mean and all 52 weekly means in the trailing-minimum window; missing weeks must not turn this into a different-length average. Baa widening uses completed calendar month-end observations separated by three calendar months. Curve uses monthly GS10 minus discount-basis TB3MS, not a substitute daily curve. CPI joins exact calendar dates, preserving missing values.

Data validity is determined by each calculation's actual dependencies:

- Headline/core YoY at month `t` require finite, valid CPI at `t` and `t−12`, with a positive denominator. Missing unrelated interior months should produce a visible gap warning but do not invalidate that endpoint ratio.
- The declared acceleration `YoY(t) − YoY(t−12)` requires CPI at `t`, `t−12` and `t−24`. It does not require every interior month merely because it spans two years.
- Rolling means/minima require their complete declared windows. A threshold *crossing* requires consecutive eligible observed states. Recession/inflation onset tests and price-path event windows require every observation consumed by those tests; a missing event month cannot be assumed to contain no event.
- Never interpolate an absent outcome, carry a neighboring month across a missing year-earlier endpoint, or apply a twelve-row shift after dropping missing calendar months. Report denominator failures and nonfinite calculations as unavailable.

Thus missing October 2025 does not invalidate August 2026 endpoint YoY when August 2025 exists. It may invalidate a path-based historical window spanning October, and a missing August 2025 value would invalidate August 2026 YoY and acceleration. The [contract validation receipt](evidence/contract_validation.json) includes deterministic examples. These are arithmetic checks, not a predictive validation requirement for the engineering control.

The existing shared calendar helper has synthetic/headline gap tests. A regression of that common helper to positional shifting would be caught; the consolidation's contrary “all tests pass” claim is not retained. Future implementation should additionally pin independent reference values for every derived row and verify dependency-local invalidity, source lineage and period alignment. Passing old tests is not certification of a new implementation.

## 4. Source lineage, time and revisions

Every acquired source and derived result must retain enough information to reconstruct what was knowable at the time:

| Field group | Required content |
|---|---|
| Source identity | Publisher, exact series ID, units, seasonal adjustment, frequency, URL, method/definition version and dependency IDs. |
| Observation | Period start and end, publisher's observation date, raw value, missing-value reason. A quarter dated April 1 means Q2, not an April observation. |
| Publication | Actual release timestamp/date and precision when supplied, release identifier, revision/vintage identifier. Unknown publication time stays null. |
| Acquisition | UTC receipt time, endpoint, response status, raw-content hash, immutable receipt, parser version and payload schema. Acquisition time is not publication time. |
| Calculation | Formula/version, exact dependent observations and hashes, derived value, validation state and any known warning. |
| Expected update | Publisher calendar when available; otherwise an explicit conservative assumption, holiday handling and next expected release deadline. Distinguish an overdue observation from a failed download. |

Use actual release availability in a future live archive. Do not add an arbitrary one-month delay to a source already acquired merely to imitate the coarse historical approximation. Instead label the prospective acquisition-based cohort separately and assess it on its own dates. Store revisions as new versions; never overwrite evidence used by an earlier review. The [published real-time Sahm series](https://fred.stlouisfed.org/series/SAHMREALTIME) has a contemporary-unemployment basis, while that fact does not confer real-time status on [claims](https://fred.stlouisfed.org/series/ICSA), [NFCI](https://fred.stlouisfed.org/series/NFCI), [CPI](https://fred.stlouisfed.org/series/CPIAUCSL), national accounts or the whole retrospective test. Series references in each CSV row lead to the underlying publisher metadata.

Primary-source disagreements must be visible: retain both records, select a declared controlling series for that computation, and explain the choice. Never silently replace an exact series with a convenient proxy. Spot oil is not a physical inventory series; national corporate profits are not index EPS; aggregate industry concentration is not a top-ten-company weight.

## 5. Proposed review workflow and data failure policy

An implementation may acquire data at its native publication cadence, with a monthly research review. Automatic economic-threshold requests for an off-cycle diagnostic review are limited to the two review flags, after the **next distinct scheduled release with a new underlying observation period** confirms the condition. A user request, a manually verified major event, or a data-integrity incident may also prompt review; these are distinct reasons to examine evidence, not additional validated predictive signals. Re-downloading the same release, or receiving a revision to the same observation alone, does not count as threshold confirmation. Record first crossing and confirmation separately. A first high observation establishes an ongoing elevated state; it does not prove a new crossing. Missing/unavailable observations break the crossing/confirmation chain and require a new valid baseline.

Next-release confirmation is a newly specified operational policy. Archive its requests, confirmations, withdrawals and human review outcomes separately from the raw monthly research states. Do not describe a confirmed request using the unconfirmed monthly study's accuracy. Record what the review resolved, which evidence changed, and any redundant prompt; do not infer usefulness from a market rally after the review.

Failure should be **local to dependencies with a clear global banner**. If Brent is unavailable, Brent and analyses requiring it become unavailable; valid labour rows remain visible with their own timestamps. The global page must say which sources are degraded and which conclusions are withheld. A degraded report must not say all required data passed or imply market safety. A dependency that is invalid cannot be rendered as below threshold.

Preserve an immutable last validated data artifact and every failed attempt. A future interface may intentionally display a clearly labeled failure/degraded page instead of the last normal page so an operator notices the failure. The prior failure-HTML behavior was documented as intentional; replacing the visible page with a failure state is not inherently a defect. Show the last validated reading's date alongside it, never mix old values into a newly dated healthy state, and distinguish threshold crossing from data unavailability in text and visual treatment.

The retained historical archive contains six snapshot and two live acquisitions among its eight reading files. Those live acquisitions occur within one open month; they do not establish consecutive completed monthly states or a prospective event record. “No eligible prospective alarms yet” is correct; “all archived runs are snapshots” is not.

## 6. Prospective evaluation, versioning and uncertainty

Future financial-event evaluation must be registered **before accumulating the evaluation cohort**. For the existing eight historical definitions, preserve and publish both named event records in the CSV; choose any confirmatory primary target explicitly before a new cohort, never after seeing its successes. Context classification does not forbid an explicitly labeled research archive, but it does forbid treating that archive as an operational alert. Untested context measures receive no event hit rate. Candidate rows need their own fixed definitions and cannot inherit another row's rate.

The existing scorer handles Tier 1 and a hardcoded 12-month diagnostic recession target. It is not sufficient for the final inventory. An eventual implementation must score specified research cohorts independently of display tier and use each declared outcome/horizon. Removing a tier filter alone would incorrectly assign a 12-month recession target to curve or equity-loss studies.

Minimum scoring policy:

1. Use only acquired live evidence available by the analysis cutoff. Keep historical snapshots separate. Final acquired states in completed UTC months may define a declared monthly research cohort; retain actual acquisition dates and do not rewrite a closed decision with later revisions.
2. Require consecutive valid monthly observations for a crossing. Missing/failed months and an initially high state cannot arm an onset. Apply the declared outcome-eligibility rule before declustering. A diagnostic target can include an event already underway; a leading-onset target must exclude it and report different denominators.
3. Keep accepted alarms at least their declared horizon apart **across software-version changes that do not alter the economic definition**. Key continuity by stable economic definition, not a presentation/version string. If the threshold, formula, source convention or event definition materially changes, open a distinct research cohort and never pool overlapping cross-version outcomes as independent successes. Retain the predecessor's pending/failed observations; a reset must not erase them.
4. Require complete dated outcome coverage through the entire horizon before assigning hit or false alarm in these monthly research cohorts. No outcome file or an unobserved outcome month means pending/unverifiable, not a false alarm. Keep diagnostic presence, strictly future onset, equity entry loss and peak drawdown separate.
5. Publish alarm dates, n, hits, false alarms, alarm false fraction, classical monthly FPR with its own denominator, comparable baselines, lead ranges and uncertainty. Monthly overlapping observations do not supply independent trials. Any formal comparison needs an appropriate dependence-aware design; a monthly unconditional rate alone is not a matched independent alarm null.
6. Retain a dated outcome-source receipt and distinguish retrospective USREC classification from the date a recession was publicly announced. Revisions produce a new scored result with a change log; they do not overwrite the original result.

The eight historical records remain descriptive. There is no equal-weight composite risk score, no calibrated joint probability, and no significance claim from the small perfect cells.

## 7. Families, global events and interpretation

Group claims and Sahm as labour; Baa level/widening and NFCI as financial conditions; headline/core/acceleration as inflation. The curve includes a policy-sensitive short rate. Equities/GDP and profits/GDP share GDP. Display measured correlations with their sample and n, but do not count correlated rows as independent votes. The archived claims/Sahm phi near 0.451 is descriptive; a new conjunction would need its own specified evaluation.

A global/geopolitical event layer can record dated source-backed events, affected jurisdictions, mechanisms proposed, physical quantities observed, uncertainty and alternative explanations. It is **untested narrative context**: this US-centered macro study supplies no measured threshold, crisis probability or trading rule for wars, sanctions, payment systems, shipping chokepoints or political intent. Oil/yields moving together do not verify a geopolitical causal chain. A physical-shipment or inventory claim requires its corresponding primary physical data and dates.

Descriptions of scenarios may inform general research questions, not personalized allocations. A future user request for portfolio advice would require separate objectives and evidence; nothing here converts these indicators into weights or market-entry rules.

## 8. Review, retirement and promotion

Review methodology, source continuity, revisions, coverage and the stated question **annually**. Review operational usefulness after **24 months** using documented distinct decisions/questions resolved, redundant prompts, data burden and reviewer experience. State plainly when a row has not demonstrated additional value and demote or retire it with a recorded reason. Suspend affected computations immediately on an unbridged definition break.

Historical-frequency extrapolation suggested that accumulating twenty new alarms could take a median around 148 years across the eight definitions, with a range around 89–393. That is an uncertain rate extrapolation, not proof that reaching twenty is impossible. It makes twenty alarms an unsuitable near-term governance promise. Five alarms or ten elapsed years would also not establish useful predictive precision automatically.

There is **no automatic promotion to prediction based on a calendar date or episode count**. A proposed predictive use must define the relevant event/horizon, acceptable uncertainty for that use, adequate mature independent evidence, baseline comparison and incremental information before evaluation. If that precision is unattainable with rare macro events, retain the diagnostic/context role and say so. Do not optimize the threshold on disappointing outcomes.

Research candidates may become dormant after 24 months without a feasible study; their proposal alone gives no operational standing. The calendar engineering control does not need macro-event validation and is not retired simply because no recent error occurred. Its correctness requirements persist as long as formulas depend on calendar identity.

## 9. Handoff boundaries and acceptance

This final package specifies future work; it has not implemented it. Before any monitoring build is described as conforming, a separate implementation should demonstrate the exact inventory and tier gates; source receipts and version history; independent reference calculations for every output; correct missing-dependency behavior; no recycled snapshots or open-month scoring; version-safe episode accounting; source-local degraded states with clear global visibility; explicit confirmation-policy labeling; accessible adverse as well as favorable evidence; and no trading-platform integration.

The research validation here checks contract schema/counts, unchanged historical thresholds and empirical fields, exact count joins and calendar-dependency examples. [Validation receipt](evidence/contract_validation.json) and [task plan](evidence/contract_task_plan.json) bound those claims. They do not certify software that has not been built.
