# Track III v11 — Logging Architecture (NEW LENS)

**Repo:** `/Users/marselkei/VS/intra` · **Branch:** `rc-1.5-curated` @ `3778344`
**Date:** 2026-05-03 · **Method:** read-only AST + grep + sample log lines (`docker logs intra-api-1`, `logs/`).

---

## Inventory & Census

### Log-call distribution (entire `backend/`)

```
   831  logger.info(
   559  logger.warning(
   556  logger.error(
   150  logger.debug(
    18  logger.critical(
   ----
  2114  total
```

INFO + WARNING + ERROR account for 1,946 / 2,114 calls (92%). Only 7% of all log sites are DEBUG — i.e. the codebase has effectively no "verbose mode"; almost every log site fires at INFO and above in production.

### Format style of WARN/ERROR/CRIT call-sites (291 total)

| Style                          | Count | Share |
|--------------------------------|-------|-------|
| f-string (`f"..."`)            | 546   | dominant |
| %-style (`"...%s..."`)         | 84    | small |
| structured (`extra={...}`)     | 27    | sparse |

(The 546 f-string count comes from a broader pattern grep that includes INFO; the ratio is the takeaway: structured logs are <5% of WARN/ERROR/CRIT sites.)

**All 47 `extra=...` sites are concentrated in `backend/infra/*` and `backend/services/*`.** The rest of the platform — `backend/organism/`, `backend/api/routes/`, `backend/strategies/`, `backend/ml/`, `backend/integrations/` — is almost entirely free-text f-string logging.

### Logger module proliferation

Three competing logger abstractions ship in this codebase:

1. `backend/utils/logging.py` — wrapper around stdlib `logging` (compatibility shim, 187 lines).
2. `backend/utils/logger.py` — **structlog**-based with PII scrubbing processor + `AuditLogger` + `PerformanceLogger` + `StandardEventLogger` + JSON renderer (665 lines).
3. `backend/infra/logging.py` — **stdlib**-based `StructuredLogger` with `JSONFormatter` + `TraceIdFilter` (OpenTelemetry) + domain helpers (`log_http_request`, `log_alpaca_request`, `log_order_event`, `log_auth_event`, `log_outbox_event`) (529 lines).

File-import distribution:
- 108 files use `logging.getLogger(__name__)` directly (stdlib).
- 62 files import a "structured" helper (`from backend.utils.logger import` or `from backend.infra.logging import`).
- Only **1** file actually `import structlog` directly (`backend/utils/logger.py` itself).

### Runtime config (containerized)

`Dockerfile:115` invokes uvicorn with `--log-config /app/logging_config.yaml`. That YAML config:
- Defines a JSON formatter inline (NOT the rich `JSONFormatter` class in `backend/infra/logging.py`).
- Defines a `RotatingFileHandler` with `maxBytes: 52428800` (50 MB), `backupCount: 5` writing to `/app/logs/application.log`.
- Sets `console` handler at INFO; `uvicorn.access` at INFO (per-request access log to stdout).
- Audit logger is wired to a file-only handler that writes to the same file (no separate audit file).

`grep -rn "configure_structured_logging" backend/` → **only the definition** in `backend/infra/logging.py:451` is found; **no caller anywhere in the codebase invokes it**. Same for `setup_logging` in `backend/utils/logger.py` and `backend/utils/logging.py`. The PII-scrubbing structlog processor in `backend/utils/logger.py:195-212` is unreachable at runtime because no code path uses structlog loggers in the request flow.

### Disk footprint (host `logs/`)

```
363M    /Users/marselkei/VS/intra/logs/
120M    app.log              (Feb 22 — never rotated, no rotation handler points to this name)
 41M    application.log      (current, May 3)
 50M    application.log.1
 50M    application.log.2
 50M    application.log.3
977K    application.log.4
 50M    application.log.5
 35M    /Users/marselkei/VS/intra/audit_trail.log  (root-of-repo, AuditLogger default)
```

`app.log` (120 MB, frozen Feb 22) is an orphaned legacy file with no active rotation owner. `application.log.4` is anomalously small (977 K vs 50 MB siblings) — the rotation handler crashed or restarted mid-cycle.

`audit_trail.log` is created in **the process CWD** (`Path("audit_trail.log")` in `AuditLogger.__init__`, `backend/utils/logger.py:218`), with no rotation. In container, that's `/app/audit_trail.log`; on the dev host it's the repo root. Audit data is unbounded.

