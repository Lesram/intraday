# Phase D — Indicator specification

**Decision:** keep a small diagnostic monitoring system, with no automatic price forecast, trade or allocation output. The machine contract is [indicators.csv](indicators.csv). It contains one record per indicator, every requested specification field, operational formula fields and links to the reproducible historical evidence.

## Architecture and the twelve indicators

Use three distinct layers: **data health first**, **fast economic state**, then **slow structural context**. No additive market-risk score combines valuation with a currently widening credit spread. A high long-horizon valuation can persist for years; a contemporaneous stress flag can arrive after a recession begins. Calling either a forecast confuses its purpose.

| Tier | Indicator | Exact operational boundary | Question answered / action |
|---|---|---|---|
| 1 — review | Claims deterioration | Four-week initial claims mean ≥20% above its trailing 52-week minimum | Is observed labour demand weakening? Request a diagnostic review after the next release confirms it. |
| 1 — review | Real-time Sahm gap | Published SAHMREALTIME ≥0.50 percentage points | Has unemployment deteriorated enough to resemble a recession already starting or underway? Diagnose, do not forecast equities. |
| 1 — review | Baa spread acceleration | Last completed-month BAA10Y − its value three calendar months earlier ≥1 percentage point | Has corporate financing risk repriced materially? Review credit and funding evidence. |
| 2 — watch | Baa spread level | BAA10Y ≥3 percentage points | Is the corporate/Treasury yield gap elevated in absolute terms? |
| 2 — watch | Financial conditions | NFCI >0 | Are measured financial conditions tighter than the index's historical average? |
| 2 — watch | Yield curve | Monthly GS10 − TB3MS <0 | Is a long-lead recession warning present? Use the same monthly bill-yield convention as validation. |
| 2 — watch | Headline inflation | Calendar CPI YoY ≥4% | Is inflation already in a higher regime? This describes observed inflation, not its future onset. |
| 2 — watch | Inflation acceleration | Calendar CPI YoY ≥4% AND its change from a year earlier ≥2 percentage points | Is elevated inflation also accelerating broadly over a year? |
| 3 — context | Core inflation | No trigger | Distinguish the underlying consumer-price basket from the energy contribution. |
| 3 — context | Brent spot oil | No trigger | Track the observed energy shock and its reversal; a spot price is not a tradable total-return index. |
| 3 — context | Corporate equity value/GDP | No trigger | Put aggregate equity valuation in a transparent accounting context over years. |
| 3 — context | NIPA after-tax profits/GDP | No trigger | Expose the earnings/profit-share assumption behind valuation scenarios. |

Tier 1 means **act on the evidence-review process**, not act with capital. These three choices are operational judgments: a materially deteriorating labour or credit observation deserves examination even though the evidence does not establish a reliable market timer. They are not selected by maximizing historical hit rate. Two labour indicators do not constitute two independent confirmations. A publication/source failure can suspend any tier; unavailable is never scored as normal.

## What the thresholds actually did

Source: blind Phase B event study, `phase_b_events/indicator_event_metrics.csv`, supplied histories captured 2026-09-19. Thresholds and outcome definitions were written before computation in `phase_b_events/preregistration.json`. Onsets are declustered; unresolved horizons are excluded. The recession diagnostic target below includes a recession **already underway or beginning in the next twelve months**. It therefore must not be described as a twelve-month recession forecast.

| Diagnostic | Full-history hits / alarms | False alarms / alarms | Wilson 95% interval for false fraction | Holdout hits / alarms, 2000 onward |
|---|---:|---:|---:|---:|
| Claims deterioration | 9/13 | 4/13 =30.8% | 12.7–57.6% | 3/5 |
| Sahm ≥0.50 | 8/11 | 3/11 =27.3% | 9.7–56.6% | 2/4 |
| Baa quarterly widening ≥1pp | 2/2 | 0/2 =0% | 0–65.8% | 2/2 |

The credit result is two observations, not a proven perfect indicator. Median lead is zero under the diagnostic event definition because the recession is already present. The separate signed-delay table shows Sahm's successful diagnoses arrived a median **four months after** recession onset; retaining that fact matters more than a flattering hit rate. Full study ranges and sample dates accompany each CSV row.

