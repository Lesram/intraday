# Final Grand Audit Prompt - Phase 9D Tomorrow Readiness

Use this prompt verbatim for the final major audit before the Monday, May 11, 2026 paper-trading session.

---

You are an independent senior trading-platform auditor. Your job is to determine whether the Intra paper-trading platform is technically safe, evidence-honest, and ready to run the next paper session. Do not rubber-stamp prior work. Your output should make it hard for us to fool ourselves.

The user wants two things:

1. A boringly stable, technically coherent paper-trading platform.
2. A strategy research loop that generates trustworthy evidence so future work can focus on trading algorithms and profitability instead of debugging infrastructure.

Your audit must separate those two questions. A platform can be technically ready for paper trading while not yet having proven profitable strategy edge.

## Current Context To Verify, Not Assume

- Repo: `/Users/marselkei/VS/intra`
- Current intended branch: `codex/phase9d-portfolio-construction`
- Latest expected Phase 9D commit: `284fd53809ec0e84f3e04c54f681cb4da1a272f8`
- Draft PR expected: `https://github.com/Lesram/intraday/pull/8`
- Paper API container: `intra-api-1` on `localhost:8000`
- Paper DB container: `trading_platform_db_paper`
- Redis container: `intra-redis-1`
- Runtime expected after Phase 9D deploy:
  - `GIT_SHA=284fd53809ec0e84f3e04c54f681cb4da1a272f8`
  - `IMAGE_SHA=284fd53809ec0e84f3e04c54f681cb4da1a272f8`
  - `ORGANISM_PHASE9_SHADOW_ENGINES_ENABLED=true`
  - `ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_ENABLED=true`
  - `ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED=true`
  - `ORGANISM_EXPLORATION_ENABLED=false`
- Phase 9D is supposed to be evidence-only:
  - no live ranking changes,
  - no live sizing changes,
  - no order placement changes,
  - no gate changes,
  - no promotion-state mutation,
  - no runtime flag changes.
- Phase 9D's current correct verdict is expected to be:
  - `portfolio_authorized=false`
  - `promotion_authorized=false`
  - blockers include `not_enough_validated_strategies` and `not_enough_independent_strategy_families`

Treat every item above as a claim to verify.

## Operating Constraints

- Read-only against live/paper production data unless the user explicitly authorizes a fix.
- No DDL, no INSERT, no UPDATE, no DELETE against the paper DB.
- No strategy changes.
- No ranking, sizing, gate, order, promotion, or runtime flag changes.
- No deploy/restart unless all of these are true:
  - host and container SHA mismatch,
  - positions are flat,
  - live-open orders are zero,
  - user has explicitly asked for deployment or the audit prompt specifically says deployment is required.
- If positions are open or live-open orders exist, do not restart anything.
- Stale `status=failed` orders may be reported as hygiene issues, but they are not live-open broker orders unless evidence says otherwise.
- Use `./venv/bin/python`.
- Use `pytest --timeout=30`.
- Use `docker exec intra-api-1 ...` for container probes.
- Use `docker exec trading_platform_db_paper psql -U trading -d algotrading -c "..."` for DB read-only probes.

## Output Required

Write a single markdown report:

`docs/engineering/FINAL_GRAND_AUDIT_2026-05-10.md`

The report must include:

- Executive summary.
- Final readiness verdict:
  - `READY_FOR_PAPER_TOMORROW`
  - `READY_WITH_WARNINGS`
  - `NOT_READY`
- One-line answer to: "Are we technically safe to run paper trading tomorrow?"
- One-line answer to: "Have we proven a profitable strategy edge?"
- PASS / FAIL / UNKNOWN matrix for every audit section below.
- Evidence snippets: command, exit code, key output, file path, line reference where useful.
- Issues found, severity-tiered: Critical / High / Medium / Low.
- Required fixes before Monday open.
- Non-blocking follow-ups after Monday close.
- Clear statement of what Phase 9D will and will not do tomorrow.

Do not hide uncertainty. If evidence is missing, mark it UNKNOWN and explain what data is needed.

---

# Audit Section 1 - Git, Branch, PR, And Deploy Truth

Verify:

