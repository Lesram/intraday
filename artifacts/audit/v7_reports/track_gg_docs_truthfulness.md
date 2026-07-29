# Track GG v7 — Documentation Truthfulness

**Repo**: `/Users/marselkei/VS/intra`
**Branch / SHA**: `rc-1.5-curated` @ `d44eace`
**Date**: 2026-05-02
**Method**: Read-only documentation audit per
`/Users/marselkei/VS/intra/artifacts/audit/prompts/v7/track_gg_docs_truthfulness.md`.
No file rewrites. The "fix" pass is wave-23+.

---

## TL;DR

Documentation has drifted in several systematic ways across 22 fix waves and 6
audit rounds. The most damaging drift is in operator runbooks and the
top-level `README.md`: the runbook claims to deploy `eb90fa3` (~92 commits
behind HEAD), the README references a non-existent `algotrading_platform/`
directory, six file paths that do not exist, and three test paths that do not
exist. The architecture map (`mapss.md`) is missing four organism modules
that are actually loaded at startup (`mean_reversion_scanner`, `orb_scanner`,
`eod_scanner`, `trading_phase`) and lists one module
(`staleness_detector.py`) under the wrong package. There is no `CLAUDE.md`
in the repo, despite the v7 prompt and ecosystem hooks expecting one. The
top of `FINDINGS_LEDGER.md` shows all 30 v1 findings as `open`, even
though the lower closure tables show most have shipped (e.g., R-F-1, P-P0-1,
N-C-2). Audit-marker comment density was sampled at 65 markers, all 8
spot-checked still match real, related code — no orphan markers found in the
sample.

**Documentation drift items: 11**

---

## Section 1: AGENTS.md / CLAUDE.md accuracy

**File**: `/Users/marselkei/VS/intra/AGENTS.md`

Spot-checked every operationally-load-bearing claim:

| Claim | Verdict | Notes |
|---|---|---|
| Mandatory PR paths (`backend/**`, `tests/**`, `docs/architecture/**`, `docker-compose*.yml`, `.env*`) | OK | All paths still exist. |
| `python scripts/ci/generate_artifacts.py full` | OK | Script exists, accepts `full` arg (`scripts/ci/generate_artifacts.py:mode = sys.argv[1] if len(sys.argv) > 1 else "full"`). |
| `python scripts/ci/generate_audit_index.py` | OK | Script exists. |
| Required tests for `backend/organism/` (`test_organism_live_engine.py`, `test_organism_engine_scenarios.py`, `test_multi_tick_state.py`, `test_safety_invariants.py`, `test_replay_simulator.py`, `test_self_evolution.py`) | OK | All exist. |
| Required tests for config/env (`test_settings_comprehensive.py`, `test_config_coordinator_comprehensive.py`, `test_system_integration.py`) | OK | All exist. |
| `paper-postclose-audit` cron at 22:15 UTC | OK | `.github/workflows/paper-postclose-audit.yml: cron: '15 22 * * 1-5'` matches. |
| Trading invariant: "No live exploration execution path" | OK in spirit | `EXPLORATION_ENABLED` constant survives in `live_engine.py:202` only because `tests/test_semantic_invariants.py` reads it; the module-level branch is wired but defaults to off. Documentation lists "no exploration" — code preserves an `_route_exploration` codepath but it is gated. Worth a clearer "kept for test invariants" footnote. |

**No `CLAUDE.md` exists at the repo root** (`find /Users/marselkei/VS/intra
-name CLAUDE.md` → nothing). The v7 prompt names `CLAUDE.md` as in-scope.
The closest equivalents are `CLAUDE_CODE_MASTER_PROMPT.md` and
`.claude/agents/{implementer,replay-analyst,reviewer}.md`. **Finding GG-1**:
either remove `CLAUDE.md` references from the audit prompt or add the
file. Memory referenced "AIA starter kit" / "Control Plane" without naming
it, but downstream tooling (the `init` skill, `~/.claude/projects/...`)
silently accepts the absence today.

