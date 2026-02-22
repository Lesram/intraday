# Independent Audit Prompt — Intra Trading Platform

**Commit:** `92a5c19` (main) | **Date:** 2026-02-21 | **Status:** Paper trading on Alpaca (~$106.8K equity, 15 positions)

---

## Objective

You are an independent auditor. Determine: **Is this platform ready to trade real money? What must be fixed first?**

Verify everything against actual code. Do not trust documentation at face value.

---

## Start Here — Read in Order

1. **`THIRD_PARTY_AUDIT_REPORT.md`** — Full inventory: 33 organism modules, 7 integrations, 191 frontend files, 7,155 tests, known issues, go-live checklist
2. **`docs/blueprints/EVOLVING_ORGANISM_BLUEPRINT.md`** — Authoritative design spec. Verify implementation matches this.
3. **`docs/PLATFORM_COMPLETE_GUIDE.md`** — 16-section reference (architecture, ML pipeline, order pipeline, risk, API, config)
4. **`README.md`** — Platform overview
5. **`docs/PLATFORM_STATUS.md`** — Current status tracker

Then audit the code across all areas below.

---

## Audit Areas

### 1. ALGORITHM LOGIC (Highest Priority)

Audit every file in `backend/organism/`. Key files and what to verify:

- **`live_engine.py`** (2,506 lines) — Core tick loop: regime → scan → size → order → exit → evolve → save. Verify 15% max-loss safety net (~line 698), position reconstruction fallback (~line 900), race conditions, silent failures.
- **`alpha_scanner.py`** (239) — 7-factor scoring. Verify weights sum to 1.0, NaN guards, MIN_COMPOSITE threshold.
- **`breakout_scanner.py`** (477) — 6-pattern detection. Check division-by-zero in ratios.
- **`kelly_sizer.py`** (390) — Half-Kelly sizing. Verify max 8% per position, 95% portfolio cap, $500 minimum (intraday), breakout bonus (1.5x/2.0x).
- **`adaptive_exits.py`** (470) — ATR exits, trailing (2x ATR activation), partial profit (40% at 2R), stress tightening (40%), 15% safety net.
- **`regime.py`** (647) — Regime detection + smoothing + KL divergence drift detection.
- **`ml_signal.py`** (590) — XGBoost ensemble. Verify no lookahead bias, confidence calibration, cold-start handling.
- **`ml_features.py`** (448) — **79 features. CRITICAL: verify ZERO lookahead bias in every feature.** Check rolling window boundaries, NaN handling.
- **`self_evolution.py`** (1,200) — Parameter evolution. Verify EMA smoothing, 20% max shift, min 8 trades. **NO dedicated tests — extra scrutiny.**
- **`promotion.py`** (412) — 6-stage pipeline. **NO dedicated tests — extra scrutiny.**
- **`brain_persistence.py`** (1,246) — Atomic saves, NaN/Inf sanitization, walk-forward gate, backup rotation.
- **`governance.py`** (250) — 8% drawdown kill, freeze/halt controls, rate limiting.

**Key questions:** Can a position be entered but never exited? Can Kelly exceed risk limits? Can evolution parameters explode? Can regime misclassification cause catastrophic behavior? Any race conditions between tick loop and background training?

### 2. ORDER EXECUTION & BROKER

Files: `backend/integrations/alpaca_broker.py` (881), `alpaca_stream.py` (705), `alpaca_market_data_stream.py` (697), `alpaca_outbox.py` (298), `backend/services/order_service.py` (1,701), `backend/models/order_integrity.py` (754)

Verify: Order state machine transitions, duplicate prevention (idempotency), partial fill handling, WebSocket reconnection (recent fix: `_cleanup_connection()`), order timeouts, fill reconciliation, race conditions.

### 3. RISK MANAGEMENT

Verify across `governance.py`, `adaptive_exits.py`, `kelly_sizer.py`, `sector_map.py`, `live_engine.py`:
- Does 8% drawdown kill actually halt trading? Recovery procedure?
- Is 15% safety net for ALL positions or only those without exit_levels?
- Sector limit (4/sector) enforced at order time or scan time?
- Correlation risk (AAPL + QQQ + MSFT = one tech bet)?
- Overnight gap risk handling?

### 4. STATE PERSISTENCE & RECOVERY

