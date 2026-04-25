# Deploy Verification — Full Patch F

**Date**: 2026-04-10 06:23–06:26 UTC
**Target HEAD**: `7d36b61` (F4/4 — structural closure tip)
**Verdict**: DEPLOYED AND VERIFIED

## Sections

### 1. Verdict
DEPLOYED AND VERIFIED

### 2. Source State
- HEAD: `7d36b61f7802764f90fbb4a415ddf252f400fde1`
- Branch: `main`, backend/ clean

### 3. Pre-Deploy
- Container: 22h uptime since F-lite deploy, healthy, RestartCount=0
- Brain: gen=36, trades=208, pnl=-496.61, best_sharpe=3.4363, ml_is_trained=true, feature_count=79
- Alpaca: ACTIVE, equity=$111,570.20, positions flat, market closed

### 4. Deployment
- `docker compose -f docker-compose.paper.yml up -d --build api`
- Start 06:23:49Z, build 06:24:59Z, healthy 06:25:14Z (85s total)
- Redis/postgres untouched

### 5. Post-Deploy Boot
- API healthy, container healthy, RestartCount=0
- Brain loaded: gen=36, runs=211, trades=208
- Trading phase: production_frozen (208/300 to evolution freeze exit)
- PREFLIGHT: 16/18 (0 critical, 2 warnings)
- Scheduler loop started
- Zero ERROR/CRITICAL in boot log

### 6. Patch Signatures (15/15 PRESENT)
All verified via docker exec grep. See running_container_code_verification.txt.

### 7. Force-Save
- HTTP 200
- success=true, forced=true
- gen=36, trades=208, pnl=-496.61, best_sharpe=3.4363
- ml_is_trained=true, feature_count=79, tick=10628

### 8. Post Force-Save Artifacts (13/14 PRESENT)
All 13 essential files freshly written at 06:25:54Z.
transfer_knowledge.json MISSING (known non-blocking gap in force_save_brain).

### 9. Manifest Consistency
- generation: 36 == 36 ✅
- total_trades: 208 == 208 ✅
- cumulative_pnl: -496.61 == -496.61 ✅
- best_sharpe: 3.4363 == 3.4363 ✅
- ml_is_trained: true ✅
- feature_count: 79 ✅

### 10. Structural Closure
Full Patch F (F1-F4 + F-lite + D + E + A + B + C) is now live.
Structural persistence work moves to observation-only pending two
clean sessions.

### 11. Hard-Stop Checks: 10/10 PASS
See hard_stop_checks.md.

### 12. Files Produced
See deploy_verification_full_patch_f_bundle/ (20 artifacts).
