# Backend Codebase Audit — Intra Trading System
**Date:** 2026-06-08 · **Scope:** `backend/**` and associated infra (frontend excluded) · **Mode:** review + safe cleanup

---

## 1. Verdict at a glance

The backend is a **mature, heavily-iterated, safety-conscious** intraday equity system (~130k lines, 303 modules, 21 subpackages). It compiles, has real CI, an extensive test suite, and a visible discipline around trading invariants. It is **not** a broken or abandoned codebase.

Its real problems are **structural debt and accumulated cruft**, not rot:
- Two god-objects (`live_engine.py` at 387 KB / ~7,900 lines, and a 700-line lifespan) concentrate most of the risk.
- The repo root is buried under point-in-time reports, archives, and 9.5 GB of runtime artifacts.
- The trading edge itself is **unproven** — the system today is a well-guarded *framework* for an edge that the ML layer does not yet provide (measured signal correlation ≈ 0.056).

Bottom line: clean the surface, decompose the two monoliths, and treat "does it actually forecast profitably" as a separate, evidence-driven workstream — because the safety scaffolding is largely sound but the alpha is not yet demonstrated.

---

## 2. Cleanup status (what happened this session)

I inventoried the cruft and **attempted** the safe deletions, but the workspace mount is **write-but-no-delete** by design (the sandbox cannot `unlink` files on your folder; this session also ran unsupervised so the delete-approval prompt was unavailable). So nothing was deleted yet. Instead I produced a vetted script:

> **`scripts/cleanup_safe.sh`** — removes only untracked, regenerable artifacts (caches, stale zips, the 42 MB `audit_trail.log`, empty `.db` files). No source, no tracked files. Run `bash scripts/cleanup_safe.sh --dry-run` first.

### Repo is 9.5 GB. Where it lives:
| Item | Size | Tracked? | Recommendation |
|---|---|---|---|
| `organism_brain_archive/` | **5.5 GB** | no | Rolling daily 256 MB brain snapshots (~21 days). **Not a duplicate** — it's live model-state history. Prune to last 7 days (script section A), don't blanket-delete. |
| `venv/` | 2.5 GB | no | Rebuildable from `requirements.lock`. Your call. |
| `logs/` | 383 MB | no | Rotate/trim. |
| `organism_brain/` | 258 MB | no | **Active** brain state — keep. |
| `audit_trail.log` | 42 MB | no | Safe delete. |
| caches (`.mypy_cache` 113 MB + 3,133 `__pycache__` + `.pytest_cache`/`.ruff_cache`/`.hypothesis`) | ~120 MB | no | Safe delete (regenerate). |
| `backend.zip`/`tests.zip`/`organism_brain.zip` + forensic snapshot | ~8 MB | no | Stale snapshots of dirs that still exist. Safe delete. |

### Repo-root document sprawl (tracked — needs your sign-off to move)
**36 loose `.md` files** at root. ~6 are real project docs (`README.md`, `AGENTS.md`, `AUDIT_PROMPT.md`, `CLAUDE_CODE_MASTER_PROMPT.md`, `OPERATOR_COMMAND_SHEET.md`). The other ~30 are **point-in-time status reports** — `WEEKEND_SPRINT_V{1,2,3}_FINAL_REPORT.md`, `MONDAY_DEPLOY_*.md`, `FRIDAY_POSTCLOSE_REVIEW.md`, `*_AUDIT.md`, `NEXT_14_DAY_EXECUTION_PLAN.md`, etc. Recommendation: **move** (not delete) these to `docs/archive/` on a branch, so root holds only living docs. They're git-tracked, so the move is fully reversible — I left this for your approval rather than rewriting history unilaterally.

---

## 3. Architecture & structure

### 3.1 The two monoliths (highest structural risk)
- **`backend/organism/live_engine.py` — 387 KB, ~7,900 lines, one `OrganismLiveEngine` class with 65+ methods and ~66 internal imports** (the most-coupled file in the repo, plus lazy imports inside dozens of methods). It owns *everything*: signal generation, entry gating, sizing, order submission, position management, pyramiding, exits, learning, evolution, persistence, diagnostics, and data fetching. This is the single biggest impediment to changing trading behavior safely — every scanner is a hard dependency, and nothing in it can be unit-tested in isolation.
  - **Suggested split seams:** `EntryOrchestrator` (scanner→gate→size), `ExitOrchestrator` (exit signals + level mgmt), `LearningManager` (retrain/evolution), `BrainPersistenceController` (state save/load/telemetry), `FeatureFeeder` (bar/feature fetch). Target ≈5 files of ~80 KB.
- **`backend/api/lifespan.py` — ~700 lines** booting 12+ subsystems sequentially with no abstraction. One subsystem's failure can cascade; there's already an env-var hack (`UVICORN_RELOAD_ACTIVE`) working around fork/reload. **Fix:** a `SubsystemRegistry` of `start_*/stop_*` units, each feature-flaggable.