For **strictly future** recession onsets, the same flags perform differently: claims 4/8 hits within twelve months, Sahm 1/4, and Baa acceleration has **zero eligible leading alarms**, so its leading-alarm probability is undefined. For a twenty-percent equity price loss from the signal month's price over twelve months, false-alarm fractions are claims **10/13**, Sahm **7/11**, and Baa acceleration **1/2**. These are monthly-average price outcomes, not daily drawdowns or net trading returns.

The curve's twenty-four-month recession result is **6/8 hits**, two false alarms, median lead **9.5 months**, range **5–16**, with post-2000 **3/4 hits**. Its false-alarm interval remains **7.1–59.1%** for the full sample. It earns a long-lead watch role, not a timed equity-sale rule. The entire event grid—including unflattering inflation and drawdown outcomes—is retained alongside the selected indicator-use records. No row may borrow the success rate of a different series, event, frequency or horizon.

Every triggered indicator reports two distinct denominators in the machine contract:

- **Alarm false fraction:** failed eligible, mature alarm episodes / all such alarm episodes. This answers “how often was the alarm wrong?”
- **Classical FPR:** alarm-positive nonevent months / all eligible nonevent months. Those monthly windows overlap; they are not independent event counts.

Undefined n=0 stays undefined. Context-only rows explicitly say that no trigger was tested and why a false-positive rate does not apply. They must not later acquire an alarm colour, alert or trading meaning without a separately registered event study.

## Sources, transportability and uncertainty

The CSV defines exact IDs, formulas, publisher links, consistent-history bounds, observation frequencies, publication/revision limitations, intended questions, thresholds and their rationale. FRED series pages identify underlying publishers. Public CSV access succeeded in the live trial. The real-time Sahm definition is documented by [FRED](https://fred.stlouisfed.org/data/SAHMREALTIME); its historical source basis differs from the other revised histories. No reconstructed publication timestamp is claimed.

CPI calculations join the exact year-earlier calendar month. The missing October 2025 observation remains missing. A source observation dated April 1 for a quarterly ratio means Q2, not an April-only measurement. Credit acceleration uses completed calendar months; a partial current month is shown only where the declared indicator is a daily level. Source timestamps and update deadlines remain explicit in the dashboard.

All retrospective “holdout” results are **chronological pseudo-out-of-sample**: thresholds were not optimized on the holdout, but most historical data are today's revised series. The exercise also involves many event/indicator comparisons and a small number of economic episodes. Wilson intervals are descriptive and assume more independence than the macro history fully provides. Historical association is not a causal mechanism, calibrated forecast interval or guarantee of future decision value.

## Independence is a cost

The machine specification links each scored indicator to pairwise alarm-phi correlations and Jaccard overlaps, with common history and n. Claims/Sahm share labour information; Baa/NFCI share financial conditions; headline inflation and its acceleration share the same CPI input. Equity/GDP and profits/GDP share a denominator and partly respond to the same nominal economy. Treat distinct labour and credit information as broader evidence, without pretending a two-flag conjunction has an independently measured hit rate.

The system intentionally omits a fitted CAPE block and a sector-allocation tilt. The input earnings series is stale and requires a contestable splice; the independent analog screen shows specification-sensitive relative returns. A transparent equity/GDP context ratio and explicit profit-share sensitivity are more defensible here than presenting a proxy splice as precise current Shiller CAPE. This is a design judgment, not evidence that CAPE has no long-horizon information.

## Retirement and change control

Each row contains a kill criterion. Immediately suspend a flag for an unbridged source-definition break. Review prospective usefulness after twenty new nonoverlapping mature alarms, or twenty-four monthly audits without distinct decision value. Preserve every failed signal and its original threshold. A threshold change creates a new specification version and prospective evaluation period; it does not erase prior false positives or reclassify open horizons.

Validate any proposed extra indicator against a clearly named outcome and a suitable baseline before promotion. Require evidence of additional information, not merely a persuasive story or a large correlation with an existing flag. Re-estimation, if justified, must use a declared training sample and leave a later holdout untouched. Slow variables may inform scenarios; they remain prohibited as time-specific trading signals in this research monitor.

The runnable implementation, archive policy, monthly report and off-cycle review rules are in [Phase E](PHASE_E_dashboard_spec.md). This specification is separate from the frozen intraday trading platform and changes none of its decision functions.