---

## Findings

### F1 — `configure_structured_logging` is dead code; runtime logging is the YAML default, so trace-correlation (`trace_id`/`span_id`) and log-level discipline never apply. — Severity: **HIGH**

`backend/infra/logging.py:451-516` defines `configure_structured_logging(...)` which:
- Installs the rich `JSONFormatter` with OpenTelemetry trace/span injection.
- Demotes `uvicorn.access`, `urllib3.connectionpool`, `sqlalchemy.engine`, `asyncpg` to WARNING.
- Adds `TraceIdFilter` to inject `trace_id` and `span_id` into every record.

**No caller invokes it.** `grep -rn configure_structured_logging backend/` returns only the definition. `backend/api/main.py` and `backend/api/factory.py` do not call any logging-configuration function. The container's logging is whatever uvicorn applies via `/app/logging_config.yaml`, which:
- Has **no** `TraceIdFilter` and **no** `trace_id` field in its inline format string.
- Leaves `uvicorn.access` at **INFO**, so every healthcheck and login attempt produces a log line.

Live container evidence (sampled `docker logs intra-api-1` 2026-05-03):
- 101 `uvicorn.access` lines in a single tail window.
- Zero `trace_id` / `span_id` / `correlation_id` / `request_id` fields in any line.
- Healthcheck pollution: `GET /health` lines appear ~3 per second from multiple sources (host, internal, k8s liveness).

**Impact:** Cross-module request tracing is impossible. When a failed login propagates "401: Invalid username or password, or account is locked due to too many failed login attempts" through `audit_service.log` → `db.get_db_session` rollback → `auth/login` 401, there is no shared identifier to stitch the three log lines (sampled at lines L296-L300 of the container log tail). On an order failure path, debugging "why did this trade reject" requires manual timestamp matching.

**Fix:** Call `configure_structured_logging` from `backend/api/lifespan.py` startup (or the first line of `backend/api/main.py`), and either replace `logging_config.yaml` with the resulting handler set, or extend the YAML to include `TraceIdFilter`. Set `uvicorn.access` to WARNING in the YAML to drop the per-request noise.

---

### F2 — PII appears verbatim in WARN/INFO log messages. The PII-scrubbing structlog processor is unreachable. — Severity: **HIGH**

`backend/utils/logger.py:107-127` defines `_scrub_string` and `backend/utils/logger.py:195-212` wires it as a structlog processor. **But:** it is wired inside `structlog.configure(...)` only, not into stdlib's logging chain. Since the actual production log path is uvicorn → stdlib root logger → YAML JSON formatter (NOT structlog), the scrubber **never runs on a live log message**.

PII / sensitive-string log sites confirmed in the auth flow (`backend/api/routes/auth.py`):
- L672: `logger.info(f"New user registered: {request.email}")` — email in cleartext.
- L766: `logger.info(f"Token refresh for user: {username}")` — username (PII per GDPR).
- L818: `logger.info(f"Password reset requested for: {request.email}")` — email tied to "wants to reset password" event (compliance-sensitive, since it confirms account existence).
- L951: `logger.info(f"Password changed successfully for user: {user_id}")` — user_id leak (less severe but reportable).

In `backend/infra/users.py`:
- L476: `logger.warning(f"Password change failed: user not found or inactive: {username}")`
- L481: `logger.warning(f"Password change failed: incorrect current password for user: {username}")`
- L501, L511: `logger.info(f"Password changed successfully for user: {username}")`

In `backend/infra/security.py`:
- L169: `_blacklist_logger.info(f"All tokens revoked for user: {username}")`

**Sampled live-container leak:** a 401 login error path emits the literal message
`"Database session error, rolling back: 401: Invalid username or password, or account is locked due to too many failed login attempts"` at ERROR level via `backend.infra.db`. Repeating that on a brute-force pattern produces a username-correlation oracle even though the username string itself is not in this particular line — but the L290/L341 audit-failure WARNINGs in `auth.py` do interpolate into the message.

`backend/api/routes/orders.py:506` also logs `has credentials: {bool(api_key and api_secret)}` — only the booleans, but adjacent code logs symbol + qty without any user-id stripping.