### 3.2 Coupling hotspots
- **`backend/infra/` is a kitchen sink** (~26 inbound imports): DB sessionmaker, repositories, alerting, outbox, guardrails, security/token-blacklist, cache, observability all in one package. A change here ripples everywhere. **Fix:** split into `persistence/`, `messaging/` (outbox+alerting), `auth/`, `observability/`.
- **API routes reach into engine internals** — `routes/orders.py`, `routes/models.py`, `routes/signals.py` import `order_service`/`model_manager`/`risk_manager` directly and call private-ish methods. Business logic leaks into the HTTP layer. **Fix:** a thin `TradingFacade` service the routes call.
- **`organism` vs `strategies` vs `ml`** overlap in responsibility (signal logic exists in all three). The `organism` brain is the live path; `strategies/` and much of `ml/` are partially shadow/secondary. Worth an explicit ownership decision.

---

## 4. Dead code & duplication (the "disinfect" pass)

Conservative findings (dynamic-import caveats noted):
- **Empty/orphaned packages — safe to remove:** `backend/brokers/` (empty `__init__`, 0 real importers), `backend/optimization/` (empty), `backend/deployment/__init__.py` (only `validator.py` has any use).
- **Deprecated compat shims — migrate then delete:**
  - `backend/database.py` — header literally says *"DEPRECATED: retained for backward compatibility only."* 2 importers (a test + one script).
  - `backend/database/repositories/` — **test-only shims** (the `__init__` docstring says so; only 2 auto-generated tests import it, vs **61** importers of the real `backend/infra/repositories/`). *Note: an earlier pass called this "duplicate query logic causing divergence" — that's overstated. It's a thin patch surface for tests, not a competing production implementation.*
- **`*_v2` files:** `organism/engines/orb_sip_v2.py` looks like an abandoned experiment but is **active** (imported by phase-9 evidence readiness). **Keep.**
- **Dead imports:** not exhaustively linted this pass. Run `ruff check backend --select F401 --statistics` for the count (config already present in `pyproject.toml`).

---

## 5. Trading correctness & risk (most important)

Read `AGENTS.md` "Trading invariants" first — the system is genuinely built around them, and **most are enforced in code**.

### 5.1 Safety-invariant enforcement — verified
| Invariant | Status |
|---|---|
| No live exploration execution path | ✅ Enforced (exploration candidates logged, never submitted) |
| Learning mode ignores ML for ranking/confidence | ✅ Enforced (`kelly_sizer` sorts by breakout/heuristic; `DROP_ML_FROM_GATE=True`) |
| Learning mode uses fixed ATR-dollar risk, not Kelly | ✅ Enforced (0.10% equity + 5% notional caps) |
| Alpha & breakout share hard safety gates | ✅ Enforced (both call `_passes_entry_gates()`) |
| EOD entry block + flatten active | ✅ Enforced (15:45 block, 15:58 flatten, pending-entry cancel) |
| **Evolution params frozen until ≥300 post-reset trades** | ✅ **Enforced** — at the orchestration layer (`background_trainer.py:201/640/663`, `live_engine.py:1298/1713/7104`). *An earlier pass flagged this as NOT enforced because it only read `self_evolution.py` (where `min_trades=8` is a different, lower-level "enough data to adapt" gate). I verified the 300-trade freeze directly — it is wired in.* |

### 5.2 The real concern: there is no demonstrated edge yet
This is the finding that matters most for "make a profit":
- ML signal correlation with realized direction is ≈ **0.056** (noise), and on resolved trades `corr(confidence, actual) ≈ -0.11` (mildly *anti*-predictive). ML currently functions as a **veto** ("don't take clearly-wrong-direction trades"), not as alpha. The earlier `-$108` cumulative loss traced to 132/182 trades that passed on ML's uncalibrated self-confidence — since patched via `DROP_ML_FROM_GATE`.
- Remaining signal sources (alpha composite, ORB, EOD, mean-reversion breakout) are **heuristic** with no documented out-of-sample backtested edge. The system is paper-only.
- **Implication:** decomposing the engine and cleaning the repo will make the system *maintainable*, but profitability requires a separate, evidence-first effort: an honest walk-forward harness, a real edge hypothesis, and promotion gates tied to out-of-sample expectancy — not to trade count.

