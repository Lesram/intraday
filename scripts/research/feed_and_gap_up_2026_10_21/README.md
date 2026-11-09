# IEX feed, regime label and gap-up momentum (2026-10-21)

Research only. Nothing here imports or changes the live decision path except
`regime_replay.py`, which loads `backend/organism/regime.py` read-only to
reproduce the installed label. No orders, no writes to `organism_brain/`.

## Verdicts

1. **The regime label's trending-up reading is an IEX artifact.** Replaying the
   installed regime code on IEX bars matched the live label on every minute of
   2026-10-19 and 2026-10-20. Over 26 sessions (09-15..10-20) it said
   trending-up on 5 sessions (250 minutes, 249 before 13:00 ET), each after SPY
   opened higher (+0.3% to +1.2%). IEX has about 1 pre-market bar a day, so
   until about 1 pm the 200-bar window still holds the previous afternoon and
   the overnight gap reads as a trend. On SIP bars the same code labelled no
   minute trending-up. `results/regime_replay.txt`.
2. **IEX bars differ from the market in the inputs the indicators use.**
   Closes agree within about 1 bp, but IEX sees about 4% of volume, its 14-bar
   ATR is about 78% of the market's (so the 3.5-ATR stop is about 2.7 market
   ATRs), only 38% of its 2x volume surges coincide with real ones, and LLY,
   COST and CAT have no bar in 25-32% of regular-hours minutes.
   `results/feed_compare.txt`.
3. **Gap-up momentum: DEAD** (pre-registered, `PREREG_gap_up.md`, sha256
   `465835eed504ebeb...`, written before any gap data was fetched). Primary
   cell, out of sample 2025-01..2026-10: 1,896 trades over 128 sessions, gross
   -0.7 bps, net -6.7 bps at 3 bps per side, session-clustered t = -2.98.
   `results/gap_up_test.txt`.
4. **Shadow strategies: no positive cell.** Replaying the signals logged
   09-16..10-20 on SIP bars: mean reversion 663 trades, net -6.5 bps (t -5.6);
   ORB long net -6.7 bps (74 trades); un-routed momentum long net -8.3 bps;
   un-routed breakout net -11.1 bps. `results/shadow_replay.txt`.

## How to run

The bars come from Alpaca's market-data API. Pass the env file that holds
`ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY`; the keys are read, never printed.
SIP history older than 15 minutes is available on the free plan.

    cd scripts/research/feed_and_gap_up_2026_10_21
    python feed_compare.py fetch --env /path/to/.env      # IEX + SIP, 2026-09-14..10-20
    python feed_compare.py compare
    PYTHONPATH=../../.. python regime_replay.py --logs-dir ~/VS/intra/logs/sessions
    python gap_up_test.py fetch-daily --env /path/to/.env
    python gap_up_test.py fetch-sessions --env /path/to/.env   # ~703 requests, resumable
    python gap_up_test.py build && python gap_up_test.py analyze
    python shadow_replay.py --evidence ~/VS/intra/organism_brain/strategy_evidence_events.jsonl

Data lands in `data/` (not committed).

## Provenance and limits

- Run on 2026-10-21 on the linked Mac's sandbox (Python 3.10, pandas 2.3) with
  the same logic; these files are the cleaned-up versions (argument parsing,
  Eastern-time windows instead of fixed UTC times, which is identical for the
  all-EDT sessions used). The regime run there loaded an unchanged copy of
  `regime.py` (sha256 `5a0f76f298556d7d...`, the 53bd8a1 file) with a
  Python 3.10 alias for `datetime.UTC`.
- The gap-up test uses fixed holding periods; the live exits (stop, breakeven,
  time limits) are approximated only by the stop variant.
- The shadow replay fills IEX-built signals at SIP prices with intrabar
  stop/target touches and no slippage model; ORB runs on the 20 static names
  with the live shadow's RV >= 1.0, not the in-play universe it was designed for.