**Impact:** A copy of `application.log` (which can grow to 5 × 50 MB = 250 MB unbounded by retention beyond `backupCount=5`) functions as a PII export. The `audit_trail.log` (35 MB on host, unbounded in container) compounds this. If the host or container filesystem is shared with logging infrastructure or backed up, every email + username transits unredacted.

**Fix (two-step):**
1. Replace `logger.info(f"... {request.email}")` patterns with hashed-or-redacted forms (`logger.info("email reset", extra={"email_hash": sha256(email)})`).
2. Plug the scrubber into stdlib's chain — easiest path is to convert it to a `logging.Filter` and add it in `logging_config.yaml` under every handler, OR call `configure_structured_logging` (Finding F1) which already sets up trace correlation and could host the filter.

---

### F3 — Per-tick logging in `live_engine.py` is essentially un-throttled; only 1 of 172 INFO/WARN sites sits behind a `tick_count %` gate. — Severity: **MEDIUM**

`backend/organism/live_engine.py` contains 215 `logger.*` calls (172 of them INFO/WARNING). The file is invoked once per tick (~10 s default cadence). Eight `tick_count %` rate-gate sites exist (L1803, L1921, L4388, L4397, L4456, L4459, L4788, L4899) — but a structural awk pass that counts `logger.(info|warning)` calls within 6 lines of any `tick_count %` gate finds **only 1**. The other 171 fire on every tick when their feature branch is reached.

At the documented 10 s tick cadence:
- 8,640 ticks/day × ≥1 INFO line per tick path = baseline ≥ 8,640 lines/day from `live_engine` alone.
- Sampling from the v11 V9 census of 1,487 handlers (per audit prompt) suggests an order-of-magnitude higher real volume. Given 5 × 50 MB rotation = 250 MB before discard, and observed `application.log` rotation cadence of every ~3 days (the `.5` file is from Mar 10, the current file was rotated to `.1` on Apr 20 — i.e. one rotation per ~3-4 days), each rotation cycle captures 50 MB of mostly-engine-loop INFO + uvicorn access lines.

**Wave-22 commit at `backend/utils/logger.py:458-468` already learned this lesson:**
> "V6 V-T-9 / Wave-22 (2026-05-03): per-operation latency emissions were INFO and dominated the log stream at >100 lines/min. Aggregate latency belongs in metrics (Histogram), not in INFO logs. Demoted to DEBUG; Prometheus ORGANISM_TICK_DURATION carries the signal."

The same pattern persists in `live_engine.py` for non-latency fields — regime annotations, gate-decision narration, restore-from-brain notes — all at INFO, all unsampled.

**Impact:** Disk pressure (250 MB rotating + 120 MB orphan + 35 MB audit = ~400 MB on dev host today, would multiply on a long-running production node), and signal-to-noise ratio so low that operationally-important events (DRAWDOWN_KILL_SWITCH, brain restore, alpha-source switch) are buried.

**Fix:** Apply a `_tick_count % N == 0` gate uniformly to per-tick narration logs (suggested cadence: 60 ticks = 10 minutes for routine state, 6 ticks = 1 minute for warnings, no gate for transitions and errors). Promote transition-detection logs (regime change, brain-version bump, position open/close) to ERROR/WARN — those are the only ones that need every-occurrence fidelity.

---

### F4 — Three competing logger module abstractions; mutually-exclusive feature sets. — Severity: **MEDIUM**

The codebase ships three logger interfaces, each providing different features:

| Module                          | Backend         | PII scrubbing | Trace IDs | Domain helpers | Audit | Used by N files |
|---------------------------------|-----------------|---------------|-----------|----------------|-------|-----------------|
| `backend/utils/logging.py`      | stdlib wrapper  | no            | no        | basic          | no    | `backend/utils/__init__.py` reexports |
| `backend/utils/logger.py`       | structlog       | yes (unused)  | partial (uuid trace_id) | yes (signal/order/risk) | yes (`AuditLogger`) | ~30 files |
| `backend/infra/logging.py`      | stdlib + JSON   | no            | yes (OTel real)         | yes (http/alpaca/order/auth) | no | ~30 files |

A given module typically picks one and stays — `backend/infra/db.py` uses `infra.logging`; `backend/infra/users.py` uses `utils.logger`; `backend/integrations/alpaca_broker.py` uses `utils.logger`; `backend/api/routes/auth.py` uses plain `logging.getLogger`. The result: **there is no consistent log schema across the platform.**