### 5.3 Correctness issues worth fixing (impact-ranked)
1. **Model-acceptance gate compares different holdout windows** (`continuous_learner.py` ~432–456): a new model is scored on *its own* recent holdout and compared to the old model's metrics from a *different* period. This lets models trained in "easy" regimes get promoted. **This is the most dangerous methodological leak** — it's how "great in validation, loses live" happens. Fix: score both models on one identical recent holdout before promotion. *(Claim originates in `DATA_LEAKAGE_AUDIT.md`; consistent with the code.)*
2. **Breakout Kelly bonus has no upside cap** (`kelly_sizer.py` ~468): a 0.85+ breakout score can push half-Kelly toward full-Kelly. Bounded by the 10% per-position cap, but still a sizing spike. Cap the bonus.
3. **Pyramid adds re-check only the circuit-breaker**, not fitness/sector/liquidity gates (`live_engine.py` ~3693). Low probability, but a degraded symbol can still receive adds.
4. **SPY cross-asset alignment is assumed, not asserted** (`ml_features.py` ~219): assumes SPY's last bar timestamp matches the symbol's. One stale feed silently corrupts cross-asset features. Add a timestamp-delta assert.

### 5.4 Data leakage — broadly clean
Spot-checks confirm: no `shift(-N)`, no `center=True` rolling, temporal train/val split per symbol, tree models (scale-invariant, no scaler leakage). The leakage risk that remains is **methodological** (5.3 #1), not feature look-ahead. Verify against `DATA_LEAKAGE_AUDIT.md` whenever that file changes — treat it as a living contract, not a one-time pass.

---

## 6. Health, build & config

- **Compiles:** `py_compile` across `backend/` is clean; both entry points (`main.py`, `backend/api/main.py`) are valid. Python ≥3.11 (3.12 in Docker).
- **CI exists** (correcting an earlier mis-claim): `.github/workflows/` has **8** pipelines — `ci.yml`, `pr-verify.yml`, `nightly.yml`, `security-scan.yml`, `canary-deployment.yml`, `staging.yml`, `paper-postclose-audit.yml`, `codex-review-trigger.yml`. CI is *not* missing.
- **Tests:** large and maintained — ~250 test files, ~1,800 test functions, markers configured (`unit/integration/live/evolution/regression/...`), uses hypothesis + testcontainers. ~14 files carry `skip`/`xfail`/TODO — worth a triage but not abandonment. Verbose dated test names (`test_apr10_patch_f3_*`) reflect many fix waves.
- **Dependencies:** `requirements.txt` (loose) + `requirements.lock` (pinned) + `requirements-dev.txt` + `pyproject.toml` are broadly consistent; Docker builds from the lock. Risk: nothing forces lock freshness. `requirements-dev.txt` duplicates some tools.
- **Config sprawl (real):** `.env`, `.env.example` (~115 vars, 309 lines), `.env.production.template`, `.env.preopen_backup_*`, plus `backend/config/base_settings.py` (**64 KB**, 100+ fields) alongside `config.py`/`coordinator.py`/`unified.py`. Known env aliasing to reconcile: `ALPACA_API_KEY` vs `ALPACA_API_KEY_ID`, `JWT_SECRET_KEY` vs `SECURITY_JWT_SECRET`, and a documented `APP_LOG_LEVEL` vs `LOG_LEVEL` mismatch. *(Correcting an earlier mis-claim: root `config/` and `configs/` both exist with distinct purposes — `config/` holds prometheus/otel/slo/postgres configs, `configs/` holds optuna/strategy payloads. Not redundant.)*
- **Deployment:** 3 docker-compose variants (dev/paper/production) + 2 Dockerfiles + `k8s/`. Coherent but lacks a documented "which is canonical."

---

## 7. Note on audit reliability

I ran four parallel reviewers and then **independently re-verified** the highest-stakes claims. Three were wrong or overstated and are corrected above: (a) the 300-trade evolution freeze *is* enforced; (b) `database/repositories` is a test shim, not divergent production logic; (c) CI and the `config/`/`configs/` dirs *do* exist. Flagging this so you weight the report's claims appropriately — where I wrote "verified," I read the code myself; where I cite a `*.md` audit file, treat it as secondary until re-checked.

---

## 8. Recommended sequence

1. **Hygiene (low risk, do now):** run `scripts/cleanup_safe.sh`; prune `organism_brain_archive` to 7 days; move the ~30 dated root reports to `docs/archive/`. Reclaims ~4 GB, makes the repo legible.
2. **Decompose the lifespan** into a subsystem registry (smaller, safer than the engine, high readability payoff).
3. **Carve `EntryOrchestrator` + `ExitOrchestrator` out of `live_engine.py`** behind characterization tests — the keystone refactor.
4. **Split `infra/`** kitchen sink; introduce a `TradingFacade` so routes stop reaching into internals.
5. **Retire the deprecated shims** (`database.py`, `database/repositories`, empty packages) once imports are migrated.
6. **Edge workstream (separate track):** fix the same-holdout promotion gate (5.3 #1), then build an honest walk-forward expectancy harness before any real-money discussion. The framework is safe; the alpha is unproven — keep those two questions separate.