1. Current branch and HEAD.
2. PR #8 exists and contains only Phase 9D scope on top of the prior truth-audit fix branch.
3. Working tree is clean, or any dirty files are understood.
4. Host HEAD matches pushed branch HEAD.
5. Container `GIT_SHA` and `IMAGE_SHA` match host HEAD.
6. Container has the Phase 9D files copied into `/app`.
7. `/healthz` returns 200.
8. `/api/v1/health/deploy` returns 200 with admin auth and reports the expected SHA, migration head, build time, and runtime config hash.
9. Migration head in DB equals latest migration file.

Suggested commands:

```bash
git status --short --branch
git rev-parse HEAD
git log --oneline --decorate -5
git ls-remote --heads origin codex/phase9d-portfolio-construction
gh pr view 8 --json number,title,state,isDraft,baseRefName,headRefName,commits,url
docker exec intra-api-1 printenv GIT_SHA IMAGE_SHA BUILD_TIME ORGANISM_PHASE9_SHADOW_ENGINES_ENABLED ORGANISM_STRATEGY_EVIDENCE_TELEMETRY_ENABLED ORGANISM_CANDIDATE_FILTER_SHADOW_TELEMETRY_ENABLED ORGANISM_EXPLORATION_ENABLED
docker exec intra-api-1 wc -l /app/backend/organism/evidence/portfolio_construction.py /app/scripts/phase9d_portfolio_construction.py
curl -sS -o /tmp/intra_healthz.txt -w "%{http_code}\n" http://localhost:8000/healthz && cat /tmp/intra_healthz.txt
docker exec trading_platform_db_paper psql -U trading -d algotrading -c "SELECT version_num FROM alembic_version;"
ls backend/migrations/versions | sort | tail
```

PASS only if host, origin, and container point to the same intended Phase 9D commit, or if any mismatch is fully explained and non-operational.

---

# Audit Section 2 - Paper Book And Broker Safety

Verify:

1. Nonzero positions count.
2. Live-open order count, excluding terminal statuses including `failed`.
3. Any stale `failed` orders are documented separately.
4. No orphan DB positions inconsistent with broker state if a broker probe is available.
5. No open short exposure unless intentionally supported.

Suggested commands:

```bash
docker exec trading_platform_db_paper psql -U trading -d algotrading -c "SELECT count(*) AS nonzero_positions FROM positions WHERE COALESCE(qty,0) <> 0;"
docker exec trading_platform_db_paper psql -U trading -d algotrading -c "SELECT count(*) AS live_open_orders FROM orders WHERE status NOT IN ('filled','canceled','cancelled','rejected','expired','failed');"
docker exec trading_platform_db_paper psql -U trading -d algotrading -c "SELECT id, symbol, side, qty, status, submitted_at, created_at, updated_at, broker_order_id FROM orders WHERE status NOT IN ('filled','canceled','cancelled','rejected','expired') ORDER BY COALESCE(submitted_at, created_at) DESC LIMIT 30;"
```

PASS for readiness if positions are flat or intentionally expected, and live-open orders are zero. Stale `failed` rows are a hygiene warning, not a deploy blocker.

---

# Audit Section 3 - Runtime Config And Trading Invariants

Verify these invariants:

1. Exploration is disabled.
2. Phase 9 shadow telemetry is enabled.
3. Candidate and strategy evidence telemetry are enabled.
4. ORB current, EOD current, and mean-reversion current live flags remain false unless there is explicit replay evidence and user approval.
5. Learning mode still ignores ML for main-book ranking/confidence/sizing.
6. Fixed ATR-dollar risk sizing remains in guarded/learning mode.
7. EOD entry block and flatten remain active.
8. StrategyGovernor blocks unknown strategy IDs before live order submission.
9. StrategyGovernor blocks `shadow_only=true` before live order submission.
10. StrategyGovernor blocks Tier 0 / Tier 1 new strategies before live order submission.
11. `alpha_baseline` remains the only current live-enabled baseline policy.
12. Phase 9D does not mutate runtime flags or promotion state.

Suggested commands:

