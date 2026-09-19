# Phase 3 ORB Shadow Outcome Report

Generated: 2026-05-05
Branch: `codex/v13-phase2-expectancy`

## Question

Do current ORB shadow candidates show enough offline expectancy to justify
promotion work beyond shadow observation?

## Verdict

Do not promote ORB live from the current evidence. The cached-bar offline
outcome simulator found a small sample, and that sample was negative across the
default setup and three quick sensitivities.

This does not mean ORB is permanently dead. It means the current ORB scanner
defaults do not deserve live risk yet. The right next move is better attribution
and larger forward shadow data, not live enablement.

## Method

I added `scripts/phase3_orb_shadow_outcome.py`, an offline simulator that:

- Loads cached intraday bars from `artifacts/backtest_rc_1_5/bars.pkl`.
- Uses the current `backend.organism.orb_scanner.ORBScanner` for candidate
  detection, not an independent reimplementation.
- Takes the first breakout per symbol/session.
- Enters at the next bar open.
- Applies 5 bps entry and 5 bps exit slippage by default.
- Exits at the scanner stop or the last available pre-15:55 ET bar.
- Reports one-share PnL and R-multiple, so results are sizing-independent.

I did not use the older May 1 production ORB shadow logs as profitability
evidence because prior parity audits found those logs were contaminated by a
stale-cache bug. The simulator uses cached bars plus the current fixed scanner
logic instead.

## Default Result

Command:

```bash
./venv/bin/python scripts/phase3_orb_shadow_outcome.py --out-dir artifacts/phase3_orb_shadow_outcome --min-trades-for-signal 30
```

Result:

| Metric | Value |
|--------|------:|
| Symbols scanned | 22 |
| Hypothetical trades | 20 |
| Gross PnL / share | `-$27.88` |
| Avg PnL / trade / share | `-$1.39` |
| Win rate | `35.0%` |
| Avg R | `-0.416` |
| Median R | `-0.424` |
| Stop rate | `40.0%` |
| Exit mix | 12 EOD, 8 stop |
| Recommendation | `insufficient_negative_sample` |

Session coverage:

| Session | Trades |
|---------|-------:|
| 2026-04-16 | 5 |
| 2026-04-17 | 7 |
| 2026-04-20 | 5 |
| 2026-04-21 | 2 |
| 2026-04-23 | 1 |

Direction mix: 11 short, 9 long.

## Sensitivities

| Variant | Trades | Gross PnL / share | Avg R | Win rate | Stop rate | Recommendation |
|---------|-------:|------------------:|------:|---------:|----------:|----------------|
| Default: top 10, RV >= 1.5, 5 bps | 20 | `-$27.88` | `-0.416` | `35.0%` | `40.0%` | `insufficient_negative_sample` |
| No slippage | 20 | `-$19.71` | `-0.273` | `40.0%` | `40.0%` | `insufficient_negative_sample` |
| Top 5 only | 15 | `-$17.64` | `-0.489` | `26.7%` | `40.0%` | `insufficient_negative_sample` |
| RV >= 3.0 | 18 | `-$28.81` | `-0.418` | `33.3%` | `38.9%` | `insufficient_negative_sample` |

The no-slippage run remained negative, so transaction friction is not the sole
reason the default result failed.

## Interpretation

The sample is below the 30-trade threshold, but it is also negative enough that
there is no reason to promote ORB live from this cache. Some symbols looked
promising in isolation, including `CAT`, `GOOGL`, `IWM`, `AMZN`, and `AAPL`, but
the aggregate scanner default lost money and the symbol-level sample sizes are
too small to trust.

The most useful signal from this slice is not a parameter tweak. It is that ORB
needs better forward shadow attribution before it deserves risk. A live enable
would be premature.

## Recommendation

Keep `ORGANISM_ORB_LIVE_ENABLED=false`.

For Phase 3, move next to confidence/entry-source attribution or alpha scanner
observability. If ORB remains interesting, the next ORB-specific step should be
collecting clean forward shadow events with outcomes attached, not tuning the
current scanner into live trading from a short cached window.
