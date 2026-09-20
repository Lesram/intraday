# Phase E — Working monitoring system and operating contract

The delivered system is a read-only research monitor. It refreshes twelve indicators, produces a recurring-report document, keeps an archive for later scoring, and builds a self-contained dashboard. The historical prototype is fixed to **2026-09-18**, using the supplied capture of **2026-09-19**. A separate successful live-source trial is retained in `artifacts/live_probe/`; it does not silently replace the review's dated historical evidence.

## What is built

| Component | File | Behaviour |
|---|---|---|
| Indicator contract | `indicators.csv` | One row per indicator; formulas, economic priors, empirical alarm/FPR records, sources, tiers and retirement rules |
| Source refresh and calculations | `pipeline/monitor.py` | Snapshot reproduction or fresh FRED requests; no credentials; every required source checked |
| Same-dashboard rebuild | `pipeline/refresh.py` | Refresh, report, source-backed dashboard build and portable HTML export; failures propagate as nonzero exit |
| Prospective scoring | `pipeline/score_archive.py` | Eligible acquired readings only; initial high reading is not a proven crossing; unresolved outcomes remain pending |
| Application source | `dashboard_app/src/content/dashboard/` | Responsive one-page display, tier filter, indicator selection, history, source inspection and false-alarm details |
| Portable artifact | `dashboard.html` | Compiled application and reviewed data in one HTML file; no remote chart libraries |
| Latest attempt / accepted reading | `pipeline/output/attempt.json` / `latest.json` | Failed attempts remain visible; last accepted reading is retained independently |
| Recurring report | `pipeline/output/report.md` | State, changes, all readings, data exceptions and next review; a failed attempt writes `failed_report.md` |
| Audit archive | `pipeline/readings/`, `attempts/`, `cache/` | Dated accepted readings, failed attempts, raw successful responses and checksums |

All output paths resolve beneath `review/`. The scripts contain no order-submission or trading-configuration code. They do not import the prior dashboard script, whose import executes output writes outside this boundary.

## Refresh and freshness

All Tier 1 and Tier 2 sources are automatable using public FRED CSV endpoints. Twelve source series support twelve derived/context indicators; some indicators use the same series. Each response is checked for schema, monotonic dates, duplicate observations, numeric validity, required history and freshness. Formula checks preserve missing calendar months and prevent a partial September from becoming a completed September credit signal. Quarterly ratios join matching quarters and convert millions to billions before division.

Freshness is judged against the next expected observation's publication deadline, with explicit source-specific lag allowances. Observation dates, period end, source acquisition time, source hash and freshness assumptions remain visible. Exact historical publication timestamps are not available from these CSVs: `published_at` must remain unknown, and acquisition time must never be relabelled publication time. Live archives establish when this monitor first knew a reading; they cannot retroactively make revised history real-time.

Failures are loud: nonzero exit, an error receipt and a failed report. No failed live download falls back silently to the supplied snapshot. The previous validated JSON remains intact. The dashboard rebuild uses the most recent **attempt**, so a failed refresh displays a failure state rather than certifying retained values as current. If the build tool itself is unavailable, the refresh exits with a separate failure and reports that the dashboard was not refreshed; the visible as-of date remains the essential safeguard for an old HTML copy.

Manual sources remain outside the automated Tier 1/2 set: consistent ISM history, margin debt, granular TIC flows, COMEX open interest, and central-bank gold flows were not present as maintained series in the package. Do not promote an occasional manually quoted number to a scored trigger. If added later, require publisher URL, observation period, acquisition timestamp, reviewer and a documented definition bridge.

## Dashboard reading order

The top shows the as-of date, historical/live mode, data-health result, and measured state. Three compact Tier 1 cards show claims deterioration, the Sahm gap and completed-month credit widening. All are diagnostic review flags. Slow equity/GDP and profit-share ratios remain separate context rows. The table shows each value, threshold, signed distance, latest observation change and source date. Percentage-valued indicators use **percentage points** for differences. Compound inflation acceleration displays both required conditions.

The indicator selector opens its actual history and empirical record: event definition, horizon, alarm denominator, holdout sample, lead time and uncertainty. Data gaps remain gaps. Histories show the last twenty-four native observations; they do not pretend that twenty-four days and twenty-four quarters are the same horizon. Source inspection retains formulas, exact series links and source receipts. Tier filtering affects the table only; the top diagnostic cards and selected evidence have their own stated scope.