```bash
./venv/bin/python scripts/runtime/write_runtime_snapshot.py
jq '.resolved | {exploration_enabled, phase9_shadow_engines_enabled, strategy_evidence_telemetry_enabled, candidate_filter_shadow_telemetry_enabled, orb_live_enabled, eod_live_enabled, mean_reversion_live_enabled}' artifacts/resolved_config_snapshot.json
rg -n "ORGANISM_ORB_LIVE_ENABLED|ORGANISM_EOD_LIVE_ENABLED|MEAN_REVERSION_LIVE_ENABLED|ORGANISM_EXPLORATION_ENABLED|PHASE9_SHADOW" .env* docker-compose.paper.yml backend scripts docs
rg -n "StrategyGovernor|authorize_signal|shadow_only|insufficient_evidence_tier|unknown_strategy_id|alpha_baseline" backend/organism tests scripts docs
```

PASS only if code and runtime agree.

---

# Audit Section 4 - Phase 9D Implementation Audit

Audit the new Phase 9D implementation specifically.

Files:

- `backend/organism/evidence/portfolio_construction.py`
- `scripts/phase9d_portfolio_construction.py`
- `tests/test_phase9d_portfolio_construction.py`
- `docs/engineering/PHASE9D_PORTFOLIO_CONSTRUCTION_IMPLEMENTATION.md`
- `docs/engineering/STRATEGY_REBUILD_MASTER_ROADMAP_2026-05-09.md`
- `docs/architecture/mapss.md`

Verify:

1. No broker/order-service imports.
2. No DB writes.
3. No API route mutation.
4. No live-engine mutation.
5. No promotion-controller mutation.
6. No runtime env mutation.
7. No order placement functions are called.
8. Replay-only evidence is blocked from portfolio allocation.
9. One strategy family is blocked from portfolio allocation.
10. Under-sampled evidence is blocked.
11. Non-positive alpha is blocked.
12. Non-positive average R is blocked.
13. Profit factor below 1.20 is blocked.
14. Symbol/session concentration controls block.
15. Correlation controls block.
16. Weighted beta controls block.
17. Any "portfolio_authorized=true" output remains advisory and still says `promotion_authorized=false`.
18. Current real output correctly says no allocation.

Suggested commands:

```bash
rg -n "OrderService|submit_symbol_order|submit_order|broker|alpaca|positions|orders|UPDATE|INSERT|DELETE|PromotionController|os.environ|putenv|docker|compose" backend/organism/evidence/portfolio_construction.py scripts/phase9d_portfolio_construction.py
./venv/bin/python -m pytest -q tests/test_phase9d_portfolio_construction.py --timeout=30
./venv/bin/python scripts/phase9d_portfolio_construction.py
jq '{portfolio_authorized, promotion_authorized, live_behavior, portfolio_blockers, counts, controls}' artifacts/phase9d_portfolio_construction/phase9d_portfolio_summary.json
```

FAIL if Phase 9D can affect live behavior or if tests allow replay-only evidence to become allocation-eligible.

---

# Audit Section 5 - Phase 9A/9B/9C Evidence Pipeline

Verify the entire strategy evidence loop, not just Phase 9D:

1. `CandidateSignal` requires first-class identity.
2. Phase 9 shadow engines are side-effect-free.
3. Shadow engines do not submit orders.
4. Shadow engines are time-causal and do not consume future bars.
5. Phase 9 telemetry writes `signal_id`, `strategy_id`, `engine_version`, `created_at`, `evidence_tier`, `shadow_only`, `git_sha`, `runtime_config_hash`.
6. Phase 8 warehouse is idempotent and reconciles counts.
7. Phase 9 shadow evidence output does not authorize promotion.
8. Platform truth observer accurately reports `not_promotion_grade` until first-class forward Phase 9 events exist.
9. No old legacy telemetry is silently upgraded into fake first-class evidence.

Suggested commands:

```bash
./venv/bin/python scripts/phase8_evidence_warehouse.py
./venv/bin/python scripts/phase9_shadow_evidence.py
./venv/bin/python scripts/phase9d_portfolio_construction.py
./venv/bin/python scripts/ci/platform_truth_observer.py
jq '{sha, count_reconciliation, promotion_authorized, research}' artifacts/phase8_evidence_warehouse/warehouse_summary.json
jq '{counts, promotion_authorized, replay_candidates}' artifacts/phase9_shadow_evidence/phase9_shadow_summary.json
jq '{counts, portfolio_authorized, promotion_authorized, portfolio_blockers}' artifacts/phase9d_portfolio_construction/phase9d_portfolio_summary.json
tail -n 20 organism_brain/strategy_evidence_events.jsonl
```

