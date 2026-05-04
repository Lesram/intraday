# Track EE v7 — Operational Readiness / SRE Audit

- **Repo:** `/Users/marselkei/VS/intra`
- **Branch / HEAD:** `rc-1.5-curated` @ `d44eace`
- **Live container:** `intra-api-1` (healthy per docker; uptime 23 min at audit)
- **Companion containers:** `intra-redis-1` (healthy, 8 days), `trading_platform_db_paper` (healthy, 8 days)
- **Audit date:** 2026-05-03 04:30 UTC
- **Mode:** read-only (live container probes via `curl`, `docker stats`, `psql` SELECTs only)

## TL;DR

The platform has the *parts* of an SRE story — health endpoints, an SLO threshold file, a postgres backup script, a daily brain rotator, runbooks under `docs/runbooks/`, a canary GitHub workflow with rollback, a single-shot deploy run-book — but most of these pieces are wired up the wrong way for paper trading, untested, or only present as scaffolding with placeholder values. Eight findings below; the highest-impact ones are: (EE-1) the docker-compose health check is shallow, lying about a container that cannot actually serve traffic; (EE-2) `/api/v1/observability/health/ready` *still* returns the V4 P-P2 sentinel `{"ready": false, "status": "unknown"}` with HTTP 200; (EE-4) the postgres backup has a single file from a manual run today, no host crontab/launchd, and no documented or tested restore; (EE-5) DR coverage matrix has six scenarios with no runbook; (EE-7) the api container has no memory or CPU limits and a Docker default 10 s SIGTERM grace.

**Operational gaps: 8.**

---

## 1. Health-check audit (deep vs shallow)

| Endpoint | Source | What it actually checks | Verdict |
|---|---|---|---|
| `/` | `factory.py:209` | Static metadata. | Trivial OK |
| `/health` (root) | `factory.py:223` → `health.py:get_trivial_health` | Returns `status=ok, version, ts`. **No I/O.** | **Shallow** |
| `/healthz` | `factory.py:235` → `liveness_check` | Same trivial response, **target of compose `healthcheck`**. | **Shallow** |
| `/livez` | `factory.py:231` | Trivial. | Shallow (correct for liveness) |
| `/readyz` | `factory.py:227` → `readiness_check` | Calls `db_health_check` (100 ms timeout) + `broker_health_check` (200 ms timeout, redis ping). 2 s micro-cache. **Returns 503 if not ready.** | **Deep** (correct) |
| `/api/v1/health` | `routes/system.py:130` | Same shallow trivial, plus a *literal note* admitting the old code lied about subsystems. | Shallow (now honest) |
| `/api/v1/observability/health/ready` | `routes/observability.py:61` | Calls `service.get_system_health()`. | **Deep — but broken** |

Live probes against `intra-api-1`:

```
GET /healthz   → 200 {"status":"ok","version":"1.0.0",...}
GET /health    → 200 {"status":"ok",...}
GET /livez     → 200 {"status":"ok",...}
GET /readyz    → 503 {"status":"not ready","checks":{"database":true,"broker":false},
                       "problems":{"broker":"Broker connection failed"}}
GET /api/v1/observability/health/ready → 200 {"ready":false,"status":"unknown",...}
```

The container reports `(healthy)` to docker because compose hits `/healthz` (shallow), even though `/readyz` is screaming and `/api/v1/observability/health/ready` admits readiness is `unknown`.

## 2. Graceful shutdown sequence

`backend/api/lifespan.py:357` `shutdown(app, ctx, baseline)` order:

1. **`scheduler._engine.force_save_brain()`** — defensive save first (Audit-G BUG-H fix). Good.
2. `ml_scheduler.stop()` (await)
3. `organism_scheduler.stop()` (await — *this also force-saves brain through the engine path*)
4. `alpaca_stream_client.stop()`
5. `aclose()` on `alpaca_broker_client` and `alpaca_data_client`
6. Cancel `stream_task`
7. `outbox_worker.stop()` — **just sets `_running = False` and `task.cancel()`; does NOT drain in-flight events** (`outbox_worker.py:114-129`)
8. `multi_strategy_live_scheduler.stop()`, `auto_breakout_scanner.stop()`
9. `reconciliation_scheduler.stop()`
10. `dispose_engine()` (DB)
11. `asyncio.gather(... timeout=2.0)` over remaining tasks (only the *last* step has a timeout)