“No threshold crossed” means only that no declared threshold is crossed. It is not a low crash probability, proof of safety or a market allocation. Context readings carry no implied timing instruction. There is no composite red/green market score and no count of correlated indicators presented as independent votes.

## Run it locally

Use Python with pandas, numpy and tabulate; the exact environment used is recorded in `artifacts/environment.json`. The bundled Codex Python path worked where the system Python lacked these packages. The optional `review/.deps` directory contains local dependencies and is excluded from version control. Source inputs remain in the original sibling `data/raw/` folder; their hashes are in `artifacts/source_manifest.json`.

From `research/macro/review/`, in a suitable Python environment:

```sh
python pipeline/monitor.py --mode snapshot --as-of 2026-09-18
python pipeline/refresh.py --mode snapshot --as-of 2026-09-18
python pipeline/refresh.py --mode live
python pipeline/refresh.py --mode live --outcomes /path/to/dated-USREC.csv
python -m unittest discover -s pipeline -p 'test_*.py' -v
python pipeline/score_archive.py --outcomes /path/to/dated-USREC.csv
```

`refresh.py --outcomes` also updates the prospective scorecard and appends its matured/pending counts to the recurring report. Omit it until independently acquired outcome labels are available. `refresh.py` accepts `--node` and `--data-plugin-root` if the documented Codex runtime is not discoverable. The default plugin path is the installed Data plugin version used in this task. The app source and already-built portable HTML are included; building after an update requires that compiler or a compatible installed Data plugin. `monitor.py` and the Markdown report do not require the dashboard compiler. Live mode defaults to today's UTC date and rejects historical as-of dates because current FRED responses are not historical vintages.

The source package is a local companion input, not committed trading-platform code. Reproduction on another machine requires it or equivalent files with matching hashes. No background scheduler, external publication, email delivery or brokerage integration is installed by this work order. Those are separate operational choices; the requested cadence and executable refresh are provided.

## Cadence and off-cycle review

**Monthly:** publish the main report after headline/core inflation are available. Include current fast-state readings, structural ratios with their actual quarter, changes since the prior monthly reading, any threshold transitions, known missing/stale sources, matured prior alarms, and a short scenario discussion tied to evidence. An unchanged slow reading is not a new observation. Never predict prices, prescribe trades, promise a crisis date, or manufacture certainty from a historical hit rate.

**Weekly:** run a data-health and fast-state check. Keep unchanged and non-actionable results quiet. Request an off-cycle human review when a new Tier 1 threshold survives the next source release, when distinct labour and credit families deteriorate together, or when source failures prevent a reliable reading. Treat claims and Sahm as one labour family, and Baa/NFCI as overlapping financial-condition evidence. These are operating-policy choices, not empirically optimized trading triggers. Monthly historical false-alarm frequencies do not automatically calibrate higher-frequency alerts.

**Quarterly:** review data failures, revisions, duplicate/redundant flags and whether an alert changed the questions examined. Include every alarm, including embarrassing false alarms. **Annually:** evaluate matured prospective observations against the locked definitions and suitable matched baselines. Avoid changing thresholds each time a signal fails. A source-definition break suspends the affected flag immediately. A changed formula or threshold creates a new specification version and a new prospective record; it must not overwrite the prior specification or scorecard.

## Archive and review loop

Preserve accepted snapshots, source responses and hashes; failed attempts are distinct. Keep observation date, period, acquired-at time and unknown publication fields distinct. Score only genuinely acquired live records against independently sourced outcome labels; snapshot reproductions do not count as prospective wins. Do not score an initial already-high reading as a crossing, count a continuously high signal repeatedly, or count a horizon before every outcome month is known. Current readings are generally unresolved, so a scorecard with no matured alarms is an honest starting state.

The included scorer covers the three Tier 1 recession-diagnostic targets. Additional drawdown/inflation/credit target scoring is supplied historically in `phase_b_events/`; prospective expansion must preserve the same economic definitions and archive appropriate independent outcome sources. Twenty new nonoverlapping matured alarms, or twenty-four monthly reviews showing no distinct decision value, trigger the retirement review specified per indicator. Twenty alarms can take many years: that is a consequence of rare macro events, not a reason to substitute overlapping monthly observations.

The source data and dated evidence remain available even if the local preview server stops. The final validation receipt records browser inspection, formula/failure tests, network results and any unavailable platform tests. A useful dashboard is an auditable set of measurements with explicit limits, not a forecasting model created by its colour scheme.