PASS if the evidence chain is honest, even if it says "not enough data yet."

---

# Audit Section 6 - Test Trust And Required Gates

Run and report:

```bash
./venv/bin/python -m pytest -q tests/test_phase9_strategy_governance.py tests/test_phase9_shadow_evidence.py tests/test_phase9d_portfolio_construction.py --timeout=30
./venv/bin/python -m pytest -q tests/test_phase8_evidence_warehouse.py tests/test_phase8_postclose_runner.py tests/test_platform_truth_observer.py tests/test_phase9_research_engines.py tests/test_phase9_etf_intraday_momentum.py tests/test_phase9d_portfolio_construction.py --timeout=30
./venv/bin/python -m pytest -q tests/test_organism_live_engine.py tests/test_organism_engine_scenarios.py tests/test_multi_tick_state.py tests/test_safety_invariants.py tests/test_replay_simulator.py tests/test_self_evolution.py --timeout=30
./venv/bin/python -m ruff check backend/organism/evidence/portfolio_construction.py scripts/phase9d_portfolio_construction.py tests/test_phase9d_portfolio_construction.py
./venv/bin/python scripts/ci/forbid_marker_only_critical_high.py
./venv/bin/python scripts/ci/forbid_marker_only_full_corpus.py
./venv/bin/python scripts/ci/lint_ratchet.py
./venv/bin/python scripts/ci/verify_findings_ledger.py
./venv/bin/python scripts/ci/check_migrations.py
./venv/bin/python scripts/ci/mutation_smoke.py
INTRA_CHANGE_SCOPE=working-tree ./venv/bin/python scripts/ci/generate_artifacts.py full
INTRA_CHANGE_SCOPE=working-tree ./venv/bin/python scripts/ci/generate_audit_index.py
```

For each command, record:

- exit code,
- pass/fail count,
- warnings,
- whether warnings are new or known.

FAIL readiness for any failing safety, replay, security, migration, or mutation gate.

---

# Audit Section 7 - API, Security, And Integration Readiness

Run live probes:

```bash
./venv/bin/python scripts/ci/phase7_security_sanity.py
./venv/bin/python scripts/ci/phase7_integration_checkpoint.py
curl -sS -o /tmp/intra_healthz.txt -w "%{http_code}\n" http://localhost:8000/healthz && cat /tmp/intra_healthz.txt
```

Verify:

1. Admin login works.
2. User-role RBAC boundaries hold.
3. Debug endpoints are absent.
4. Logout blacklists token.
5. Deploy health endpoint is admin-only.
6. Strategy health endpoint exposes current strategy PnL.
7. Integration checkpoint returns `19 pass, 0 warn, 0 fail`.

PASS only if all probes pass.

---

# Audit Section 8 - Logs, Background Loops, And Tomorrow Capture Readiness

Verify:

1. Startup completed cleanly.
2. No repeated traceback/error loop.
3. Any errors are expected probe artifacts and not background failures.
4. Brain save loop is healthy.
5. Phase 9 shadow signal capture path is enabled.
6. Post-close evidence scripts can run manually.
7. Reports are generated in known paths.

Suggested commands:

```bash
docker logs --since=20m intra-api-1 2>&1 | rg -i "traceback|exception|critical|error|failed to" || true
docker logs --since=20m intra-api-1 2>&1 | tail -n 120
ls -lah artifacts/phase8_evidence_warehouse artifacts/phase9_shadow_evidence artifacts/phase9d_portfolio_construction
```

Classify log errors:

- expected security probe artifacts,
- transient startup warnings,
- real runtime failures,
- unknown.

FAIL readiness for unexplained recurring runtime errors.

---

# Audit Section 9 - Data Integrity And Brain State

Verify:

1. Audit log hash chain if `audit_logs` exists.
2. Brain manifest exists and is parseable.
3. Brain total trades and DB realized trades discrepancy is understood.
4. No corrupt latest brain files.
5. No uncontrolled snapshot pollution.
6. Data-integrity health endpoint returns a coherent explanation even if DB/brain scopes differ.

Suggested commands:

