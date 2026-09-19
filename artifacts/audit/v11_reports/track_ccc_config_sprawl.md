# Track CCC v11 — Configuration Sprawl

**Repo:** `/Users/marselkei/VS/intra`
**Branch:** `rc-1.5-curated`
**HEAD:** `3778344` (note: prompt referenced `11c2275`; current HEAD differs)
**Date:** 2026-05-02
**Method:** read-only grep of `backend/`, `.env*`, `docker-compose*.yml`, `docker exec intra-api-1 env`

---

## Inventory snapshot

| Source                               | Count |
| ------------------------------------ | ----- |
| `os.getenv` / `os.environ` refs in `backend/`            | **202** distinct env-var names |
| `.env` (live, gitignored)            | **86** assignments |
| `.env.example` (committed template)  | ~75 active lines (mostly commented) |
| `.env.production.template` (committed) | placeholder |
| `docker-compose.yml` (dev)           | 53 explicit env wires |
| `docker-compose.paper.yml` (running) | 31 explicit env wires + `env_file: .env` |
| `docker-compose.production.yml`      | 40 explicit env wires |
| `backend/config/settings.py`         | 828 lines |
| `backend/config/base_settings.py`    | 1745 lines |
| `backend/config/config.py`           | 187 lines |
| `backend/config/unified.py`          | 230 lines |
| `backend/config/coordinator.py`      | 263 lines |

Five overlapping config modules totaling ~3.3k LoC. There is no single canonical schema; each module loads env vars independently.

---

## Findings

### CCC-1 — Production startup-validator audits the wrong env-var names ("phantom validator")

**Severity:** P1 — security-critical, false sense of safety.

`backend/infra/production.py:316-388` defines `ConfigValidator` with these required keys:

```python
REQUIRED_VARS = ["DATABASE_URL", "JWT_SECRET"]
REQUIRED_PRODUCTION_VARS = ["ALPACA_API_KEY", "ALPACA_SECRET_KEY"]
```

But the **actual** canonical names the running code reads are:

| Validator checks       | Code actually reads                                        |
| ---------------------- | ---------------------------------------------------------- |
| `JWT_SECRET`           | `SECURITY_JWT_SECRET` (`backend/infra/security.py:382, 447, 499, 567`) and `JWT_SECRET_KEY` (`backend/config/base_settings.py:914`) |
| `ALPACA_API_KEY`       | `ALPACA_API_KEY_ID` (preferred everywhere — `lifespan.py:584`, `alpaca_data.py:39`, `alpaca_stream.py:48`, `alpaca_broker.py:90`); `ALPACA_API_KEY` is only a fallback |
| `ALPACA_SECRET_KEY`    | `ALPACA_API_SECRET_KEY` (preferred); `ALPACA_SECRET_KEY` is only a fallback |

Compounding: `_check_database_url()` warns if `DATABASE_URL` does not start with `postgresql://` / `postgres://`. The actual `.env` value is `postgresql+asyncpg://trading:trading_password@…` — the validator emits a false-positive warning every startup, training operators to ignore it.

**Concrete failure mode:** an operator could deploy production with `JWT_SECRET` unset (only `SECURITY_JWT_SECRET` set), the validator passes, and JWT signing still works because `security.py` falls back to `SECURITY_JWT_SECRET`. Conversely, if the operator sets *only* `JWT_SECRET` and not `JWT_SECRET_KEY` / `SECURITY_JWT_SECRET`, the validator passes but the running code raises `"JWT secret key is required"` at first request. Validator and runtime do not agree on what "configured" means.

**Files:** `/Users/marselkei/VS/intra/backend/infra/production.py:316-388`, `/Users/marselkei/VS/intra/backend/infra/security.py:382-567`, `/Users/marselkei/VS/intra/backend/config/base_settings.py:101-132`.

---

### CCC-2 — Safety-critical risk caps have three different "defaults" across compose / env / code

**Severity:** P0 — kill-switch / loss-cap divergence.

| Variable                     | code default                                                | dev compose             | paper compose | prod compose                | live `.env` |
| ---------------------------- | ----------------------------------------------------------- | ----------------------- | ------------- | --------------------------- | ----------- |
| `ORGANISM_DRAWDOWN_KILL_PCT` | `0.05` (`backend/organism/governance.py:51`)                | `0.05` (compose:81)     | not wired     | **`0.08`** (compose:62)     | `0.20`      |
| `ORGANISM_MAX_DAILY_LOSS`    | `0.0` ⇒ disabled (`backend/organism/live_engine.py:221`)    | not wired               | not wired     | `50` (USD/day)              | `5500`      |
| `ORGANISM_MAX_NOTIONAL`      | `0.0` ⇒ disabled (`backend/organism/live_engine.py:220`)    | not wired               | not wired     | `200` (per-trade USD)       | `2000`      |
| `DAILY_NOTIONAL_CAP_USD`     | `10000` (`backend/infra/guardrails.py:114`)                 | not wired               | not wired     | not wired                   | `10000`     |

Implications:

