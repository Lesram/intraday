# Independent pipeline correctness review

Review date: 2026-09-20 UTC. Scope: the monitor, refresh/export bridge, prospective scorer, indicator-contract generator, existing tests and dashboard consumption of their fields. No Phase C sources were opened and no sealed Phase A/B file was modified. Root retained ownership of dashboard layout and prose.

```json
{"task_id":"brief002_pipeline_review","scope":"Check source/decision timing, formula parity, freshness, compound conditions, alarm baselines and outcome maturity","owned_changes":["review/pipeline/monitor.py","review/pipeline/score_archive.py","review/pipeline/build_spec.py","review/pipeline/test_monitor.py","review/pipeline/test_archive.py","review/indicators.csv"],"runtime_behavior_changed":false,"monitor_version":"002.2","trading_platform_changes":false}
```

The macro monitor's behavior changed; `runtime_behavior_changed:false` above refers specifically to the repository's paper/live trading runtime, which this monitor neither imports nor modifies.

## Correctness findings and fixes

| Finding | Before | Corrected behavior | Evidence |
|---|---|---|---|
| Periodic data became stale before the next release could be due | August CPI expired September 25 under a flat 25-day age limit; quarterly releases could expire shortly after publication | Deadline is next observation period end plus explicit conservative release grace. August CPI remains valid through October 25; thereafter failure. Age and effective age limit are still displayed | Monthly/quarterly deadline tests |
| A transient weekly flag inherited monthly validation | Prospective scorer processed every archived run, including intramonth reversals | One final acquired reading per closed UTC month; intramonth crossings that reverse before that final reading do not enter monthly scorecard | Reversal/open-month tests; sampling caveat in every studied specification row |
| Unknown states could manufacture an onset | Unavailable/failed snapshots were skipped, preserving a stale false baseline across gaps | Missing, failed or unavailable months reset the baseline; consecutive observed months are required; initial high is never a proven crossing | Three gap/reset tests and initial-high test |
| Alarm timing could use an observation/as-of date instead of information availability | Origin used `as_of`; no acquisition timestamp required | Origin uses recorded acquisition/completion time; absent timestamps are excluded from prospective history; publication time stays null | Acquisition-month and missing-acquisition tests |
| A still-open horizon month could be called mature | Presence of all monthly labels alone implied maturity | Every outcome month must exist **and** the horizon month must have ended; otherwise pending | Future/open-horizon and missing-label tests |
| Malformed/incorrect source content could pass as old good data | Wrong-series headers and an invalid numeric token could be silently assigned/dropped | Known series headers must match; only recognized missing markers may become missing; nonfinite derived values become unavailable | Wrong-series, malformed-latest-value and nonfinite-value tests |
| Some source/derivation failures bypassed the failed dashboard attempt | A corrupt bundle or invalid weekly calendar could abort before failure artifact | Source-load/derivation errors are recorded in a failed attempt, preserving the last validated reading | Loader-exception and failed-refresh tests |
| Independence and purpose were too generic | CSV pointed to a separate correlation file and repeated a tier-wide purpose | Each studied indicator includes its two largest absolute measured alarm-phi correlations with n and dates; every row has its own question. Unvalidated context correlations explicitly remain unmeasured | Regenerated 12-row `indicators.csv` |

The compound inflation condition was already correctly implemented as acceleration >=2 percentage points **and** headline YoY >=4%. Tests now additionally reject a nonfinite condition. The numerical distance continues to describe the acceleration component; the headline gate remains separate and disclosed.

## Release-deadline assumptions

These are operational grace assumptions, not historical publication calendars. They deliberately allow normal delay and some late publication; passing them does not mean every publisher's newest release has been positively confirmed.

