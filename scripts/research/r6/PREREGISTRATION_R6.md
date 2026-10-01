# R-6 — Regime stand-down calibration (audit finding F-03): pre-registration

Written 2026-10-01, before any of the test data below has been downloaded or looked at.
Research only: nothing here changes the platform, the frozen surface or the forward clock.
A passing result is a proposal for a shadow-first module and an owner decision, never an
automatic change.

## 0. Provenance (honest)

- The question comes from the owner (2026-09-30): "is the chop definition too narrow / are the
  parameters too strict?" The platform labels about 83% of regular-session ticks chop
  (38 logged sessions since 2026-06-16) and REGIME_POLICY routes chop only to mean reversion,
  which is not live.
- Two of the hypotheses below were generated from the lifetime paper ledger (611 clean trades,
  2026-03-30 to 2026-09-21). That ledger is therefore in-sample for them and cannot test them:
  - entries labeled chop: n=367, -5.7 bps per trade net of 3 bps round trip (t about -2.9);
    trending_up: n=51, -5.9 bps; high_vol: n=34, +24.6 bps (t about 2.0), 20 of them entered
    10:00-12:00 ET (+46 bps);
  - the June 2026 walk-forward (artifacts/phase2/param_sweep_result_2026-06-27.txt) found no
    edge for momentum or breakout on the 22-symbol June corpus.
- The research program's evidence ledger already lists "chop filter caused the drought (R-5
  pitch)" as falsified. R-6 asks a different question: whether trading more (or differently
  labeled) regimes has positive expectancy, not why trades stopped.

## 1. Data

- 1-minute bars, 2025-01-02 to the pull date, for the platform's 20 core symbols and 8 more
  sector ETFs, Alpaca market data v2 (`adjustment=all`; SIP where the plan allows it, IEX
  otherwise, recorded per file), pulled by `pull_research_bars.py` on the owner's Mac.
- Calendar 2025 is the out-of-sample year: the strategy, its thresholds and both hypotheses
  above were developed on 2026 data. 2026-01-02 onward is in-sample and is used only for
  calibration checks and to reproduce the ledger's behaviour (sanity).
- A file with feed=iex for a symbol that is sip elsewhere is analysed both ways; a result that
  depends on the feed mix is reported as such.

## 2. Engine and costs

- The frozen engine in replay (`backend/organism/replay_simulator.py`) at the PR #35 merge,
  with the live exit engine, fixed ATR-dollar risk sizing, the opening block, the EOD block and
  flatten, and the 15:45 ET late-entry block. No parameter is tuned.
- Costs: 3 bps per side (6 bps round trip), the research program's floor. Results at 1.5 bps
  per side are reported alongside but decide nothing.
- Clusters for t-statistics: trading sessions (cluster-robust standard errors).

## 3. Arms

| Arm | Change from control | Question |
|---|---|---|
| A0 | none (current REGIME_POLICY and detector) | control |
| A1 | chop -> ["momentum", "breakout"] | does trading the chop label add expectancy? |
| A2 | trend sensitivity 0.5 (the RC-2 shadow detector) | does a gentler trend label add expectancy? |
| H  | A0's entries in high_vol, 10:00-12:00 ET | is the ledger's high-vol pocket real? |

## 4. Kill bars (decided now, applied mechanically)

For A1 and A2 the test is on the incremental trades (those the arm takes and A0 does not), in
2025 only:

- PASS: n >= 60 incremental trades, net expectancy > 0 at 3 bps per side, cluster-robust
  t >= 2.0, and the arm's total net P&L >= A0's.
- DEAD: net expectancy <= 0, or t <= 0.
- INDETERMINATE: anything else (including n < 60). Indeterminate is not a reason to trade.

For H: PASS needs n >= 60 qualifying 2025 trades with net expectancy > 0 and t >= 2.0;
DEAD if expectancy <= 0; otherwise INDETERMINATE.

No arm may be re-specified after the 2025 result is seen. A new idea is a new memo.

## 5. What happens next

- Any PASS: a shadow-first module and a pre-registered forward gate (Rule A) proposed to the
  owner; the live policy changes only with his sign-off and a new activation.
- All DEAD: F-03 is answered "keep the stand-down"; the regime label is not where edge is,
  and research moves to the program's daily-horizon backlog.
- The replay itself is checked first against the 2026 ledger (A0 should reproduce the
  ledger's broad regime mix and trade counts); if it cannot, results are reported as
  unreliable and no verdict is drawn.
