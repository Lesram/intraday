# Forward-evidence pipeline — verification note

**Work order 2026-07-23, Task 4 (REPORT ONLY).** No code changed. Drift-verify green.
**FROZEN_AT = 2026-07-07T20:36:49.008305+00:00.**

## 1. What feeds the verdict, and what does not (with citations)

Two readers, two inputs. They are **not** the same corpus.

### The gate = REAL FILLS ONLY
- `scripts/phase2_gate.py:31` → `corpus = load_forward_corpus(str(TRADES), frozen_at)`
  where `TRADES = organism_brain/trade_history.csv`.
- `backend/organism/phase2_gate.py:116` `def load_forward_corpus(trade_history_path, frozen_at)`:
  - line 120 `df = pd.read_csv(trade_history_path)` — the closed-trade ledger.
  - line 124-125 `closed = pd.to_datetime(df["closed_at"]…)` then
    `df = df[closed.notna() & (closed > cutoff)]` — **strictly after FROZEN_AT.**
  - returns `strategy, regime, session, net_pnl, closed_at`.

So the Phase-2 verdict corpus counts **only trades that actually filled and closed
after the freeze.** Nothing else can move a strategy off `INSUFFICIENT`.

### The attribution report = real fills PLUS shadow signals (separate file)
- `scripts/phase3_attribution_report.py:45` calls the **same** `load_forward_corpus`
  for the capital (real-fill) section — identical to the gate.
- `scripts/phase3_attribution_report.py:31` `EVIDENCE = organism_brain/strategy_evidence_events.jsonl`;
  line 68 `with EVIDENCE.open() as fh:` reads the framework **shadow signal** stream.

The phase-9 `fw_momentum` / `fw_mean_reversion` / `fw_orb` events are tagged
`phase9_shadow_only_no_order_path` — they never reach an order and therefore never
appear in `trade_history.csv`. They feed **only** the attribution report's shadow
section, never the gate. The RC-1.5 / ORB shadow scanners are the same: signal
telemetry, not fills.

**Conclusion: confirmed.** The verdict corpus = real fills after FROZEN_AT. Shadow
streams are informational and do not (and by design cannot) advance the verdict.

## 2. Current numbers (measured 2026-07-23)

### Real-fill verdict corpus — `python scripts/phase2_gate.py`
```
FROZEN_AT=2026-07-07T20:36:49Z   forward trades = 0
  momentum         state=INSUFFICIENT   n=0
  breakout         state=INSUFFICIENT   n=0
  mean_reversion   state=INSUFFICIENT   n=0
  orb              state=INSUFFICIENT   n=0
```
`trade_history.csv`: 583 rows, 441 with a valid `closed_at`. **Max `closed_at`
= 2026-07-07T18:37:25Z — ~2 h BEFORE the freeze.** Rows strictly after FROZEN_AT: **0.**
The corpus is empty because the last real close (META) predates the freeze stamp;
there has not been a single fill since. This is by construction, not a bug.

### Shadow accumulation — `python scripts/phase3_attribution_report.py`, section [3]
Un-routed framework signals since the freeze (counts only — **no PnL**, because
`no_order_path` events never priced an entry/exit):

| strategy | regime | signals |
|---|---|---:|
| momentum | chop | 4867 |
| momentum | trending_down | 1211 |
| orb | chop | 212 |
| orb | trending_down | 110 |
| orb | high_vol | 101 |
| orb | trending_up | 5 |
| mean_reversion | trending_down | 115 |
| mean_reversion | chop | 63 |
| mean_reversion | high_vol | 28 |

~6.7k shadow signals accrued, **none of which carry gross or costed-net PnL** — they
are signal-emission telemetry, not simulated fills. The only PnL-bearing shadow
stream is exit-policy shadow (`shadow_exit_telemetry.jsonl`), whose faithful
evidence is n=1 (META −$0.525, 07-07) — also pre-freeze. So per-strategy forward
PnL evidence since FROZEN_AT is **zero on every axis.**

## 3. Structural consequence

**In a chop tape where the frozen live path stands down (`direction_zero`), the
verdict corpus accrues nothing, indefinitely.** The gate reads fills; the frozen
system produces no fills in chop; therefore n stays 0 and every strategy stays
`INSUFFICIENT` for as long as the regime persists — regardless of how many thousands
of shadow signals pile up. The forward clock advances in wall-time; the *evidence*
clock does not advance at all without fills.

## 4. DECISION ITEM (Marsel) — three honest options, none implemented here

- **(a) Wait for trending / high-vol tape.** Zero methodology risk, slow. This is
  the plan's default: the freeze holds, and the first genuine trend session that
  produces fills starts the real n. Cost: could be weeks; the corpus stays 0 until
  then. **Recommended if the priority is a clean, unimpeachable verdict.**
- **(b) Pre-register an amendment admitting shadow-attribution outcomes as
  per-strategy evidence.** Would let the ~6.7k shadow signals (once given a costed
  PnL model) count toward the verdict. This is a **methodology change** → it must be
  written down and consciously re-frozen (new FROZEN_AT), and it imports the
  shadow's modeling assumptions (fill price, slippage, no market impact) into the
  verdict. Faster to a number, weaker as evidence.
- **(c) Accept a longer horizon.** Keep real-fills-only (a), but formally extend the
  n_target window / calendar expectation so "still INSUFFICIENT" is not read as
  failure. Documentation-only; changes expectations, not the pipeline.

These are **decision-surface / clock-sensitive** and belong to Marsel. This note
changes nothing.