**Container signal/timeout posture:**
- `Dockerfile` has no `STOPSIGNAL` → defaults to `SIGTERM`.
- `docker-compose.paper.yml` has no `stop_grace_period` → defaults to **10 seconds** before `docker stop` escalates to `SIGKILL`.
- `Config.StopTimeout = 1` (per `docker inspect` — non-zero, but unusual; effectively the compose 10 s grace dominates).

**Risks:**
- No per-component timeout on steps 2–10. If `alpaca_stream_client.stop()` (websocket close) blocks for >10 s the whole shutdown is force-killed before `dispose_engine()` runs and before the outbox `task.cancel()` resolves.
- Outbox stop does not flush; in-flight events are lost across restart (rely on at-least-once redelivery from DB row state — that is in fact the design but it is not asserted in the shutdown comments).
- WebSocket disconnect: `socketio_server.py:123` has a `disconnect(sid)` *handler* but no shutdown-side `await sio.disconnect()` for connected clients. Clients learn the server is gone via TCP RST.

**Verdict: half-graceful.** Brain is safe (belt-and-suspenders save). DB and outbox are mostly safe. Streams + WS clients can hang the whole shutdown into SIGKILL territory.

## 3. Deploy rollback procedure

- `MONDAY_DEPLOY_eb90fa3.md` lines 146–171 contain a 6-step rollback: halt via API, `docker-compose down api`, restore brain from `artifacts/deploy_preflight_eb90fa3/...`, `git checkout ce06d41`, rebuild, verify `/health`, write a `ROLLBACK_NOTE.md`. **Single-deploy specific** — there is no generic `ROLLBACK.md`.
- `OPERATOR_COMMAND_SHEET.md` references this run-book by name only and does not enumerate rollback steps.
- `.github/workflows/canary-deployment.yml` has SLO-burn-based automated rollback (lines mentioning `Rollback canary deployment`, `triggering rollback`, etc.), but it targets **Kubernetes** (`KUBE_CONFIG_PROD`, `PROD_NAMESPACE: trading-platform-production`). Paper trading runs on docker-compose on a Mac. Two universes.
- **Brain compatibility on rollback:** not analyzed. The Phase A H4 freeze + manifest schema fields (`generation`, `total_trades`, `cumulative_pnl`, `best_sharpe`, `ml_is_trained`, `feature_count`) are validated *at startup* (per the runbook step 17) but no `manifest.json` schema-version field exists, so a brain written by a newer commit and loaded by an older commit is structural-tolerant only by accident.
- **Alembic downgrade:** all 16 versioned migrations in `backend/migrations/versions/` define a `downgrade()` function — mechanically reversible. The deploy runbook does *not* mention running `alembic downgrade -1` if a migration was applied as part of the deploy. If a deploy ever ships a migration, current rollback steps will leave the schema ahead of the rolled-back code.

## 4. Backup / restore

**Postgres (`scripts/db/pg_backup.sh`, N-H-3):**
- Script is sound: `pg_dump | gzip`, retention via `ls -1t | tail -n +$((KEEP+1)) | xargs rm`, errors out if container missing.
- Recommended cron line is in the *script header*, not installed: `crontab -l` for `marselkei` returns "no crontab"; no launchd plist for pg_backup.
- `backups/postgres/` contains exactly **one** dump: `pg-algotrading-20260502T230639Z.sql.gz` (857 KB), made manually today.
- **No restore script, no restore documentation** in `docs/runbooks/DATABASE_RECOVERY.md` for *this* dump format. Restore would have to be reconstructed by an operator under fire (`gunzip -c ... | docker exec -i trading_platform_db_paper psql -U trading -d algotrading`).
- `scripts/backup/rehearsal.py` exists (DatabaseBackupManager class) but is wired to a hard-coded `trading_staging` URL, not `paper`, and is not on any schedule.
- The pg_backup script itself does **not** verify the dump can be loaded (no `pg_restore --list` smoke test, no test-database round-trip).