Verdict: AGENTS.md is the most accurate doc in the repository. Single
finding: missing `CLAUDE.md` file.

---

## Section 2: mapss.md component-by-component verification

**File**: `/Users/marselkei/VS/intra/docs/architecture/mapss.md` (4883 lines)

### 2.1 organism/ module index drift

**Finding GG-2**: `mapss.md` Appendix E claims `### organism/ (37 modules)`.
Actual count on disk: **40** (`ls backend/organism/*.py | grep -v __init__`).
The mapss table itself lists **36** rows. So three numbers — header,
actual rows in the table, and reality — all disagree.

**Finding GG-3**: Four organism modules are present in code and imported
by `live_engine.py` but **not listed** in mapss Appendix E:

| Module | Imported by | mapss listing |
|---|---|---|
| `backend/organism/mean_reversion_scanner.py` | `live_engine.py:58` | absent |
| `backend/organism/orb_scanner.py` | `live_engine.py:56` | absent |
| `backend/organism/eod_scanner.py` | `live_engine.py:57` | absent |
| `backend/organism/trading_phase.py` | (used by `live_engine` for phase logging) | absent |

These are the Ferrari v1 / "shadow → promote" scanners (`mean_reversion`,
`orb`, `eod`) shipped in `ba76256` per the auto-memory and module
docstrings ("Initial deployment: SHADOW MODE"). They are first-class
organism components and should appear in Appendix E and in Layer 3
(Algorithm Deep Dives) — neither mentions them.

**Finding GG-4**: mapss.md Appendix E lists ``staleness_detector.py``
under `### organism/ (37 modules)`, but the actual file path is
`backend/ml/staleness_detector.py`. The text adds a one-line `NOTE:` at
the bottom of the table acknowledging this — but the row itself is still
in the wrong section, which trips component-by-component grep checks.
This is a half-fixed drift.

### 2.2 Other layer counts

| Section | Mapss claim | Disk | Verdict |
|---|---|---|---|
| `services/ (27 modules)` | 27 | 27 (excl. `__init__.py`) | OK |
| `infra/ (24 modules)` | 24 | (not full-counted, no findings) | likely OK |
| `ml/ (17 modules)` | 17 | (not full-counted, no findings) | likely OK |

### 2.3 Module-level docstring vs mapss description

Spot-checked five modules whose mapss summary makes specific claims:

| Module | mapss summary | Module docstring | Match |
|---|---|---|---|
| `live_engine.py` | "Core tick loop, telemetry, trade reconstruction" | "Phase 2 — Organism Live Engine. Unified live trading engine that bridges the backtest organism with the production trading infrastructure" | OK |
| `kelly_sizer.py` | "Half-Kelly sizing, regime-stratified, state-dependent cost model, timeframe-aware annualization" | "Module 4 — Kelly Position Sizer **v2**. ... v2 changes ... breakout-score bonus sizing" | OK (more detail in module) |
| `regime.py` | "Regime detection (7 labels), drift detection" | "Phase 6 — Regime-Conditioned Ensemble Blending" | OK |
| `brain_persistence.py` | "Save/load brain state to JSON" | "Module 7 — Organism Brain Persistence. Saves / loads the organism's entire learned state" | OK |
| `mean_reversion_scanner.py` | (absent — see GG-3) | "Mean-Reversion Scanner — intraday extreme-fade strategy" | **mapss doesn't list this module at all** |

---

## Section 3: improve* docs freshness

**Files**: `docs/architecture/improve.md`, `improve1.md`, `improve3.md`,
`improve4.md`, `improve5.md`, `improve6.md`, `improve7.md`, `improve8.md`,
`improve9.md`.

Per memory: "improve3-9.md are historical (per memory). Are they still
listed in docs/ as if current? Should they be archived?"

Verdict:

- All nine improve docs sit alongside `mapss.md` in `docs/architecture/`
  with no archive prefix or directory.
