# ORB on stocks in play (2026-10-21)

Research only; nothing here imports or changes the live engine.

**Verdict: DEAD for 2025-01-02..2026-10-20.** The published 5-minute opening-range breakout on the 20 "stocks in play"
(Zarattini, Barbon & Aziz, 2024) loses after costs on data after the paper's sample.

- Pre-registered rule (`PREREG_orb.md`, sha256 `8ee93696c16284d6...`, written before any bar data for this test):
  7,179 trades over 451 sessions, net mean -0.47 R at 3 bps per side, session-clustered t -12.0. Fails the kill bar.
- The rule counts a stop touch inside the fill minute as a stop-out, and 56% of fills have one. Resolving those minutes
  from SIP trades (`orb_ticks.py`) shows 70% of them really were stopped after the entry. With that resolved: -0.22 R
  (t -5.0), gross -3.6 bps per trade before costs; long trades only -0.23 R (t -3.8). Still negative at 1 bp per side.
- Even the impossible-best bound (no stop checks in the fill minute at all) fails the bar at 3 bps per side
  (+0.11 R, t 1.6; long only +0.09 R, t 0.65).

Full numbers: `results/orb_results.txt`.

## How to run

    export INTRA_ENV=/path/to/.env ORB_DATA=data/orb
    python orb.py symbols; python orb.py calendar; python orb.py daily; python orb.py elig
    python orb.py first5; python orb.py select; python orb.py intraday; python orb.py sim
    python orb_ticks.py fetch; python orb_ticks.py summary

About 6,500 market-data requests in all; every fetch step is resumable.

## Limits

- Survivorship: only symbols listed on 2026-10-21; delisted names are missing. This usually flatters long results.
- Opening and intraday bars are SIP 5- and 1-minute bars; fills have no spread or queue model beyond the bar open on gaps.
- The trades check uses every SIP trade in the minute, including conditions that bars may exclude.
- The run used the same logic on the linked Mac's sandbox (Python 3.10, pandas 2.3); `orb.py` here merges its steps
  and the two sensitivities into one `sim` report.