**Brain (`scripts/runtime/rotate_brain_backup.py` via `~/Library/LaunchAgents/com.intra.brain-backup.plist`):**
- Healthy. `/Users/marselkei/VS/intra/logs/brain_backup.log` shows daily snapshots from 2026-04-25 through 2026-05-02 to `organism_brain_archive/YYYY-MM-DD/`.
- All snapshots live on the same disk as live brain — **no off-host copy**. If the host dies the rotator dies with it.
- Restore = `cp -r organism_brain_archive/YYYY-MM-DD/* organism_brain/` (mentioned only inline in `MONDAY_DEPLOY_eb90fa3.md` rollback step 3, not in any runbook).

## 5. Disaster-recovery scenario coverage matrix

| Scenario | Runbook? | Recovery time est. | Status |
|---|---|---|---|
| DB volume corrupted | `docs/runbooks/DATABASE_RECOVERY.md` | 30–60 min (backup → load) | **Partial** — runbook exists but references non-existent backup tooling commands and no `pg_backup.sh` restore wiring |
| Container host disk full | none | unknown | **MISSING** |
| Alpaca API key revoked / rotated | none | unknown | **MISSING** (only `PAPER_TRADING_ROLLOUT.md` mentions setting `ALPACA_PAPER`) |
| WS provider multi-day outage | `docs/runbooks/BROKER_FAILOVER.md` references failover; no runbook for "stream is down for >1 day, what do we do" | unknown | **MISSING** |
| Bug requires immediate rollback | `MONDAY_DEPLOY_eb90fa3.md` (deploy-specific) | ~10 min | Specific only |
| Brain corruption (non-recoverable) | none — recovery is implicit ("restore from `organism_brain_archive`") | 5 min if rotator ran | **MISSING** as runbook |
| Network partition api↔db | none | unknown | **MISSING** |
| Outbox backlog > capacity | none (related: `scripts/db/clear_outbox.sql` exists for stuck events) | unknown | **MISSING** runbook (tooling exists) |

`docs/runbooks/INCIDENT_RESPONSE.md` is largely *placeholder* — phone numbers `+1-xxx-xxx-xxxx`, slack handles `@oncall-primary`, never filled in. Alongside the K8s-targeted canary workflow this gives the appearance of operational maturity without the substance.

## 6. SLO / SLI inventory and gaps

- `config/slo_thresholds.json` defines: availability 99.9 %, p95 < 300 ms, p99 < 500 ms, error_rate < 1 %, order_success_rate 99.5 %, signal_processing_latency p95 < 200 ms — all under the `production` profile (the platform runs `APP_ENVIRONMENT=development`, which has *much* looser targets: availability 95 %, p95 < 1000 ms).
- `config/slo_alerts.json` exists.
- `backend/monitoring/slo_metrics.py`, `slo_alerts.py`, `slo_dashboard.py`, `slo_monitor.py`, `enhanced_slo_manager.py` — substantial Python infrastructure.
- `app.state.slo_collector = SLOMetricsCollector()` is initialized at startup (`lifespan.py:88`).
- **Gap 1:** SLO targets are tagged `production`, but the running container is `development`. There is no documented contract for which SLO profile applies in paper trading.
- **Gap 2:** No SLO covers the three things this platform exists to do — tick-to-decision latency, brain save success rate, evolution freeze invariant. The SLOs are HTTP-shape, not engine-shape.
- **Gap 3:** No documented error-budget burn-down. `slo_alerts.py` has burn-rate code but I cannot confirm thresholds are wired to the actual alert sinks.
- **Gap 4:** Live container emits `WARNING - Failed to record readyz_db_ms metric: 'MetricsRegistry' object has no attribute 'create_gauge'` every 10 s — the SLI plumbing for readiness latency is dead. Same warning for `readyz_broker_ms`. Two of the SLIs the readiness probe was instrumented to feed are silently dropped.

## 7. Runbook completeness