Verify in `brain_persistence.py` and `live_engine.py`: Atomic saves, restart state consistency, fallback ATR estimation (2% of entry), brain validation, cross-process safety.

### 5. SECURITY

Verify: JWT implementation, API endpoint authorization, SQL injection prevention, hardcoded secrets (search entire codebase), dependency CVEs (`requirements.txt`, `package.json`), WebSocket auth.

### 6. TEST COVERAGE

Backend: 7,021 passed (384 test files). Frontend: 134 passed (18 files). Verify critical path coverage (exits, safety net, Kelly, drawdown kill). The audit report identifies 13 organism modules without dedicated tests and ~49 frontend components without tests — assess risk of each gap.

### 7. INFRASTRUCTURE

`docker-compose.yml`, `Dockerfile`, `Dockerfile.production`, `.env.example`, `.github/workflows/`. Verify: non-root containers, secret management, DB pooling/timeouts, CI/CD gates, production Dockerfile readiness.

### 8. DATA INTEGRITY & PERFORMANCE

Verify: Price data validation, NaN feature propagation, equity curve accuracy (fills vs estimates), tick completion within 10s interval, memory leaks in ring buffer.

### 9. DOCUMENTATION & COMPLETENESS

Cross-reference `EVOLVING_ORGANISM_BLUEPRINT.md` against implementation. What % is implemented? What's missing? What's undocumented? Check API route docs match actual routes.

### 10. COMPLIANCE & AUDIT TRAIL

Verify: Trade logging (every order/fill/cancel with timestamps), decision reconstruction from telemetry, governance change logging, regulatory gaps.

---

## Output Format

### 1. Executive Summary
- Readiness grade (A-F), Go/No-Go for live trading, top 5 findings, top 5 strengths

### 2. Findings by Area
For each area: Status (Pass/Concerns/Fail), findings with **file paths and line numbers**, severity (Critical/High/Medium/Low), specific fix recommendations

### 3. Algorithm Deep Dive
- Composite scoring math correctness
- Kelly criterion correctness
- Exit parameter reasonableness
- Regime detection stability
- Evolution engine constraints
- Death spiral scenarios (losses → bad evolution → more losses)

### 4. Completeness vs Blueprint
- % of `EVOLVING_ORGANISM_BLUEPRINT.md` implemented
- Features documented but not implemented
- Features implemented but not documented

### 5. Go-Live Checklist
Mark each: Ready / Needs Work / Blocked / Not Started — Core logic, Risk management, Order execution, State persistence, Monitoring, Security, Tests, Documentation, Incident response, Rollback procedures

### 6. Prioritized Action Items
- **P0 (Blocker)**: Must fix before live trading
- **P1 (Critical)**: Must fix before scaling capital
- **P2 (Important)**: Fix within first month
- **P3 (Nice-to-have)**: Improvements

Each item: description, file(s), estimated effort, risk if not addressed

### 7. Architecture Recommendations
What to change, what to reconsider, what monitoring to add

---

## Ground Rules

1. **Be brutal.** A missed bug loses real money.
2. **Verify, don't trust.** The audit report was written by the dev team — cross-check every claim.
3. **Think adversarially.** For each module: what's the worst that could happen?
4. **Follow the money.** Maximum scrutiny on every code path that submits orders.
5. **Check the edges.** Market open/close, overnight gaps, API timeouts, WebSocket drops, state corruption.
6. **Reference specifics.** Every finding needs a file path and line number.

---

## Current State

| Parameter | Value |
|-----------|-------|
| Account | Alpaca paper, ~$106.8K equity |
| Positions | 15 (max allowed) |
| Universe | 30 symbols |
| Tick interval | 10s during market hours |
| Drawdown kill | 8% |
| Mode | Long-only |
| Sector limit | 4 per GICS sector |
| Tests | 7,021 backend + 134 frontend = 7,155 passing, 0 failures |
| Recent fixes | WebSocket concurrency, 15% safety net, position reconstruction, 78 test failures |

**Prior audits** (archived in `docs/archive/audits/`): Jan 18 (C-/NO-GO, 103 issues fixed), Jan 20 (B+), Jan 23 (passed), Feb 16 (blueprint compliance). Do NOT rely on these — audit independently.

*Begin now. The goal: what stands between this platform and safely trading real capital?*