1. **Kill switch differs by 4×** between hard-coded code default (5%), prod-compose fallback (8%), and live `.env` (20%). If `.env` is missing in production, the operator believes drawdown-kill is at 8% when the code says 5%. In paper, neither compose passes the var, so the value comes solely from `env_file: .env`; if `.env` is absent the kill drops silently to 5%. Three sources of truth for one safety bound.
2. **`ORGANISM_MAX_DAILY_LOSS` and `ORGANISM_MAX_NOTIONAL` are *off* by code default** (`0` = disabled). Production compose adds `$50/$200` defaults; paper compose adds nothing. The live `.env` runs at `$5500/$2000` — 110× / 10× the production fallback. If a deployment forgets to source `.env`, the per-trade and daily-loss caps simply do not exist (code treats `0.0` as "feature disabled" — `live_engine.py` comment: "0 = disabled").
3. The recent commit `eb90fa3` ("align docker-compose.yml drawdown-kill fallback with code default") closed this gap *only* in `docker-compose.yml`. Production compose (`0.08`) was not touched.

**Files:** `/Users/marselkei/VS/intra/backend/organism/governance.py:51-135`, `/Users/marselkei/VS/intra/backend/organism/live_engine.py:220-221`, `/Users/marselkei/VS/intra/backend/infra/guardrails.py:114`, all three `docker-compose*.yml`, `.env`.

---

### CCC-3 — Alpaca credential name has 4 spellings; operators can set the "wrong" one and silently pass

**Severity:** P2 — operational footgun.

The codebase accepts up to four names for the Alpaca API key and three for the secret, layered as fallbacks:

```python
# backend/integrations/alpaca_data.py:39
self.api_key = os.getenv("ALPACA_API_KEY_ID") or os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
# backend/integrations/alpaca_stream.py:48 — identical chain
# backend/integrations/alpaca_broker.py:90 — identical chain
# backend/api/lifespan.py:584 — only first two
# backend/organism/replay_simulator.py:628 — only first two
# backend/organism/market_scanner.py:95 — only first two
# backend/organism/training.py:277 — only first two
# backend/infra/production.py:322 — REQUIRED list contains ONLY "ALPACA_API_KEY" (legacy)
```

Compose drift compounds it:

- `docker-compose.yml`        wires both `ALPACA_API_KEY` and `ALPACA_API_KEY_ID` (with dummy fallback)
- `docker-compose.paper.yml`  wires only `ALPACA_API_KEY_ID` (relies on `.env`)
- `docker-compose.production.yml` wires `ALPACA_API_KEY_ID:-${ALPACA_API_KEY}` (id-with-key-fallback)
- `.env.example` shows the legacy `ALPACA_API_KEY` placeholder; `.env` uses canonical `ALPACA_API_KEY_ID`

An operator following `.env.example` who sets `ALPACA_API_KEY` will get partial functionality: integrations modules find it (chain falls through), but `replay_simulator`, `market_scanner`, `training`, and `lifespan` only check `ALPACA_API_KEY_ID` first, then `ALPACA_API_KEY` — they'll work too. **However**, the Stage-1 production-validator (CCC-1) only requires the legacy `ALPACA_API_KEY`. So it's possible to satisfy the validator with the legacy name and pass, while the canonical name remains unset. No single source of truth; no test asserts that exactly one canonical name is required.

**Files:** `backend/integrations/alpaca_*.py`, `backend/organism/{replay_simulator,market_scanner,training}.py`, `backend/api/lifespan.py:584-642`, `backend/infra/production.py:321-324`, all compose files, `.env.example:272`.

---

### CCC-4 — Configuration documentation is 3 months stale; running container has 20+ ORGANISM_* vars not documented anywhere

**Severity:** P2 — knowledge debt.

- `docs/setup/ENVIRONMENT.md` last modified **2026-02-18** (272 lines).
  - `grep -c "ORGANISM_\|MR_\|FERRARI\|DROP_ML\|MAX_NOTIONAL\|MAX_DAILY_LOSS"` → **0 matches**.
  - Documents zero of the organism-engine env vars.
- `.env.example` mentions five `ORGANISM_*` vars (commented out) and zero of: `ORGANISM_ALPHA_TOP_N`, `ORGANISM_DROP_ML_FROM_GATE`, `ORGANISM_MAX_DAILY_LOSS`, `ORGANISM_MAX_NOTIONAL`, `ORGANISM_HALT_TRADING`, `ORGANISM_FREEZE_ADAPTATION`, `ORGANISM_REPLAY_MODE`, `ORGANISM_TRAINING_REGIME_BOOST`, `ORGANISM_TRAINING_SCORE_ALPHA`, `ORGANISM_DRIFT_CHECK_INTERVAL_S`, etc.
- `docker exec intra-api-1 env | grep ORGANISM_` lists **20 ORGANISM_\* vars active in production**, of which none appear in `ENVIRONMENT.md` and only ~5 appear in `.env.example`.
- The seven hardening flags (H1–H7) shipped to the engine since Feb introduced new env vars (`ORGANISM_ALPHA_TOP_N`, `ORGANISM_EXPLORATION_ENABLED`, `ORGANISM_DROP_ML_FROM_GATE`); none are documented.

