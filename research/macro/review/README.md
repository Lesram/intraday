# Macro review 002 — start here

The review is complete across the five requested phases. Its main finding is that **the first report's precise forecast and allocation conclusions are not supported by its calculations**. Several underlying observations survive, but incomplete return horizons, stale formulas, changed denominators and reviewer-supplied prediction deadlines materially affect the results.

## Read or use the result

| Deliverable | What it answers |
|---|---|
| [Adjudication](PHASE_C_adjudication.md) | Which conclusions survived, which failed, all twelve requested attacks and the evidence that would settle remaining disputes |
| [Portable dashboard](dashboard.html) | Current dated measurements, thresholds, changes, source dates and false alarms; open in a browser |
| [Indicator specification](PHASE_D_indicator_spec.md) · [CSV](indicators.csv) | Twelve defined indicators: three diagnostic review flags, five watch variables, four context variables |
| [Operating guide](PHASE_E_dashboard_spec.md) | Refresh, monthly reporting, off-cycle review, archiving and retirement rules |
| [Generated report](pipeline/output/report.md) | Example recurring report from the validated historical snapshot |
| [Blind transcript analysis](PHASE_A_transcript_analysis.md) | All 58 captured transcripts, narrative changes, pitches, sources and contradiction candidates |
| [Blind regime study](PHASE_B_independent_regime_analysis.md) | Independent historical selection, forward returns and an honest range of outcomes |
| [Blind indicator/event study](PHASE_B_event_validation.md) | False alarms, event definitions, lead/lag, holdout and correlated indicators |
| [Sealed record](LOG.md) | Hashes fixed before opening the prior conclusions |
| [Validation and audit index](LIVE_AUDIT_INDEX.md) | Tests, source integrity, platform boundaries and remaining limitations |

The dashboard is a historical snapshot as of 2026-09-18 using the supplied 2026-09-19 capture. Each series shows its own observation date. Live source access was separately tested successfully. No background schedule or external publication has been installed.

## The practical result

Keep claims deterioration, the Sahm unemployment gap and rapid Baa-spread widening as requests to review economic evidence. They are diagnostic flags, often coincident with a recession, with meaningful false-alarm rates. They do not instruct trades. Keep valuation and profit share as slow context. A calm credit reading is not a guarantee of safety, and a high valuation is not a crash clock.

The original 82.1% factual-verdict share reproduces under its chosen label convention, but it is not a probability that a channel's story is true. The review separately supplies 72 blind verdict re-adjudications,48 unresolved-claim classifications,60 prediction re-adjudications, matched benchmark sensitivity and controlled historical robustness checks. Sample designs and limits accompany each result.

## Run the monitor

From this directory, with Python/pandas/numpy/tabulate:

```sh
python pipeline/monitor.py --mode snapshot --as-of 2026-09-18
python pipeline/refresh.py --mode live
python -m unittest discover -s pipeline -p 'test_*.py' -v
```

The live refresh uses public FRED endpoints without credentials, saves source receipts and a report, and rebuilds the same dashboard. `refresh.py` needs the installed Data dashboard compiler and Node; `--node` and `--data-plugin-root` allow explicit paths. `monitor.py` works without that compiler. Dependencies are listed in [requirements.txt](pipeline/requirements.txt), and the exact local environment is in `artifacts/environment.json`.

To score future acquired monthly alarms against recession labels:

```sh
python pipeline/score_archive.py --outcomes /path/to/dated-USREC.csv
```

Snapshot runs never count as prospective successes. Initial-high readings are not assumed crossings, incomplete horizons stay pending, and failed source reads do not fall back silently. The current prospective scorecard has no matured episodes, as expected for a new monitor.

## Reproduction and limits

The original source package remains untouched in the parent macro directory. Reproducing the historical research requires that companion package; its 344 file hashes are recorded. The portable dashboard embeds its reviewed data and opens without the source package or a server. Phase A/B outputs are immutable after their 75-file seal. All new files and output writes are inside review. Five lengthy transcript-extraction tables remain local and are excluded from the public PR; [public packaging](PUBLIC_PACKAGE.md) documents this distinction.

Most historical series are revised data, not reconstructed publication vintages. Economic event samples are small, often dependent, and not evidence of causal or tradable skill.35 excluded paid videos are all Jikh;50 additional public catalogue videos are missing. The review does not establish either complete service's performance.

The frozen trading surface verifies unchanged. The broader platform test attempt could not collect because FastAPI was absent in the available runtime; no platform test success is claimed. The review's own 35 tests pass. Its artifact pack and audit index are located here because the task expressly prohibits writes outside this directory. An existing freeze timestamp differs from the July timestamp in the supplied operating contract; the review records that pre-existing discrepancy without resetting it.

The [draft PR](https://github.com/Lesram/intraday/pull/21) is open. Hosted checks are blocked by existing workflow configuration: retired artifact actions and a secret-pattern grep that matches normal repository code. [CI diagnosis](artifacts/ci_status.json) records the evidence. These CI files were outside the authorized write boundary and remain unchanged.