```bash
test -f organism_brain/manifest.json && jq '{generation, total_trades, saved_at, ml_is_trained, cumulative_pnl}' organism_brain/manifest.json
docker exec trading_platform_db_paper psql -U trading -d algotrading -c "SELECT count(*) FROM realized_trades;"
docker exec trading_platform_db_paper psql -U trading -d algotrading -c "SELECT to_regclass('public.audit_logs') AS audit_logs_table;"
docker exec trading_platform_db_paper psql -U trading -d algotrading -c "WITH chain AS (SELECT id, prev_hash, current_hash, ts, LAG(current_hash) OVER (ORDER BY id) AS expected_prev FROM audit_logs) SELECT count(*) AS broken FROM chain WHERE expected_prev IS NOT NULL AND prev_hash != expected_prev;" || true
ls -ld organism_brain.pre_* 2>/dev/null || true
```

PASS if data is coherent enough for paper trading and discrepancies are not silently ignored.

---

# Audit Section 10 - Old Implementation Regression Sweep

Do not only audit Phase 9D. Spot-check old implementation surfaces most likely to invalidate tomorrow's data:

1. JWT auth works behaviorally.
2. Settings admin endpoint requires auth.
3. Debug routes are absent.
4. Orders RBAC blocks user role.
5. Kill-switch envs are non-empty.
6. StrategyGovernor is mandatory in the live entry path.
7. Live engine trims future bars before ranking/sizing.
8. Legacy scanners are time-causal.
9. Phase 9 engines are time-causal.
10. Phase 8 warehouse clears generated tables before rebuilding.
11. Close-shorts maintenance route is dry-run by default and requires confirmation.
12. No current ORB/EOD/MR live promotion slipped in.

Suggested commands:

```bash
rg -n "_authorize_live_entry_order|trim_feature_frames_asof|StrategyGovernor|record_signals|clear_generated_tables|dry_run|CLOSE_SHORTS" backend tests scripts docs
./venv/bin/python -m pytest -q tests/test_phase9_strategy_governance.py tests/test_phase3_candidate_shadow_telemetry.py tests/test_phase8_evidence_warehouse.py tests/test_organism_maintenance_routes.py --timeout=30
docker exec intra-api-1 printenv ORGANISM_DRAWDOWN_KILL_PCT ORGANISM_MAX_DAILY_LOSS ORGANISM_MAX_NOTIONAL
```

FAIL if any old issue can skew tomorrow's paper data.

---

# Audit Section 11 - Strategy Reality Check For Tomorrow

Answer clearly:

1. What strategy is actually trading tomorrow?
2. What strategies are shadow-only tomorrow?
3. Will Phase 9D improve live PnL tomorrow?
4. What evidence should tomorrow collect?
5. What post-close reports must be run?
6. What decision can be made after one session, and what decision cannot?

Expected framing:

- Live trading remains the guarded `alpha_baseline`.
- Phase 9B/9C engines collect shadow evidence only.
- Phase 9D does not improve tomorrow's live trades directly.
- Phase 9D improves decision quality by preventing premature allocation/scaling.
- Profitability improvement comes after enough clean forward evidence, replay, and micro-paper gates.

If you disagree with this framing, explain why with code/runtime evidence.

---

# Audit Section 12 - Final Readiness Verdict

Return one of:

## READY_FOR_PAPER_TOMORROW

Use only if:

- runtime deploy truth is coherent,
- paper book is safe,
- security/integration probes pass,
- safety/replay tests pass,
- no live-order leaks,
- Phase 9 evidence capture is active,
- Phase 9D is advisory-only,
- no Critical/High blockers remain.

## READY_WITH_WARNINGS

Use if:

- no trading-safety blockers exist,
- warnings are known or non-blocking,
- strategy edge is unproven but evidence capture is honest.

## NOT_READY

Use if:

- host/container deploy mismatch is unexplained,
- positions/orders make restart unsafe,
- auth/security probes fail,
- strategy gates can leak live orders,
- telemetry/evidence capture is broken,
- recurring runtime errors exist,
- Phase 9D can mutate live behavior,
- migrations/data integrity are broken in a way that skews paper trading.

End with:

- "What must be fixed before Monday open."
- "What can wait until Monday post-close."
- "What we should measure tomorrow."
- "What success looks like after tomorrow's post-close report."

Begin.