A real production query "find all auth events for user_id=42 in the last hour":
- Will pick up `backend.api.routes.auth`'s f-string format from one source.
- Will pick up `backend.services.audit_service`'s structured `Audit log created` (no fields visible in tail) from another.
- Will pick up `backend.infra.db`'s rollback ERROR with the auth message buried in a SQLAlchemy detail string.
- Will miss anything that went through `backend.utils.logger.AuditLogger` because that writes to a separate file (`audit_trail.log`) without the user_id field even being a top-level key.

**Impact:** Centralized log search (Loki/ELK/Datadog) cannot index a single field name. The wave of work required to consolidate downstream is large — but the underlying entropy is being added daily.

**Fix:** Pick one (recommendation: `backend/infra/logging.py` + its `StructuredLogger` because it has real OTel trace correlation and stdlib compatibility) and codemod the others. Mark `backend/utils/logger.py` and `backend/utils/logging.py` as deprecated.

---

### F5 — `audit_trail.log` is unrotated and writes to CWD; in containers this is `/app/audit_trail.log`, and there is no retention or shipping to durable storage. — Severity: **MEDIUM**

`backend/utils/logger.py:215-233` defines `AuditLogger` with default `log_file: str = "audit_trail.log"` — a relative path. `Path(log_file).parent.mkdir(...)` resolves relative to the process CWD. The handler is a plain `logging.FileHandler` with **no rotation**.

`backend/utils/logger.py:414` instantiates `audit_logger = AuditLogger()` at module-import time, so the file is created/opened the moment any code imports the module — usually before lifespan startup runs.

Host evidence: `audit_trail.log` (35 MB, May 2) sits in the repo root. In a container with `/app` as CWD, it would be at `/app/audit_trail.log` — **outside** the `logs/` volume that's mounted for `application.log`. Since `docker-compose.paper.yml` mounts `./logs:/app/logs` only, the audit file is **inside the container's overlayfs**, lost on every container restart.

The YAML config does have an `audit` logger entry pointing to `file` handler (`/app/logs/application.log`), but `AuditLogger.__init__` adds its **own** `FileHandler` to `logging.getLogger("audit")` — so audit events end up duplicated to `audit_trail.log` (no rotation, lost on restart) and `application.log` (rotated, capped at 250 MB). Neither is shipped off-host.

**Impact:** Compliance / regulatory requirements on audit trails (e.g., SEC Rule 17a-4 for broker-dealers; 7-year retention for trade reconstruction) are not met. Even basic post-incident forensics can lose data on container restart.

**Fix:** (a) Switch `AuditLogger` to `RotatingFileHandler` or `TimedRotatingFileHandler` with explicit absolute path (`/app/logs/audit_trail.log`). (b) Mount/ship `logs/audit_trail.log` to S3 / external storage with the per-day rotation tag. (c) Remove the duplicate stdlib audit handler — pick one path. (d) Add a startup smoke check in `lifespan.py` that asserts the audit file is rotation-enabled and reachable.

---

## Quick wins (cumulative)

1. **Delete the `app.log` (120 MB) orphan** — no handler is writing to it; `git rm logs/app.log` (after archive).
2. **Add `uvicorn.access` → WARNING in `logging_config.yaml`** — drops ~80% of stdout volume.
3. **Add a one-line `from backend.infra.logging import configure_structured_logging; configure_structured_logging(...)` to lifespan startup** — F1 fix.
4. **Wrap `logger.info(f"... {email}")` sites in `auth.py` with email_hash** (3 sites identified above) — F2 fix without depending on F1.
5. **Throttle the top 5 highest-volume `live_engine.py` INFO sites with `% 60`** — F3 partial.

## Counts referenced

- Total log calls: 2,114
- INFO / WARN / ERROR / DEBUG / CRIT split: 831 / 559 / 556 / 150 / 18
- Files using stdlib logging: 108
- Files using structured helpers: 62
- Files using `import structlog`: 1
- `configure_structured_logging` callers: 0
- `backend/organism/live_engine.py` total log calls: 215
- `live_engine.py` INFO/WARN inside throttle gates: 1 of 172 (0.6%)
- `logs/` disk usage: 363 MB
- `audit_trail.log` size (host): 35 MB, no rotation
- Container `uvicorn.access` lines per typical 5 min window: ~100+