| Source | Cadence | Rule |
|---|---|---|
| ICSA | Weekly | Last week-ending observation +14 calendar days |
| NFCI | Weekly | Last observation +14 calendar days |
| BAA10Y | Daily business days | Last observation +7 calendar days |
| DCOILBRENTEU | Daily business days | Last observation +10 calendar days |
| SAHMREALTIME, GS10, TB3MS | Monthly | End of next observation month +20 calendar days |
| CPIAUCSL, CPILFESL | Monthly | End of next observation month +25 calendar days |
| NCBEILQ027S, GDP, CPATAX | Quarterly | End of next observation quarter +100 calendar days |

Every receipt retains `observation_date`, `period_end`, `age_days`, `max_age_days`; new fields are `next_observation_due_by`, `freshness_basis`, `acquired_at`, acquisition precision, and `published_at:null`. Supplied snapshot acquisition is known only to the day (2026-09-19); fresh API receipts have UTC timestamps. A publisher calendar can replace grace assumptions later, with explicit versioning. The current quarterly allowance is conservative and is not a claim that publication normally takes 100 days.

## Formula and timestamp parity

`pipeline_formula_parity.json` records eight matched history comparisons after applying the sealed study's declared coarse one-month availability shifts where applicable. Maximum absolute error is below 1e-10 for every formula: claims 704 comparable months, Sahm799, Baa level488, Baa change485, NFCI667, curve871, CPI858, acceleration846. This comparison is also a persistent regression test in `test_monitor.py`.

Claims retain the full 55-week warm-up and missing-week protection. Baa change uses last observations in completed calendar months and a three-calendar-month difference. CPI growth and acceleration use exact calendar alignment; the missing October2025 observation is not bridged. Native observations after the requested cutoff are excluded. Quarter ratios retain exact observation alignment and cannot fill a missing newer component with an older quarter.

The **operational display** shows latest available values. The **historical evidence** uses monthly states and coarse availability lags. The **prospective scorecard** uses the last actually acquired state in each closed month. Those clocks are explicit and are not represented as identical real-time experiments. Source-based publication timestamps remain unknown. The output does not backdate acquisition to the economic observation period.

## Verification

- **35 tests passed; zero failures/errors.** Full output: `pipeline_review_tests.txt`; machine summary: `pipeline_review_tests.json`.
- Dated snapshot: 12 indicator rows, zero errors, version002.2 in `pipeline_review_snapshot/attempt.json`.
- Fresh official-source run: all12 source series acquired successfully;12 indicator rows, zero errors in `pipeline_review_live/attempt.json`. No fallback to supplied captures.
- Eight-formula historical parity passed across485–871 months per comparison (claims704); exact counts above.
- Prospective scorer ran successfully and produced **zero eligible alarm episodes**. Existing live captures are in an open month and cannot establish two closed-month states. This is expected, not missing test coverage. Evidence: `pipeline_review_scorecard.csv` and its metadata JSON.
- Dashboard JSX and export bridge were inspected for these field changes. Existing `age_days/max_age_days` fields remain compatible. Root owns rebuilding the final offline dashboard so its embedded data/specification reflect version002.2.

Reproduction: run the bundled Python with `-m unittest discover -s review/pipeline -p 'test_*.py' -v`; regenerate the contract with `review/pipeline/build_spec.py`; run `review/pipeline/monitor.py --mode snapshot --as-of 2026-09-18`. A live invocation requires today's UTC date. All outputs remain inside `review/`.

## Remaining limits

USREC labels are retrospective and may be revised, so a mature false-alarm result remains an as-of-label assessment. Scorecards now fingerprint supplied outcome files and leave unknown original publication/acquisition timestamps null; they must be re-scored when labels revise. The final archived run in a month is the actual available monitoring record, not a reconstruction of an unrecorded daily month-end close. A late-month source release that was never acquired cannot be recovered retrospectively without breaking prospective integrity.

The monitor does not implement independent-signal voting, trade recommendations, or an automatic response to a crossed threshold. Native-frequency flags are human diagnostic prompts; their daily/weekly precision is not established by monthly backtest rates. Source-grace windows do not replace an exact publisher release-calendar service. No unresolved correctness defect was identified within the bounded review after these fixes.
