# Phase 5 Shadow Evidence Loop Report

Generated: 2026-05-05 UTC
Branch: `codex/v13-phase2-expectancy`

## Verdict

Phase 5 is deployed, collecting paper shadow evidence, and the post-close
outcome join now works against event-time bars. The result is not a promotion:
`alpha_breakout_chop` has enough joined outcomes and is negative across the
1/5/10-bar windows. The smaller `conf_45_55` slice is mildly positive in this
sample, but it has only `14` events, below the Phase 5 sample gate.

No candidate filter should be promoted to live behavior from this evidence.
`alpha_breakout_chop` should be treated as rejected or needing a redesigned
hypothesis. `conf_45_55` can keep collecting, but only as shadow evidence.

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
- Strategy-only state at Phase 5 deploy check: `505` trades, total PnL
  `-812.7209`, win rate `0.3267`, Sharpe per trade `-1.4319`.
- Post-close runtime check: container SHA `abc35ff7d`, `/healthz` healthy,
  telemetry enabled, active telemetry file at `62` rows.

## Tools Added

- `scripts/phase5_fetch_shadow_bars.py`
  - Reads shadow telemetry symbols.
  - Fetches Alpaca historical bars for those symbols around the observed
    telemetry timestamp window. The first version used a broad ascending
    historical query and could truncate to stale early-history bars before
    reaching the paper-session events.
  - Writes `artifacts/phase5_shadow_live_bars/bars.pkl`.
- `scripts/phase5_shadow_outcome_join.py`
  - Joins telemetry events to subsequent bars.
  - Reports 1/5/10-bar directional outcomes by filter.
  - Refuses live promotion; passing gates only permits replay review.
- `backend/organism/brain_persistence.py`
  - Preserves the active `candidate_filter_shadow_telemetry.jsonl` file across
    full brain-save directory swaps. Without this, Phase 5 rows survived only in
    backup snapshots and the active capture file disappeared after a save/restart
    cycle.

## Evidence Commands

```bash
./venv/bin/python scripts/phase5_fetch_shadow_bars.py --lookback 1000
./venv/bin/python scripts/phase5_shadow_outcome_join.py --cache-dir artifacts/phase5_shadow_live_bars --bar-file bars.pkl
./venv/bin/python scripts/phase4_candidate_shadow_analysis.py --out-dir artifacts/phase5_shadow_analysis
```

Outputs:

- `artifacts/phase5_shadow_live_bars/summary_shadow_live_bars.json`
- `artifacts/phase5_shadow_outcome_join/summary_shadow_outcome_join.json`
- `artifacts/phase5_shadow_outcome_join/shadow_event_outcomes.csv`
- `artifacts/phase5_shadow_outcome_join/shadow_filter_horizon_summary.csv`
- `artifacts/phase5_shadow_analysis/summary_candidate_shadow_analysis.json`

## Current Evidence

Post-close candidate telemetry analyzer:

| Metric | Value |
| --- | ---: |
| Total rows | `62` |
| Valid events | `62` |
| Observed filters | `alpha_breakout_chop`, `conf_45_55` |
| `alpha_breakout_chop` events | `56` |
| `conf_45_55` events | `14` |
| Events with outcome | `0` |
| Recommendation | `collect_outcomes_before_promotion` |

Post-close outcome join:

| Metric | Value |
| --- | ---: |
| Valid events | `62` |
| Joined horizon rows | `186` |
| Event status | `joined: 186` |
| Recommendation | `insufficient_shadow_sample` |

Filter/horizon evidence:

| Filter | Horizon | Events | Outcomes | Mean directional bps | Win rate | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `alpha_breakout_chop` | `1` | `56` | `56` | `-1.3378` | `0.3929` | sample + outcome pass, negative |
| `alpha_breakout_chop` | `5` | `56` | `56` | `-3.4810` | `0.3393` | sample + outcome pass, negative |
| `alpha_breakout_chop` | `10` | `56` | `56` | `-2.5868` | `0.3929` | sample + outcome pass, negative |
| `conf_45_55` | `1` | `14` | `14` | `2.3161` | `0.5000` | sample fail |
| `conf_45_55` | `5` | `14` | `14` | `7.0155` | `0.5000` | sample fail |
| `conf_45_55` | `10` | `14` | `14` | `2.1171` | `0.5000` | sample fail |

Live-bar fetch:

- Observed symbols: `AAPL`, `AMD`, `AMZN`, `AVGO`, `CRM`, `IWM`, `PSQ`, `QQQ`,
  `TSLA`, `XLK`.
- Event-window query: `2026-05-05T13:39:44Z` through
  `2026-05-05T20:33:06Z`.
- Fetch succeeded and covered the telemetry timestamps; per-symbol bars ended
  between `2026-05-05T20:27:00Z` and `2026-05-05T20:32:00Z`.

## Completion Criteria Still Open

Phase 5's post-close evidence pass is complete for today's captured session,
but the broader shadow program is not complete for every candidate filter:

- `alpha_breakout_chop`: sample gate passed, outcome gate passed, evidence is
  negative across all measured horizons. Do not promote; discard or redesign.
- `conf_45_55`: outcome join works, but only `14` events exist. Keep collecting
  in shadow if this hypothesis remains interesting.
- A full future session can continue shadow collection, but it should not block
  the conclusion that `alpha_breakout_chop` is not ready for replay review.

## Current Recommendation

Do not promote any candidate filter. Treat `alpha_breakout_chop` as a rejected
gate candidate for now. Keep `conf_45_55` shadow-only until it reaches at least
`30` events and `20` joined outcomes, then rerun the same post-close join.

## Follow-Up

For any future shadow session:

```bash
./venv/bin/python scripts/phase5_fetch_shadow_bars.py --lookback 1000
./venv/bin/python scripts/phase5_shadow_outcome_join.py --cache-dir artifacts/phase5_shadow_live_bars --bar-file bars.pkl
./venv/bin/python scripts/phase4_candidate_shadow_analysis.py --out-dir artifacts/phase5_shadow_analysis
```

The one-time post-close automation has served its purpose once this report,
artifacts, and audit index are committed and pushed.
