# Track Z9 v11 — Closure Regression on Waves 50-65

V10 fix waves 50-58 + V11 prep deferrals 60-65 = 14 fix waves. **Z9 verifies every closure marker is in place + behavioral tests pass + container has the post-rebuild code.**

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `11c2275`. Baseline V10 = `e0df067`.

## Method

### 1. Per-finding marker check

| Wave | Markers expected |
|---|---|
| 50 | AA4-2, AA4-3, AA4-4 (AA4-1 = operator deploy) |
| 51 | WW-1, PP2-1, UU2-A, UU2-C |
| 52 | YY-1, YY-2, YY-5 |
| 53 | DD4-1, DD4-2, DD4-4 |
| 54 | VV-3 |
| 55 | XX-1, XX-2 |
| 56 | WW-2, WW-3, PP2-2, PP2-3, Z8-1 |
| 57 | UU2-B (lint rule) |
| 58 | (docs) |
| 59 | AA4-4 follow-up (verify_api_key) |
| 60 | DD4-3 (effective_regime_for_symbol) |
| 61 | XX-3 (portfolio_history migration) |
| 62 | YY-3, YY-4 |
| 63 | HH2-N-1 partial |
| 64 | VV-1 |
| 65 | VV-2 |

For each, grep the marker, verify presence.

### 2. Behavioral test bundle

```
./venv/bin/python -m pytest tests/test_wave50_fixes.py tests/test_wave51_fixes.py tests/test_wave52_fixes.py tests/test_wave53_fixes.py tests/test_wave54_fixes.py tests/test_wave55_fixes.py tests/test_wave56_fixes.py tests/test_wave57_fixes.py tests/test_wave60_fixes.py tests/test_wave61_fixes.py tests/test_wave62_fixes.py tests/test_wave63_fixes.py tests/test_wave64_fixes.py tests/test_wave65_fixes.py tests/test_organism_live_engine.py tests/test_reachability_v8.py -q --timeout=30
```

Expected: 100% pass.

### 3. Container vs source-SHA verification (DD-DEPLOY lens)

```
docker exec intra-api-1 wc -l /app/backend/infra/security.py /app/backend/api/lifespan.py /app/backend/organism/brain_persistence.py /app/backend/organism/live_engine.py
wc -l backend/infra/security.py backend/api/lifespan.py backend/organism/brain_persistence.py backend/organism/live_engine.py
```

Container counts must equal host counts. Confirms the rebuild + restart picked up wave 60-65.

### 4. Brain coherence

```
cat organism_brain/manifest.json | jq '{generation, total_trades, ml_is_trained, best_sharpe}'
```

Compare to V10-end snapshot.

### 5. Migration tree

```
./venv/bin/python scripts/ci/check_migrations.py
```

Expected: head = 20260503_000003 (wave-61 portfolio_history).

### 6. Wave-28 marker check on HEAD~16..HEAD

Acceptable: some legitimate fails on the docs-only waves (49, 58); document.

## Output

`artifacts/audit/v11_reports/track_z9_closure_regression.md` with:
- Per-marker presence table (~30 markers)
- Test pass count
- Container vs source counts
- Brain coherence delta
- Migration head
- "Closure regressions: N" + TL;DR

Quality bar: 0-2 findings.
