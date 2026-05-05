# Phase 5 Shadow Evidence Loop Report

Generated: 2026-05-05 UTC
Branch: `codex/v13-phase2-expectancy`

## Verdict

Phase 5 is deployed and collecting paper shadow evidence, but it is not yet
complete enough for a trading decision.

Candidate-filter shadow telemetry is enabled in the paper API container and has
started writing live observations. The first evidence slice has `4` valid
events, all tagged `alpha_breakout_chop`. That proves the Phase 5 exposure
capture path is active. It does not prove expectancy yet: no joined outcomes
exist because the current historical bar fetch returned bars ending before the
live telemetry timestamps.

## Runtime State

Paper API was rebuilt and restarted with:

```text
ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED=true
ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_PATH=organism_brain/candidate_filter_shadow_telemetry.jsonl
```

Runtime checks:

- `/healthz`: healthy after restart.
- Container env: telemetry enabled.
- Startup preflight: `16/18` checks passed, `0` critical failures, `2`
  warnings.
- Strategy health endpoint is available behind auth.
- Strategy-only state at check time: `502` trades, total PnL `-790.4508`,
  win rate `0.3287`, Sharpe per trade `-1.3931`.

## Tools Added

- `scripts/phase5_fetch_shadow_bars.py`
  - Reads shadow telemetry symbols.
  - Fetches Alpaca historical bars for those symbols.
  - Writes `artifacts/phase5_shadow_live_bars/bars.pkl`.
- `scripts/phase5_shadow_outcome_join.py`
  - Joins telemetry events to subsequent bars.
  - Reports 1/5/10-bar directional outcomes by filter.
  - Refuses live promotion; passing gates only permits replay review.

## Evidence Commands

```bash
./venv/bin/python scripts/phase5_fetch_shadow_bars.py --lookback 1000
./venv/bin/python scripts/phase5_shadow_outcome_join.py --cache-dir artifacts/phase5_shadow_live_bars --bar-file bars.pkl
./venv/bin/python scripts/phase4_candidate_shadow_analysis.py
```

Outputs:

- `artifacts/phase5_shadow_live_bars/summary_shadow_live_bars.json`
- `artifacts/phase5_shadow_outcome_join/summary_shadow_outcome_join.json`
- `artifacts/phase5_shadow_outcome_join/shadow_event_outcomes.csv`
- `artifacts/phase5_shadow_outcome_join/shadow_filter_horizon_summary.csv`
- `artifacts/phase4_candidate_shadow_analysis/summary_candidate_shadow_analysis.json`

## Current Evidence

Candidate telemetry analyzer:

| Metric | Value |
| --- | ---: |
| Total rows | `4` |
| Valid events | `4` |
| Observed filter | `alpha_breakout_chop` |
| Filter events | `4` |
| Events with outcome | `0` |
| Recommendation | `collect_outcomes_before_promotion` |

Outcome join:

| Metric | Value |
| --- | ---: |
| Valid events | `4` |
| Joined outcomes | `0` |
| Event status | `no_bar_at_or_after_event: 4` |
| Recommendation | `collect_matching_bar_outcomes` |

Live-bar fetch:

- Observed symbols: `AMZN`, `CRM`, `QQQ`, `TSLA`.
- Fetch succeeded, but returned bars ended before the live telemetry
  timestamps. This is a data-availability blocker for outcome joining, not a
  strategy result.

## Completion Criteria Still Open

Phase 5 is not complete until all are true:

- At least one full liquid paper session has run with telemetry enabled.
- Each candidate filter has at least `30` live shadow events.
- Each candidate filter has at least `20` joined outcome events.
- Outcome joins cover subsequent bars for the telemetry timestamps.
- A post-session report recommends one of:
  - discard candidate,
  - keep collecting,
  - replay review,
  - Phase 6 guarded promotion experiment.

## Current Recommendation

Keep the paper container running with telemetry enabled through the session.
After market close, rerun the bar fetch and outcome join. If historical bars
still lag the session, add a runtime stream-bar export; do not promote any
candidate-filter gate from the current evidence.