| Runbook | Status |
|---|---|
| `OPERATOR_COMMAND_SHEET.md` (repo root) | **Stale** — header dated 2026-04-25 (Saturday), states "Live container: ce06d41", "Repo HEAD: eb90fa3". Audit branch is `rc-1.5-curated` @ `d44eace`. Should be archived or refreshed. |
| `MONDAY_DEPLOY_eb90fa3.md` (repo root) | **Stale + scoped** — deploy-specific to a commit that is no longer the current candidate. Useful as historical artifact and rollback template. |
| `docs/runbooks/INCIDENT_RESPONSE.md` | Placeholder phone numbers / slack handles. Reads like a template never filled in. |
| `docs/runbooks/DATABASE_RECOVERY.md` | Reasonable structure; commands reference `docker-compose exec postgres pg_isready -U postgres`, but the running DB user is `trading` and DB name is `algotrading` (per compose). Commands as written would fail. |
| `docs/runbooks/BROKER_FAILOVER.md` | Present. |
| `docs/runbooks/ML_MODEL_RECOVERY.md` | Present. |
| `docs/runbooks/ORDER_SYSTEM_FAILURE.md` | Present. |
| `docs/runbooks/PAPER_TRADING_ROLLOUT.md` | Most current (references current paper config). |
| `docs/operations/OPERATIONAL_CADENCE.md`, `POST_LAUNCH_MONITORING.md`, `ALPACA_PORTFOLIO_SYNC.md` | Operational notes; not under a Severity/Recovery-time runbook discipline. |

There is no master `docs/runbooks/INDEX.md` mapping symptom → runbook.

## 8. Capacity planning baseline

Snapshot (live, 2026-05-03 04:26 UTC, post-restart in audit window):

| Metric | Value | Limit | Headroom |
|---|---|---|---|
| `intra-api-1` MEM | 351 MiB | **none** (host: 7.65 GiB) | host-bounded |
| `intra-api-1` CPU | 4.35 % | **none** | host-bounded |
| `intra-api-1` PIDs | 52 | (no limit) | n/a |
| `intra-api-1` FDs (pid 1) | 31 | (process default) | stable vs audit-Q baseline (31) |
| api `VmRSS` | 342 MB | n/a | grew from 346 MiB (V4 Q snapshot) — flat |
| postgres MEM | 57 MiB | none | host-bounded |
| redis MEM | 9.5 MiB | 256 MB (compose) | OK |
| pg active connections | 11 | 200 (`max_connections`) | 5.5 % |
| pg pool size (api) | 20+30 overflow | 200 server-side | OK |
| outbox depth (sent) | 1 393 | n/a | growing — no trim policy visible |
| outbox depth (failed) | 5 | n/a | manual review needed |

Memory and FD growth between V4 Q (audit-Q) and now (audit-EE) are flat — no leak signal. **But because the api container has no `mem_limit` or `cpus` cap (`HostConfig.Memory=0`, `HostConfig.NanoCpus=0`), an OOM in the api container would take down the host. `docker-compose.production.yml` *does* set `cpus: 2.0 / memory: 2G` per service; paper does not.

The 1 393 `sent` outbox events with no archival policy will grow without bound; the only mitigation is the manual `scripts/db/clear_outbox.sql` — not a maintenance schedule.

## 9. Incident response readiness

- On-call rotation: **not defined** — `INCIDENT_RESPONSE.md` placeholders.
- Severity levels: documented in `DATABASE_RECOVERY.md` (P1–P4) and `INCIDENT_RESPONSE.md` (skeleton).
- Escalation path: not specified beyond Slack channel names.
- Post-mortem template: not committed.
- Past post-mortems: extensive incident notes exist in `docs/engineering/` (e.g. `incident_recovery_wave/`, `no_trade_incident_master/`, `away_mode_hardening/`) but they are deploy-readiness artifacts, not blameless post-mortems.

## 10. Configuration management

- Env var change: edit `.env` then `docker-compose -f docker-compose.paper.yml build api && up -d api` per memory and `MONDAY_DEPLOY_eb90fa3.md`. **No live reload.**
- Live reload of any setting: no evidence; `get_settings()` is `lru_cache`d at first call.
- Configuration drift detection: `scripts/runtime/write_runtime_snapshot.py` + `scripts/ci/check_spec_drift.py` cover spec-vs-runtime drift. No dev-vs-paper-vs-prod drift checker.
- Secrets rotation procedure: not documented anywhere I could find.
- The compose recently fixed an `APP_LOG_LEVEL` phantom (Audit-L finding L-8) — the kind of drift that goes undetected for months without runtime snapshot inspection.