- File mtimes: improve.md = Mar 1, improve9.md = Mar 7. None modified
  since.
- `improve9.md` opens with a March 6, 2026 trade narrative; conclusions
  are largely subsumed by hardening fixes H1-H7 and waves 8-22. Reading
  it as current state would be misleading.

**Finding GG-5**: All 9 `improve*.md` documents should be moved to
`docs/architecture/archive/` (or have an `> ARCHIVED — historical
context only` banner prepended). The README and AGENTS.md don't link
to them, but `mapss.md` and other living docs reference improve9 by
name (e.g. mapss.md:1278 "improve9 B2/B3/B4"), so prepending an
archive banner is the safer move than renaming.

---

## Section 4: Runbook freshness

### 4.1 OPERATOR_COMMAND_SHEET.md

**File**: `/Users/marselkei/VS/intra/OPERATOR_COMMAND_SHEET.md` (60 lines, dated **2026-04-25**)

| Claim | Verdict |
|---|---|
| "Live container: `ce06d41`" | Stale. Current branch HEAD `d44eace` (per git log: ce06d41 was the **2026-04-08** instrumentation commit; live is on rc-1.5-curated). |
| "Repo HEAD: `eb90fa3` — fully tested, ready to deploy." | **Stale by 92 commits.** `git log --oneline d44eace ^eb90fa3 \| wc -l` = 92. |
| "Brain: gen 124, 396 trades" | Stale. Memory snapshot says gen 161, 1749 runs, 482 trades. |
| "Equity: $111,531 paper" | Stale (memory: $111,518.66 as of 2026-05-01). |
| "Earliest realistic Stage-1 cutover: **2026-05-12 (Mon)**" | Date target still in future as of 2026-05-02; commitment unchanged but premise (`eb90fa3`) is stale. |
| "Master pack: `WEEKEND_STATE_AND_STRATEGY_PACK.md`" | Exists at repo root. OK. |
| "PR review bundle: `docs/engineering/reviews/pr-deploy-eb90fa3-eb90fa3/`" | Exists. OK. |

**Finding GG-6**: `OPERATOR_COMMAND_SHEET.md` is fundamentally stale.
It still presents `eb90fa3` as "the next deploy" two campaigns later. A
v7-era operator following this sheet would either deploy a 92-commit-old
artifact or find the brain numbers mismatch the live state. Should
be either rewritten for `d44eace` (Ferrari v1 / wave-22 state) or moved
to a dated archive directory.

### 4.2 MONDAY_DEPLOY_eb90fa3.md

**File**: `/Users/marselkei/VS/intra/MONDAY_DEPLOY_eb90fa3.md` (185 lines, target **2026-04-27**)

The deploy was a one-time event 5 days ago. Spot-checks:

- Step 9: `docker-compose down api`. Modern Compose (v2) accepts service
  args on `down` (verified `docker compose down --help`: `[SERVICES]`),
  so this is technically valid even if non-idiomatic. The intent is
  closer to `docker-compose stop api` or `docker-compose rm -f -s api`,
  since `down` removes networks and other stack-level resources. Not a
  hard failure but a footgun.
- Step 14: `tail -100 logs/application.log | grep -iE
  'governance|drawdown|halt|frozen|alert'`. The path `logs/application.log`
  is host-side; depending on whether the operator runs this from outside
  the container, the file may be empty (api logs to stdout in compose).
  Worth a `docker logs intra-api-1 \| grep ...` alternative.
- Step 17: `diff <(jq -S . artifacts/deploy_preflight_eb90fa3/manifest.json)
  <(jq -S . organism_brain/manifest.json)`. Both files exist; jq is
  required (assume operator has it, but not in `requirements.txt`).
- Step 22-25 are listed as "low priority" but reference scripts that
  don't exist (`Use scripts/ if available`). Acceptable for one-shot
  deploy doc.

