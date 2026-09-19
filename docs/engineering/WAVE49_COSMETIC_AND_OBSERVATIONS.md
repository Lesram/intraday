# Wave 49 — Cosmetic Cleanup + V9 Observations (2026-05-03)

**Branch:** rc-1.5-curated @ post-wave-48 (2ca51a9)
**Status:** documentation-only wave; no code changes.

This wave wraps the V9 audit cycle (waves 41-49) with two
forward-looking artifacts:

## UU-4 deferred to V10 lint rule (cosmetic)

V9 UU audit identified ~14 cargo-culted `try/except: pass` blocks
around safe in-memory operations (e.g. dict.pop with a default,
list.append, etc.) where no exception path actually exists.  These
are noise but not bugs.

Rather than surgically removing them in this wave (each removal
needs verification that the wrapped op truly can't raise — high effort,
low signal), V10 should ship a lint rule:

```python
# Proposed V10 ruff config:
# Ban `try/except Exception: pass` around expressions whose AST shows
# only attribute access, dict indexing with default, or list mutation.
# Allow with `# noqa: UU-4` for documented safe-defensive cases.
```

Until V10 ships the rule, leave the existing cargo-cult sites in
place.  They're cosmetic, not correctness issues.

## DD3-6 diagnostic observations (no fix; observe over time)

V9 DD3 audit observed (Day-1 production trade analysis):
- 16 trades, +$69.35 PnL, 50% win.
- Edge concentrated in 1 AMD trade (+$51); without it, +$1.19/trade — indistinguishable from zero.
- Pyramid_cut accounts for 31% of closes; chop-min-hold gate failed
  to suppress 3 of 5 cuts where bars_held < 10.

Wave-44 DD3-1 fix (pyramider Layer 2 reachability) addresses one
suspected upstream cause of the over-cut behavior.  Wave-44 DD3-5
fix (fitness gate handles missing data) addresses the bypass that
let low-quality symbols through.

Recommended observation window: 2 weeks of post-deploy data, with
fitness gate now actually rejecting symbols + Layer 2 actually firing.
If edge stays concentrated in 1-2 symbols, the issue is symbol selection
upstream of the strategy logic — outside DD3 scope.

## V9 wave summary (waves 41-49)

| Wave | Findings closed | Severity |
|---|---|---|
| 41 | PP-1, PP-2, PP-3, PP-4, UU-1, UU-2, UU-3 | Critical (5) + High (1) + Medium (1) |
| 42 | AA3-1, AA3-2, AA3-3 | High (2) + Medium (1) |
| 43 | DD3-2, DD3-3 | High (2) |
| 44 | DD3-1, DD3-4, DD3-5 | High (1) + Medium (2) |
| 45 | PP-5, PP-6 | High (2) |
| 46 | TT-2 | High (1) |
| 47 | TT-4, TT-5, AA3-4 | Medium (2) + Info (1) |
| 48 | Z7-1, W4-1, W4-3 | Medium (1) + Low (2) |
| 49 | (this doc — UU-4 deferred, DD3-6 observed) | — |

**Total V9 closures: 25 of 32 actionable findings.**

**V9 deferred (require schema migrations / multi-day soak):**
- BB3-F1, BB3-F3, BB3-F4: schema changes, alembic migration window
- TT-3: partial expression index, alembic migration
- TT-1: tick p99 reduction (watchdog covers worst case at 30s; further
  optimization is V10 perf-pass work)
- W4-2: positive-assertion grep convention drift (doc / wave-author
  convention)
- UU-4: cargo-cult try/except (lint rule for V10)
- DD3-6: edge concentration (observe; pyramider + fitness fixes may resolve)

## V10 forward planning

Per V8 OO + V9 confirmation: each new lens yields 5-10 first-round
findings.  V10 should retain all 11 lenses (AA, BB, DD, HH, NN, OO,
PP, UU, TT, W3/W4, Z6/Z7) at rotating depth, plus add 1-2 NEW lenses:

Candidates:
- **VV — Frontend/backend contract drift** (V8 OO recommendation; not
  yet shipped).
- **WW — Multi-day operational soak** (V8 OO recommendation; need
  staging environment).
- **XX — Migration round-trip on real DB snapshot** (V8 OO
  recommendation; need scratch DB).

V10 yield expectation: 5-20 findings.  If <5 = cycle has truly
converged; reduce to quarterly.