## 11. Container hardening checklist

| Item | `docker-compose.paper.yml` | Notes |
|---|---|---|
| `restart: unless-stopped` | api/redis/postgres all set | OK |
| Memory limit | **none** on any service (only redis has internal `--maxmemory 256mb`) | Production compose sets `mem_limit`; paper does not |
| CPU limit | **none** | Same |
| Health check timing | api `interval=30s, timeout=10s, retries=3, start_period=60s` | reasonable, but feeds the *shallow* `/healthz` |
| `stop_grace_period` | **not set** → 10 s default | risk of mid-shutdown SIGKILL (see §2) |
| Log rotation (V4 wave-14) | `max-size=100m, max-file=5` on api | Confirmed present (lines 92–96). **Not applied to redis or postgres** — those still use the default unbounded `json-file` driver |
| Network isolation | All on `intra_trading-network` (bridge) | OK |
| Exposed ports | api 8000, redis 6379, postgres 5432 | Redis and Postgres are exposed to the host. For paper-trading-on-laptop this is benign; for any host with public access it is a hardening miss |
| Redis bind | `redis-server --bind 127.0.0.1 ...` (line 105) | **Bug** — Redis binds to its own loopback only. The api container's broker_health_check fails with `Connection refused` because Redis refuses cross-container traffic. This was logged as a "known issue" in personal memory but never fixed |
| `STOPSIGNAL` in Dockerfile | not set → `SIGTERM` default | OK if uvicorn handles it (it does) |

Multi-container failure modes:
- **Redis down:** broker_health_check raises → `/readyz` 503; live engine continues (it does not fail-stop on Redis). This is *currently* the live state.
- **Postgres down:** `/readyz` 503; api logs `Database session error, rolling back: 401` repeatedly (visible in current `docker logs`). Order placement fails. There is no documented playbook for "Postgres goes down during market hours".

## 12. Observability dashboards

- `monitoring/grafana/dashboards/trading-platform-overview.json`
- `monitoring/grafana/dashboards/api-performance-deep-dive.json`

Two committed dashboards. No `dashboards/README.md`, no provisioning manifest, no Grafana datasource config, and no evidence Grafana is *running* (no Grafana container in compose). They are JSON files at rest, not active dashboards.

I did not validate whether they reference wave-12e + wave-21 metric names — without a live Grafana to import them into, that check is paper-only and out of scope here.

## Findings (8)

1. **EE-1 — Compose health check is shallow and lying.** `docker-compose.paper.yml` healthcheck targets `/healthz`, which is a no-I/O trivial response. Container reports `(healthy)` even when `/readyz` is 503 *right now* due to broker (Redis) being unreachable. Fix: point the compose healthcheck at `/readyz` (deep check, 503 on failure) **or** add a separate `start_period`-wrapped readiness gate. Severity: **HIGH** (false confidence).

2. **EE-2 — V4 P-P2 finding `/api/v1/observability/health/ready` returns `{"ready": false, "status": "unknown"}` is *still* present.** Confirmed live: `curl /api/v1/observability/health/ready` → `200 {"ready":false,"status":"unknown"}`. The route resolves `service.get_system_health()` whose status mapping has fallen out of sync — `HealthStatus.HEALTHY`/`DEGRADED` are not what `service` is returning. Severity: **MEDIUM** (legacy K8s probe path; if anything ever consumes it, the platform looks unready forever).

3. **EE-3 — Redis bind 127.0.0.1 leaves broker check permanently red.** `docker-compose.paper.yml:105` runs `redis-server --bind 127.0.0.1 ...`, which means Redis only listens on its *own* container loopback. The api container resolves `redis:6379` to `172.18.0.2:6379` and gets `Connection refused`. `/readyz` is permanently 503-broker-failed. The api functions because the engine doesn't actually *use* Redis on the hot path — but the entire broker SLI is dead. Severity: **HIGH** (one-character fix: `--bind 0.0.0.0` or remove `--bind`).