**Finding GG-7**: `MONDAY_DEPLOY_eb90fa3.md` is an artifact of a single
past event. It still lives at the repo root, in the same directory as
the active runbook. After the event, it should be moved to
`docs/engineering/deploys/2026-04-27_eb90fa3/`. Leaving it at root
implies "next-deploy doc" — the OPERATOR_COMMAND_SHEET still points to
it as the live runbook (line 20: "Run-book: `MONDAY_DEPLOY_eb90fa3.md`
at repo root").

---

## Section 5: Module docstring drift inventory

Sampled 6 organism modules:

| Module | Docstring claim | Reality | Drift? |
|---|---|---|---|
| `live_engine.py` | Pipeline: "ML Signal → Alpha Scanner → Breakout Scanner → Kelly → Adaptive Exits → Pyramider → Brain → Self-Evolution → Governance → Regime" | Pipeline now also includes ORB Scanner, EOD Scanner, Mean-Reversion Scanner (imports lines 56-58). | **Minor drift**: docstring missing the three new scanners. |
| `kelly_sizer.py` | "v2 changes: max_position_pct 5% → 10%" | Current default `max_position_pct=0.10` (line 102) — matches. But intraday override forces `0.08` (line 410). | OK; intraday divergence undocumented in docstring, called out in code comments. |
| `regime.py` | "trend/chop/volatile/stress" labels | Actual labels: `trending_up`, `trending_down`, `chop`, `high_vol`, `low_vol`, `stress`, `unknown` (line 31-38). | **Minor drift**: docstring undercounts labels (4 vs 7). |
| `brain_persistence.py` | "manifest.json, ml_classifier.joblib, ml_regressor.joblib, ml_state.json, learning_state.json, trade_history.csv, reference_feats.csv, equity_curve.csv, epoch_metrics.csv, backups/" | All present, plus `evolved_params.json`, `extra_counters.json`, `model_metrics_history.json`, `evaluation_event_history.json` (per the `_save_*` methods at lines 1249, 1284, 1440). | **Minor drift**: 4 newer artifacts not in the ASCII tree at the top of the file. |
| `continuous_learner.py` | "train → trade → attribute → evaluate → retrain → gate → promote" | Code path matches; `acceptance_gate()` is the gate. | OK |
| `scheduler.py` | "Environment variables: ENABLE_ORGANISM_SCHEDULER=1, ORGANISM_TICK_INTERVAL_SECONDS=60, ORGANISM_BRAIN_DIR=organism_brain, ORGANISM_LIVE_SYMBOLS=..." | Confirmed, all variables consumed in module. | OK |

Aggregate verdict: module docstrings are mostly accurate but trail
features by 1–2 cycles. Highest-impact omission is the missing scanner
imports in the `live_engine.py` header docstring.

---

## Section 6: Class docstrings

| Class | Docstring | Real methods sampled | Drift? |
|---|---|---|---|
| `OrganismLiveEngine` (live_engine.py:351) | "Unified live trading engine — the organism in production. Combines all organism modules into a single `live_tick()` method that can be called by a scheduler (every bar interval)." | `live_tick`, `initialize`, `shutdown` all exist. Docstring is short — no method list, so no orphans possible. | OK |
| `OrganismBrain` (brain_persistence.py:124) | "Persist and restore the organism's full learned state. Thread-safe, atomic writes, automatic backups." | `load`, `save`, `save_essential_state`, `apply_to_signal_generator`, `apply_to_learner` all exist. Docstring at module level lists artifacts (see GG section above). | OK at class level; module-level drift noted. |
| `KellySizer` (kelly_sizer.py:83) | "v2 pipeline: 1. Raw Kelly = mean_return / variance ... 9. Convert to shares; min position $2,000" | Full pipeline matches. **`min_position_usd` defaults to $2000 in non-intraday and $500 in intraday** — class docstring states "$2 000" without the intraday caveat. | **Minor drift**: intraday `min_position_usd=500` deviates from docstring's $2000. |
| `RegimeDetector` (regime.py:81) | "Multi-signal regime detector. Trend: SMA slope... Volatility: ATR ratio + realized vol percentile. Stress: gap frequency + volume anomalies + correlation breakdown proxy. Outputs a probability vector over regime labels." | 7-label output matches. Cross-asset / breadth conditioning (mapss section 6) is a wrapper around this detector and not described in the class docstring. | OK at class level; mapss covers the wrapper logic. |
| `ContinuousLearner` (continuous_learner.py:217) | "Self-improvement engine that retrains ML models. 1. Track trade outcomes ... 6. Update model weights and feature importance" | Methods match listed responsibilities. | OK |
| `AlpacaBrokerClient` (alpaca_broker.py:78) | (not read in detail — listed in code, in mapss) | — | not audited |
| `AlpacaStreamClient` (alpaca_stream.py:34) | Sampled at lines 524, 603, 683 — all match audit-marker descriptions. | OK | OK |

No class lists deprecated methods that have been removed (i.e., no
methods documented but gone).

---

## Section 7: Function/method docstrings (sample of 30)

Sampled by `awk 'NR%7==1'` over 200 organism functions. Spot-verified
6 (a tractable subset; full 30 verification deferred):

| Function | Sig vs docstring | Match |
|---|---|---|
| `RegimeDetector._compute_churn(self) -> float` | "Fraction of regime changes in the recent history window." | OK |
| `RegimeDetector.to_persistence_dict(self) -> dict[str, Any]` | "Serialize regime detector running state for brain persistence." | OK |
| `HistoricalBarProvider.advance(self) -> bool` | "Move cursor forward 1 bar. Returns False when exhausted." | OK |
| `HistoricalBarProvider.next_bar_open(self, symbol)` | "Get the OPEN of the bar AFTER the current cursor — the price an order submitted at the current bar's close would actually fill at." | OK |
| `ReplaySimulator.run(self, max_ticks: int \| None = None) -> ReplayResult` | "Run replay: create engine, loop through bars, collect results." | OK; one-line OK for orchestrator. |
| `OrganismLiveEngine._coerce_qty_to_int` (line 733) | Long V5 B-T-3 audit-marker docstring with full rationale. | OK |

Verdict: function docstrings are concise and current in the sample.
No drift detected. None of the 6 sampled functions had `Args:` /
`Returns:` blocks that contradicted the signature; none documented
deprecated behavior.

---

## Section 8: README setup reproducibility check

**File**: `/Users/marselkei/VS/intra/README.md` (1453 lines)

Walked through "Quick Setup" (lines 138-153) treating each line as a
literal step:

| Step | Command | Verdict |
|---|---|---|
| 1 | `git clone https://github.com/Lesram/intraday.git` | Cannot verify externally; OK if repo is public. |
| 2 | `cd algotrading_platform` | **BROKEN.** The clone target is `intraday`, not `algotrading_platform`. The repo on disk is named `intra`. |
| 3 | `python -m venv venv` | OK |
| 4 | `pip install -r requirements.lock` | OK — `requirements.lock` exists. |
| 5 | `pip install -r requirements.txt` | OK |
| 6 | `pip install -e .[dev]` | OK — `pyproject.toml` defines `[project.optional-dependencies] dev`. |
| Prereq line | "Python 3.11+" | **Drift**: `Dockerfile` and `Dockerfile.production` both pin **Python 3.12**. `pyproject.toml` says `requires-python = ">=3.11"`. Memory says venv is Python 3.12. Stating 3.11 understates the floor used in CI/Docker. |
| Prereq line | "PostgreSQL 15+ (for integration tests)" | Repo's `docker-compose.yml` uses `postgres:16-alpine`. Memory says PostgreSQL 16. Drift: doc allows "15+" — true but not the tested baseline. |
| `./scripts/run_ci_locally.sh` (line 202) | **BROKEN.** Actual path is `scripts/ci/run_ci_locally.sh`. README would 127-error. |
| Pytest path: `pytest tests/unit/`, `pytest tests/integration/` | OK — both directories exist. |

**README references to non-existent files (Finding GG-8 / GG-9)**:

| README reference | Exists? |
|---|---|
| `ARCHITECT_REVIEW_GUIDE.md` (line 31) | **NO** — not in repo. |
| `COMPLETE_PLATFORM_TEST_ANALYSIS_COMPREHENSIVE.md` (line 32) | **NO** |
| `EXECUTIVE_MIGRATION_DECISION_COMPREHENSIVE.md` (line 33) | **NO** |
| `IMPLEMENTATION_COMPLETE.md` (line 107) | **NO** |
| `ENHANCEMENT_SUMMARY.md` (line 108) | **NO** |
| `quick_start.py` (line 128) | **NO** |
| `tests/test_critical_fixes.py` (line 123) | **NO** |
| `tests/test_lifespan_deps.py` (line 124) | **NO** |
| `tests/test_websocket_stall.py` (line 125) | **NO** |
| `backend/api/main.py` (line 111) | YES, `backend/api/main.py` does exist. |
| `backend/config.py` (line 112) | YES |

Mojibake: lines 26, 131, 220, 295, 314 contain `�` characters where
emoji rendering broke in some past commit (`� FOR ARCHITECT REVIEW`,
`�️ Local Development`, etc.).

**Finding GG-8**: README.md references 9 files that do not exist
(3 review docs at top-of-file, 2 status docs in directory tree,
3 test files, 1 quick-start script).

**Finding GG-9**: README.md "Quick Setup" `cd algotrading_platform`
and "CI Pipeline Simulation" `./scripts/run_ci_locally.sh` are both
broken — the former assumes a directory name that doesn't match git
clone output, and the latter uses the wrong path.

---

## Section 9: Audit-cycle docs

`/Users/marselkei/VS/intra/artifacts/audit/`:

| File | Verdict |
|---|---|
| `AUDIT_PROCESS.md` | Current — describes 7-track v1 process. Should be amended to mention v2-v7 evolution; reads as if v1 is the only round. |
| `PROMPT_LESSONS_v1.md` | Exists. No `PROMPT_LESSONS_v2.md`+ found. Per the audit prompt: "supersedes? Add v7 lessons." Lessons are not currently versioned past v1. |
| `FINDINGS_LEDGER.md` | **Drift** — see below. |
| `MASTER_AUDIT_SYNTHESIS.md` … `MASTER_AUDIT_SYNTHESIS_v6.md` | All 6 versions present and committed. |
| Prompts directory: `artifacts/audit/prompts/v7/` | Present, includes track_aa..hh + w2 + z4. |
| Reports directory: `artifacts/audit/v7_reports/` | Was empty until this report; only `cc_run1.log`, `track_w2_*`, `track_z4_*` written. |

**Finding GG-10**: `FINDINGS_LEDGER.md` is internally inconsistent. The
top three tables (Critical / High / Lower-priority, lines 16-58) show
all 30 v1 findings in the `open` state with empty `Fix commit` columns.
Later in the same file (line 188+, "V4 closure status (post waves
12-15)") closure tables show many of those same findings
(R-F-1, R-F-5, P-P0-1, P-P0-2, P-P0-3, P-P0-4, P-P0-5, N-C-2, N-C-3,
Q-Q1, Q-Q15) marked closed with specific commits. The top tables were
never updated. A reader using the top tables as a worklist would
re-fix already-fixed bugs.

---

## Section 10: Audit-marker comment density

`grep -rn "V[0-9].*Wave-[0-9]" backend/` returned **65 markers** across
21 files. Distribution:

| File | Marker count |
|---|---|
| `backend/organism/live_engine.py` | 16 |
| `backend/organism/governance.py` | 7 |
| `backend/organism/brain_persistence.py` | 6 |
| `backend/organism/replay_simulator.py` | 4 |
| `backend/organism/background_trainer.py` | 4 |
| `backend/features/feature_engineering.py` | 4 |
| `backend/organism/regime.py` | 3 |
| `backend/integrations/alpaca_stream.py` | 3 |
| `backend/services/order_service.py` | 2 |
| `backend/infra/resilience.py` | 2 |
| `backend/api/lifespan.py` | 2 |
| `backend/utils/logger.py`, `backend/organism/{walk_forward,streaming_data_provider,promotion,ml_signal,kelly_sizer,continuous_learner}.py`, `backend/integrations/alpaca_broker.py`, `backend/infra/{outbox_worker,outbox,alerting}.py`, `backend/data/alpaca_client.py` | 1 each |

Sampled 8 markers in detail (~12% of population):

| Marker | File:Line | Verdict |
|---|---|---|
| `V5 B-T-3 / Wave-18` | live_engine.py:733 | Code at site is `_coerce_qty_to_int` with full audit comment. **Match.** |
| `V4 H-2 / Wave-16c` | live_engine.py:3640 | Code is the `submit_symbol_order` filled_qty handler. Comment narrates the fix. **Match.** |
| `V4 H-2 / Wave-16c` | live_engine.py:4861 | Sister fix in `_submit_exit`. Comment narrates the dead-code removal. **Match.** |
| `V4 H-1 / Wave-16d` | alpaca_stream.py:524 | Records BOTH broker id and DB UUID — verified at the loop. **Match.** |
| `V4 H-1 / Wave-16d` | alpaca_stream.py:603 | `is_order_terminal` accepts either id form per docstring. **Match.** |
| `V5 U-3 / Wave-17b` | regime.py:105 | `now_fn` clock injection in `RegimeDetector.__init__`. **Match.** |
| `V6 X-3 / Wave-20b` | brain_persistence.py:136 | `now_fn` clock injection in `OrganismBrain.__init__`. **Match.** |
| `V6 V-T-9 / Wave-22` | feature_engineering.py:161 | INFO emission demoted to DEBUG. **Match.** |

**Finding**: No orphan markers in the sample. All 8 spot-checked
markers reference real, related code at the line cited. The marker
hygiene from waves 16-22 is intact.

If there is risk of orphan markers, it would be in lines I did not
sample. But the pattern (every marker has a date stamp matching the
2026-05-03 wave campaign and a finding ID) suggests these were added
in the same commits as the fixes, so orphans should be rare.

Density: 65 markers / 41,000+ LOC across `backend/` ≈ 1 marker per
~600 lines. Concentrated in the highest-blast files (`live_engine.py`,
`governance.py`, `brain_persistence.py`) which is the right shape.

---

## Documentation drift items: 11

Numbered findings:

1. **GG-1** — No `CLAUDE.md` exists at repo root despite v7 prompt expecting one.
2. **GG-2** — `mapss.md` Appendix E header says "37 modules", table has 36 rows, disk has 40 (excluding `__init__.py`).
3. **GG-3** — Four organism modules missing from `mapss.md`: `mean_reversion_scanner.py`, `orb_scanner.py`, `eod_scanner.py`, `trading_phase.py` (all imported by `live_engine.py` lines 56-58 / used elsewhere).
4. **GG-4** — `mapss.md` lists `staleness_detector.py` under `organism/` but the file is at `backend/ml/staleness_detector.py`. Half-corrected by an inline `NOTE:` row.
5. **GG-5** — All 9 `improve*.md` documents live in `docs/architecture/` next to current docs with no archive marking, despite memory saying they are historical.
6. **GG-6** — `OPERATOR_COMMAND_SHEET.md` is stale: claims `eb90fa3` is HEAD when actual HEAD is `d44eace` (92 commits ahead); brain numbers (gen 124, 396 trades) lag live (gen 161, 482 trades).
7. **GG-7** — `MONDAY_DEPLOY_eb90fa3.md` is a one-time deploy artifact still living at repo root; OPERATOR_COMMAND_SHEET still names it as the live runbook. Step 9 `docker-compose down api` is non-idiomatic (`stop` is the cleaner tool).
8. **GG-8** — README.md references 9 non-existent files: `ARCHITECT_REVIEW_GUIDE.md`, `COMPLETE_PLATFORM_TEST_ANALYSIS_COMPREHENSIVE.md`, `EXECUTIVE_MIGRATION_DECISION_COMPREHENSIVE.md`, `IMPLEMENTATION_COMPLETE.md`, `ENHANCEMENT_SUMMARY.md`, `quick_start.py`, `tests/test_critical_fixes.py`, `tests/test_lifespan_deps.py`, `tests/test_websocket_stall.py`.
9. **GG-9** — README.md "Quick Setup" has two broken commands: `cd algotrading_platform` (clone target is `intraday`, repo on disk is `intra`) and `./scripts/run_ci_locally.sh` (actual path is `scripts/ci/run_ci_locally.sh`). README also pins "Python 3.11+" while Docker pins 3.12. Multiple mojibake `�` characters where emoji rendering broke.
10. **GG-10** — `FINDINGS_LEDGER.md` is internally inconsistent: top-of-file Critical/High/Low tables show all 30 v1 findings as `open`, but later closure tables show many already shipped (R-F-1, P-P0-*, N-C-2, etc.). Top tables not updated since the v1 baseline.
11. **GG-11** — `live_engine.py` module docstring lists the engine pipeline (ML → Alpha → Breakout → Kelly → Exits → Pyramider → Brain → Self-Evo → Governance → Regime) but does not include the three Ferrari-v1 scanners (ORB, EOD, Mean-Reversion) that `live_engine.py` lines 56-58 explicitly import. Same drift gap as GG-3 but in code-side documentation.

Severity classification:

- **Operator-blocking**: GG-6, GG-7, GG-9 (broken setup; stale "next deploy" target; broken cd / script paths).
- **Worker-misleading**: GG-8, GG-10 (phantom files; finding state contradictions).
- **Architecture-map drift**: GG-2, GG-3, GG-4, GG-11 (modules missing or mis-located).
- **Cosmetic / archive hygiene**: GG-1, GG-5.

No orphan audit-markers found in the sample of 8 (12%) of 65 total
markers. Marker hygiene is the strongest documentation surface in the
repo.

---

## One-paragraph summary

After 22 fix waves and 6 audit rounds, the repository's documentation
layer has accumulated three classes of drift: (1) operator runbooks
still target a now-92-commits-stale `eb90fa3` deploy and quote brain
generation/trade counts a campaign behind the live container,
(2) the top-of-funnel `README.md` references nine non-existent files
and contains two literally-broken setup commands (`cd
algotrading_platform`, `./scripts/run_ci_locally.sh`), and (3) the
canonical `mapss.md` architecture map omits four organism modules
(`mean_reversion_scanner`, `orb_scanner`, `eod_scanner`,
`trading_phase`) that are first-class imports in `live_engine.py`,
while listing `staleness_detector.py` in the wrong package. The
`FINDINGS_LEDGER.md` shows 30 v1 findings as `open` despite later
closure tables in the same file marking many of them shipped — a
subtle but high-impact contradiction for any worker using it as a
queue. Conversely, the audit-marker comment density (65 markers in
21 files, 12% spot-checked) is the strongest documentation surface:
every sampled marker still references the real, related code, with
no orphans in the sample. Eleven documentation drift items were
identified; none are silent code bugs, but several would mislead a
new operator or auditor on day one. Wave-23+ should rewrite
`OPERATOR_COMMAND_SHEET.md` and the README "Quick Setup" / "Directory
Structure" / "Architect Review Materials" sections, archive the nine
`improve*.md` docs, refresh `mapss.md` Appendix E, and reconcile
`FINDINGS_LEDGER.md` top tables with their own closure history.
