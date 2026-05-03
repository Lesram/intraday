# Track EE v7 — Operational Readiness / SRE (NEW SURFACE)

V4 Track P touched observability. V7 Track EE covers the broader
operational surface: runbooks, disaster recovery, graceful shutdown,
SLOs, deploy rollback, capacity planning.

Repo: /Users/marselkei/VS/intra. Branch rc-1.5-curated @ `d44eace`.

## Method

### 1. Health check semantics

- `/healthz` (root) — what does it actually check?
- `/api/v1/observability/health/ready` — V4 P-P2 finding: returned
  `{"ready": false, "status": "unknown"}` for healthy container. Still?
- Is the docker-compose `healthcheck` a deep or shallow check?
- Liveness vs readiness — distinguished?
- What happens when the engine is healthy but DB is down? (Does
  `/healthz` lie?)

### 2. Graceful shutdown sequence

- `lifespan.shutdown` order of operations.
- Phase 1 fix: brain save first. Audit current code: still in that order?
- WS disconnects: do they wait for in-flight messages to drain?
- Outbox worker: does it complete in-flight events?
- DB connections: drained?
- Timeout: how long does shutdown have? Force-kill threshold?
- SIGTERM vs SIGINT vs SIGKILL handling.

### 3. Deploy rollback procedure

- Is there a documented rollback procedure?
- Brain compatibility on rollback (older code reading newer brain
  format) — handled?
- Database migration rollback (Alembic `downgrade`)?
- Sample rollback test (synthetic): build current → snapshot brain →
  build prior commit → re-deploy → verify brain still loads.

### 4. Backup / restore

- N-H-3 added `scripts/db/pg_backup.sh`. Is it scheduled (cron)?
- Brain backup: docker-compose volume mount to host. How often is
  the host volume itself backed up (off-host)?
- Restore procedure documented? Tested?
- Backup integrity check: does the backup script verify the dump can
  be loaded?

### 5. Disaster recovery scenarios

For each: documented runbook? Recovery time estimate?
- DB volume corrupted.
- Container host disk full.
- Alpaca API key revoked / rotated.
- WS provider has a multi-day outage.
- Bug discovered after deployment requires immediate rollback.
- Brain corruption (non-recoverable).
- Network partition between API and DB containers.

### 6. SLO / SLI definition

- Is there a documented SLO (e.g. tick latency < 5s p99)?
- Are there SLIs measured (Prometheus histograms / counters)?
- Error budget burn-down available?
- Alert thresholds tied to SLO breaches?

### 7. Runbook completeness

Inventory existing runbooks:
- `OPERATOR_COMMAND_SHEET.md` (in repo)
- `MONDAY_DEPLOY_eb90fa3.md` (in repo, stale?)
- Other runbook docs in `docs/`
- Are they current?
- For each high-blast event from V4 Track P's coverage matrix, is there
  a runbook entry?

### 8. Capacity planning / load expectations

- Tick-rate: 5-10s nominal. What's the upper bound the engine can sustain?
- DB connection pool: 20+10 (audit-N). Sufficient for sustained load?
- Outbox backlog: what's the steady-state vs surge? Rate limits?
- Memory growth: V4 Q snapshot was 346 MiB. Has it grown? Plot estimate.
- File descriptor growth: 31 FDs at audit-Q. Stable?

### 9. Incident response

- On-call rotation defined?
- Severity levels documented?
- Escalation path (Slack / PagerDuty)?
- Post-mortem template + blameless review process?
- Past post-mortems collected?

### 10. Configuration management

- Env var change procedure: edit `.env` + restart? Or live reload?
- Live reload of which settings is supported (vs requires restart)?
- Configuration drift detection between dev / paper / prod?
- Secrets rotation procedure?

### 11. Container / orchestration audit

- `docker-compose.paper.yml` config:
  - Restart policy: `unless-stopped`?
  - Memory limit set?
  - CPU limit set?
  - Health check timing reasonable?
  - Log driver + rotation (V4 wave-14 added; verify).
- Multi-container failure modes: redis down → API behavior? postgres down?
- Networking: each service's exposed ports — necessary?

### 12. Observability dashboards

- Are there committed Grafana dashboards (`docs/grafana/` or similar)?
- Do they reference the wave-12e + wave-21 metrics?
- Are dashboards reproducible (JSON committed) or only in operator's
  local Grafana?

## Output

`artifacts/audit/v7_reports/track_ee_operational_readiness.md` with:
- Health-check audit (deep vs shallow per endpoint)
- Shutdown sequence diagram + verdict
- Rollback procedure assessment
- Backup/restore state + recommendation
- DR scenario × runbook coverage matrix
- SLO/SLI inventory + gaps
- Runbook completeness check
- Capacity planning baseline + headroom estimate
- Incident response readiness
- Configuration management review
- Container hardening checklist
- Dashboard inventory
- "Operational gaps: N" + TL;DR

## Constraints

Read-only on production. `docker stats`, `docker logs`, `psql` SELECTs ok.

## Quality bar

Expect 4-8 findings. Especially:
- A DR scenario without a runbook
- A health check that's actually shallow (only "did the process start?")
- A backup that's never been restored
- A graceful shutdown that hangs on one component

End with a one-paragraph summary.