4. **EE-4 — Postgres backup is one untested file with no schedule, no restore, no integrity check.** `scripts/db/pg_backup.sh` is sound, but: no `crontab`/launchd entry installed; only one dump exists (manual run today, 857 KB); no restore script; no documented restore procedure; no `pg_restore --list` smoke test inside the script. The runbook `DATABASE_RECOVERY.md` references commands that won't work against the actual `trading`/`algotrading` user/db pair. Severity: **HIGH** (an untested backup is a hope, not a backup).

5. **EE-5 — Six DR scenarios have no runbook.** Disk-full, Alpaca key revocation/rotation, WS multi-day outage, brain-corruption-as-a-runbook, network partition api↔db, and outbox backlog overflow — none have documented procedures. The `INCIDENT_RESPONSE.md` placeholder phone numbers (`+1-xxx-xxx-xxxx`) suggest the document was templated and never operationalized. Severity: **MEDIUM** (real-money cutover blocker per `OPERATOR_COMMAND_SHEET.md` gate #11/#12).

6. **EE-6 — Graceful shutdown has no per-component timeout under a 10 s SIGTERM grace.** Brain save is correctly first; but DB dispose, stream stop, broker `aclose`, and outbox `task.cancel()` all run sequentially without individual `wait_for(timeout=...)` guards. Default Docker grace is 10 s. A hung WebSocket close will kill the shutdown mid-DB-dispose. No `stop_grace_period` in compose. Outbox stop does not drain in-flight events (it relies on at-least-once redelivery from DB state — fine, but undocumented). Severity: **MEDIUM**.

7. **EE-7 — api container has no memory or CPU limit.** `docker-compose.paper.yml` api service is missing `mem_limit`/`cpus` (or v3 `deploy.resources.limits`). Production compose has them. An api OOM event takes down the host. Restart policy is `unless-stopped` so the container will come back, but the brain may be mid-write at the moment of OOM. Also, redis/postgres logging block is *not* configured for rotation — only api got the V4 wave-14 fix. Severity: **MEDIUM**.

8. **EE-8 — SLO infrastructure is wired to a profile that doesn't match the running env, and two SLI gauges silently fail.** `config/slo_thresholds.json` targets the `production` profile (99.9 % availability, 300 ms p95) but `APP_ENVIRONMENT=development`. The runtime emits a continuous `WARNING - Failed to record readyz_db_ms metric: 'MetricsRegistry' object has no attribute 'create_gauge'` (and the same for `readyz_broker_ms`) — readiness-latency SLIs are dead. There is no SLO covering tick-to-decision latency, brain save success, or evolution-freeze invariant — i.e. none of the SLOs cover what this platform *does*. Severity: **MEDIUM**.

## One-paragraph summary

The Intra paper-trading platform has the right *vocabulary* of operational readiness — health probes, SLO config, runbooks, deploy run-book, automated rollback workflow, postgres + brain backup scripts — but the implementation has consistent integrity gaps that would bite within minutes of a real incident: the docker-compose healthcheck is shallow and currently masks a permanently-503 broker readiness state caused by a one-line Redis bind misconfiguration; the postgres backup ran once, today, manually, with no schedule, no restore script, and no documented restore path; the legacy V4 P-P2 readiness sentinel `{"ready": false, "status": "unknown"}` is still live on `/api/v1/observability/health/ready`; the api container has no memory or CPU cap and a default 10-second SIGTERM grace with no per-component shutdown timeouts; SLO thresholds target a `production` profile that the container is not running under, and two readiness-latency SLIs are silently dropped because of an attribute error logged every 10 seconds; six high-blast DR scenarios (disk full, Alpaca key revoke, multi-day WS outage, brain corruption, network partition, outbox overflow) have no runbook; `OPERATOR_COMMAND_SHEET.md` and `MONDAY_DEPLOY_eb90fa3.md` are stale relative to the current `rc-1.5-curated@d44eace` branch; and `INCIDENT_RESPONSE.md` ships with placeholder phone numbers. None of these block paper trading from continuing, but at least EE-1, EE-3, EE-4, and EE-5 must close before the planned Stage-1 real-money cutover (referenced earliest 2026-05-12 in `OPERATOR_COMMAND_SHEET.md`).