The de-facto "documentation" is the live `.env` file — which is gitignored. An operator joining the project today has no committed reference for the runtime knobs that govern the trading loop. The single cross-cutting comment in `docker-compose.paper.yml` ("Audit-L finding L-2: default flipped 1→0") proves the team is patching env-default drift without updating the schema docs.

**Files:** `/Users/marselkei/VS/intra/docs/setup/ENVIRONMENT.md`, `/Users/marselkei/VS/intra/.env.example`, container env (`docker exec intra-api-1 env`).

---

### CCC-5 — `docker-compose.paper.yml` (the running config) bypasses *all* explicit ORGANISM_* env wiring; relies entirely on `.env`

**Severity:** P2 — fragile contract.

`docker-compose.paper.yml` declares `env_file: .env` and wires only credentials/CORS/DB/JWT explicitly. It does **not** pass `ORGANISM_*`, `ALPHA_*`, `MAX_DAILY_LOSS`, `MAX_NOTIONAL`, `MR_*`, `DROP_ML_FROM_GATE`, etc. as `environment:` entries.

Diff between dev and paper composes (env-var names only):

- Variables in **dev compose only** (17 ORGANISM_* + others, including `GF_SECURITY_ADMIN_PASSWORD`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `ENABLE_OUTBOX_PATTERN`, `ENABLE_BACKGROUND_TASKS`, `ENABLE_WEBSOCKET`).
- Variables in **paper compose only**: `ALPACA_PAPER`, `CORS_ORIGINS`, `DEBUG`, `LOG_LEVEL`, `USE_MOCK_BROKER`, `USE_MOCK_DATA`.

Implications:

1. There is no compose-level record of which engine knobs the paper deployment depends on; operators must read `.env` to know.
2. Dev (`docker-compose.yml`) and paper (`docker-compose.paper.yml`) use *different* fallback patterns for the same vars: dev uses `${VAR:-default}`, paper omits the var entirely (forcing `.env`). If `.env` is absent in paper, organism boots with **code defaults**, which for `ORGANISM_DROP_ML_FROM_GATE` is `false` — silently re-enabling ML in the gate (cf. memory note "surgical fix #2 (DROP_ML_FROM_GATE default-true)" — deployed via the May-1 fix; the *code* default is still `false`).
3. The "two-step source of truth" (compose + `.env`) means a `git diff` of compose files does not surface paper-trading config changes; they only show up in the gitignored `.env`. CI cannot detect drift in the actively trading config.

**Files:** all three `docker-compose*.yml`, `.env`, `backend/organism/live_engine.py` (DROP_ML default).

---

## Bonus observations (not findings)

- **`SLACK_WEBHOOK_URL`** is referenced in `backend/infra/alerting.py:186` but absent from `.env`, all three compose files, and `.env.example`. Alerting is silently disabled. (Memory ledger flags this as known.)
- **JWT-secret triple aliasing**: `.env` sets `JWT_SECRET=...` then `SECURITY_JWT_SECRET=${JWT_SECRET}` and `JWT_SECRET_KEY=${JWT_SECRET}`. This works around CCC-1 but bakes in the sprawl rather than fixing it.
- **Backup `.env.preopen_backup_20260310_235853`** exists in working tree. Verified gitignored (`.env.*` in `.gitignore:123`); *not* tracked by git. Contains real Alpaca paper credentials (same key as live `.env`). No secret leak; flag only that this file should be cleaned up when no longer needed.
- **Plaintext secrets in committed `.env.production.template`**: only `CHANGE_TO_REAL_*` / `CHANGE_ME_GENERATE_SECURE` placeholders. Clean.
- **No hot-reload**: `lifespan.py` and `coordinator.py` show no `SIGHUP` / config-watch path. Config changes require container restart. This is intentional and aligned with the deploy-gate norm in memory ("Code-on-disk ≠ deployed-to-container until ... build && up -d").
- **5 config modules** (`settings.py`, `base_settings.py`, `config.py`, `unified.py`, `coordinator.py`) is itself a smell — Track CCC's primary lens is env-var sprawl, but module sprawl deserves a separate Track-DDD pass.

---

## Summary table

| # | Finding | Severity | Risk |
|---|---------|----------|------|
| CCC-1 | Production validator audits non-canonical env-var names | P1 | False security; deploy can pass with wrong vars set |
| CCC-2 | Safety-critical risk caps differ across compose/env/code | P0 | Kill-switch and loss-caps may silently disable or differ 4×–110× |
| CCC-3 | 4 spellings for Alpaca API key, no canonicalization | P2 | Operator footgun; legacy validator passes on legacy names |
| CCC-4 | `docs/setup/ENVIRONMENT.md` 3 months stale; 0 ORGANISM_* docs | P2 | Knowledge debt; live `.env` is the de-facto schema |
| CCC-5 | `docker-compose.paper.yml` (running) wires zero ORGANISM_* env | P2 | Drift between paper/dev/prod composes invisible to git diff |

**Total findings: 5** (within prompt's 2–5 quality bar).
